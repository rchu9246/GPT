from __future__ import annotations
import json, os
from datetime import date, datetime, timezone
from pathlib import Path
import requests

TIMEOUT = 60
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
RUN_DATE = os.getenv("RUN_DATE", str(date.today())).strip()
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip()

INITIAL_CAPITAL = float(os.getenv("PAPER_INITIAL_CAPITAL", "1000000"))
POSITION_SIZE = float(os.getenv("PAPER_POSITION_SIZE", "0.10"))
MAX_SINGLE_POSITION = float(os.getenv("PAPER_MAX_SINGLE_POSITION", "0.15"))
MAX_GROSS_EXPOSURE = float(os.getenv("PAPER_MAX_GROSS_EXPOSURE", "0.80"))
MAX_OPEN_POSITIONS = int(os.getenv("PAPER_MAX_OPEN_POSITIONS", "10"))
MAX_NEW_ORDERS = int(os.getenv("PAPER_MAX_NEW_ORDERS", "5"))
MIN_SIGNAL_SCORE = float(os.getenv("PAPER_SCORE_THRESHOLD", "65"))
SLIPPAGE_RATE = float(os.getenv("PAPER_SLIPPAGE_RATE", "0.001"))
COMMISSION_RATE = float(os.getenv("PAPER_COMMISSION_RATE", "0.001425"))
STOP_LOSS = float(os.getenv("PAPER_STOP_LOSS", "0.05"))
TAKE_PROFIT = float(os.getenv("PAPER_TAKE_PROFIT", "0.10"))

ARTIFACT_DIR = Path("artifacts/paper_trading_phase23")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers.update({
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
})

def u(t): return f"{SUPABASE_URL}/rest/v1/{t}"
def check(r,c):
    if not r.ok: raise RuntimeError(f"{c}: HTTP {r.status_code}: {r.text[:1500]}")
def fetch_all(t,p):
    r=s.get(u(t),params=p,timeout=TIMEOUT); check(r,f"fetch {t}"); return r.json()
def insert(t,p):
    r=s.post(u(t),headers={"Prefer":"return=representation"},json=p,timeout=TIMEOUT); check(r,f"insert {t}")
    x=r.json(); return x[0] if x else p
def upsert(t,p,c):
    r=s.post(u(t),params={"on_conflict":c},headers={"Prefer":"resolution=merge-duplicates,return=representation"},json=p,timeout=TIMEOUT)
    check(r,f"upsert {t}"); x=r.json(); return x[0] if x else p
def patch_where(t,f,p):
    r=s.patch(u(t),params=f,headers={"Prefer":"return=minimal"},json=p,timeout=TIMEOUT); check(r,f"patch {t}")
def fnum(v,d=0.0):
    try: return float(v) if v not in (None,"") else d
    except: return d

def current_positions():
    return fetch_all("gptq_paper_positions",{"select":"*","strategy_version":f"eq.{STRATEGY_VERSION}"})

def latest_snapshot():
    x=fetch_all("gptq_paper_equity_snapshots",{"select":"*","strategy_version":f"eq.{STRATEGY_VERSION}","order":"run_date.desc","limit":"1"})
    return x[0] if x else None

def eligible_signals():
    x=fetch_all("gptq_paper_signals",{
        "select":"*","run_date":f"eq.{RUN_DATE}","strategy_version":f"eq.{STRATEGY_VERSION}",
        "eligible":"eq.true","order":"score.desc,rank_no.asc"
    })
    return [r for r in x if fnum(r.get("score")) >= MIN_SIGNAL_SCORE]

def get_or_create_run():
    x=fetch_all("gptq_paper_runs",{"select":"*","run_date":f"eq.{RUN_DATE}","strategy_version":f"eq.{STRATEGY_VERSION}","limit":"1"})
    if x: return x[0]
    return upsert("gptq_paper_runs",{"run_date":RUN_DATE,"strategy_version":STRATEGY_VERSION,"status":"RUNNING","starting_cash":INITIAL_CAPITAL},"run_date,strategy_version")

def already_executed(signal_id):
    return bool(fetch_all("gptq_paper_orders",{"select":"id","source_signal_id":f"eq.{signal_id}","strategy_version":f"eq.{STRATEGY_VERSION}","side":"eq.BUY","limit":"1"}))

def log_decision(sig,decision,reason,fill=None,shares=0,notional=0,exposure=None):
    upsert("gptq_paper_execution_decisions",{
        "run_date":RUN_DATE,"strategy_version":STRATEGY_VERSION,"signal_id":sig.get("id"),
        "stock_id":sig["stock_id"],"symbol":sig.get("symbol"),"score":sig.get("score"),
        "decision":decision,"reason":reason,"reference_price":sig.get("reference_price"),
        "simulated_fill_price":round(fill,4) if fill else None,"shares":shares,
        "notional":round(notional,2),"projected_exposure":round(exposure,6) if exposure is not None else None
    },"run_date,strategy_version,stock_id")

def main():
    sigs=eligible_signals()
    pos=current_positions()
    snap=latest_snapshot()
    cash=fnum(snap.get("cash")) if snap else INITIAL_CAPITAL
    mv=sum(fnum(p.get("market_value")) for p in pos)
    equity=cash+mv
    starting_cash,starting_equity=cash,equity
    paper_run=get_or_create_run()
    run_id=paper_run.get("id")

    exrun=upsert("gptq_paper_execution_runs",{
        "run_date":RUN_DATE,"strategy_version":STRATEGY_VERSION,"status":"RUNNING",
        "eligible_signals":len(sigs),"starting_cash":round(cash,2),"starting_equity":round(equity,2)
    },"run_date,strategy_version")

    open_ids={int(p["stock_id"]) for p in pos}
    capacity=max(0,MAX_OPEN_POSITIONS-len(pos))
    approved=rejected=orders_created=positions_created=0
    executions=[]; errors=[]

    for sig in sigs:
        if approved>=MAX_NEW_ORDERS:
            log_decision(sig,"REJECTED","MAX_NEW_ORDERS_REACHED"); rejected+=1; continue
        if capacity<=0:
            log_decision(sig,"REJECTED","MAX_OPEN_POSITIONS_REACHED"); rejected+=1; continue
        sid=int(sig["stock_id"]); signal_id=int(sig["id"])
        if sid in open_ids:
            log_decision(sig,"REJECTED","POSITION_ALREADY_OPEN"); rejected+=1; continue
        if already_executed(signal_id):
            log_decision(sig,"REJECTED","SIGNAL_ALREADY_EXECUTED"); rejected+=1; continue

        ref=fnum(sig.get("reference_price"))
        if ref<=0:
            log_decision(sig,"REJECTED","INVALID_REFERENCE_PRICE"); rejected+=1; continue

        current_mv=sum(fnum(p.get("market_value")) for p in pos)
        current_eq=cash+current_mv
        current_exp=current_mv/current_eq if current_eq>0 else 1
        if current_exp>=MAX_GROSS_EXPOSURE:
            log_decision(sig,"REJECTED","MAX_GROSS_EXPOSURE_REACHED",exposure=current_exp); rejected+=1; continue

        target=min(POSITION_SIZE,MAX_SINGLE_POSITION)*current_eq
        room=max(0,current_eq*MAX_GROSS_EXPOSURE-current_mv)
        budget=min(target,room,cash/(1+COMMISSION_RATE))
        fill=ref*(1+SLIPPAGE_RATE)
        shares=int(budget/fill)
        if shares<=0:
            log_decision(sig,"REJECTED","INSUFFICIENT_CASH_OR_EXPOSURE_ROOM"); rejected+=1; continue

        notional=fill*shares
        commission=notional*COMMISSION_RATE
        total_cost=notional+commission
        projected_mv=current_mv+ref*shares
        projected_eq=cash-total_cost+projected_mv
        projected_exp=projected_mv/projected_eq if projected_eq>0 else 1

        if total_cost>cash or projected_exp>MAX_GROSS_EXPOSURE+1e-9:
            log_decision(sig,"REJECTED","RISK_LIMIT_EXCEEDED",fill,shares,notional,projected_exp); rejected+=1; continue

        try:
            insert("gptq_paper_orders",{
                "run_id":run_id,"run_date":RUN_DATE,"strategy_version":STRATEGY_VERSION,
                "stock_id":sid,"symbol":sig.get("symbol"),"side":"BUY",
                "signal_score":sig.get("score"),"signal_label":sig.get("signal_label"),
                "reference_price":round(ref,4),"simulated_fill_price":round(fill,4),
                "shares":shares,"notional":round(notional,2),"status":"FILLED",
                "reason":"PHASE23_AUTOMATIC_SIGNAL_EXECUTION","realized_pnl":0,"holding_days":0,
                "execution_mode":"SHADOW_ONLY_NO_BROKER","source_signal_id":signal_id,
                "risk_approved":True,"risk_reason":"ALL_RISK_GATES_PASSED"
            })
            cash-=total_cost
            upsert("gptq_paper_positions",{
                "strategy_version":STRATEGY_VERSION,"stock_id":sid,"symbol":sig.get("symbol"),
                "shares":shares,"average_price":round(fill,4),"last_price":round(ref,4),
                "market_value":round(ref*shares,2),"unrealized_pnl":round((ref-fill)*shares,2),
                "opened_at":RUN_DATE,"updated_at":datetime.now(timezone.utc).isoformat(),
                "entry_score":sig.get("score"),"entry_signal":sig.get("signal_label"),
                "highest_price":round(ref,4),"holding_days":0,
                "stop_price":round(fill*(1-STOP_LOSS),4),"take_profit_price":round(fill*(1+TAKE_PROFIT),4),
                "source_signal_id":signal_id,"execution_mode":"SHADOW_ONLY_NO_BROKER"
            },"strategy_version,stock_id")
            patch_where("gptq_paper_signals",{"id":f"eq.{signal_id}"},{"selected":True,"reject_reason":None})
            log_decision(sig,"APPROVED","ALL_RISK_GATES_PASSED",fill,shares,notional,projected_exp)
            approved+=1; orders_created+=1; positions_created+=1; capacity-=1
            open_ids.add(sid); pos=current_positions()
            executions.append({"symbol":sig.get("symbol"),"score":sig.get("score"),"shares":shares,"fill":round(fill,4),"notional":round(notional,2)})
        except Exception as e:
            msg=str(e)[:1200]; errors.append({"symbol":sig.get("symbol"),"error":msg})
            log_decision(sig,"ERROR",msg); rejected+=1

    pos=current_positions()
    final_mv=sum(fnum(p.get("market_value")) for p in pos)
    final_upnl=sum(fnum(p.get("unrealized_pnl")) for p in pos)
    final_eq=cash+final_mv
    gross=final_mv/final_eq if final_eq>0 else 0

    upsert("gptq_paper_equity_snapshots",{
        "run_date":RUN_DATE,"strategy_version":STRATEGY_VERSION,"cash":round(cash,2),
        "market_value":round(final_mv,2),"total_equity":round(final_eq,2),
        "realized_pnl":0,"unrealized_pnl":round(final_upnl,2),"open_positions":len(pos)
    },"run_date,strategy_version")

    status="COMPLETED" if not errors else "COMPLETED_WITH_ERRORS"
    patch_where("gptq_paper_execution_runs",{"id":f"eq.{exrun['id']}"},{
        "status":status,"approved_signals":approved,"rejected_signals":rejected,
        "orders_created":orders_created,"positions_created":positions_created,
        "ending_cash":round(cash,2),"ending_equity":round(final_eq,2),
        "gross_exposure":round(gross,6),"errors":errors,
        "completed_at":datetime.now(timezone.utc).isoformat()
    })
    if run_id is not None:
        patch_where("gptq_paper_runs",{"id":f"eq.{run_id}"},{
            "status":"COMPLETED","ending_cash":round(cash,2),"ending_equity":round(final_eq,2),
            "unrealized_pnl":round(final_upnl,2),"orders_created":orders_created,
            "positions_open":len(pos),"completed_at":datetime.now(timezone.utc).isoformat()
        })

    report={"run_date":RUN_DATE,"strategy_version":STRATEGY_VERSION,"mode":"SHADOW_ONLY_NO_BROKER",
            "status":status,"eligible_signals":len(sigs),"approved_signals":approved,
            "rejected_signals":rejected,"orders_created":orders_created,"positions_created":positions_created,
            "positions_open":len(pos),"starting_cash":round(starting_cash,2),"ending_cash":round(cash,2),
            "starting_equity":round(starting_equity,2),"ending_equity":round(final_eq,2),
            "market_value":round(final_mv,2),"unrealized_pnl":round(final_upnl,2),
            "gross_exposure":round(gross,6),"executions":executions,"errors":errors}

    (ARTIFACT_DIR/"phase23_execution_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary=os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("# GPT Quant V9.2 Paper Trading Phase 2.3\n\n")
            for k in ["mode","status","eligible_signals","approved_signals","rejected_signals","orders_created","positions_created","positions_open","ending_cash","market_value","ending_equity","unrealized_pnl","gross_exposure"]:
                f.write(f"- **{k}**: `{report[k]}`\n")
            f.write("\n## Executions\n\n| Symbol | Score | Shares | Fill | Notional |\n|---|---:|---:|---:|---:|\n")
            for x in executions:
                f.write(f"| {x['symbol']} | {x['score']} | {x['shares']} | {x['fill']} | {x['notional']} |\n")
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
