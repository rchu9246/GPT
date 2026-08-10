from __future__ import annotations

import json
import math
import os
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

TIMEOUT = 60
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip()
RUN_DATE = os.getenv("RUN_DATE", str(date.today())).strip()

INITIAL_CAPITAL = float(os.getenv("PAPER_INITIAL_CAPITAL", "1000000"))
SCORE_THRESHOLD = float(os.getenv("PAPER_SCORE_THRESHOLD", "65"))
POSITION_SIZE = float(os.getenv("PAPER_POSITION_SIZE", "0.10"))
MAX_NEW_ORDERS = int(os.getenv("PAPER_MAX_NEW_ORDERS", "5"))
MAX_OPEN_POSITIONS = int(os.getenv("PAPER_MAX_OPEN_POSITIONS", "10"))
MAX_DAILY_GROSS_EXPOSURE = float(os.getenv("PAPER_MAX_GROSS_EXPOSURE", "0.80"))
MAX_SINGLE_POSITION = float(os.getenv("PAPER_MAX_SINGLE_POSITION", "0.15"))
STOP_LOSS = float(os.getenv("PAPER_STOP_LOSS", "0.05"))
TAKE_PROFIT = float(os.getenv("PAPER_TAKE_PROFIT", "0.10"))
MAX_HOLDING_DAYS = int(os.getenv("PAPER_MAX_HOLDING_DAYS", "10"))
TRAILING_STOP = float(os.getenv("PAPER_TRAILING_STOP", "0.06"))

SLIPPAGE_RATE = float(os.getenv("PAPER_SLIPPAGE_RATE", "0.001"))
COMMISSION_RATE = float(os.getenv("PAPER_COMMISSION_RATE", "0.001425"))
TAX_RATE = float(os.getenv("PAPER_TAX_RATE", "0.003"))

ARTIFACT_DIR = Path(os.getenv("PAPER_ARTIFACT_DIR", "artifacts/paper_trading_phase2"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "GPT-Quant-V9.2-Paper-Trading-Phase2/1.0",
})


def api_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def check(response: requests.Response, context: str) -> None:
    if not response.ok:
        raise RuntimeError(f"{context}: HTTP {response.status_code}: {response.text[:1400]}")


def fetch_all(table: str, params: dict[str, str], page_size: int = 1000) -> list[dict[str, Any]]:
    rows, offset = [], 0
    while True:
        p = dict(params)
        p["limit"] = str(page_size)
        p["offset"] = str(offset)
        r = session.get(api_url(table), params=p, timeout=TIMEOUT)
        check(r, f"fetch {table}")
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        offset += page_size


def insert(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = session.post(
        api_url(table),
        headers={"Prefer": "return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"insert {table}")
    rows = r.json()
    return rows[0] if rows else payload


def upsert(table: str, payload: dict[str, Any], on_conflict: str) -> dict[str, Any]:
    r = session.post(
        api_url(table),
        params={"on_conflict": on_conflict},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"upsert {table}")
    rows = r.json()
    return rows[0] if rows else payload


def patch_where(table: str, filters: dict[str, str], payload: dict[str, Any]) -> None:
    r = session.patch(
        api_url(table),
        params=filters,
        headers={"Prefer": "return=minimal"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"patch {table}")


def delete_where(table: str, filters: dict[str, str]) -> None:
    r = session.delete(
        api_url(table),
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


def sma(values: list[float], period: int) -> float | None:
    return sum(values[-period:]) / period if len(values) >= period else None


def ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2 / (period + 1)
    cur = values[0]
    for value in values[1:]:
        cur = alpha * value + (1 - alpha) * cur
    return cur


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = sum(max(x, 0) for x in recent) / period
    losses = sum(max(-x, 0) for x in recent) / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - 100 / (1 + rs)


def atr(rows: list[dict[str, Any]], period: int = 14) -> float:
    if len(rows) <= period:
        return 0.0
    vals = []
    for i in range(1, len(rows)):
        high = fnum(rows[i]["high"])
        low = fnum(rows[i]["low"])
        prev_close = fnum(rows[i-1]["close"])
        vals.append(max(high-low, abs(high-prev_close), abs(low-prev_close)))
    return sum(vals[-period:]) / period


def clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def historical_score(window: list[dict[str, Any]]) -> tuple[float, str]:
    closes = [fnum(r["close"]) for r in window]
    volumes = [fnum(r["volume"]) for r in window]
    close = closes[-1]
    ema20 = ema(closes[-120:], 20) or 0
    ema60 = ema(closes[-160:], 60) or 0
    ema120 = ema(closes[-220:], 120) or 0

    trend = 0.0
    trend += 30 if close > ema20 > 0 else 0
    trend += 35 if ema20 > ema60 > 0 else 0
    trend += 35 if ema60 > ema120 > 0 else 0

    rsi14 = rsi(closes)
    ema12 = ema(closes[-80:], 12) or 0
    ema26 = ema(closes[-100:], 26) or 0
    macd = ema12 - ema26
    roc20 = (close / closes[-21] - 1) * 100 if len(closes) > 20 else 0

    momentum = clamp(
        (100 - abs(rsi14 - 60) * 3) * 0.45
        + clamp(50 + macd * 20) * 0.25
        + clamp(50 + roc20 * 2.5) * 0.30
    )
    vol20 = sma(volumes, 20) or volumes[-1] or 1
    volume_score = clamp(45 + (volumes[-1] / vol20 - 1) * 45)

    high20 = max(closes[-20:])
    high60 = max(closes[-60:])
    breakout = clamp(
        clamp(100 + (close / high20 - 1) * 100 * 10) * 0.65
        + clamp(100 + (close / high60 - 1) * 100 * 6) * 0.35
    )

    daily_returns = [
        (closes[i] / closes[i-1] - 1) * 100
        for i in range(1, len(closes)) if closes[i-1]
    ]
    volatility = statistics.pstdev(daily_returns[-20:]) if len(daily_returns) > 1 else 0
    atr_pct = atr(window) / close * 100 if close else 0
    risk = clamp(100 - volatility * 11 - max(atr_pct - 2, 0) * 8)

    total = (
        trend * 0.24
        + momentum * 0.20
        + volume_score * 0.14
        + 50 * 0.08
        + breakout * 0.14
        + clamp(50 + roc20 * 2.5) * 0.08
        + 60 * 0.05
        + risk * 0.07
    )
    label = (
        "S級強多" if total >= 85 else
        "A級多頭" if total >= 75 else
        "B級觀察" if total >= 65 else
        "C級中性" if total >= 50 else
        "D級避開"
    )
    return round(total, 2), label


def risk_event(event_type: str, severity: str, message: str, symbol: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    insert("gptq_paper_risk_events", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "event_type": event_type,
        "severity": severity,
        "symbol": symbol,
        "message": message,
        "metadata": metadata or {},
    })


def get_latest_price_rows() -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    stocks = fetch_all("stocks", {
        "select": "id,symbol,name",
        "is_active": "eq.true",
        "order": "symbol.asc",
    })
    prices = fetch_all("daily_prices", {
        "select": "stock_id,trade_date,open,high,low,close,volume",
        "order": "stock_id.asc,trade_date.asc",
    })
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in prices:
        if row["trade_date"] <= RUN_DATE:
            grouped[int(row["stock_id"])].append(row)
    return stocks, grouped


def main() -> int:
    run = upsert("gptq_paper_runs", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "status": "RUNNING",
        "starting_cash": INITIAL_CAPITAL,
    }, "run_date,strategy_version")
    run_id = run.get("id")

    stocks, grouped = get_latest_price_rows()
    positions = fetch_all("gptq_paper_positions", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
    })
    pos_by_stock = {int(p["stock_id"]): p for p in positions}

    # Rebuild cash from latest equity snapshot when available.
    snapshots = fetch_all("gptq_paper_equity_snapshots", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "run_date.desc",
        "limit": "1",
    })
    cash = fnum(snapshots[0]["cash"]) if snapshots else INITIAL_CAPITAL

    realized_pnl_today = 0.0
    exits = []

    # 1) Position lifecycle: mark-to-market and exits.
    for p in list(positions):
        sid = int(p["stock_id"])
        rows = grouped.get(sid, [])
        if not rows:
            continue
        latest = rows[-1]
        last = fnum(latest["close"])
        avg = fnum(p["average_price"])
        shares = int(p["shares"])
        holding_days = int(p.get("holding_days") or 0) + 1
        highest = max(fnum(p.get("highest_price"), avg), last)

        stop_price = avg * (1 - STOP_LOSS)
        take_profit_price = avg * (1 + TAKE_PROFIT)
        trailing_price = highest * (1 - TRAILING_STOP)

        exit_reason = None
        if last <= stop_price:
            exit_reason = "STOP_LOSS"
        elif last >= take_profit_price:
            exit_reason = "TAKE_PROFIT"
        elif holding_days >= MAX_HOLDING_DAYS:
            exit_reason = "MAX_HOLDING_DAYS"
        elif last <= trailing_price and highest > avg:
            exit_reason = "TRAILING_STOP"

        if exit_reason:
            fill = last * (1 - SLIPPAGE_RATE)
            gross = fill * shares
            commission = gross * COMMISSION_RATE
            tax = gross * TAX_RATE
            net_proceeds = gross - commission - tax
            cost_basis = avg * shares
            pnl = net_proceeds - cost_basis

            order = insert("gptq_paper_orders", {
                "run_id": run_id,
                "run_date": RUN_DATE,
                "strategy_version": STRATEGY_VERSION,
                "stock_id": sid,
                "symbol": p.get("symbol"),
                "side": "SELL",
                "signal_score": p.get("entry_score"),
                "signal_label": p.get("entry_signal"),
                "reference_price": round(last, 4),
                "simulated_fill_price": round(fill, 4),
                "shares": shares,
                "notional": round(gross, 2),
                "status": "FILLED",
                "reason": "SHADOW_EXIT",
                "realized_pnl": round(pnl, 2),
                "holding_days": holding_days,
                "exit_reason": exit_reason,
            })
            exits.append(order)
            realized_pnl_today += pnl
            cash += net_proceeds
            delete_where("gptq_paper_positions", {
                "strategy_version": f"eq.{STRATEGY_VERSION}",
                "stock_id": f"eq.{sid}",
            })
            risk_event("POSITION_EXIT", "INFO", f"{exit_reason}: {p.get('symbol')}", p.get("symbol"), {
                "fill_price": round(fill, 4), "realized_pnl": round(pnl, 2)
            })
        else:
            patch_where("gptq_paper_positions", {
                "strategy_version": f"eq.{STRATEGY_VERSION}",
                "stock_id": f"eq.{sid}",
            }, {
                "last_price": round(last, 4),
                "market_value": round(last * shares, 2),
                "unrealized_pnl": round((last - avg) * shares, 2),
                "highest_price": round(highest, 4),
                "holding_days": holding_days,
                "stop_price": round(stop_price, 4),
                "take_profit_price": round(take_profit_price, 4),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

    # Refresh positions after exits.
    positions = fetch_all("gptq_paper_positions", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
    })
    pos_by_stock = {int(p["stock_id"]): p for p in positions}

    # 2) Generate daily live signals.
    signals = []
    for stock in stocks:
        sid = int(stock["id"])
        rows = grouped.get(sid, [])
        if len(rows) < 122:
            continue
        latest = rows[-1]
        score, label = historical_score(rows)
        ref = fnum(latest["close"])
        eligible = score >= SCORE_THRESHOLD and ref > 0
        reject_reason = None if eligible else "BELOW_SCORE_THRESHOLD"

        signal_row = upsert("gptq_paper_signals", {
            "run_date": RUN_DATE,
            "strategy_version": STRATEGY_VERSION,
            "stock_id": sid,
            "symbol": stock.get("symbol"),
            "score": score,
            "signal_label": label,
            "reference_price": round(ref, 4),
            "eligible": eligible,
            "selected": False,
            "reject_reason": reject_reason,
        }, "run_date,strategy_version,stock_id")
        if eligible:
            signals.append({
                "stock_id": sid,
                "symbol": stock.get("symbol"),
                "score": score,
                "label": label,
                "reference_price": ref,
            })

    signals.sort(key=lambda x: (-x["score"], x["symbol"] or ""))

    # 3) Exposure/risk calculation.
    positions = fetch_all("gptq_paper_positions", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
    })
    market_value = sum(fnum(p.get("market_value")) for p in positions)
    equity_before_entries = cash + market_value
    gross_exposure = market_value / equity_before_entries if equity_before_entries > 0 else 0

    if gross_exposure >= MAX_DAILY_GROSS_EXPOSURE:
        risk_event("GROSS_EXPOSURE_BLOCK", "WARN", "No new entries: gross exposure limit reached", metadata={
            "gross_exposure": gross_exposure,
            "limit": MAX_DAILY_GROSS_EXPOSURE,
        })

    new_capacity = max(0, MAX_OPEN_POSITIONS - len(positions))
    orders = []
    candidates = [s for s in signals if s["stock_id"] not in {int(p["stock_id"]) for p in positions}]
    candidates = candidates[:min(MAX_NEW_ORDERS, new_capacity)]

    # 4) Simulated entries.
    for signal in candidates:
        if equity_before_entries <= 0:
            break

        current_market_value = sum(fnum(p.get("market_value")) for p in positions)
        current_equity = cash + current_market_value
        gross_exposure = current_market_value / current_equity if current_equity > 0 else 0
        if gross_exposure >= MAX_DAILY_GROSS_EXPOSURE:
            break

        ref = signal["reference_price"]
        fill = ref * (1 + SLIPPAGE_RATE)
        target_fraction = min(POSITION_SIZE, MAX_SINGLE_POSITION)
        target_notional = current_equity * target_fraction
        max_exposure_room = max(0.0, current_equity * MAX_DAILY_GROSS_EXPOSURE - current_market_value)
        notional_budget = min(target_notional, max_exposure_room, cash / (1 + COMMISSION_RATE))
        shares = int(notional_budget / fill)
        if shares <= 0:
            risk_event("ENTRY_REJECTED", "INFO", "Insufficient cash/exposure room", signal["symbol"])
            continue

        notional = fill * shares
        commission = notional * COMMISSION_RATE
        total_cost = notional + commission
        if total_cost > cash:
            continue

        cash -= total_cost
        order = insert("gptq_paper_orders", {
            "run_id": run_id,
            "run_date": RUN_DATE,
            "strategy_version": STRATEGY_VERSION,
            "stock_id": signal["stock_id"],
            "symbol": signal["symbol"],
            "side": "BUY",
            "signal_score": signal["score"],
            "signal_label": signal["label"],
            "reference_price": round(ref, 4),
            "simulated_fill_price": round(fill, 4),
            "shares": shares,
            "notional": round(notional, 2),
            "status": "FILLED",
            "reason": "LIVE_SIGNAL_SHADOW_ENTRY",
            "realized_pnl": 0,
            "holding_days": 0,
        })
        orders.append(order)

        upsert("gptq_paper_positions", {
            "strategy_version": STRATEGY_VERSION,
            "stock_id": signal["stock_id"],
            "symbol": signal["symbol"],
            "shares": shares,
            "average_price": round(fill, 4),
            "last_price": round(ref, 4),
            "market_value": round(ref * shares, 2),
            "unrealized_pnl": round((ref-fill) * shares, 2),
            "opened_at": RUN_DATE,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entry_score": signal["score"],
            "entry_signal": signal["label"],
            "highest_price": round(ref, 4),
            "holding_days": 0,
            "stop_price": round(fill * (1 - STOP_LOSS), 4),
            "take_profit_price": round(fill * (1 + TAKE_PROFIT), 4),
        }, "strategy_version,stock_id")

        patch_where("gptq_paper_signals", {
            "run_date": f"eq.{RUN_DATE}",
            "strategy_version": f"eq.{STRATEGY_VERSION}",
            "stock_id": f"eq.{signal['stock_id']}",
        }, {"selected": True, "reject_reason": None})

        positions = fetch_all("gptq_paper_positions", {
            "select": "*",
            "strategy_version": f"eq.{STRATEGY_VERSION}",
        })

    # 5) Final daily mark-to-market.
    positions = fetch_all("gptq_paper_positions", {
        "select": "*",
        "strategy_version": f"eq.{STRATEGY_VERSION}",
    })
    latest_price_by_stock = {
        sid: fnum(rows[-1]["close"]) for sid, rows in grouped.items() if rows
    }

    market_value = 0.0
    unrealized = 0.0
    for p in positions:
        sid = int(p["stock_id"])
        last = latest_price_by_stock.get(sid, fnum(p.get("last_price")))
        shares = int(p["shares"])
        avg = fnum(p["average_price"])
        mv = last * shares
        upnl = (last - avg) * shares
        market_value += mv
        unrealized += upnl

    total_equity = cash + market_value

    upsert("gptq_paper_equity_snapshots", {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "total_equity": round(total_equity, 2),
        "realized_pnl": round(realized_pnl_today, 2),
        "unrealized_pnl": round(unrealized, 2),
        "open_positions": len(positions),
    }, "run_date,strategy_version")

    if run_id is not None:
        patch_where("gptq_paper_runs", {"id": f"eq.{run_id}"}, {
            "status": "COMPLETED",
            "ending_cash": round(cash, 2),
            "ending_equity": round(total_equity, 2),
            "realized_pnl": round(realized_pnl_today, 2),
            "unrealized_pnl": round(unrealized, 2),
            "orders_created": len(orders) + len(exits),
            "positions_open": len(positions),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

    report = {
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "mode": "SHADOW_ONLY_NO_BROKER",
        "signals_found": len(signals),
        "entries_created": len(orders),
        "exits_created": len(exits),
        "positions_open": len(positions),
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "total_equity": round(total_equity, 2),
        "realized_pnl_today": round(realized_pnl_today, 2),
        "unrealized_pnl": round(unrealized, 2),
        "risk": {
            "score_threshold": SCORE_THRESHOLD,
            "position_size": POSITION_SIZE,
            "max_open_positions": MAX_OPEN_POSITIONS,
            "max_gross_exposure": MAX_DAILY_GROSS_EXPOSURE,
            "stop_loss": STOP_LOSS,
            "take_profit": TAKE_PROFIT,
            "max_holding_days": MAX_HOLDING_DAYS,
            "trailing_stop": TRAILING_STOP,
        }
    }

    (ARTIFACT_DIR/"paper_trading_phase2_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("# GPT Quant V9.2 Paper Trading Phase 2\n\n")
            for k, v in report.items():
                if k != "risk":
                    f.write(f"- **{k}**: `{v}`\n")
            f.write("\n## Risk Controls\n\n")
            for k, v in report["risk"].items():
                f.write(f"- **{k}**: `{v}`\n")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
