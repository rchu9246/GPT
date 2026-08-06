from __future__ import annotations
import argparse, csv, json, math, os
from datetime import datetime, timezone
from pathlib import Path

ALIASES = {
 "total_return":["total_return","return","return_pct"],
 "annual_return":["annual_return","annualized_return","cagr"],
 "max_drawdown":["max_drawdown","mdd","max_dd"],
 "sharpe":["sharpe","sharpe_ratio"],
 "sortino":["sortino","sortino_ratio"],
 "win_rate":["win_rate","winrate"],
 "profit_factor":["profit_factor","pf"],
 "total_trades":["total_trades","trades","trade_count"],
 "average_trade":["average_trade","avg_trade","expectancy"],
 "exposure":["exposure","market_exposure"],
 "volatility":["volatility","annual_volatility"],
 "calmar":["calmar","calmar_ratio"],
}
PCT={"total_return","annual_return","max_drawdown","win_rate","exposure","volatility"}
HIGH={"total_return","annual_return","sharpe","sortino","win_rate","profit_factor","average_trade","calmar"}
LOW={"max_drawdown","volatility"}
NAMES={k:k.replace("_"," ").title() for k in ALIASES}

def num(v):
    try:
        x=float(str(v).replace("%","").replace(",","").strip())
        return None if math.isnan(x) or math.isinf(x) else x
    except: return None

def load(path):
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(p)
    if p.suffix.lower()==".json":
        d=json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(d,list): d=d[0]
        if not isinstance(d,dict): raise ValueError("JSON metrics must be an object")
        return d
    if p.suffix.lower()==".csv":
        with p.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
        if len(rows)!=1: raise ValueError("CSV must contain exactly one data row")
        return rows[0]
    raise ValueError("Use JSON or CSV")

def normalize(d):
    lower={str(k).lower().strip():v for k,v in d.items()}
    out={}
    for m,aliases in ALIASES.items():
        v=None
        for a in aliases:
            if a in lower: v=num(lower[a]); break
        if m in PCT and v is not None and abs(v)<=1.5: v*=100
        out[m]=v
    return out

def quality_delta(metric,old,new):
    if metric=="max_drawdown": return abs(old)-abs(new)
    if metric in LOW: return old-new
    return new-old

def fmt(metric,v):
    if v is None:return "N/A"
    if metric in PCT:return f"{v:.2f}%"
    if metric=="total_trades":return f"{v:,.0f}"
    return f"{v:.4f}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--v9",required=True); ap.add_argument("--v91",required=True)
    ap.add_argument("--policy",required=True); ap.add_argument("--output-dir",default="artifacts/comparison")
    ap.add_argument("--fail-on-regression",action="store_true"); a=ap.parse_args()
    old,new=normalize(load(a.v9)),normalize(load(a.v91))
    policy=json.loads(Path(a.policy).read_text(encoding="utf-8"))
    failures=[]; warnings=[]; rows=[]
    for m in ALIASES:
        o,n=old[m],new[m]
        delta=None if o is None or n is None else n-o
        rel=None if delta is None or abs(o)<1e-12 else delta/abs(o)*100
        improved=None if delta is None or m not in HIGH|LOW else quality_delta(m,o,n)>0
        rows.append({"metric":m,"v9":o,"v91":n,"delta":delta,"relative_delta_pct":rel,"improved":improved})
    for m in policy.get("required_metrics",[]):
        if old.get(m) is None or new.get(m) is None: failures.append(f"Required metric missing: {m}")
    for m,r in policy.get("regression_rules",{}).items():
        o,n=old.get(m),new.get(m)
        if o is None or n is None: warnings.append(f"Gate skipped for missing metric: {m}"); continue
        q=quality_delta(m,o,n); qr=None if abs(o)<1e-12 else q/abs(o)*100
        aa=num(r.get("max_absolute_regression")); rr=num(r.get("max_relative_regression_pct"))
        if aa is not None and q < -aa: failures.append(f"{m} absolute regression {q:.4f} exceeds {-aa:.4f}")
        if rr is not None and qr is not None and qr < -rr: failures.append(f"{m} relative regression {qr:.2f}% exceeds {-rr:.2f}%")
    for m,minimum in policy.get("v91_minimums",{}).items():
        v=new.get(m); minimum=num(minimum)
        if v is None: warnings.append(f"Minimum check skipped for missing metric: {m}")
        elif minimum is not None and v<minimum: failures.append(f"{m}={v:.4f} below minimum {minimum:.4f}")
    passed=not failures
    lines=["# GPT Quant V9 vs V9.1 Backtest Comparison","",f"**Gate result:** {'PASS ✅' if passed else 'FAIL ❌'}","",
           "| Metric | V9 | V9.1 | Absolute Δ | Relative Δ | Result |",
           "|---|---:|---:|---:|---:|:---:|"]
    for r in rows:
        symbol="✅" if r["improved"] is True else "⚠️" if r["improved"] is False else "—"
        d="N/A" if r["delta"] is None else fmt(r["metric"],r["delta"])
        rel="N/A" if r["relative_delta_pct"] is None else f'{r["relative_delta_pct"]:+.2f}%'
        lines.append(f'| {NAMES[r["metric"]]} | {fmt(r["metric"],r["v9"])} | {fmt(r["metric"],r["v91"])} | {d} | {rel} | {symbol} |')
    lines+=["","## Gate diagnostics",""]
    lines += [f"- ❌ {x}" for x in failures] + [f"- ⚠️ {x}" for x in warnings]
    if not failures and not warnings: lines.append("- No regressions or missing required metrics detected.")
    md="\n".join(lines)+"\n"
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    (out/"v9-vs-v91-report.md").write_text(md,encoding="utf-8")
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"passed":passed,"failures":failures,"warnings":warnings,"metrics":rows}
    (out/"v9-vs-v91-report.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    html="<html><head><meta charset='utf-8'><style>body{font-family:Arial;margin:32px}pre{white-space:pre-wrap}</style></head><body><pre>"+md.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")+"</pre></body></html>"
    (out/"v9-vs-v91-report.html").write_text(html,encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write(md)
    print(md)
    return 2 if a.fail_on_regression and not passed else 0
if __name__=="__main__": raise SystemExit(main())
