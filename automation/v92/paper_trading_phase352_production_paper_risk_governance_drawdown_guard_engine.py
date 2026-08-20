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
OUT = ROOT / "phase352_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE352_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py"
UPSTREAM_JSON = ROOT / "phase351_output/phase351_performance_analytics.json"

LEDGER_TABLE = "paper_performance_ledger_v92"
POSITIONS_TABLE = "paper_positions_v92"
GOVERNANCE_TABLE = "paper_risk_governance_v92"

RESULT_JSON = OUT / "phase352_risk_governance.json"

CONTRACT = "PHASE352_PRODUCTION_PAPER_RISK_GOVERNANCE_DRAWDOWN_GUARD_ENGINE"

# Default governance thresholds. They are intentionally conservative and paper-only.
CAUTION_DRAWDOWN = float(os.getenv("PHASE352_CAUTION_DRAWDOWN", "-0.05"))
REDUCE_DRAWDOWN = float(os.getenv("PHASE352_REDUCE_DRAWDOWN", "-0.10"))
HALT_DRAWDOWN = float(os.getenv("PHASE352_HALT_DRAWDOWN", "-0.15"))

CAUTION_DAILY_LOSS = float(os.getenv("PHASE352_CAUTION_DAILY_LOSS", "-0.025"))
HALT_DAILY_LOSS = float(os.getenv("PHASE352_HALT_DAILY_LOSS", "-0.05"))

MAX_EXPOSURE_CAUTION = float(os.getenv("PHASE352_MAX_EXPOSURE_CAUTION", "0.80"))
MAX_EXPOSURE_HALT = float(os.getenv("PHASE352_MAX_EXPOSURE_HALT", "0.95"))

MAX_CONCENTRATION_CAUTION = float(os.getenv("PHASE352_MAX_CONCENTRATION_CAUTION", "0.35"))
MAX_CONCENTRATION_HALT = float(os.getenv("PHASE352_MAX_CONCENTRATION_HALT", "0.50"))

CONSECUTIVE_LOSS_CAUTION = int(os.getenv("PHASE352_CONSECUTIVE_LOSS_CAUTION", "3"))
CONSECUTIVE_LOSS_HALT = int(os.getenv("PHASE352_CONSECUTIVE_LOSS_HALT", "5"))


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
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:800]}"
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


def run_upstream() -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE351_PORTFOLIO_ID"] = PORTFOLIO_ID

    proc = subprocess.run(
        [sys.executable, str(UPSTREAM)],
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
            f"Phase 3.5.1 evidence missing; upstream exit={proc.returncode}"
        )

    return proc.returncode, load_json(UPSTREAM_JSON)


def safe_float(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = data.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_latest_ledger() -> dict[str, Any]:
    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("order", "ledger_date.desc"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("No performance ledger rows found")

    return rows[0]


def load_open_positions() -> list[dict[str, Any]]:
    return rest_get(
        POSITIONS_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("status", "eq.OPEN"),
        ],
    )


def load_recent_ledger_returns(limit: int = 30) -> list[float]:
    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "ledger_date,daily_return"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("order", "ledger_date.desc"),
            ("limit", str(limit)),
        ],
    )

    values = []
    for row in rows:
        try:
            values.append(float(row.get("daily_return") or 0))
        except (TypeError, ValueError):
            values.append(0.0)

    return values


def consecutive_losses(returns_desc: list[float]) -> int:
    count = 0
    for value in returns_desc:
        if value < 0:
            count += 1
        else:
            break
    return count


def exposure_metrics(
    ledger: dict[str, Any],
    positions: list[dict[str, Any]],
) -> tuple[float, float]:
    nav = float(ledger.get("nav") or 0)
    market_value = float(ledger.get("market_value") or 0)

    if nav <= 0:
        return 0.0, 0.0

    exposure = market_value / nav

    max_concentration = 0.0
    for pos in positions:
        try:
            mv = float(pos.get("market_value") or 0)
        except (TypeError, ValueError):
            mv = 0.0

        if mv > 0:
            max_concentration = max(max_concentration, mv / nav)

    return exposure, max_concentration


def validate_upstream(analytics: dict[str, Any]) -> None:
    if analytics.get("status") != "PASS":
        raise RuntimeError("Phase 3.5.1 analytics did not PASS")

    if analytics.get("analytics_state") not in {
        "INSUFFICIENT_HISTORY_VALID_STATE",
        "ANALYTICS_READY",
    }:
        raise RuntimeError(
            f"Unexpected analytics_state={analytics.get('analytics_state')!r}"
        )

    for key in (
        "synthetic_market_data",
        "synthetic_signals",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    ):
        if analytics.get(key) is not False:
            raise RuntimeError(
                f"Safety contract violation: {key}={analytics.get(key)!r}"
            )

    if analytics.get("fail_closed_policy") is not True:
        raise RuntimeError("fail_closed_policy must remain enabled")


def classify_risk(
    analytics: dict[str, Any],
    ledger: dict[str, Any],
    positions: list[dict[str, Any]],
    recent_returns: list[float],
) -> dict[str, Any]:
    analytics_state = analytics["analytics_state"]

    current_drawdown = safe_float(analytics, "current_drawdown", 0.0)
    maximum_drawdown = safe_float(analytics, "maximum_drawdown", 0.0)
    daily_return = float(ledger.get("daily_return") or 0)
    cumulative_return = float(ledger.get("cumulative_return") or 0)

    exposure, concentration = exposure_metrics(ledger, positions)
    loss_streak = consecutive_losses(recent_returns)

    drawdown_guard = (
        current_drawdown <= CAUTION_DRAWDOWN
        or maximum_drawdown <= CAUTION_DRAWDOWN
    )

    daily_loss_guard = daily_return <= CAUTION_DAILY_LOSS
    exposure_guard = exposure >= MAX_EXPOSURE_CAUTION
    concentration_guard = concentration >= MAX_CONCENTRATION_CAUTION
    consecutive_loss_guard = loss_streak >= CONSECUTIVE_LOSS_CAUTION

    hard_halt = (
        current_drawdown <= HALT_DRAWDOWN
        or maximum_drawdown <= HALT_DRAWDOWN
        or daily_return <= HALT_DAILY_LOSS
        or exposure >= MAX_EXPOSURE_HALT
        or concentration >= MAX_CONCENTRATION_HALT
        or loss_streak >= CONSECUTIVE_LOSS_HALT
    )

    reduce = (
        current_drawdown <= REDUCE_DRAWDOWN
        or maximum_drawdown <= REDUCE_DRAWDOWN
    )

    if analytics_state == "INSUFFICIENT_HISTORY_VALID_STATE":
        risk_state = "INSUFFICIENT_HISTORY_VALID_STATE"
        new_entries_authorized = True
        risk_reduction_factor = 1.0
        reason = (
            "Performance history is still below the analytics readiness threshold; "
            "paper trading remains allowed under existing fail-closed safety controls."
        )

    elif hard_halt:
        risk_state = "PAPER_HALT"
        new_entries_authorized = False
        risk_reduction_factor = 0.0
        reason = "One or more hard paper-risk halt thresholds were breached."

    elif reduce:
        risk_state = "RISK_REDUCED"
        new_entries_authorized = True
        risk_reduction_factor = 0.5
        reason = "Drawdown reached the paper-risk reduction band."

    elif (
        drawdown_guard
        or daily_loss_guard
        or exposure_guard
        or concentration_guard
        or consecutive_loss_guard
    ):
        risk_state = "CAUTION"
        new_entries_authorized = True
        risk_reduction_factor = 0.75
        reason = "One or more caution-level paper-risk guards were triggered."

    else:
        risk_state = "NORMAL"
        new_entries_authorized = True
        risk_reduction_factor = 1.0
        reason = "All paper-risk governance checks are within normal limits."

    return {
        "analytics_state": analytics_state,
        "risk_state": risk_state,
        "new_paper_entries_authorized": new_entries_authorized,
        "paper_halt": risk_state == "PAPER_HALT",
        "current_drawdown": current_drawdown,
        "maximum_drawdown": maximum_drawdown,
        "daily_return": daily_return,
        "cumulative_return": cumulative_return,
        "annualized_volatility": analytics.get("annualized_volatility"),
        "sharpe_ratio": analytics.get("sharpe_ratio"),
        "portfolio_exposure": exposure,
        "max_position_concentration": concentration,
        "consecutive_loss_days": loss_streak,
        "drawdown_guard_triggered": drawdown_guard,
        "daily_loss_guard_triggered": daily_loss_guard,
        "exposure_guard_triggered": exposure_guard,
        "concentration_guard_triggered": concentration_guard,
        "consecutive_loss_guard_triggered": consecutive_loss_guard,
        "risk_reduction_factor": risk_reduction_factor,
        "governance_reason": reason,
    }


def persist_governance(
    governance_date: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "governance_date": governance_date,
        "risk_state": state["risk_state"],
        "current_drawdown": state["current_drawdown"],
        "daily_return": state["daily_return"],
        "portfolio_exposure": state["portfolio_exposure"],
        "max_position_concentration": state["max_position_concentration"],
        "consecutive_loss_days": state["consecutive_loss_days"],
    }

    governance_id = "P352G-" + stable_hash(seed)[:28]

    row = {
        "governance_id": governance_id,
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "governance_date": governance_date,
        **state,
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

    rest_upsert(
        GOVERNANCE_TABLE,
        [row],
        "portfolio_id,governance_date",
    )

    rows = rest_get(
        GOVERNANCE_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("governance_date", f"eq.{governance_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Risk governance persistence verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.5.2",
        "",
        "## Production Paper Risk Governance + Drawdown Guard Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Governance Status: **{result['status']}**",
        f"- Governance Date: `{result['governance_date']}`",
        "",
        "### Risk Governance",
        "",
        f"- Analytics State: **{result['analytics_state']}**",
        f"- Risk State: **{result['risk_state']}**",
        f"- New Paper Entries Authorized: **{'YES' if result['new_paper_entries_authorized'] else 'NO'}**",
        f"- Paper Halt: **{'YES' if result['paper_halt'] else 'NO'}**",
        f"- Risk Reduction Factor: **{result['risk_reduction_factor']:.2f}**",
        f"- Reason: {result['governance_reason']}",
        "",
        "### Risk Metrics",
        "",
        f"- Current Drawdown: **{result['current_drawdown']:.6%}**",
        f"- Maximum Drawdown: **{result['maximum_drawdown']:.6%}**",
        f"- Daily Return: **{result['daily_return']:.6%}**",
        f"- Cumulative Return: **{result['cumulative_return']:.6%}**",
        f"- Portfolio Exposure: **{result['portfolio_exposure']:.6%}**",
        f"- Max Position Concentration: **{result['max_position_concentration']:.6%}**",
        f"- Consecutive Loss Days: **{result['consecutive_loss_days']}**",
        "",
        "### Guard Status",
        "",
        f"- Drawdown Guard: **{'TRIGGERED' if result['drawdown_guard_triggered'] else 'CLEAR'}**",
        f"- Daily Loss Guard: **{'TRIGGERED' if result['daily_loss_guard_triggered'] else 'CLEAR'}**",
        f"- Exposure Guard: **{'TRIGGERED' if result['exposure_guard_triggered'] else 'CLEAR'}**",
        f"- Concentration Guard: **{'TRIGGERED' if result['concentration_guard_triggered'] else 'CLEAR'}**",
        f"- Consecutive Loss Guard: **{'TRIGGERED' if result['consecutive_loss_guard_triggered'] else 'CLEAR'}**",
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

    (OUT / "phase352_risk_governance.md").write_text(
        text,
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")

    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    upstream_exit, analytics = run_upstream()
    validate_upstream(analytics)

    ledger = load_latest_ledger()
    positions = load_open_positions()
    returns_desc = load_recent_ledger_returns()

    state = classify_risk(
        analytics,
        ledger,
        positions,
        returns_desc,
    )

    governance_date = str(ledger["ledger_date"])
    persisted = persist_governance(
        governance_date,
        state,
    )

    result = {
        "version": "3.5.2",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "upstream_process_exit_code": upstream_exit,
        "governance_id": persisted["governance_id"],
        "governance_date": str(persisted["governance_date"]),
        "analytics_state": persisted["analytics_state"],
        "risk_state": persisted["risk_state"],
        "new_paper_entries_authorized": bool(
            persisted["new_paper_entries_authorized"]
        ),
        "paper_halt": bool(persisted["paper_halt"]),
        "current_drawdown": float(persisted["current_drawdown"] or 0),
        "maximum_drawdown": float(persisted["maximum_drawdown"] or 0),
        "daily_return": float(persisted["daily_return"] or 0),
        "cumulative_return": float(persisted["cumulative_return"] or 0),
        "annualized_volatility": (
            float(persisted["annualized_volatility"])
            if persisted.get("annualized_volatility") is not None
            else None
        ),
        "sharpe_ratio": (
            float(persisted["sharpe_ratio"])
            if persisted.get("sharpe_ratio") is not None
            else None
        ),
        "portfolio_exposure": float(persisted["portfolio_exposure"] or 0),
        "max_position_concentration": float(
            persisted["max_position_concentration"] or 0
        ),
        "consecutive_loss_days": int(
            persisted["consecutive_loss_days"] or 0
        ),
        "drawdown_guard_triggered": bool(
            persisted["drawdown_guard_triggered"]
        ),
        "daily_loss_guard_triggered": bool(
            persisted["daily_loss_guard_triggered"]
        ),
        "exposure_guard_triggered": bool(
            persisted["exposure_guard_triggered"]
        ),
        "concentration_guard_triggered": bool(
            persisted["concentration_guard_triggered"]
        ),
        "consecutive_loss_guard_triggered": bool(
            persisted["consecutive_loss_guard_triggered"]
        ),
        "risk_reduction_factor": float(
            persisted["risk_reduction_factor"]
        ),
        "governance_reason": persisted.get("governance_reason") or "",
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

    if result["paper_halt"] and result["new_paper_entries_authorized"]:
        raise RuntimeError(
            "Governance contradiction: PAPER_HALT cannot authorize new paper entries"
        )

    if result["risk_state"] == "PAPER_HALT":
        if result["risk_reduction_factor"] != 0.0:
            raise RuntimeError(
                "PAPER_HALT must force risk_reduction_factor=0"
            )

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    print(
        "PHASE352 PASS: paper-risk governance evaluated. "
        f"state={result['risk_state']}, "
        f"new_entries={'YES' if result['new_paper_entries_authorized'] else 'NO'}, "
        f"drawdown={result['current_drawdown']:.8f}, "
        f"exposure={result['portfolio_exposure']:.8f}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
