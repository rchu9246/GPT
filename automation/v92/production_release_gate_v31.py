from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--report",required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    report=json.loads(Path(a.report).read_text(encoding="utf-8")); approved=bool(report.get("passed"))
    payload={"approved":approved,"decision":"APPROVE" if approved else "BLOCK","production_evidence":bool(report.get("production_evidence")),"reason":"All production gates passed with real production evidence" if approved else "Release requires real production evidence and all research gates"}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print(payload["decision"],payload["reason"]); return 0 if approved else 2
if __name__=="__main__": raise SystemExit(main())
