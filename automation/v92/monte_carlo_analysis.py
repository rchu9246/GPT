from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from statistics import mean


def read_pnl(path: Path) -> list[float]:
    values: list[float] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            values.append(float(row["pnl"]))
    if not values:
        raise ValueError("Trades CSV contains no rows")
    return values


def drawdown(equity: list[float]) -> float:
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak != 0:
            worst = min(worst, (value / peak - 1.0) * 100.0)
    return worst


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--starting-equity", type=float, default=1_000_000.0)
    parser.add_argument("--max-p95-drawdown", type=float, default=25.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    pnl = read_pnl(args.trades)

    final_returns: list[float] = []
    max_drawdowns: list[float] = []
    ruin_count = 0

    for _ in range(args.iterations):
        sample = [rng.choice(pnl) for _ in pnl]
        equity = [args.starting_equity]
        for value in sample:
            equity.append(equity[-1] + value)
        final_return = (equity[-1] / args.starting_equity - 1.0) * 100.0
        dd = drawdown(equity)
        final_returns.append(final_return)
        max_drawdowns.append(abs(dd))
        if min(equity) <= 0:
            ruin_count += 1

    p95_dd = percentile(max_drawdowns, 0.95)
    ruin_probability = ruin_count / args.iterations
    passed = p95_dd <= args.max_p95_drawdown and ruin_probability == 0.0

    payload = {
        "passed": passed,
        "iterations": args.iterations,
        "mean_return": mean(final_returns),
        "median_return": percentile(final_returns, 0.50),
        "p05_return": percentile(final_returns, 0.05),
        "p95_drawdown": p95_dd,
        "ruin_probability": ruin_probability,
        "max_allowed_p95_drawdown": args.max_p95_drawdown,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "monte_carlo.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = "\n".join([
        "# Monte Carlo Robustness",
        "",
        f"**Result:** {'PASS ✅' if passed else 'FAIL ❌'}",
        "",
        f"- Iterations: `{args.iterations}`",
        f"- Mean return: `{payload['mean_return']:.2f}%`",
        f"- Median return: `{payload['median_return']:.2f}%`",
        f"- 5th percentile return: `{payload['p05_return']:.2f}%`",
        f"- 95th percentile drawdown: `{p95_dd:.2f}%`",
        f"- Probability of ruin: `{ruin_probability:.2%}`",
        "",
    ])
    (args.output_dir / "monte_carlo.md").write_text(md, encoding="utf-8")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
