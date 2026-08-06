from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def metric_value(comparison: dict[str, Any], metric: str) -> float | None:
    for row in comparison.get("metrics", []):
        if row.get("metric") == metric:
            value = row.get("v91")
            return None if value is None else float(value)
    return None


def score_sharpe(value: float | None) -> float:
    if value is None:
        return 0.0
    return clamp(value / 2.0 * 25.0, 0.0, 25.0)


def score_sortino(value: float | None) -> float:
    if value is None:
        return 0.0
    return clamp(value / 3.0 * 15.0, 0.0, 15.0)


def score_drawdown(value: float | None) -> float:
    if value is None:
        return 0.0
    magnitude = abs(value)
    if magnitude <= 8:
        return 20.0
    if magnitude >= 25:
        return 0.0
    return clamp((25.0 - magnitude) / 17.0 * 20.0, 0.0, 20.0)


def score_profit_factor(value: float | None) -> float:
    if value is None:
        return 0.0
    if value <= 1.0:
        return 0.0
    return clamp((value - 1.0) / 1.0 * 15.0, 0.0, 15.0)


def score_wfa(wfa: dict[str, Any]) -> float:
    return clamp(float(wfa.get("pass_rate", 0.0)) * 15.0, 0.0, 15.0)


def score_monte_carlo(mc: dict[str, Any]) -> float:
    p95 = float(mc.get("p95_drawdown", 100.0))
    ruin = float(mc.get("ruin_probability", 1.0))
    if ruin > 0:
        return 0.0
    if p95 <= 10:
        return 10.0
    if p95 >= 30:
        return 0.0
    return clamp((30.0 - p95) / 20.0 * 10.0, 0.0, 10.0)


def readiness(score: float, production_evidence: bool, all_gates: bool) -> tuple[str, str]:
    if not production_evidence:
        return "VALIDATION_ONLY", "Continue integration validation"
    if not all_gates:
        return "BLOCKED", "Continue optimization"
    if score >= 90:
        return "READY_FOR_PAPER_TRADING", "Deploy to paper trading"
    if score >= 80:
        return "RESEARCH_CONTINUE", "Continue research validation"
    return "REJECT", "Reject current candidate"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--wfa", type=Path, required=True)
    parser.add_argument("--monte-carlo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    comparison = load(args.comparison)
    wfa = load(args.wfa)
    monte = load(args.monte_carlo)
    manifest = load(args.manifest)

    components = {
        "sharpe": score_sharpe(metric_value(comparison, "sharpe")),
        "sortino": score_sortino(metric_value(comparison, "sortino")),
        "drawdown": score_drawdown(metric_value(comparison, "max_drawdown")),
        "profit_factor": score_profit_factor(
            metric_value(comparison, "profit_factor")
        ),
        "walk_forward": score_wfa(wfa),
        "monte_carlo": score_monte_carlo(monte),
    }

    total = round(sum(components.values()), 2)
    production_evidence = bool(manifest.get("production_evidence"))
    gates = {
        "regression": bool(comparison.get("passed")),
        "walk_forward": bool(wfa.get("passed")),
        "monte_carlo": bool(monte.get("passed")),
    }
    all_gates = all(gates.values())
    state, recommendation = readiness(
        total,
        production_evidence,
        all_gates,
    )

    payload = {
        "research_score": total,
        "grade": (
            "A+" if total >= 95
            else "A" if total >= 90
            else "B" if total >= 80
            else "C" if total >= 70
            else "D"
        ),
        "production_readiness": state,
        "recommendation": recommendation,
        "production_evidence": production_evidence,
        "gates": gates,
        "components": components,
        "confidence": round(total / 100.0, 4),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
