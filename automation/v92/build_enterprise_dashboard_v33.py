from __future__ import annotations

import argparse
import csv
import html
import json
import os
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_equity(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {"timestamp": row["timestamp"], "equity": float(row["equity"])}
            for row in csv.DictReader(handle)
        ]


def drawdown_series(equity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    peak = None
    output: list[dict[str, Any]] = []
    for row in equity:
        value = float(row["equity"])
        peak = value if peak is None else max(peak, value)
        dd = 0.0 if not peak else (value / peak - 1.0) * 100.0
        output.append({"timestamp": row["timestamp"], "drawdown": dd})
    return output


def metrics_by_name(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["metric"]: row
        for row in comparison.get("metrics", [])
        if row.get("metric")
    }


def fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def icon(value: bool) -> str:
    return "✅" if value else "❌"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--wfa", type=Path, required=True)
    parser.add_argument("--monte-carlo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--equity", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    score = load(args.score)
    comparison = load(args.comparison)
    wfa = load(args.wfa)
    mc = load(args.monte_carlo)
    manifest = load(args.manifest)
    metrics = metrics_by_name(comparison)
    equity = read_equity(args.equity)
    drawdowns = drawdown_series(equity)

    def current(name: str) -> Any:
        return metrics.get(name, {}).get("v91")

    def delta(name: str) -> Any:
        return metrics.get(name, {}).get("delta")

    lines = [
        "# GPT Quant V9.2 Enterprise Dashboard v3.3",
        "",
        f"## Research Score: **{score['research_score']:.2f} / 100** · Grade **{score['grade']}**",
        "",
        f"**Production Readiness:** `{score['production_readiness']}`  ",
        f"**Recommendation:** {score['recommendation']}  ",
        f"**Evidence:** `{score['source_type']}`  ",
        "",
        "## Executive Decision",
        "",
        f"> {score['rationale']}",
        "",
        "## Gate Status",
        "",
        "| Gate | Status |",
        "|---|:---:|",
        f"| Regression | {icon(score['gates']['regression'])} |",
        f"| Walk-Forward | {icon(score['gates']['walk_forward'])} |",
        f"| Monte Carlo | {icon(score['gates']['monte_carlo'])} |",
        f"| Production Evidence | {icon(score['production_evidence'])} |",
        "",
        "## Performance",
        "",
        "| Metric | V9.1 | Δ vs V9 |",
        "|---|---:|---:|",
        f"| Total Return | {fmt(current('total_return'), 2, '%')} | {fmt(delta('total_return'), 2, '%')} |",
        f"| Annual Return | {fmt(current('annual_return'), 2, '%')} | {fmt(delta('annual_return'), 2, '%')} |",
        f"| Sharpe | {fmt(current('sharpe'), 3)} | {fmt(delta('sharpe'), 3)} |",
        f"| Sortino | {fmt(current('sortino'), 3)} | {fmt(delta('sortino'), 3)} |",
        f"| Profit Factor | {fmt(current('profit_factor'), 3)} | {fmt(delta('profit_factor'), 3)} |",
        "",
        "## Risk & Robustness",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Max Drawdown | {fmt(current('max_drawdown'), 2, '%')} |",
        f"| Volatility | {fmt(current('volatility'), 2, '%')} |",
        f"| WFA Pass Rate | {fmt(float(wfa.get('pass_rate', 0))*100, 2, '%')} |",
        f"| Monte Carlo P95 Drawdown | {fmt(mc.get('p95_drawdown'), 2, '%')} |",
        f"| Probability of Ruin | {fmt(float(mc.get('ruin_probability', 0))*100, 2, '%')} |",
        "",
        "## Research Score Components",
        "",
        "| Component | Score |",
        "|---|---:|",
    ]
    for key, value in score["components"].items():
        lines.append(f"| {key.replace('_', ' ').title()} | {value:.2f} |")

    markdown = "\n".join(lines) + "\n"

    chart_payload = {
        "equity": equity,
        "drawdown": drawdowns,
        "components": score["components"],
    }

    cards = [
        ("Research Score", f"{score['research_score']:.1f}/100"),
        ("Grade", score["grade"]),
        ("Readiness", score["production_readiness"]),
        ("Recommendation", score["recommendation"]),
        ("Sharpe", fmt(current("sharpe"), 2)),
        ("Max Drawdown", fmt(current("max_drawdown"), 2, "%")),
        ("WFA Pass Rate", fmt(float(wfa.get("pass_rate", 0))*100, 1, "%")),
        ("MC P95 Drawdown", fmt(mc.get("p95_drawdown"), 2, "%")),
    ]
    card_html = "".join(
        f"<div class='card'><div class='label'>{html.escape(label)}</div>"
        f"<div class='value'>{html.escape(str(value))}</div></div>"
        for label, value in cards
    )

    gate_html = "".join(
        f"<div class='gate'><span>{html.escape(name.replace('_',' ').title())}</span>"
        f"<strong>{'PASS' if value else 'FAIL'}</strong></div>"
        for name, value in {
            **score["gates"],
            "production_evidence": score["production_evidence"],
        }.items()
    )

    chart_json = json.dumps(chart_payload, ensure_ascii=False)
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPT Quant V9.2 Enterprise Dashboard v3.3</title>
<style>
:root{{--bg:#0b1020;--panel:#151b2f;--text:#edf2f7;--muted:#97a3b6;--accent:#65a3ff;--good:#30c48d;--bad:#f97066}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,Arial,sans-serif;background:var(--bg);color:var(--text)}}
header{{padding:30px 34px;border-bottom:1px solid #26304a;background:linear-gradient(135deg,#11182c,#182441)}}
header h1{{margin:0 0 8px;font-size:28px}}
header p{{margin:0;color:var(--muted)}}
main{{padding:26px 34px 50px;max-width:1500px;margin:auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}}
.card,.section{{background:var(--panel);border:1px solid #26304a;border-radius:14px;box-shadow:0 8px 24px rgba(0,0,0,.18)}}
.card{{padding:18px}}
.label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.value{{font-size:24px;font-weight:750;margin-top:8px;word-break:break-word}}
.section{{margin-top:18px;padding:22px}}
.section h2{{margin-top:0}}
.gates{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}}
.gate{{display:flex;justify-content:space-between;padding:13px 15px;border-radius:10px;background:#10162a}}
.gate strong{{color:var(--good)}}
canvas{{width:100%;height:280px;background:#10162a;border-radius:10px}}
pre{{white-space:pre-wrap;line-height:1.55;color:#dce5f2}}
.badge{{display:inline-block;padding:7px 11px;border-radius:999px;background:#22345d;color:#bcd6ff;font-weight:700}}
</style>
</head>
<body>
<header>
<h1>GPT Quant V9.2 Enterprise Dashboard v3.3</h1>
<p>Evidence source: {html.escape(str(score['source_type']))} · <span class="badge">{html.escape(score['production_readiness'])}</span></p>
</header>
<main>
<div class="grid">{card_html}</div>
<div class="section"><h2>Research Gates</h2><div class="gates">{gate_html}</div></div>
<div class="section"><h2>Equity Curve</h2><canvas id="equity"></canvas></div>
<div class="section"><h2>Drawdown Curve</h2><canvas id="drawdown"></canvas></div>
<div class="section"><h2>Executive Report</h2><pre>{html.escape(markdown)}</pre></div>
</main>
<script>
const payload={chart_json};
function drawLine(canvasId, rows, key, stroke){{
 const c=document.getElementById(canvasId),ctx=c.getContext('2d');
 c.width=c.clientWidth*devicePixelRatio;c.height=c.clientHeight*devicePixelRatio;
 ctx.scale(devicePixelRatio,devicePixelRatio);
 const w=c.clientWidth,h=c.clientHeight,p=28;
 const vals=rows.map(r=>Number(r[key]));
 const min=Math.min(...vals),max=Math.max(...vals),range=(max-min)||1;
 ctx.strokeStyle='#34405f';ctx.lineWidth=1;
 for(let i=0;i<5;i++){{let y=p+(h-2*p)*i/4;ctx.beginPath();ctx.moveTo(p,y);ctx.lineTo(w-p,y);ctx.stroke();}}
 ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.beginPath();
 vals.forEach((v,i)=>{{const x=p+(w-2*p)*(i/Math.max(vals.length-1,1));const y=h-p-(h-2*p)*((v-min)/range);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}});
 ctx.stroke();
}}
drawLine('equity',payload.equity,'equity','#65a3ff');
drawLine('drawdown',payload.drawdown,'drawdown','#f97066');
</script>
</body>
</html>"""

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "enterprise_dashboard_v33.md").write_text(markdown, encoding="utf-8")
    (args.output_dir / "enterprise_dashboard_v33.html").write_text(html_doc, encoding="utf-8")
    (args.output_dir / "enterprise_dashboard_v33.json").write_text(
        json.dumps({
            "score": score,
            "comparison": comparison,
            "walk_forward": wfa,
            "monte_carlo": mc,
            "manifest": manifest,
            "charts": chart_payload,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
