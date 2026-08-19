#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase349_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE349_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()
INITIAL_CASH = Decimal(os.getenv("PHASE349_INITIAL_CASH", "1000000"))

UPSTREAM = ROOT / "automation/v92/paper_trading_phase34846_zero_eligible_canonical_runtime_completion_daily_paper_cycle.py"
UPSTREAM_JSON = ROOT / "phase34846_output/phase34846_daily_paper_cycle.json"
PHASE348_JSON = ROOT / "phase348_output/phase348_execution.json"

RESULT_JSON = OUT / "phase349_portfolio_lifecycle_mtm.json"

CONTRACT = "PHASE349_PRODUCTION_PAPER_PORTFOLIO_LIFECYCLE_DAILY_MARK_TO_MARKET_ENGINE"

PORTFOLIO_TABLE = "paper_portfolios_v92"
POSITIONS_TABLE = "paper_positions_v92"
EVENTS_TABLE = "paper_position_events_v92"
SNAPSHOT_TABLE = "paper_portfolio_snapshots_v92"
MARKET_TABLE = "daily_prices"

ZERO_STATE = "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS"
EXECUTED_STATE = "REAL_CANONICAL_EVIDENCE_EXECUTED"


def D(v: Any) -> Decimal:
    return Decimal(str(v))


def money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def supabase() -> tuple[str, dict[str, str]]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not base or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing")
    return base, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(table: str, params: list[tuple[str, str]]) -> list[dict[str, Any]]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"
    r = requests.get(url, headers=headers, params=params, timeout=25)
    if r.status_code >= 400:
        raise RuntimeError(f"{table}: GET HTTP {r.status_code}: {r.text[:600]}")
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"{table}: GET returned non-list")
    return [x for x in data if isinstance(x, dict)]


def rest_upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    if not rows:
        return
    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    url = f"{base}/rest/v1/{quote(table, safe='')}"
    r = requests.post(
        url,
        headers=headers,
        params={"on_conflict": on_conflict},
        data=json.dumps(rows, ensure_ascii=False, default=str),
        timeout=25,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{table}: UPSERT HTTP {r.status_code}: {r.text[:900]}")


def run_upstream(approver: str) -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    proc = subprocess.run(
        [sys.executable, str(UPSTREAM), "--approver", approver],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if not UPSTREAM_JSON.exists():
        raise RuntimeError(f"Phase 3.4.8.4.6 evidence missing; exit={proc.returncode}")

    return proc.returncode, load_json(UPSTREAM_JSON)


def validate_upstream(data: dict[str, Any]) -> None:
    if data.get("status") != "PASS":
        raise RuntimeError("Upstream daily cycle did not PASS")
    if data.get("daily_cycle_status") != "COMPLETED":
        raise RuntimeError("Upstream daily cycle not COMPLETED")

    for key in (
        "synthetic_market_data",
        "synthetic_fallback_allowed",
        "synthetic_evidence_present",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    ):
        if data.get(key) is not False:
            raise RuntimeError(f"Safety violation: {key}={data.get(key)!r}")

    if data.get("fail_closed_policy") is not True:
        raise RuntimeError("Safety violation: fail_closed_policy must be true")

    if int(data.get("stocks_with_history") or 0) <= 0:
        raise RuntimeError("No real market history available")

    if int(data.get("signal_engine_stocks_scanned") or 0) <= 0:
        raise RuntimeError("Signal engine scanned zero stocks")


def ensure_portfolio() -> dict[str, Any]:
    rows = rest_get(
        PORTFOLIO_TABLE,
        [("select", "*"), ("portfolio_id", f"eq.{PORTFOLIO_ID}")],
    )
    if rows:
        return rows[0]

    row = {
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "initial_cash": str(INITIAL_CASH),
        "cash": str(INITIAL_CASH),
        "realized_pnl": "0",
        "status": "ACTIVE",
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    rest_upsert(PORTFOLIO_TABLE, [row], "portfolio_id")
    return row


def load_positions() -> list[dict[str, Any]]:
    return rest_get(
        POSITIONS_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("status", "eq.OPEN"),
        ],
    )


def load_real_price(symbol: str) -> tuple[str, Decimal]:
    rows = rest_get(
        MARKET_TABLE,
        [
            ("select", "*"),
            ("symbol", f"eq.{symbol}"),
            ("order", "date.desc"),
            ("limit", "1"),
        ],
    )

    if not rows:
        # try stock_id alias if daily_prices uses stock_id
        rows = rest_get(
            MARKET_TABLE,
            [
                ("select", "*"),
                ("stock_id", f"eq.{symbol}"),
                ("order", "date.desc"),
                ("limit", "1"),
            ],
        )

    if not rows:
        raise RuntimeError(f"NO_REAL_MARKET_PRICE: {symbol}")

    row = rows[0]
    market_date = str(
        row.get("date")
        or row.get("trade_date")
        or row.get("market_date")
        or ""
    )[:10]

    raw_price = (
        row.get("close")
        or row.get("close_price")
        or row.get("price")
    )

    if not market_date or raw_price is None:
        raise RuntimeError(f"INVALID_REAL_MARKET_PRICE_ROW: {symbol}")

    price = D(raw_price)
    if price <= 0:
        raise RuntimeError(f"INVALID_REAL_MARKET_PRICE: {symbol}={price}")

    return market_date, price


def get_phase348_fills() -> list[dict[str, Any]]:
    if not PHASE348_JSON.exists():
        return []
    data = load_json(PHASE348_JSON)
    fills = data.get("fills") or []
    return [x for x in fills if isinstance(x, dict)]


def apply_simulated_fills(
    portfolio: dict[str, Any],
    positions: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    run_date: str,
) -> tuple[Decimal, Decimal, list[dict[str, Any]], list[dict[str, Any]]]:
    cash = D(portfolio.get("cash", INITIAL_CASH))
    realized = D(portfolio.get("realized_pnl", 0))

    by_symbol = {str(p["symbol"]): dict(p) for p in positions}
    events: list[dict[str, Any]] = []

    for fill in fills:
        symbol = str(fill.get("symbol") or "").strip()
        side = str(fill.get("side") or fill.get("signal") or "BUY").upper()
        qty = D(fill.get("quantity") or fill.get("qty") or 0)
        price = D(fill.get("fill_price") or fill.get("price") or 0)

        if not symbol or qty <= 0 or price <= 0:
            continue

        if side not in {"BUY", "SELL"}:
            continue

        event_seed = {
            "portfolio_id": PORTFOLIO_ID,
            "run_date": run_date,
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "price": str(price),
        }
        event_id = "P349E-" + stable_hash(event_seed)[:28]

        # Idempotency: if event already persisted, skip it.
        existing_event = rest_get(
            EVENTS_TABLE,
            [("select", "event_id"), ("event_id", f"eq.{event_id}")],
        )
        if existing_event:
            continue

        pos = by_symbol.get(symbol)

        if side == "BUY":
            cost = money(qty * price)
            if cost > cash:
                raise RuntimeError(
                    f"PAPER_CASH_INSUFFICIENT: {symbol} cost={cost} cash={cash}"
                )

            old_qty = D(pos.get("quantity", 0)) if pos else D(0)
            old_avg = D(pos.get("avg_entry_price", 0)) if pos else D(0)

            new_qty = old_qty + qty
            new_avg = money(
                ((old_qty * old_avg) + (qty * price)) / new_qty
            )

            cash = money(cash - cost)

            by_symbol[symbol] = {
                "portfolio_id": PORTFOLIO_ID,
                "strategy_version": STRATEGY,
                "symbol": symbol,
                "quantity": str(new_qty),
                "avg_entry_price": str(new_avg),
                "last_market_price": str(price),
                "market_value": str(money(new_qty * price)),
                "unrealized_pnl": str(money((price - new_avg) * new_qty)),
                "realized_pnl": str(D(pos.get("realized_pnl", 0)) if pos else D(0)),
                "opened_date": pos.get("opened_date") if pos else run_date,
                "last_mark_date": run_date,
                "status": "OPEN",
                "synthetic_evidence": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "evidence_sha256": stable_hash(event_seed),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            cash_delta = -cost
            realized_delta = D(0)

        else:
            if not pos:
                raise RuntimeError(f"PAPER_SELL_WITHOUT_POSITION: {symbol}")

            old_qty = D(pos["quantity"])
            avg = D(pos["avg_entry_price"])

            if qty > old_qty:
                raise RuntimeError(
                    f"PAPER_SELL_EXCEEDS_POSITION: {symbol} qty={qty} held={old_qty}"
                )

            proceeds = money(qty * price)
            realized_delta = money((price - avg) * qty)
            realized = money(realized + realized_delta)
            cash = money(cash + proceeds)

            new_qty = old_qty - qty

            if new_qty == 0:
                pos["quantity"] = "0"
                pos["market_value"] = "0"
                pos["unrealized_pnl"] = "0"
                pos["status"] = "CLOSED"
                pos["last_market_price"] = str(price)
                pos["last_mark_date"] = run_date
                pos["realized_pnl"] = str(money(D(pos.get("realized_pnl", 0)) + realized_delta))
                pos["updated_at"] = datetime.now(timezone.utc).isoformat()
            else:
                pos["quantity"] = str(new_qty)
                pos["market_value"] = str(money(new_qty * price))
                pos["unrealized_pnl"] = str(money((price - avg) * new_qty))
                pos["last_market_price"] = str(price)
                pos["last_mark_date"] = run_date
                pos["realized_pnl"] = str(money(D(pos.get("realized_pnl", 0)) + realized_delta))
                pos["updated_at"] = datetime.now(timezone.utc).isoformat()

            by_symbol[symbol] = pos
            cash_delta = proceeds

        events.append(
            {
                "event_id": event_id,
                "portfolio_id": PORTFOLIO_ID,
                "strategy_version": STRATEGY,
                "event_date": run_date,
                "event_type": side,
                "symbol": symbol,
                "quantity": str(qty),
                "price": str(price),
                "cash_delta": str(cash_delta),
                "realized_pnl_delta": str(realized_delta),
                "source_contract": CONTRACT,
                "synthetic_evidence": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "evidence_sha256": stable_hash(event_seed),
            }
        )

    return cash, realized, list(by_symbol.values()), events


def mark_to_market(
    positions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Decimal, Decimal, str | None]:
    market_value = D(0)
    unrealized = D(0)
    latest_date: str | None = None
    updated: list[dict[str, Any]] = []

    for pos in positions:
        if str(pos.get("status")) != "OPEN":
            updated.append(pos)
            continue

        symbol = str(pos["symbol"])
        mark_date, price = load_real_price(symbol)

        qty = D(pos["quantity"])
        avg = D(pos["avg_entry_price"])

        mv = money(qty * price)
        upnl = money((price - avg) * qty)

        pos = dict(pos)
        pos["last_market_price"] = str(price)
        pos["market_value"] = str(mv)
        pos["unrealized_pnl"] = str(upnl)
        pos["last_mark_date"] = mark_date
        pos["synthetic_evidence"] = False
        pos["broker_order_submission_enabled"] = False
        pos["real_money_trading_enabled"] = False
        pos["evidence_sha256"] = stable_hash(
            {
                "portfolio_id": PORTFOLIO_ID,
                "symbol": symbol,
                "mark_date": mark_date,
                "price": str(price),
                "qty": str(qty),
                "avg": str(avg),
            }
        )
        pos["updated_at"] = datetime.now(timezone.utc).isoformat()

        market_value += mv
        unrealized += upnl

        if latest_date is None or mark_date > latest_date:
            latest_date = mark_date

        updated.append(pos)

    return updated, money(market_value), money(unrealized), latest_date


def persist_state(
    portfolio: dict[str, Any],
    positions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    cash: Decimal,
    realized: Decimal,
) -> None:
    portfolio_row = {
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "initial_cash": str(D(portfolio.get("initial_cash", INITIAL_CASH))),
        "cash": str(money(cash)),
        "realized_pnl": str(money(realized)),
        "status": "ACTIVE",
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    rest_upsert(PORTFOLIO_TABLE, [portfolio_row], "portfolio_id")

    if positions:
        rest_upsert(POSITIONS_TABLE, positions, "portfolio_id,symbol")

    if events:
        rest_upsert(EVENTS_TABLE, events, "event_id")


def snapshot(
    upstream: dict[str, Any],
    cash: Decimal,
    realized: Decimal,
    market_value: Decimal,
    unrealized: Decimal,
    open_positions: int,
    mark_date: str,
) -> dict[str, Any]:
    nav = money(cash + market_value)

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "date": mark_date,
        "cash": str(cash),
        "market_value": str(market_value),
        "nav": str(nav),
        "realized": str(realized),
        "unrealized": str(unrealized),
        "state": upstream.get("canonical_runtime_state"),
    }

    snapshot_id = "P349S-" + stable_hash(seed)[:28]

    row = {
        "snapshot_id": snapshot_id,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "snapshot_date": mark_date,
        "cash": str(money(cash)),
        "market_value": str(market_value),
        "nav": str(nav),
        "realized_pnl": str(money(realized)),
        "unrealized_pnl": str(money(unrealized)),
        "open_positions": open_positions,
        "canonical_runtime_state": upstream.get("canonical_runtime_state"),
        "daily_cycle_status": upstream.get("daily_cycle_status"),
        "market_data_source": upstream.get("market_data_source"),
        "latest_market_date": upstream.get("latest_market_date"),
        "synthetic_evidence": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "evidence_sha256": stable_hash(seed),
    }

    rest_upsert(SNAPSHOT_TABLE, [row], "portfolio_id,snapshot_date")
    return row


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.9",
        "",
        "## Production Paper Portfolio Lifecycle + Daily Mark-to-Market Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Cycle Status: **{result['status']}**",
        "",
        "### Daily Runtime",
        "",
        f"- Canonical Runtime State: **{result['canonical_runtime_state']}**",
        f"- Daily Cycle Status: **{result['daily_cycle_status']}**",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Latest Market Date: `{result['latest_market_date']}`",
        f"- Eligible V9.1 Signals: **{result['eligible_v91_signals']}**",
        f"- New Simulated Fills Applied: **{result['fills_applied']}**",
        "",
        "### Portfolio",
        "",
        f"- Cash: **{result['cash']:.2f}**",
        f"- Market Value: **{result['market_value']:.2f}**",
        f"- NAV: **{result['nav']:.2f}**",
        f"- Realized P&L: **{result['realized_pnl']:.2f}**",
        f"- Unrealized P&L: **{result['unrealized_pnl']:.2f}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
        "",
        "### Safety Boundary",
        "",
        "- Synthetic market data: **DISABLED**",
        "- Synthetic signals: **DISABLED**",
        "- Fake prices: **DISABLED**",
        "- Broker API used: **NO**",
        "- Broker credentials used: **NO**",
        "- Broker order submission: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Live-money release authorized: **NO**",
        "- Fail-closed policy: **ENABLED**",
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    if result["positions"]:
        lines.extend(["", "### Open Paper Positions", ""])
        for p in result["positions"]:
            if p.get("status") == "OPEN":
                lines.append(
                    f"- `{p['symbol']}` qty={p['quantity']} avg={p['avg_entry_price']} "
                    f"mark={p.get('last_market_price')} mv={p.get('market_value')} "
                    f"uPnL={p.get('unrealized_pnl')}"
                )

    text = "\n".join(lines) + "\n"
    (OUT / "phase349_portfolio_lifecycle_mtm.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE349_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    upstream_exit, upstream = run_upstream(approver)
    validate_upstream(upstream)

    portfolio = ensure_portfolio()
    positions = load_positions()

    run_date = str(
        upstream.get("latest_market_date")
        or datetime.now(timezone.utc).date().isoformat()
    )

    fills = get_phase348_fills()

    if upstream.get("canonical_runtime_state") == ZERO_STATE:
        fills = []

    cash, realized, positions_after_fills, events = apply_simulated_fills(
        portfolio,
        positions,
        fills,
        run_date,
    )

    mtm_positions, market_value, unrealized, latest_mark_date = mark_to_market(
        positions_after_fills
    )

    persist_state(
        portfolio,
        mtm_positions,
        events,
        cash,
        realized,
    )

    open_count = sum(1 for p in mtm_positions if p.get("status") == "OPEN")

    snapshot_date = latest_mark_date or run_date

    snap = snapshot(
        upstream,
        cash,
        realized,
        market_value,
        unrealized,
        open_count,
        snapshot_date,
    )

    nav = D(snap["nav"])

    result = {
        "version": "3.4.9",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "upstream_process_exit_code": upstream_exit,
        "canonical_runtime_state": upstream.get("canonical_runtime_state"),
        "daily_cycle_status": upstream.get("daily_cycle_status"),
        "market_data_source": upstream.get("market_data_source"),
        "latest_market_date": upstream.get("latest_market_date"),
        "eligible_v91_signals": int(upstream.get("eligible_v91_signals") or 0),
        "fills_applied": len(events),
        "cash": float(money(cash)),
        "market_value": float(market_value),
        "nav": float(nav),
        "realized_pnl": float(money(realized)),
        "unrealized_pnl": float(unrealized),
        "open_positions": open_count,
        "positions": mtm_positions,
        "snapshot_id": snap["snapshot_id"],
        "synthetic_market_data": False,
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
    }

    if result["canonical_runtime_state"] == ZERO_STATE:
        if result["fills_applied"] != 0:
            raise RuntimeError("Zero-eligible day applied fills")
    elif result["canonical_runtime_state"] == EXECUTED_STATE:
        if result["eligible_v91_signals"] <= 0:
            raise RuntimeError("Executed state without eligible signal evidence")

    if result["cash"] < 0:
        raise RuntimeError("Paper cash became negative")

    if result["nav"] < 0:
        raise RuntimeError("Paper NAV became negative")

    result["evidence_sha256"] = stable_hash(result)

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(
        "PHASE349 PASS: persistent paper portfolio lifecycle + daily mark-to-market complete. "
        f"portfolio={PORTFOLIO_ID}, cash={result['cash']:.2f}, "
        f"market_value={result['market_value']:.2f}, nav={result['nav']:.2f}, "
        f"open_positions={result['open_positions']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
