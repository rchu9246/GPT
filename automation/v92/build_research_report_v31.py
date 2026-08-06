from __future__ import annotations
import argparse,html,json,os
from pathlib import Path

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True); p.add_argument("--comparison",required=True)
    p.add_argument("--wfa",required=True); p.add_argument("--monte-carlo",required=True)
    p.add_argument("--output-dir",type=Path,required=True); a=p.parse_args()
    manifest,comparison,wfa,mc=map(load,[a.manifest,a.comparison,a.wfa,a.monte_carlo])
    checks={"comparison":bool(comparison.get("passed")),"walk_forward":bool(wfa.get("passed")),"monte_carlo":bool(mc.get("passed"))}
    production=bool(manifest.get("production_evidence"))
    passed=all(checks.values()) and production
    status="PASS ✅" if passed else ("VALIDATION ONLY ⚠️" if all(checks.values()) else "FAIL ❌")
    payload={"passed":passed,"status":status,"production_evidence":production,"source_type":manifest.get("source_type"),"checks":checks,"manifest":manifest,"comparison":comparison,"walk_forward":wfa,"monte_carlo":mc}
    md="\n".join([
      "# GPT Quant V9.2 Production Research Pipeline v3.1","",
      f"**Production Research Gate:** {status}","",
      f"- Evidence source: `{manifest.get('source_type')}`",
      f"- Production evidence: `{production}`",
      f"- WFA pass rate: `{wfa.get('pass_rate',0):.2%}`",
      f"- Monte Carlo P95 drawdown: `{mc.get('p95_drawdown',0):.2f}%`",
      f"- Probability of ruin: `{mc.get('ruin_probability',0):.2%}`","",
      "> Synthetic smoke evidence validates the pipeline only and can never approve production release." if not production else ""
    ])
    a.output_dir.mkdir(parents=True,exist_ok=True)
    (a.output_dir/"production_research_report.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    (a.output_dir/"production_research_report.md").write_text(md+"\n",encoding="utf-8")
    (a.output_dir/"production_research_report.html").write_text("<html><body><pre>"+html.escape(md)+"</pre></body></html>",encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write(md+"\n")
    return 0
if __name__=="__main__": raise SystemExit(main())
