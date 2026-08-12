#!/usr/bin/env python3
"""GPT Quant V9.2 Phase 2.5 - retry-safe orchestrator hotfix."""
import json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LOG_DIR=ROOT/"phase25_logs"; LOG_DIR.mkdir(parents=True,exist_ok=True)
URL=os.environ["SUPABASE_URL"].rstrip("/")
KEY=os.environ["SUPABASE_SERVICE_ROLE_KEY"]
VERSION=os.getenv("PAPER_STRATEGY_VERSION","V9.1")
MODE=os.getenv("PAPER_TRADING_MODE","SHADOW_ONLY_NO_BROKER")
FAIL_CLOSED=os.getenv("PHASE25_FAIL_CLOSED","true").lower()=="true"
RUN_DATE=datetime.now(timezone.utc).astimezone().date().isoformat()
RUN_KEY=f"{RUN_DATE}-{VERSION}"
PHASES=[
("2.2","Market Data Ingestion",ROOT/"automation/v92/paper_trading_phase22_market_ingestion.py"),
("2.1","Signal Generation",ROOT/"automation/v92/paper_trading_phase21_signal_engine.py"),
("2.3","Automatic Signal Execution",ROOT/"automation/v92/paper_trading_phase23_signal_execution.py"),
("2.4","Automatic Position Management",ROOT/"automation/v92/paper_trading_phase24_position_management.py"),
]

def now(): return datetime.now(timezone.utc).isoformat()

def rest(method,table,query="",payload=None,prefer=None):
    u=f"{URL}/rest/v1/{table}"+(("?"+query) if query else "")
    h={"apikey":KEY,"Authorization":f"Bearer {KEY}","Content-Type":"application/json","Accept":"application/json"}
    if prefer: h["Prefer"]=prefer
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(u,data=data,headers=h,method=method)
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        body=e.read().decode(errors="replace")
        raise RuntimeError(f"Supabase {method} {table}: HTTP {e.code}: {body}") from e

def existing():
    q=urllib.parse.urlencode({"run_key":f"eq.{RUN_KEY}","select":"*","limit":"1"})
    rows=rest("GET","gptq_paper_orchestrator_runs",q)
    return rows[0] if rows else None

def patch(payload):
    q=urllib.parse.urlencode({"run_key":f"eq.{RUN_KEY}"})
    return rest("PATCH","gptq_paper_orchestrator_runs",q,payload,"return=representation")

def start_run():
    p={"run_key":RUN_KEY,"strategy_version":VERSION,"mode":MODE,"status":"RUNNING",
       "pipeline_status":"STARTING","result":{},"started_at":now(),"finished_at":None}
    old=existing()
    if old:
        print(f"[Phase 2.5] Existing run {RUN_KEY}; reusing it safely.")
        rows=patch(p); return rows[0] if rows else old
    try:
        rows=rest("POST","gptq_paper_orchestrator_runs",payload=p,prefer="return=representation")
        return rows[0] if rows else p
    except RuntimeError as e:
        if "409" not in str(e): raise
        old=existing()
        if not old: raise
        print(f"[Phase 2.5] 409 recovered for {RUN_KEY}.")
        rows=patch(p); return rows[0] if rows else old

def update(**fields):
    patch(fields)

def run_phase(phase,name,script):
    logfile=LOG_DIR/f"phase{phase.replace('.','_')}.log"
    t=time.time()
    if not script.exists():
        return {"phase":phase,"name":name,"status":"FAIL","exit_code":127,
                "duration_seconds":0,"log":str(logfile.relative_to(ROOT)),
                "error":f"Missing script: {script}"}
    p=subprocess.run([sys.executable,str(script)],cwd=ROOT,env=os.environ.copy(),
                     text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    out=p.stdout or ""; logfile.write_text(out,encoding="utf-8")
    if out: print(out,end="" if out.endswith("\n") else "\n")
    return {"phase":phase,"name":name,"status":"PASS" if p.returncode==0 else "FAIL",
            "exit_code":p.returncode,"duration_seconds":round(time.time()-t,2),
            "log":str(logfile.relative_to(ROOT))}

def outputs(r):
    (ROOT/"phase25_result.json").write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# GPT Quant V9.2 Paper Trading Phase 2.5","",
           f"- run_key: `{r['run_key']}`",f"- mode: `{r['mode']}`",
           f"- strategy_version: `{r['strategy_version']}`",f"- status: **{r['status']}**",
           f"- pipeline: **{r['pipeline']}**","","## Pipeline","",
           "| Phase | Component | Status | Exit code | Seconds |","|---|---|---:|---:|---:|"]
    for p in r["phases"]:
        lines.append(f"| {p['phase']} | {p['name']} | {p['status']} | {p['exit_code']} | {p['duration_seconds']} |")
    if r.get("error"): lines += ["","## Error","",f"`{r['error']}`"]
    (ROOT/"phase25_summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    start_run()
    r={"run_key":RUN_KEY,"started_at":now(),"mode":MODE,"strategy_version":VERSION,
       "status":"RUNNING","pipeline":"RUNNING","phases":[]}
    try:
        for phase,name,script in PHASES:
            print(f"=== Phase {phase}: {name} ===")
            update(status="RUNNING",pipeline_status=f"PHASE_{phase}_RUNNING",result=r)
            x=run_phase(phase,name,script); r["phases"].append(x)
            if x["status"]!="PASS" and FAIL_CLOSED:
                r["status"]="FAILED"; r["pipeline"]="BLOCKED"
                r["error"]=f"Phase {phase} failed; downstream trading blocked"; break
        if r["status"]=="RUNNING": r["status"]="COMPLETED"; r["pipeline"]="COMPLETED"
    except Exception as e:
        r["status"]="FAILED"; r["pipeline"]="BLOCKED"; r["error"]=f"{type(e).__name__}: {e}"
    r["finished_at"]=now(); outputs(r)
    try:
        update(status=r["status"],pipeline_status=r["pipeline"],result=r,finished_at=r["finished_at"])
    except Exception as e:
        print(f"::error::Finalize failed: {e}"); r["status"]="FAILED"; r["pipeline"]="BLOCKED"; outputs(r)
    print(json.dumps(r,ensure_ascii=False,indent=2))
    return 0 if r["status"]=="COMPLETED" else 1

if __name__=="__main__": raise SystemExit(main())
