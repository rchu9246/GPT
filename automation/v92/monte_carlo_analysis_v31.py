from __future__ import annotations
import argparse,csv,json,random
from pathlib import Path
from statistics import mean

def read_pnl(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f: values=[float(r["pnl"]) for r in csv.DictReader(f)]
    if len(values)<10: raise ValueError("Monte Carlo requires at least 10 trades")
    return values

def drawdown(eq):
    peak=eq[0]; worst=0
    for v in eq:
        peak=max(peak,v); worst=min(worst,(v/peak-1)*100 if peak else 0)
    return worst

def pct(values,q):
    s=sorted(values); pos=(len(s)-1)*q; lo=int(pos); hi=min(lo+1,len(s)-1); w=pos-lo
    return s[lo]*(1-w)+s[hi]*w

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trades",required=True); p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--iterations",type=int,default=1000); p.add_argument("--starting-equity",type=float,default=1_000_000)
    p.add_argument("--max-p95-drawdown",type=float,default=25); p.add_argument("--seed",type=int,default=42)
    a=p.parse_args(); pnl=read_pnl(a.trades); rng=random.Random(a.seed); rets=[]; dds=[]; ruin=0
    for _ in range(a.iterations):
        sample=[rng.choice(pnl) for _ in pnl]; eq=[a.starting_equity]
        for x in sample: eq.append(eq[-1]+x)
        rets.append((eq[-1]/a.starting_equity-1)*100); dds.append(abs(drawdown(eq))); ruin+=min(eq)<=0
    p95=pct(dds,.95); rp=ruin/a.iterations; passed=p95<=a.max_p95_drawdown and rp==0
    payload={"passed":passed,"iterations":a.iterations,"mean_return":mean(rets),"p05_return":pct(rets,.05),"p95_drawdown":p95,"ruin_probability":rp}
    a.output_dir.mkdir(parents=True,exist_ok=True)
    (a.output_dir/"monte_carlo.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    return 0 if passed else 2
if __name__=="__main__": raise SystemExit(main())
