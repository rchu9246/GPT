from __future__ import annotations

import argparse
import math
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())
ENGINE_VERSION = "9.4.0"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def read(client: SupabaseRestClient, table: str, query: str, required: bool = False) -> list[dict[str, Any]]:
    try:
        rows = client.get(table, query)
        return rows if isinstance(rows, list) else []
    except Exception:
        if required:
            raise
        return []


def stable_id(*parts: Any) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join(map(str, parts))))


def calc_var(position: float, volatility: float | None) -> float:
    vol = 0.20 if volatility is None else abs(volatility)
    if vol > 1:
        vol /= 100.0
    return abs(position) * vol * 1.645


def assess(row: dict[str, Any], max_single: float, max_var: float) -> dict[str, Any]:
    proposed = num(row.get("final_position_size"), 0.0) or 0.0
    sizing_status = str(row.get("sizing_status") or "BLOCKED")
    recommendation = str(row.get("recommendation") or "REJECT")
    metrics = row.get("risk_metrics") or {}
    drawdown = num(metrics.get("max_drawdown")) if isinstance(metrics, dict) else None
    volatility = num(metrics.get("volatility")) if isinstance(metrics, dict) else None

    blockers: list[str] = []
    warnings: list[str] = []
    if sizing_status == "BLOCKED":
        blockers.append("POSITION_SIZING_BLOCKED")
    if recommendation == "REJECT":
        blockers.append("RECOMMENDATION_REJECT")

    approved = min(proposed, max_single)
    if proposed > max_single:
        warnings.append("CAPPED_BY_MAX_SINGLE_POSITION")

    dd_mult = 1.0
    if drawdown is None:
        dd_mult = 0.70
        warnings.append("MAX_DRAWDOWN_MISSING")
    elif abs(drawdown) >= 30:
        blockers.append("MAX_DRAWDOWN_CRITICAL")
        dd_mult = 0.0
    elif abs(drawdown) >= 20:
        dd_mult = 0.50
        warnings.append("MAX_DRAWDOWN_HIGH")
    elif abs(drawdown) >= 15:
        dd_mult = 0.75
        warnings.append("MAX_DRAWDOWN_ELEVATED")

    approved *= dd_mult
    position_var = calc_var(approved, volatility)
    if position_var > max_var and position_var > 0:
        approved *= max_var / position_var
        position_var = calc_var(approved, volatility)
        warnings.append("SCALED_BY_POSITION_VAR")

    if blockers:
        approved = 0.0
        decision = "BLOCK"
    elif approved <= 0:
        decision = "BLOCK"
    elif approved < proposed:
        decision = "SCALE_DOWN"
    else:
        decision = "APPROVE"

    return {
        "proposed_position_size": round(proposed, 6),
        "approved_position_size": round(approved, 6),
        "position_var": round(position_var, 6),
        "risk_decision": decision,
        "blockers": blockers,
        "warnings": warnings,
        "risk_metrics": {
            "max_drawdown": drawdown,
            "volatility": volatility,
            "drawdown_multiplier": round(dd_mult, 6),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="GPT Quant V9 Risk Manager v1.0")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--max-single-position", type=float, default=0.10)
    p.add_argument("--max-total-exposure", type=float, default=0.60)
    p.add_argument("--max-open-positions", type=int, default=10)
    p.add_argument("--daily-loss-limit", type=float, default=0.02)
    p.add_argument("--portfolio-drawdown-limit", type=float, default=0.10)
    p.add_argument("--max-var-per-position", type=float, default=0.02)
    args = p.parse_args()

    if not 0 < args.max_single_position <= 0.25:
        raise ValueError("max-single-position must be > 0 and <= 0.25")
    if not 0 < args.max_total_exposure <= 1.0:
        raise ValueError("max-total-exposure must be > 0 and <= 1.0")
    if not 1 <= args.max_open_positions <= 100:
        raise ValueError("max-open-positions must be between 1 and 100")

    client = SupabaseRestClient()
    sizing = read(client, "gpt_quant_v9_position_sizing_results", f"order=sizing_date.desc,rank_no.asc&limit={args.limit}", True)
    if not sizing:
        raise RuntimeError("No position sizing results found")

    states = read(client, "gpt_quant_v9_risk_portfolio_state", "order=state_date.desc&limit=1")
    state = states[0] if states else {}
    daily_pnl = num(state.get("daily_pnl"), 0.0) or 0.0
    portfolio_dd = num(state.get("portfolio_drawdown"), 0.0) or 0.0

    kill = False
    kill_reasons: list[str] = []
    if daily_pnl <= -abs(args.daily_loss_limit):
        kill = True
        kill_reasons.append("DAILY_LOSS_LIMIT_BREACHED")
    if portfolio_dd >= abs(args.portfolio_drawdown_limit):
        kill = True
        kill_reasons.append("PORTFOLIO_DRAWDOWN_LIMIT_BREACHED")

    results = []
    for row in sizing:
        r = assess(row, args.max_single_position, args.max_var_per_position)
        r.update({
            "sizing_result_id": row.get("id"),
            "ranking_id": row.get("ranking_id"),
            "source_version_no": row.get("source_version_no"),
            "rank_no": int(row.get("rank_no") or 999),
        })
        results.append(r)

    if kill:
        for r in results:
            r["approved_position_size"] = 0.0
            r["risk_decision"] = "KILL_SWITCH"
            r["blockers"] = list(dict.fromkeys(r["blockers"] + kill_reasons))

    active = sorted([r for r in results if r["approved_position_size"] > 0], key=lambda x: x["rank_no"])
    allowed = {r["sizing_result_id"] for r in active[: args.max_open_positions]}
    for r in results:
        if r["approved_position_size"] > 0 and r["sizing_result_id"] not in allowed:
            r["approved_position_size"] = 0.0
            r["risk_decision"] = "BLOCK"
            r["blockers"].append("MAX_OPEN_POSITIONS_EXCEEDED")

    total = sum(r["approved_position_size"] for r in results)
    exposure_scale = 1.0
    if total > args.max_total_exposure and total > 0:
        exposure_scale = args.max_total_exposure / total
        for r in results:
            if r["approved_position_size"] > 0:
                r["approved_position_size"] = round(r["approved_position_size"] * exposure_scale, 6)
                r["risk_decision"] = "SCALE_DOWN"
                r["warnings"].append("SCALED_BY_TOTAL_EXPOSURE")

    total = round(sum(r["approved_position_size"] for r in results), 6)
    total_var = round(sum(r["position_var"] for r in results), 6)

    for r in results:
        client.upsert("gpt_quant_v9_risk_decisions", {
            "id": stable_id("risk", RUN_DATE, r["sizing_result_id"]),
            "risk_date": RUN_DATE,
            "sizing_result_id": r["sizing_result_id"],
            "ranking_id": r["ranking_id"],
            "source_version_no": r["source_version_no"],
            "rank_no": r["rank_no"],
            "proposed_position_size": r["proposed_position_size"],
            "approved_position_size": r["approved_position_size"],
            "position_var": r["position_var"],
            "risk_decision": r["risk_decision"],
            "blockers": r["blockers"],
            "warnings": r["warnings"],
            "risk_metrics": r["risk_metrics"],
            "kill_switch_active": kill,
            "paper_only": True,
            "live_trading_enabled": False,
            "broker_submission_enabled": False,
            "engine_version": ENGINE_VERSION,
            "calculated_at": now(),
        }, "risk_date,sizing_result_id")

    client.upsert("gpt_quant_v9_risk_summaries", {
        "id": stable_id("risk-summary", RUN_DATE),
        "risk_date": RUN_DATE,
        "daily_pnl": daily_pnl,
        "portfolio_drawdown": portfolio_dd,
        "max_single_position": args.max_single_position,
        "max_total_exposure": args.max_total_exposure,
        "max_open_positions": args.max_open_positions,
        "daily_loss_limit": args.daily_loss_limit,
        "portfolio_drawdown_limit": args.portfolio_drawdown_limit,
        "max_var_per_position": args.max_var_per_position,
        "approved_total_exposure": total,
        "estimated_total_var": total_var,
        "approved_positions": sum(r["approved_position_size"] > 0 for r in results),
        "blocked_positions": sum(r["approved_position_size"] <= 0 for r in results),
        "kill_switch_active": kill,
        "kill_switch_reasons": kill_reasons,
        "exposure_scale": round(exposure_scale, 6),
        "paper_only": True,
        "live_trading_enabled": False,
        "broker_submission_enabled": False,
        "engine_version": ENGINE_VERSION,
        "calculated_at": now(),
    }, "risk_date")

    print(f"Risk Manager complete: total_exposure={total:.4%}, kill_switch={kill}")
    print("Paper only: true")
    print("Live trading: false")


if __name__ == "__main__":
    main()
