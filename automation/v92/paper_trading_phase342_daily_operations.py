import json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
MODE="SHADOW_ONLY_NO_BROKER"
STRATEGY=os.getenv("PAPER_STRATEGY_VERSION","V9.1")
OUT=ROOT/"phase342_output"; OUT.mkdir(exist_ok=True)
p341=ROOT/"automation/v92/paper_trading_phase341_daily_qualification.py"
p34=ROOT/"automation/v92/paper_trading_phase34_human_approval_release.py"
def call(cmd,env):
 p=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
 print(p.stdout); print(p.stderr,file=sys.stderr)
 return p
def main():
 if MODE!="SHADOW_ONLY_NO_BROKER": raise RuntimeError("Safety lock")
 if not p341.exists() or not p34.exists(): raise RuntimeError("Missing Phase 3.4/3.4.1 engine")
 env=os.environ.copy(); env["STRATEGY_VERSION"]=STRATEGY
 env["PAPER_STRATEGY_VERSION"]=STRATEGY; env["PAPER_TRADING_MODE"]=MODE
 if call([sys.executable,str(p341)],env).returncode: raise RuntimeError("3.4.1 failed")
 ok=False
 for cmd in ([sys.executable,str(p34),"--action","evaluate","--strategy-version",STRATEGY],
             [sys.executable,str(p34),"evaluate"],[sys.executable,str(p34)]):
  r=call(cmd,env)
  if r.returncode==0: ok=True; break
  s=((r.stdout or "")+(r.stderr or "")).lower()
  if not any(x in s for x in ("unrecognized arguments","usage:","invalid choice")): break
 if not ok: raise RuntimeError("3.4 evaluation failed")
 d={"phase":"3.4.2","status":"PASS","strategy_version":STRATEGY,"mode":MODE,
    "human_approval_required":True,"automatic_approval":False,
    "broker_execution_enabled":False,"real_money_enabled":False,
    "completed_at":datetime.now(timezone.utc).isoformat()}
 (OUT/"daily_operations.json").write_text(json.dumps(d,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(d,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())