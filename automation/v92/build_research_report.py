from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--wfa", type=Path, required=True)
    parser.add_argument("--monte-carlo", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    comparison = load(args.comparison)
    wfa = load(args.wfa)
    monte = load(args.monte_carlo)
    policy = load(args.policy)

    checks = {
        "comparison": bool(comparison.get("passed")),
        "walk_forward": bool(wfa.get("passed")),
        "monte_carlo": bool(monte.get("passed")),
    }
    passed = all(checks.values())

    payload = {
        "passed": passed,
        "checks": checks,
        "comparison": comparison,
        "walk_forward": wfa,
        "monte_carlo": monte,
        "policy": policy,
    }

    lines = [
        "# GPT Quant V9.2 Production Research Report",
        "",
        f"**Production Research Gate:** {'PASS ✅' if passed else 'FAIL ❌'}",
        "",
        "| Gate | Status |",
        "|---|:---:|",
        f"| V9 vs V9.1 Regression | {'✅' if checks['comparison'] else '❌'} |",
        f"| Walk-Forward Analysis | {'✅' if checks['walk_forward'] else '❌'} |",
        f"| Monte Carlo Robustness | {'✅' if checks['monte_carlo'] else '❌'} |",
        "",
        "## Key research metrics",
        "",
        f"- WFA pass rate: `{wfa.get('pass_rate', 0):.2%}`",
        f"- Monte Carlo P95 drawdown: `{monte.get('p95_drawdown', 0):.2f}%`",
        f"- Monte Carlo probability of ruin: `{monte.get('ruin_probability', 0):.2%}`",
        "",
    ]

    markdown = "\n".join(lines)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "production_research_report.md").write_text(
        markdown + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "production_research_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "production_research_report.html").write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font-family:Arial;margin:32px}pre{white-space:pre-wrap}</style>"
        "</head><body><pre>"
        + html.escape(markdown)
        + "</pre></body></html>",
        encoding="utf-8",
    )

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
