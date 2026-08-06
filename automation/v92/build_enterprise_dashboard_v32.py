from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def metric_map(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["metric"]: row
        for row in comparison.get("metrics", [])
        if "metric" in row
    }


def fmt(value: Any, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def status_icon(value: bool) -> str:
    return "✅" if value else "❌"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--wfa", type=Path, required=True)
    parser.add_argument("--monte-carlo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    score = load(args.score)
    comparison = load(args.comparison)
    wfa = load(args.wfa)
    monte = load(args.monte_carlo)
    manifest = load(args.manifest)
    metrics = metric_map(comparison)

    def v91(name: str) -> Any:
        return metrics.get(name, {}).get("v91")

    lines = [
        "# GPT Quant V9.2 Enterprise Research Dashboard v3.2",
        "",
        f"## Research Score: **{score['research_score']:.2f} / 100**",
        "",
        f"- Grade: **{score['grade']}**",
        f"- Production Readiness: **{score['production_readiness']}**",
        f"- Recommendation: **{score['recommendation']}**",
        f"- Evidence Source: `{manifest.get('source_type', 'unknown')}`",
        "",
        "## Gate Status",
        "",
        "| Gate | Status |",
        "|---|:---:|",
        f"| Regression | {status_icon(score['gates']['regression'])} |",
        f"| Walk-Forward | {status_icon(score['gates']['walk_forward'])} |",
        f"| Monte Carlo | {status_icon(score['gates']['monte_carlo'])} |",
        f"| Production Evidence | {status_icon(score['production_evidence'])} |",
        "",
        "## Performance",
        "",
        "| Metric | V9.1 |",
        "|---|---:|",
        f"| Total Return | {fmt(v91('total_return'), '%')} |",
        f"| Annual Return | {fmt(v91('annual_return'), '%')} |",
        f"| Sharpe | {fmt(v91('sharpe'), '', 3)} |",
        f"| Sortino | {fmt(v91('sortino'), '', 3)} |",
        f"| Profit Factor | {fmt(v91('profit_factor'), '', 3)} |",
        "",
        "## Risk & Robustness",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Max Drawdown | {fmt(v91('max_drawdown'), '%')} |",
        f"| WFA Pass Rate | {fmt(float(wfa.get('pass_rate', 0))*100, '%')} |",
        f"| Monte Carlo P95 Drawdown | {fmt(monte.get('p95_drawdown'), '%')} |",
        f"| Probability of Ruin | {fmt(float(monte.get('ruin_probability', 0))*100, '%')} |",
        "",
        "## Score Components",
        "",
        "| Component | Score |",
        "|---|---:|",
    ]

    for key, value in score["components"].items():
        lines.append(f"| {key.replace('_', ' ').title()} | {value:.2f} |")

    markdown = "\n".join(lines) + "\n"

    cards = [
        ("Research Score", f"{score['research_score']:.1f}/100"),
        ("Grade", score["grade"]),
        ("Readiness", score["production_readiness"]),
        ("Recommendation", score["recommendation"]),
        ("Sharpe", fmt(v91("sharpe"), "", 2)),
        ("Max Drawdown", fmt(v91("max_drawdown"), "%")),
        ("WFA Pass Rate", fmt(float(wfa.get("pass_rate", 0))*100, "%")),
        ("MC P95 Drawdown", fmt(monte.get("p95_drawdown"), "%")),
    ]

    html_cards = "".join(
        f"<div class='card'><div class='label'>{html.escape(label)}</div>"
        f"<div class='value'>{html.escape(value)}</div></div>"
        for label, value in cards
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPT Quant V9.2 Enterprise Research Dashboard v3.2</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f4f6f8;color:#202124}}
header{{padding:28px 32px;background:#111827;color:white}}
main{{padding:28px 32px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px}}
.card{{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 10px rgba(0,0,0,.08)}}
.label{{font-size:13px;color:#667085;text-transform:uppercase;letter-spacing:.04em}}
.value{{font-size:25px;font-weight:700;margin-top:9px;word-break:break-word}}
section{{background:white;margin-top:20px;padding:22px;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,.06)}}
pre{{white-space:pre-wrap;font-family:Arial,sans-serif;line-height:1.55}}
</style>
</head>
<body>
<header>
<h1>GPT Quant V9.2 Enterprise Research Dashboard v3.2</h1>
<p>Evidence source: {html.escape(str(manifest.get('source_type', 'unknown')))}</p>
</header>
<main>
<div class="grid">{html_cards}</div>
<section><pre>{html.escape(markdown)}</pre></section>
</main>
</body>
</html>"""

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "enterprise_research_dashboard.md").write_text(
        markdown,
        encoding="utf-8",
    )
    (args.output_dir / "enterprise_research_dashboard.html").write_text(
        html_doc,
        encoding="utf-8",
    )
    (args.output_dir / "enterprise_research_dashboard.json").write_text(
        json.dumps({
            "score": score,
            "comparison": comparison,
            "walk_forward": wfa,
            "monte_carlo": monte,
            "manifest": manifest,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "w", encoding="utf-8") as handle:
            handle.write(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
