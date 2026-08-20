#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase360_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE360_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

MASTER_TABLE = "paper_master_cycles_v92"
EOD_TABLE = "paper_eod_ledger_v92"

RESULT_JSON = OUT / "phase360_master_cycle.json"
RESULT_MD = OUT / "phase360_master_cycle.md"

CONTRACT = "PHASE360_PRODUCTION_PAPER_DAILY_MASTER_ORCHESTRATOR"

STAGES = [
    {
        "id": "phase350",
        "name": "Daily Orchestrator + Persistent Performance Ledger",
        "script": ROOT / "automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py",
        "output": ROOT / "phase350_output/phase350_daily_orchestrator.json",
    },
    {
        "id": "phase351",
        "name": "Performance Analytics + Risk Metrics",
        "script": ROOT / "automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py",
        "output": ROOT / "phase351_output/phase351_performance_analytics.json",
    },
    {
        "id": "phase352",
        "name": "Risk Governance + Drawdown Guard",
        "script": ROOT / "automation/v92/paper_trading_phase352_production_paper_risk_governance_drawdown_guard_engine.py",
        "output": ROOT / "phase352_output/phase352_risk_governance.json",
    },
    {
        "id": "phase353",
        "name": "Position Sizing + Risk Budget Allocation",
        "script": ROOT / "automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py",
        "output": ROOT / "phase353_output/phase353_position_sizing.json",
    },
    {
        "id": "phase354",
        "name": "Order Intent + Simulated Execution Lifecycle",
        "script": ROOT / "automation/v92/paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine.py",
        "output": ROOT / "phase354_output/phase354_execution_lifecycle.json",
    },
    {
        "id": "phase355",
        "name": "Position Reconciliation + Execution Settlement",
        "script": ROOT / "automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py",
        "output": ROOT / "phase355_output/phase355_settlement.json",
    },
    {
        "id": "phase356",
        "name": "EOD Accounting + Portfolio Ledger Finalization",
        "script": ROOT / "automation/v92/paper_trading_phase356_eod_accounting_portfolio_ledger_finalization_engine.py",
        "output": None,
    },
]

VALID_ZERO_STATES = {
    "NO_ELIGIBLE_V91_SIGNAL_ZERO_ORDERS",
    "INSUFFICIENT_HISTORY_VALID_STATE",
    "ZERO_ORDER_VALID_STATE",
    "ZERO_FILL_VALID_STATE",
    "PAPER_HALT_ZERO_ORDERS",
    "PAPER_HALT_ZERO_SETTLEMENT",
    "ALREADY_SETTLED_IDEMPOTENT",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:1000]}"
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
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1400]}"
        )


def stage_env(approver: str) -> dict[str, str]:
    env = os.environ.copy()

    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    for phase in ("350", "351", "352", "353", "354", "355"):
        env[f"PHASE{phase}_PORTFOLIO_ID"] = PORTFOLIO_ID

    env["PHASE350_APPROVER"] = approver

    return env


def run_stage(
    stage: dict[str, Any],
    approver: str,
) -> dict[str, Any]:
    stage_id = stage["id"]
    script = stage["script"]
    output = stage["output"]

    if not script.exists():
        raise RuntimeError(f"{stage_id}: script missing: {script}")

    cmd = [sys.executable, str(script)]

    if stage_id == "phase350":
        cmd += ["--approver", approver]

    started = now_iso()

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=stage_env(approver),
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(
            f"\n===== {stage_id} stdout =====\n{proc.stdout}",
            end="" if proc.stdout.endswith("\n") else "\n",
        )

    if proc.stderr:
        print(
            f"\n===== {stage_id} stderr =====\n{proc.stderr}",
            file=sys.stderr,
            end="" if proc.stderr.endswith("\n") else "\n",
        )

    payload: dict[str, Any] | None = None

    if output is not None:
        if not output.exists():
            raise RuntimeError(
                f"{stage_id}: expected output missing after exit={proc.returncode}: {output}"
            )
        payload = load_json(output)

    if proc.returncode != 0:
        raise RuntimeError(
            f"{stage_id}: process failed with exit code {proc.returncode}"
        )

    if payload is not None and payload.get("status") != "PASS":
        raise RuntimeError(
            f"{stage_id}: output status is not PASS: {payload.get('status')!r}"
        )

    return {
        "stage_id": stage_id,
        "name": stage["name"],
        "status": "PASS",
        "exit_code": proc.returncode,
        "started_at": started,
        "completed_at": now_iso(),
        "payload": payload,
    }


def validate_safety(stage_results: list[dict[str, Any]]) -> None:
    unsafe_false_keys = (
        "synthetic_market_data",
        "synthetic_signals",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    )

    for stage in stage_results:
        payload = stage.get("payload")
        if not isinstance(payload, dict):
            continue

        for key in unsafe_false_keys:
            if key in payload and payload[key] is not False:
                raise RuntimeError(
                    f"{stage['stage_id']}: safety violation: {key}={payload[key]!r}"
                )

        if "fail_closed_policy" in payload and payload["fail_closed_policy"] is not True:
            raise RuntimeError(
                f"{stage['stage_id']}: fail_closed_policy must remain enabled"
            )


def upsert_eod_from_settlement(
    settlement: dict[str, Any],
) -> dict[str, Any]:
    ledger_date = str(settlement["settlement_date"])

    row = {
        "ledger_date": ledger_date,
        "nav": settlement["nav_after"],
        "cash": settlement["cash_after"],
        "market_value": settlement["market_value_after"],
        "realized_pnl": settlement["realized_pnl_after"],
        "unrealized_pnl": settlement["unrealized_pnl_after"],
    }

    # paper_eod_ledger_v92 is created by Phase 3.5.6 SQL.
    # This master makes Phase 3.5.6 operationally useful even if the local
    # Phase 3.5.6 Python runner is intentionally minimal.
    rest_upsert(
        EOD_TABLE,
        [row],
        "ledger_date",
    )

    rows = rest_get(
        EOD_TABLE,
        [
            ("select", "*"),
            ("ledger_date", f"eq.{ledger_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Phase 3.6.0 EOD ledger verification failed")

    return rows[0]


def final_state_from(stage_results: list[dict[str, Any]]) -> str:
    p350 = stage_results[0].get("payload") or {}
    p351 = stage_results[1].get("payload") or {}
    p352 = stage_results[2].get("payload") or {}
    p354 = stage_results[4].get("payload") or {}
    p355 = stage_results[5].get("payload") or {}

    states = [
        p350.get("canonical_runtime_state"),
        p351.get("analytics_state"),
        p352.get("risk_state"),
        p354.get("execution_state"),
        p355.get("settlement_state"),
    ]

    if any(state == "PAPER_HALT" for state in states):
        return "PAPER_HALT_COMPLETED"

    if all(
        state in VALID_ZERO_STATES or state in {None, "NORMAL", "CAUTION", "RISK_REDUCED", "ANALYTICS_READY"}
        for state in states
    ):
        return "DAILY_MASTER_CYCLE_COMPLETED"

    return "DAILY_MASTER_CYCLE_COMPLETED"


def persist_master_cycle(
    stage_results: list[dict[str, Any]],
    eod: dict[str, Any],
    started_at: str,
) -> dict[str, Any]:
    p350 = stage_results[0]["payload"] or {}
    p351 = stage_results[1]["payload"] or {}
    p352 = stage_results[2]["payload"] or {}
    p353 = stage_results[3]["payload"] or {}
    p354 = stage_results[4]["payload"] or {}
    p355 = stage_results[5]["payload"] or {}

    cycle_date = str(
        p355.get("settlement_date")
        or p350.get("ledger_date")
        or eod.get("ledger_date")
    )

    final_state = final_state_from(stage_results)

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "cycle_date": cycle_date,
        "final_state": final_state,
        "phase350": p350.get("evidence_sha256"),
        "phase351": p351.get("evidence_sha256"),
        "phase352": p352.get("evidence_sha256"),
        "phase353": p353.get("evidence_sha256"),
        "phase354": p354.get("evidence_sha256"),
        "phase355": p355.get("evidence_sha256"),
        "eod": {
            "cash": eod.get("cash"),
            "market_value": eod.get("market_value"),
            "nav": eod.get("nav"),
        },
    }

    row = {
        "master_cycle_id": "P360M-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "cycle_date": cycle_date,
        "master_status": "PASS",
        "final_state": final_state,
        "failed_stage": None,
        "phase350_status": "PASS",
        "phase351_status": "PASS",
        "phase352_status": "PASS",
        "phase353_status": "PASS",
        "phase354_status": "PASS",
        "phase355_status": "PASS",
        "phase356_status": "PASS",
        "canonical_runtime_state": p350.get("canonical_runtime_state"),
        "analytics_state": p351.get("analytics_state"),
        "risk_state": p352.get("risk_state"),
        "execution_state": p354.get("execution_state"),
        "settlement_state": p355.get("settlement_state"),
        "eligible_signals": int(p353.get("eligible_signals") or 0),
        "sized_candidates": int(p353.get("sized_candidates") or 0),
        "order_intents_created": int(p354.get("order_intents_created") or 0),
        "simulated_fills_created": int(p354.get("simulated_fills_created") or 0),
        "fills_settled": int(p355.get("fills_settled") or 0),
        "cash": eod.get("cash"),
        "market_value": eod.get("market_value"),
        "nav": eod.get("nav"),
        "realized_pnl": eod.get("realized_pnl"),
        "unrealized_pnl": eod.get("unrealized_pnl"),
        "open_positions": int(p355.get("open_positions_after") or 0),
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
        "started_at": started_at,
        "completed_at": now_iso(),
        "updated_at": now_iso(),
    }

    rest_upsert(
        MASTER_TABLE,
        [row],
        "portfolio_id,cycle_date",
    )

    rows = rest_get(
        MASTER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("cycle_date", f"eq.{cycle_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Master-cycle persistence verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.6.0",
        "",
        "## Production Paper Daily Master Orchestrator",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Master Status: **{result['status']}**",
        f"- Final State: **{result['final_state']}**",
        f"- Cycle Date: `{result['cycle_date']}`",
        "",
        "### Stage Results",
        "",
    ]

    for stage in result["stages"]:
        lines.append(
            f"- {stage['stage_id']} — {stage['name']}: **{stage['status']}**"
        )

    lines.extend(
        [
            "",
            "### Canonical Runtime",
            "",
            f"- Canonical Runtime State: **{result['canonical_runtime_state']}**",
            f"- Analytics State: **{result['analytics_state']}**",
            f"- Risk State: **{result['risk_state']}**",
            f"- Execution State: **{result['execution_state']}**",
            f"- Settlement State: **{result['settlement_state']}**",
            "",
            "### Daily Activity",
            "",
            f"- Eligible Signals: **{result['eligible_signals']}**",
            f"- Sized Candidates: **{result['sized_candidates']}**",
            f"- Order Intents Created: **{result['order_intents_created']}**",
            f"- Simulated Fills Created: **{result['simulated_fills_created']}**",
            f"- Fills Settled: **{result['fills_settled']}**",
            "",
            "### EOD Portfolio",
            "",
            f"- Cash: **{result['cash']:.2f}**",
            f"- Market Value: **{result['market_value']:.2f}**",
            f"- NAV: **{result['nav']:.2f}**",
            f"- Realized P&L: **{result['realized_pnl']:.2f}**",
            f"- Unrealized P&L: **{result['unrealized_pnl']:.2f}**",
            f"- Open Positions: **{result['open_positions']}**",
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
    )

    text = "\n".join(lines) + "\n"
    RESULT_MD.write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE360_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    started_at = now_iso()
    results: list[dict[str, Any]] = []

    for stage in STAGES:
        print(f"\n>>> RUN {stage['id']}: {stage['name']}")
        result = run_stage(stage, approver)
        results.append(result)

    validate_safety(results)

    settlement = results[5]["payload"]
    if not isinstance(settlement, dict):
        raise RuntimeError("Phase 3.5.5 settlement evidence missing")

    eod = upsert_eod_from_settlement(settlement)

    master = persist_master_cycle(
        results,
        eod,
        started_at,
    )

    result = {
        "version": "3.6.0",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "master_cycle_id": master["master_cycle_id"],
        "cycle_date": str(master["cycle_date"]),
        "final_state": master["final_state"],
        "canonical_runtime_state": master.get("canonical_runtime_state"),
        "analytics_state": master.get("analytics_state"),
        "risk_state": master.get("risk_state"),
        "execution_state": master.get("execution_state"),
        "settlement_state": master.get("settlement_state"),
        "eligible_signals": int(master.get("eligible_signals") or 0),
        "sized_candidates": int(master.get("sized_candidates") or 0),
        "order_intents_created": int(master.get("order_intents_created") or 0),
        "simulated_fills_created": int(master.get("simulated_fills_created") or 0),
        "fills_settled": int(master.get("fills_settled") or 0),
        "cash": float(master.get("cash") or 0),
        "market_value": float(master.get("market_value") or 0),
        "nav": float(master.get("nav") or 0),
        "realized_pnl": float(master.get("realized_pnl") or 0),
        "unrealized_pnl": float(master.get("unrealized_pnl") or 0),
        "open_positions": int(master.get("open_positions") or 0),
        "stages": [
            {
                "stage_id": r["stage_id"],
                "name": r["name"],
                "status": r["status"],
                "exit_code": r["exit_code"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
            }
            for r in results
        ],
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": master["evidence_sha256"],
    }

    if len(result["stages"]) != 7:
        raise RuntimeError("Master cycle did not execute all seven stages")

    if any(stage["status"] != "PASS" for stage in result["stages"]):
        raise RuntimeError("One or more master stages did not PASS")

    if result["cash"] < 0 or result["nav"] < 0:
        raise RuntimeError("Invalid negative paper portfolio state")

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE360 PASS: full production-paper daily master cycle completed. "
        f"date={result['cycle_date']}, "
        f"final_state={result['final_state']}, "
        f"nav={result['nav']:.2f}, "
        f"fills={result['simulated_fills_created']}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
