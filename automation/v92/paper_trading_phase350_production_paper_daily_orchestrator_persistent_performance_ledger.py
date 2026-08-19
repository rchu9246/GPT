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
OUT = ROOT / "phase350_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE350_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase349_production_paper_portfolio_lifecycle_daily_mark_to_market_engine.py"
UPSTREAM_JSON = ROOT / "phase349_output/phase349_portfolio_lifecycle_mtm.json"

LEDGER_TABLE = "paper_performance_ledger_v92"
RESULT_JSON = OUT / "phase350_daily_orchestrator.json"

CONTRACT = "PHASE350_PRODUCTION_PAPER_DAILY_ORCHESTRATOR_PERSISTENT_PERFORMANCE_LEDGER"


def D(value: Any) -> Decimal:
    return Decimal(str(value))


def q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


def rest_get(
    table: str,
    params: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:700]}"
        )

    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(f"{table}: expected list response")

    return [x for x in data if isinstance(x, dict)]


def rest_upsert(
    table: str,
    rows: list[dict[str, Any]],
    on_conflict: str,
) -> None:
    if not rows:
        return

    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.post(
        url,
        headers=headers,
        params={"on_conflict": on_conflict},
        data=json.dumps(rows, ensure_ascii=False, default=str),
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1000]}"
        )


def run_upstream(approver: str) -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()

    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE349_PORTFOLIO_ID"] = PORTFOLIO_ID

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
        print(
            proc.stderr,
            file=sys.stderr,
            end="" if proc.stderr.endswith("\n") else "\n",
        )

    if not UPSTREAM_JSON.exists():
        raise RuntimeError(
            f"Phase 3.4.9 evidence missing; upstream exit={proc.returncode}"
        )

    return proc.returncode, load_json(UPSTREAM_JSON)


def validate_safety(data: dict[str, Any]) -> None:
    if data.get("status") != "PASS":
        raise RuntimeError("Phase 3.4.9 did not PASS")

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
            raise RuntimeError(
                f"Safety contract violation: {key}={data.get(key)!r}"
            )

    if data.get("fail_closed_policy") is not True:
        raise RuntimeError("fail_closed_policy must remain enabled")

    if str(data.get("portfolio_id") or "") != PORTFOLIO_ID:
        raise RuntimeError(
            f"Portfolio mismatch: {data.get('portfolio_id')!r} != {PORTFOLIO_ID!r}"
        )

    if D(data.get("nav", 0)) < 0:
        raise RuntimeError("NAV cannot be negative")

    if D(data.get("cash", 0)) < 0:
        raise RuntimeError("Cash cannot be negative")


def load_previous_ledger(ledger_date: str) -> dict[str, Any] | None:
    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("ledger_date", f"lt.{ledger_date}"),
            ("order", "ledger_date.desc"),
            ("limit", "1"),
        ],
    )

    return rows[0] if rows else None


def load_first_ledger() -> dict[str, Any] | None:
    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("order", "ledger_date.asc"),
            ("limit", "1"),
        ],
    )

    return rows[0] if rows else None


def build_ledger(upstream: dict[str, Any]) -> dict[str, Any]:
    ledger_date = str(
        upstream.get("latest_market_date")
        or datetime.now(timezone.utc).date().isoformat()
    )

    nav = money(D(upstream["nav"]))
    cash = money(D(upstream["cash"]))
    market_value = money(D(upstream["market_value"]))
    realized_pnl = money(D(upstream["realized_pnl"]))
    unrealized_pnl = money(D(upstream["unrealized_pnl"]))

    previous = load_previous_ledger(ledger_date)
    first = load_first_ledger()

    previous_nav = (
        money(D(previous["nav"]))
        if previous is not None
        else None
    )

    initial_nav = (
        money(D(first["initial_nav"]))
        if first is not None and first.get("initial_nav") is not None
        else nav
    )

    if previous_nav is not None and previous_nav != 0:
        daily_return = q((nav / previous_nav) - D(1))
    else:
        daily_return = D(0)

    if initial_nav != 0:
        cumulative_return = q((nav / initial_nav) - D(1))
    else:
        cumulative_return = D(0)

    previous_hwm = (
        money(D(previous["high_water_mark"]))
        if previous is not None
        else nav
    )

    high_water_mark = max(previous_hwm, nav)

    if high_water_mark != 0:
        drawdown = q((nav / high_water_mark) - D(1))
    else:
        drawdown = D(0)

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "ledger_date": ledger_date,
        "nav": str(nav),
        "cash": str(cash),
        "market_value": str(market_value),
        "canonical_runtime_state": upstream.get("canonical_runtime_state"),
        "daily_cycle_status": upstream.get("daily_cycle_status"),
        "open_positions": int(upstream.get("open_positions") or 0),
        "eligible_signals": int(upstream.get("eligible_v91_signals") or 0),
        "fills_applied": int(upstream.get("fills_applied") or 0),
    }

    ledger_id = "P350L-" + stable_hash(seed)[:28]

    row = {
        "ledger_id": ledger_id,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "ledger_date": ledger_date,
        "cycle_status": "COMPLETED",
        "canonical_runtime_state": upstream.get("canonical_runtime_state"),
        "market_data_source": upstream.get("market_data_source"),
        "latest_market_date": upstream.get("latest_market_date"),
        "cash": str(cash),
        "market_value": str(market_value),
        "nav": str(nav),
        "realized_pnl": str(realized_pnl),
        "unrealized_pnl": str(unrealized_pnl),
        "previous_nav": str(previous_nav) if previous_nav is not None else None,
        "initial_nav": str(initial_nav),
        "daily_return": str(daily_return),
        "cumulative_return": str(cumulative_return),
        "high_water_mark": str(high_water_mark),
        "drawdown": str(drawdown),
        "open_positions": int(upstream.get("open_positions") or 0),
        "eligible_signals": int(upstream.get("eligible_v91_signals") or 0),
        "fills_applied": int(upstream.get("fills_applied") or 0),
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": stable_hash(seed),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return row


def persist_ledger(row: dict[str, Any]) -> dict[str, Any]:
    rest_upsert(
        LEDGER_TABLE,
        [row],
        "portfolio_id,ledger_date",
    )

    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("ledger_date", f"eq.{row['ledger_date']}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Performance ledger write verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.5.0",
        "",
        "## Production Paper Daily Orchestrator + Persistent Performance Ledger",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Orchestrator Status: **{result['status']}**",
        "",
        "### Daily Runtime",
        "",
        f"- Ledger Date: `{result['ledger_date']}`",
        f"- Cycle Status: **{result['cycle_status']}**",
        f"- Canonical Runtime State: **{result['canonical_runtime_state']}**",
        f"- Market Data Source: `{result['market_data_source']}`",
        f"- Latest Market Date: `{result['latest_market_date']}`",
        "",
        "### Portfolio",
        "",
        f"- Cash: **{result['cash']:.2f}**",
        f"- Market Value: **{result['market_value']:.2f}**",
        f"- NAV: **{result['nav']:.2f}**",
        f"- Realized P&L: **{result['realized_pnl']:.2f}**",
        f"- Unrealized P&L: **{result['unrealized_pnl']:.2f}**",
        f"- Open Positions: **{result['open_positions']}**",
        "",
        "### Persistent Performance Ledger",
        "",
        "- Ledger Written: **YES**",
        f"- Previous NAV: **{result['previous_nav'] if result['previous_nav'] is not None else 'NONE'}**",
        f"- Initial NAV: **{result['initial_nav']:.2f}**",
        f"- Daily Return: **{result['daily_return']:.6%}**",
        f"- Cumulative Return: **{result['cumulative_return']:.6%}**",
        f"- High Water Mark: **{result['high_water_mark']:.2f}**",
        f"- Drawdown: **{result['drawdown']:.6%}**",
        f"- Eligible Signals: **{result['eligible_signals']}**",
        f"- Fills Applied: **{result['fills_applied']}**",
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

    text = "\n".join(lines) + "\n"

    (OUT / "phase350_daily_orchestrator.md").write_text(
        text,
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")

    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE350_APPROVER", "rchu9246"),
    )

    args = parser.parse_args()
    approver = args.approver.strip()

    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    upstream_exit, upstream = run_upstream(approver)
    validate_safety(upstream)

    ledger_row = build_ledger(upstream)
    persisted = persist_ledger(ledger_row)

    result = {
        "version": "3.5.0",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "upstream_process_exit_code": upstream_exit,
        "ledger_id": persisted["ledger_id"],
        "ledger_date": str(persisted["ledger_date"]),
        "cycle_status": persisted["cycle_status"],
        "canonical_runtime_state": persisted["canonical_runtime_state"],
        "market_data_source": persisted.get("market_data_source"),
        "latest_market_date": str(persisted.get("latest_market_date") or ""),
        "cash": float(persisted["cash"]),
        "market_value": float(persisted["market_value"]),
        "nav": float(persisted["nav"]),
        "realized_pnl": float(persisted["realized_pnl"]),
        "unrealized_pnl": float(persisted["unrealized_pnl"]),
        "previous_nav": (
            float(persisted["previous_nav"])
            if persisted.get("previous_nav") is not None
            else None
        ),
        "initial_nav": float(persisted["initial_nav"]),
        "daily_return": float(persisted["daily_return"]),
        "cumulative_return": float(persisted["cumulative_return"]),
        "high_water_mark": float(persisted["high_water_mark"]),
        "drawdown": float(persisted["drawdown"]),
        "open_positions": int(persisted["open_positions"]),
        "eligible_signals": int(persisted["eligible_signals"]),
        "fills_applied": int(persisted["fills_applied"]),
        "ledger_written": True,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": persisted["evidence_sha256"],
    }

    if result["cycle_status"] != "COMPLETED":
        raise RuntimeError("Performance ledger cycle_status must be COMPLETED")

    if result["nav"] < 0 or result["cash"] < 0:
        raise RuntimeError("Invalid negative portfolio state")

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE350 PASS: daily production-paper orchestrator + persistent performance ledger complete. "
        f"date={result['ledger_date']}, nav={result['nav']:.2f}, "
        f"daily_return={result['daily_return']:.8f}, "
        f"cumulative_return={result['cumulative_return']:.8f}, "
        f"drawdown={result['drawdown']:.8f}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
