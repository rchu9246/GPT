"""Read-only, fail-closed public report from the isolated forward evidence store."""
from __future__ import annotations
import argparse, json
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from .forward_validation import (ForwardStore, SHADOW_STRATEGY_REGISTRY, REGISTRY_FINGERPRINT,
    account_id, validation_status)
from .ledger import AppendOnlyLedger, replay_account
from .phase2_research import INITIAL_CASH
from .safety import SAFETY

START = date(2026, 10, 5)
D = Decimal

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def build_report(store: ForwardStore) -> dict:
    SAFETY.assert_safe()
    require(store.boundary()==START, "wrong forward start boundary")
    registry=read(store.registry_path)
    expected=json.loads(json.dumps([asdict(s) for s in SHADOW_STRATEGY_REGISTRY]))
    require(registry=={"registry_fingerprint":REGISTRY_FINGERPRINT,"strategies":expected}, "registry contamination")
    dates=store.completed_dates()
    require(bool(dates) and dates[0]==START and all(d>=START for d in dates), "pre-forward or missing start evidence")
    manifests=[read(store.runs/f"{d}.json") for d in dates]
    benchmark=AppendOnlyLedger.load(store.root/"benchmark.jsonl")
    require([e.event_date for e in benchmark.events]==list(dates), "benchmark dates differ")
    market={d:read(store.root/"market_evidence"/f"{d}.json") for d in dates
        if (store.root/"market_evidence"/f"{d}.json").exists()}
    for i,(day,m) in enumerate(zip(dates,manifests)):
        require(m["mode"]=="FORWARD_SHADOW" and m["paper_only"] is True and m["broker_orders_created"]==0, "non-paper manifest")
        require(m["business_date"]==m["data_date"]==str(day) and m["forward_trading_days"]==i+1, "date/count mismatch")
        require(m["strategy_registry_fingerprint"]==REGISTRY_FINGERPRINT, "manifest registry mismatch")
        require({a["strategy_id"] for a in m["strategies"]}=={s.strategy_id for s in SHADOW_STRATEGY_REGISTRY}
            and len(m["strategies"])==18, "scoreboard strategy mismatch")
        require(D(dict(benchmark.events[i].payload)["twse_index"])==D(m["benchmark"]["twse_index"]), "benchmark mark mismatch")
        base=D(manifests[0]["benchmark"]["twse_index"])
        require(D(m["benchmark"]["twse_return"])==D(m["benchmark"]["twse_index"])/base-1, "benchmark return mismatch")
    latest=manifests[-1]; rows=[]; orders=[]; fills=[]; seen=set(); reconciliations=[]
    for spec in SHADOW_STRATEGY_REGISTRY:
        ledger,_=store.ledger(spec)
        require(all(e.event_date in dates for e in ledger.events), "ledger outside evidence dates")
        for e in ledger.events:
            p=dict(e.payload)
            if e.event_type=="TARGETS":
                require(p["spec_fingerprint"]==spec.spec_fingerprint and p["signal_date"]==str(e.event_date), "target cross-strategy contamination")
        targets={e.event_id:e for e in ledger.events if e.event_type=="TARGETS"}
        def signal_score(target, symbol):
            payload=dict(target.payload)
            score=json.loads(payload.get("signal_scores","{}")).get(symbol)
            candidate=next((c for m in manifests if m["business_date"]==str(target.event_date)
                for c in m["top_candidates"] if c["symbol"]==symbol),None)
            if score is None and candidate:
                weights=dict(spec.weights)
                score=str(sum((D(v)*D(candidate["factor_scores"][k]) for k,v in weights.items()),D(0))/sum((D(v) for v in weights.values()),D(0)))
            return score
        executed={(dict(e.payload)["target_event_id"],dict(e.payload)["symbol"]) for e in ledger.events if e.event_type=="TARGET_SYMBOL_EXECUTED"}
        account_fills=[]
        for e in ledger.events:
            if e.event_type!="PAPER_FILL": continue
            p=dict(e.payload); key=p["fill_id"]
            require(key not in seen, "duplicate fill across accounts")
            seen.add(key)
            require(p["lineage"]==spec.spec_fingerprint and p.get("target_event_id") in targets, "fill lineage mismatch")
            signal=targets[p["target_event_id"]].event_date
            require(p.get("signal_date")==str(signal) and signal<e.event_date, "same-day/future signal fill")
            tradable=[d for d in dates if d>signal and d in market and any(b["symbol"]==p["symbol"] for b in market[d]["bars"])]
            require(tradable and tradable[0]==e.event_date, "not first actual tradable date")
            bar=next(b for b in market[e.event_date]["bars"] if b["symbol"]==p["symbol"])
            require(D(p["price"])==D(bar["open"]) and p.get("observation_id")==bar["observation_id"]
                and p.get("reference")=="TWSE_ACTUAL_NEXT_TRADABLE_OPEN", "unproven actual next-open price")
            f={"fill_id":key,"signal_date":str(signal),"execution_date":str(e.event_date),"symbol":p["symbol"],
                "side":"BUY" if int(p["quantity"])>0 else "SELL","shares":abs(int(p["quantity"])),
                "signal_score":signal_score(targets[p["target_event_id"]],p["symbol"]),
                "reference":p["reference"],"fill_price":p["price"],"transaction_cost":p["fee"],
                "status":"FILLED","strategy_id":spec.strategy_id,"target_event_id":p["target_event_id"],
                "observation_id":p["observation_id"]}
            account_fills.append(f); fills.append(f)
        for e in targets.values():
            p=dict(e.payload)
            for symbol,weight in json.loads(p["targets"]).items():
                matched=[f for f in account_fills if f["target_event_id"]==e.event_id and f["symbol"]==symbol]
                if matched:
                    orders.extend({**f,"target_weight":weight,"order_intent":"TARGET"} for f in matched)
                else:
                    orders.append({"signal_date":str(e.event_date),"execution_date":None,"symbol":symbol,"side":"TARGET",
                        "shares":None,"signal_score":signal_score(e,symbol),"reference":"NEXT_ACTUAL_TRADABLE_OPEN",
                        "fill_price":None,"transaction_cost":None,"target_weight":weight,"order_intent":"TARGET",
                        "status":"EXECUTED_NO_FILL" if (e.event_id,symbol) in executed else "PENDING_NEXT_TRADABLE_OPEN",
                        "strategy_id":spec.strategy_id})
        # Reduction fills for symbols no longer in target weights remain visible as orders.
        for f in account_fills:
            if not any(o.get("fill_id")==f["fill_id"] for o in orders): orders.append({**f,"order_intent":"REDUCE_TARGET"})
        curve=[]
        for day,m in zip(dates,manifests):
            a=next(a for a in m["strategies"] if a["strategy_id"]==spec.strategy_id)
            daily_fill_ids=[dict(e.payload)["fill_id"] for e in ledger.events if e.event_type=="PAPER_FILL" and e.event_date==day]
            require(a["fills"]==daily_fill_ids, "manifest fill list differs from ledger")
            state=replay_account([e for e in ledger.events if e.event_date<=day],INITIAL_CASH)
            require(a["account_id"]==account_id(spec) and a["spec_fingerprint"]==spec.spec_fingerprint, "account contamination")
            require(state.cash==D(a["cash"]) and state.fees==D(a["transaction_cost_cumulative"])
                and dict(state.positions)==dict(a["positions"]), "cash reset/positions reconciliation failure")
            require(D(a["cash"])+D(a["market_value"])==D(a["equity"]), "equity identity failure")
            if state.positions:
                require(day in market, "missing position marks")
                marks={b["symbol"]:D(b["close"]) for b in market[day]["bars"]}
                require(sum((marks[s]*q for s,q in state.positions),D(0))==D(a["market_value"]), "incorrect market value")
            require(D(a["return"])==D(a["equity"])/INITIAL_CASH-1 and D(a["cumulative_pnl"])==D(a["equity"])-INITIAL_CASH, "return/PnL contamination")
            require(D(a["benchmark_return"])==D(m["benchmark"]["twse_return"])
                and D(a["excess_return"])==D(a["return"])-D(a["benchmark_return"]), "unaligned excess return")
            require(a["validation_status"]==validation_status(m["forward_trading_days"],a.get("forward_metrics")).value, "premature evidence gate")
            daily=[f for f in account_fills if f["execution_date"]==str(day)]
            opening=replay_account([e for e in ledger.events if e.event_date<day],INITIAL_CASH).cash
            purchases=sum((D(f["fill_price"])*f["shares"] for f in daily if f["side"]=="BUY"),D(0))
            sales=sum((D(f["fill_price"])*f["shares"] for f in daily if f["side"]=="SELL"),D(0))
            costs=sum((D(f["transaction_cost"]) for f in daily),D(0))
            require(opening-purchases-costs+sales==state.cash, "daily cash reconciliation failure")
            reconciliations.append({"strategy_id":spec.strategy_id,"date":str(day),"opening_cash":str(opening),
                "purchases":str(purchases),"sales":str(sales),"transaction_costs":str(costs),"ending_cash":str(state.cash),"status":"PASS"})
            curve.append({"date":str(day),"equity":a["equity"],"return":a["return"],"benchmark_return":a["benchmark_return"]})
        a=next(a for a in latest["strategies"] if a["strategy_id"]==spec.strategy_id)
        state=replay_account(ledger.events,INITIAL_CASH); averages=dict(state.average_costs)
        positions=[]
        for symbol,q in state.positions:
            last=next(b for b in market[dates[-1]]["bars"] if b["symbol"]==symbol)["close"]
            symbol_fills=[f for f in account_fills if f["symbol"]==symbol]
            running=0; opened=None
            for f in symbol_fills:
                if running==0 and f["side"]=="BUY": opened=f["execution_date"]
                running+=f["shares"]*(1 if f["side"]=="BUY" else -1)
            positions.append({"symbol":symbol,"shares":q,"average_price":str(averages[symbol]),"last_price":last,
                "market_value":str(D(last)*q),"unrealized_pnl":str((D(last)-averages[symbol])*q),
                "weight":str(D(last)*q/D(a["equity"])),"opened_date":opened})
        rows.append({**a,"hypothesis":spec.hypothesis,"top_n":spec.top_n,"rebalance_frequency":spec.rebalance_frequency,
            "forward_days":len(dates),"sharpe":a.get("forward_metrics",{}).get("sharpe","0"),"position_details":positions,"curve":curve})
    counts=Counter(a["validation_status"] for a in rows)
    for day,m in zip(dates,manifests):
        require(m["fill_count"]==sum(f["execution_date"]==str(day) for f in fills), "manifest fill count mismatch")
    best=max(rows,key=lambda a:(D(a["return"]),a["strategy_id"]))
    first_fills=[f for f in fills if f["signal_date"]==str(START)]
    first_pending=any(o["signal_date"]==str(START) and o["status"]=="PENDING_NEXT_TRADABLE_OPEN" for o in orders)
    candidates=[]
    for c in latest["top_candidates"]:
        # Historic manifests did not include a strategy label; the sealed contract uses registry[0].
        strategy=c.get("strategy_id",SHADOW_STRATEGY_REGISTRY[0].strategy_id)
        active=next((o for o in orders if o["strategy_id"]==strategy and o["symbol"]==c["symbol"] and o["status"]=="PENDING_NEXT_TRADABLE_OPEN"),None)
        candidates.append({**c,"strategy_id":strategy,"order_intent":"TARGET" if active else "NONE",
            "execution_status":active["status"] if active else "NO_NEW_INTENT"})
    return {"contract":"V10_FORWARD_DASHBOARD_V1","mode":"FORWARD_SHADOW","paper_only":True,
        "safety":{"PAPER_ONLY":True,"BROKER_ORDER_SUBMISSION_ENABLED":False,"REAL_MONEY_TRADING_ENABLED":False,"PRODUCTION_EXECUTION_AVAILABLE":False},
        "generated_at":datetime.now(timezone.utc).isoformat(),"source":"V10_FORWARD_STORE",
        "forward_validation_start_date":str(START),"latest_business_date":str(dates[-1]),"forward_trading_days":len(dates),
        "run_id":latest["run_id"],"latest_run_status":"PASS","data_date":latest["data_date"],
        "data_freshness":latest["data_freshness"],"total_symbols":latest["total_symbols"],
        "eligible_symbols":latest["eligible_symbols"],"excluded_symbols":latest["excluded_symbols"],
        "exclusion_reasons":latest["exclusion_reasons"],"status_counts":dict(counts),"strategies":rows,
        "top_candidates":candidates,"orders":orders,"fills":fills,"reconciliations":reconciliations,
        "first_fill_date":min((f["execution_date"] for f in first_fills),default="PENDING"),
        "first_fill_validation":"PASS" if first_fills and not first_pending else "PENDING","next_open_semantics":"PASS",
        "best_strategy_id":best["strategy_id"],"profitability_label":"PRELIMINARY / INSUFFICIENT EVIDENCE" if len(dates)<60 else best["validation_status"],
        "preliminary_gate":{"days":len(dates),"required":20},"qualification_gate":{"days":len(dates),"required":60}}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--store",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); report=build_report(ForwardStore(a.store)); a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"latest_business_date":report["latest_business_date"],"fills":len(report["fills"]),"first_fill_validation":report["first_fill_validation"]}))

if __name__=="__main__": main()
