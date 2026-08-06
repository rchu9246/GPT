from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from statistics import mean, pstdev

def read_equity(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows=[(r["timestamp"],float(r["equity"])) for r in csv.DictReader(f)]
    if len(rows)<4: raise ValueError("Equity curve requires at least 4 rows")
    return rows

def max_drawdown(values):
    peak=values[0]; worst=0.0
    for value in values:
        peak=max(peak,value)
        worst=min(worst,(value/peak-1.0)*100.0)
    return worst

def sharpe(returns):
    if len(returns)<2: return 0.0
    sigma=pstdev(returns)
    return 0.0 if sigma==0 else mean(returns)/sigma*(len(returns)**0.5)

def analyze(values):
    returns=[values[i]/values[i-1]-1 for i in range(1,len(values)) if values[i-1]]
    return {"total_return":(values[-1]/values[0]-1)*100,"max_drawdown":max_drawdown(values),"sharpe":sharpe(returns)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--equity",required=True); p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--windows",type=int,default=5); p.add_argument("--min-pass-rate",type=float,default=.60)
    a=p.parse_args(); curve=read_equity(a.equity); vals=[v for _,v in curve]
    windows=max(2,min(a.windows,len(vals)//4)); size=max(2,len(vals)//windows)
    results=[]
    for i in range(windows):
        start=i*size; end=len(vals) if i==windows-1 else min(len(vals),start+size+1)
        if end-start<2: continue
        m=analyze(vals[start:end]); m.update({"window":i+1,"start":curve[start][0],"end":curve[end-1][0]})
        m["passed"]=m["total_return"]>0 and m["max_drawdown"]>-25
        results.append(m)
    rate=sum(x["passed"] for x in results)/len(results) if results else 0
    passed=rate>=a.min_pass_rate
    payload={"passed":passed,"pass_rate":rate,"minimum_pass_rate":a.min_pass_rate,"windows":results}
    a.output_dir.mkdir(parents=True,exist_ok=True)
    (a.output_dir/"walk_forward.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    return 0 if passed else 2
if __name__=="__main__": raise SystemExit(main())
