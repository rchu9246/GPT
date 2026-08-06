from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


def read_equity(path: Path) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append((row["timestamp"], float(row["equity"])))
    if len(rows) < 4:
        raise ValueError("Equity curve requires at least 4 rows")
    return rows


def max_drawdown(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        dd = (value / peak - 1.0) * 100.0
        worst = min(worst, dd)
    return worst


def sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    sigma = pstdev(returns)
    if sigma == 0:
        return 0.0
    return mean(returns) / sigma * (len(returns) ** 0.5)


def analyze_window(values: list[float]) -> dict[str, float]:
    returns = [
        values[i] / values[i - 1] - 1.0
        for i in range(1, len(values))
        if values[i - 1] != 0
    ]
    total_return = (values[-1] / values[0] - 1.0) * 100.0
    return {
        "total_return": total_return,
        "max_drawdown": max_drawdown(values),
        "sharpe": sharpe(returns),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--equity", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--windows", type=int, default=5)
    parser.add_argument("--min-pass-rate", type=float, default=0.60)
    args = parser.parse_args()

    curve = read_equity(args.equity)
    values = [value for _, value in curve]
    windows = max(2, min(args.windows, len(values) // 2))
    size = max(2, len(values) // windows)

    results: list[dict[str, Any]] = []
    for index in range(windows):
        start = index * size
        end = len(values) if index == windows - 1 else min(len(values), start + size + 1)
        if end - start < 2:
            continue
        metrics = analyze_window(values[start:end])
        metrics.update({
            "window": index + 1,
            "start": curve[start][0],
            "end": curve[end - 1][0],
            "passed": metrics["total_return"] > 0 and metrics["max_drawdown"] > -25,
        })
        results.append(metrics)

    pass_rate = (
        sum(1 for item in results if item["passed"]) / len(results)
        if results else 0.0
    )
    passed = pass_rate >= args.min_pass_rate

    payload = {
        "passed": passed,
        "pass_rate": pass_rate,
        "minimum_pass_rate": args.min_pass_rate,
        "windows": results,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "walk_forward.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Walk-Forward Analysis",
        "",
        f"**Result:** {'PASS ✅' if passed else 'FAIL ❌'}",
        "",
        f"- Pass rate: `{pass_rate:.2%}`",
        f"- Minimum required: `{args.min_pass_rate:.2%}`",
        "",
        "| Window | Return | Max DD | Sharpe | Pass |",
        "|---:|---:|---:|---:|:---:|",
    ]
    for item in results:
        lines.append(
            f'| {item["window"]} | {item["total_return"]:.2f}% | '
            f'{item["max_drawdown"]:.2f}% | {item["sharpe"]:.3f} | '
            f'{"✅" if item["passed"] else "❌"} |'
        )
    (args.output_dir / "walk_forward.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
