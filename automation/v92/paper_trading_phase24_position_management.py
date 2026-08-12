from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

TIMEOUT = 60
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

RUN_DATE = os.getenv("RUN_DATE", str(date.today())).strip()
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip()

STOP_LOSS = float(os.getenv("PAPER_STOP_LOSS", "0.05"))
TAKE_PROFIT = float(os.getenv("PAPER_TAKE_PROFIT", "0.10"))
TRAILING_STOP = float(os.getenv("PAPER_TRAILING_STOP", "0.06"))
MAX_HOLDING_DAYS = int(os.getenv("PAPER_MAX_HOLDING_DAYS", "10"))
EXIT_SIGNAL_THRESHOLD = float(os.getenv("PAPER_EXIT_SIGNAL_THRESHOLD", "50"))
SELL_SLIPPAGE_RATE = float(os.getenv("PAPER_SELL_SLIPPAGE_RATE", "0.001"))
COMMISSION_RATE = float(os.getenv("PAPER_COMMISSION_RATE", "0.001425"))
TRANSACTION_TAX_RATE = float(os.getenv("PAPER_TRANSACTION_TAX_RATE", "0.003"))

ARTIFACT_DIR = Path("artifacts/paper_trading_phase24")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers.update({
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "GPT-Quant-V9.2-Phase2.4/1.0",
})

def url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"

def check(r: requests.Response, context: str) -> None:
    if not r.ok:
        raise RuntimeError(f"{context}: HTTP {r.status_code}: {r.text[:1600]}")

def fetch(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    r = s.get(url(table), params=params, timeout=TIMEOUT)
    check(r, f"fetch {table}")
    return r.json()

def insert(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = s.post(
        url(table),
        headers={"Prefer": "return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"insert {table}")
    rows = r.json()
    return rows[0] if rows else payload

def upsert(table: str, payload: dict[str, Any], on_conflict: str) -> dict[str, Any]:
    r = s.post(
        url(table),
        params={"on_conflict": on_conflict},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"upsert {table}")
    rows = r.json()
    return rows[0] if rows else payload

def patch(table: str, filters: dict[str, str], payload: dict[str, Any]) -> None:
    r = s.patch(
        url(table),
        params=filters,
        headers={"Prefer": "return=minimal"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"patch {table}")

def delete(table: str, filters: dict[str, str]) -> None:
    r = s.delete(
        url(table),
        params=filters,
        headers={"Prefer": "return=minimal"},
        timeout=TIMEOUT,
    )
    check(r, f"delete {table}")

def fnum(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default

def current_positions() -> list[dict[str, Any]]:
    return fetch("gptq_paper_positions", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "symbol.asc",
    })

def latest_snapshot() -> dict[str, Any] | None:
    rows = fetch("gptq_paper_equity_snapshots", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "run_date.desc",
        "limit": "1",
    })
    return rows[0] if rows else None

def latest_price(stock_id: int) -> dict[str, Any] | None:
    rows = fetch("daily_prices", {
        "select": "stock_id,trade_date,close",
        "stock_id": f"eq.{stock_id}",
        "trade_date": f"lte.{RUN_DATE}",
        "order": "trade_date.desc",
        "limit": "1",
    })
    return rows[0] if rows else None

def today_signal(stock_id: int) -> dict[str, Any] | None:
    rows = fetch("gptq_paper_signals", {
        "select": "id,stock_id,score,eligible,signal_label,reference_price",
        "run_date": f"eq.{RUN_DATE}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "stock_id": f"eq.{stock_id}",
        "limit": "1",
    })
    return rows[0] if rows else None

def get_or_create_paper_run() -> dict[str, Any]:
    rows = fetch("gptq_paper_runs", {
        "select": "*",
        "run_date": f"eq.{RUN_DATE}",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "limit": "1",
    })
    if rows:
        return rows[0]

    snap = latest_snapshot()
    cash = fnum(snap.get("cash")) if snap else 1000000.0
    return upsert("gptq_paper_runs", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "status": "RUNNING",
        "starting_cash": round(cash, 2),
    }, "run_date,strategy_version")

def log_decision(
    position: dict[str, Any],
    decision: str,
    reason: str,
    last_price: float,
    highest: float,
    holding_days: int,
    upnl: float,
    realized: float = 0.0,
    exit_fill: float | None = None,
) -> None:
    upsert("gptq_paper_position_management_decisions", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "stock_id": position["stock_id"],
        "symbol": position.get("symbol"),
        "decision": decision,
        "reason": reason,
        "entry_price": position.get("average_price"),
        "last_price": round(last_price, 4),
        "highest_price": round(highest, 4),
        "holding_days": holding_days,
        "unrealized_pnl": round(upnl, 2),
        "realized_pnl": round(realized, 2),
        "exit_fill_price": round(exit_fill, 4) if exit_fill is not None else None,
    }, "run_date,strategy_version,stock_id")

def main() -> int:
    positions_before = current_positions()
    snapshot = latest_snapshot()
    cash = fnum(snapshot.get("cash")) if snapshot else 1000000.0
    starting_cash = cash

    run = get_or_create_paper_run()
    run_id = run.get("id")

    mgmt_run = upsert("gptq_paper_position_management_runs", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "status": "RUNNING",
        "positions_before": len(positions_before),
        "ending_cash": round(cash, 2),
    }, "run_date,strategy_version")

    marked = exits = stop_count = take_count = trailing_count = hold_count = weak_count = 0
    realized_today = 0.0
    errors: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []

    for pos in positions_before:
        try:
            stock_id = int(pos["stock_id"])
            shares = int(pos.get("shares") or 0)
            entry = fnum(pos.get("average_price"))
            if shares <= 0 or entry <= 0:
                raise RuntimeError("Invalid paper position shares or average_price")

            px = latest_price(stock_id)
            if not px:
                raise RuntimeError("No daily price available")

            last = fnum(px.get("close"))
            market_date = px.get("trade_date")
            highest = max(fnum(pos.get("highest_price"), entry), last)
            prev_mark_date = pos.get("last_mark_date")
            holding_days = int(pos.get("holding_days") or 0)
            if prev_mark_date != market_date:
                holding_days += 1

            market_value = last * shares
            upnl = (last - entry) * shares

            stop_price = fnum(pos.get("stop_price"), entry * (1 - STOP_LOSS))
            take_price = fnum(pos.get("take_profit_price"), entry * (1 + TAKE_PROFIT))
            trailing_price = highest * (1 - TRAILING_STOP)

            signal = today_signal(stock_id)
            score = fnum(signal.get("score")) if signal else None

            reason = None
            if last <= stop_price:
                reason = "STOP_LOSS"
            elif last >= take_price:
                reason = "TAKE_PROFIT"
            elif highest > entry and last <= trailing_price:
                reason = "TRAILING_STOP"
            elif holding_days >= MAX_HOLDING_DAYS:
                reason = "MAX_HOLDING_DAYS"
            elif signal is not None and score is not None and score < EXIT_SIGNAL_THRESHOLD:
                reason = "SIGNAL_WEAKNESS"

            if reason:
                exit_fill = last * (1 - SELL_SLIPPAGE_RATE)
                gross_proceeds = exit_fill * shares
                commission = gross_proceeds * COMMISSION_RATE
                tax = gross_proceeds * TRANSACTION_TAX_RATE
                net_proceeds = gross_proceeds - commission - tax
                realized = (exit_fill - entry) * shares - commission - tax
                cash += net_proceeds
                realized_today += realized

                insert("gptq_paper_orders", {
                    "run_id": run_id,
                    "run_date": RUN_DATE,
                    "strategy_version": STRATEGY_VERSION,
                    "stock_id": stock_id,
                    "symbol": pos.get("symbol"),
                    "side": "SELL",
                    "signal_score": score,
                    "signal_label": signal.get("signal_label") if signal else None,
                    "reference_price": round(last, 4),
                    "simulated_fill_price": round(exit_fill, 4),
                    "shares": shares,
                    "notional": round(gross_proceeds, 2),
                    "status": "FILLED",
                    "reason": reason,
                    "realized_pnl": round(realized, 2),
                    "holding_days": holding_days,
                    "execution_mode": "SHADOW_ONLY_NO_BROKER",
                    "source_signal_id": pos.get("source_signal_id"),
                    "risk_approved": True,
                    "risk_reason": f"PHASE24_{reason}",
                    "commission": round(commission + tax, 2),
                    "slippage": round(last * SELL_SLIPPAGE_RATE * shares, 2),
                })

                delete("gptq_paper_positions", {
                    "strategy_version": f"eq.{STRATEGY_VERSION}",
                    "stock_id": f"eq.{stock_id}",
                })

                exits += 1
                if reason == "STOP_LOSS": stop_count += 1
                elif reason == "TAKE_PROFIT": take_count += 1
                elif reason == "TRAILING_STOP": trailing_count += 1
                elif reason == "MAX_HOLDING_DAYS": hold_count += 1
                elif reason == "SIGNAL_WEAKNESS": weak_count += 1

                log_decision(pos, "EXIT", reason, last, highest, holding_days, upnl, realized, exit_fill)

                report_rows.append({
                    "symbol": pos.get("symbol"),
                    "decision": "EXIT",
                    "reason": reason,
                    "last_price": round(last, 4),
                    "exit_fill": round(exit_fill, 4),
                    "holding_days": holding_days,
                    "realized_pnl": round(realized, 2),
                })
            else:
                patch("gptq_paper_positions", {
                    "strategy_version": f"eq.{STRATEGY_VERSION}",
                    "stock_id": f"eq.{stock_id}",
                }, {
                    "last_price": round(last, 4),
                    "market_value": round(market_value, 2),
                    "unrealized_pnl": round(upnl, 2),
                    "highest_price": round(highest, 4),
                    "holding_days": holding_days,
                    "stop_price": round(stop_price, 4),
                    "take_profit_price": round(take_price, 4),
                    "last_mark_date": market_date,
                    "exit_signal_score": score,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })

                marked += 1
                log_decision(pos, "HOLD", "NO_EXIT_TRIGGER", last, highest, holding_days, upnl)

                report_rows.append({
                    "symbol": pos.get("symbol"),
                    "decision": "HOLD",
                    "reason": "NO_EXIT_TRIGGER",
                    "last_price": round(last, 4),
                    "highest_price": round(highest, 4),
                    "holding_days": holding_days,
                    "unrealized_pnl": round(upnl, 2),
                })

        except Exception as exc:
            errors.append({
                "symbol": pos.get("symbol"),
                "error": str(exc)[:1200],
            })

    remaining = current_positions()
    ending_mv = sum(fnum(p.get("market_value")) for p in remaining)
    ending_upnl = sum(fnum(p.get("unrealized_pnl")) for p in remaining)
    ending_eq = cash + ending_mv

    upsert("gptq_paper_equity_snapshots", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "cash": round(cash, 2),
        "market_value": round(ending_mv, 2),
        "total_equity": round(ending_eq, 2),
        "realized_pnl": round(realized_today, 2),
        "unrealized_pnl": round(ending_upnl, 2),
        "open_positions": len(remaining),
    }, "run_date,strategy_version")

    status = "COMPLETED" if not errors else "COMPLETED_WITH_ERRORS"

    patch("gptq_paper_position_management_runs", {
        "id": f"eq.{mgmt_run['id']}",
    }, {
        "status": status,
        "positions_marked": marked,
        "exits_triggered": exits,
        "stop_loss_exits": stop_count,
        "take_profit_exits": take_count,
        "trailing_stop_exits": trailing_count,
        "max_holding_exits": hold_count,
        "signal_weakness_exits": weak_count,
        "realized_pnl_today": round(realized_today, 2),
        "ending_cash": round(cash, 2),
        "ending_market_value": round(ending_mv, 2),
        "ending_equity": round(ending_eq, 2),
        "unrealized_pnl": round(ending_upnl, 2),
        "errors": errors,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    if run_id is not None:
        patch("gptq_paper_runs", {"id": f"eq.{run_id}"}, {
            "status": "COMPLETED",
            "ending_cash": round(cash, 2),
            "ending_equity": round(ending_eq, 2),
            "realized_pnl": round(realized_today, 2),
            "unrealized_pnl": round(ending_upnl, 2),
            "positions_open": len(remaining),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    report = {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "mode": "SHADOW_ONLY_NO_BROKER",
        "status": status,
        "positions_before": len(positions_before),
        "positions_marked": marked,
        "exits_triggered": exits,
        "stop_loss_exits": stop_count,
        "take_profit_exits": take_count,
        "trailing_stop_exits": trailing_count,
        "max_holding_exits": hold_count,
        "signal_weakness_exits": weak_count,
        "starting_cash": round(starting_cash, 2),
        "ending_cash": round(cash, 2),
        "ending_market_value": round(ending_mv, 2),
        "ending_equity": round(ending_eq, 2),
        "realized_pnl_today": round(realized_today, 2),
        "unrealized_pnl": round(ending_upnl, 2),
        "positions_open": len(remaining),
        "decisions": report_rows,
        "errors": errors,
    }

    (ARTIFACT_DIR / "phase24_position_management_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("# GPT Quant V9.2 Paper Trading Phase 2.4\n\n")
            for key in [
                "mode","status","positions_before","positions_marked","exits_triggered",
                "stop_loss_exits","take_profit_exits","trailing_stop_exits",
                "max_holding_exits","signal_weakness_exits","ending_cash",
                "ending_market_value","ending_equity","realized_pnl_today",
                "unrealized_pnl","positions_open"
            ]:
                f.write(f"- **{key}**: `{report[key]}`\n")

            f.write("\n## Position Decisions\n\n")
            f.write("| Symbol | Decision | Reason | Last Price | Holding Days | P&L |\n")
            f.write("|---|---|---|---:|---:|---:|\n")
            for row in report_rows:
                pnl = row.get("realized_pnl", row.get("unrealized_pnl", 0))
                f.write(
                    f"| {row['symbol']} | {row['decision']} | {row['reason']} | "
                    f"{row['last_price']} | {row['holding_days']} | {pnl} |\n"
                )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
