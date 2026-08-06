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


def metric_map(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("metric")): row
        for row in comparison.get("metrics", [])
        if row.get("metric")
    }


def metric(metrics: dict[str, dict[str, Any]], name: str) -> float | None:
    value = metrics.get(name, {}).get("v91")
    return None if value is None else float(value)


def linear_score(value: float | None, target: float, weight: float) -> float:
    if value is None or target <= 0:
        return 0.0
    return clamp(value / target * weight, 0.0, weight)


def drawdown_score(value: float | None, weight: float = 20.0) -> float:
    if value is None:
        return 0.0
    magnitude = abs(value)
    if magnitude <= 8:
        return weight
    if magnitude >= 25:
        return 0.0
    return clamp((25.0 - magnitude) / 17.0 * weight, 0.0, weight)


def monte_carlo_score(mc: dict[str, Any], weight: float = 10.0) -> float:
    ruin = float(mc.get("ruin_probability", 1.0))
    p95 = float(mc.get("p95_drawdown", 100.0))
    if ruin > 0:
        return 0.0
    if p95 <= 10:
        return weight
    if p95 >= 30:
        return 0.0
    return clamp((30.0 - p95) / 20.0 * weight, 0.0, weight)


def classify(score: float, production: bool, gates_pass: bool) -> tuple[str, str, str]:
    if not production:
        return (
            "VALIDATION_ONLY",
            "Continue integration validation",
            "Smoke evidence cannot authorize deployment",
        )
    if not gates_pass:
        return (
            "BLOCKED",
            "Continue optimization",
            "One or more research gates failed",
        )
    if score >= 90:
        return (
            "READY_FOR_PAPER_TRADING",
            "Deploy to paper trading",
            "All research gates passed with production evidence",
        )
    if score >= 80:
        return (
            "RESEARCH_CONTINUE",
            "Continue research validation",
            "Research quality is acceptable but below deployment threshold",
        )
    return (
        "REJECT",
        "Reject current candidate",
        "Research score is below minimum threshold",
    )


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
    mc = load(args.monte_carlo)
    manifest = load(args.manifest)
    metrics = metric_map(comparison)

    components = {
        "sharpe": linear_score(metric(metrics, "sharpe"), 2.0, 25.0),
        "sortino": linear_score(metric(metrics, "sortino"), 3.0, 15.0),
        "drawdown": drawdown_score(metric(metrics, "max_drawdown"), 20.0),
        "profit_factor": linear_score(
            None if metric(metrics, "profit_factor") is None
            else max(metric(metrics, "profit_factor") - 1.0, 0.0),
            1.0,
            15.0,
        ),
        "walk_forward": clamp(float(wfa.get("pass_rate", 0.0)) * 15.0, 0.0, 15.0),
        "monte_carlo": monte_carlo_score(mc, 10.0),
    }

    total = round(sum(components.values()), 2)
    gates = {
        "regression": bool(comparison.get("passed")),
        "walk_forward": bool(wfa.get("passed")),
        "monte_carlo": bool(mc.get("passed")),
    }
    production = bool(manifest.get("production_evidence"))
    readiness, recommendation, rationale = classify(
        total,
        production,
        all(gates.values()),
    )

    payload = {
        "dashboard_version": "3.3",
        "research_score": total,
        "grade": (
            "A+" if total >= 95
            else "A" if total >= 90
            else "B" if total >= 80
            else "C" if total >= 70
            else "D"
        ),
        "production_readiness": readiness,
        "recommendation": recommendation,
        "rationale": rationale,
        "production_evidence": production,
        "source_type": manifest.get("source_type", "unknown"),
        "gates": gates,
        "components": {key: round(value, 2) for key, value in components.items()},
        "confidence_pct": round(total, 2),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
