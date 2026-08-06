from __future__ import annotations
import argparse,html,json,math,os
from pathlib import Path
METRICS=['total_return','annual_return','max_drawdown','sharpe','sortino','win_rate','profit_factor','total_trades','average_trade','exposure','volatility','calmar']
PCT={'total_return','annual_return','max_drawdown','win_rate','exposure','volatility'}
HIGH={'total_return','annual_return','sharpe','sortino','win_rate','profit_factor','average_trade','calmar'}
LOW={'max_drawdown','volatility'}
def num(v):
    try:
        x=float(str(v).replace('%','').replace(',','').strip()); return None if math.isnan(x) or math.isinf(x) else x
    except:return None
def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def norm(d):
    out={}
    for m in METRICS:
        v=num(d.get(m)); out[m]=v*100 if m in PCT and v is not None and abs(v)<=1.5 else v
    return out
def qdelta(m,o,n):
    if m=='max_drawdown': return abs(o)-abs(n)
    return o-n if m in LOW else n-o
def fmt(m,v):
    if v is None:return 'N/A'
    if m in PCT:return f'{v:.2f}%'
    if m=='total_trades':return f'{v:,.0f}'
    return f'{v:.4f}'
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--v9',required=True); ap.add_argument('--v91',required=True); ap.add_argument('--policy',required=True); ap.add_argument('--output-dir',type=Path,required=True); ap.add_argument('--fail-on-regression',action='store_true'); a=ap.parse_args()
    old,new=norm(load(a.v9)),norm(load(a.v91)); pol=load(a.policy); fail=[]; warn=[]; rows=[]
    for m in METRICS:
        o,n=old[m],new[m]; d=None if o is None or n is None else n-o; rel=None if d is None or abs(o)<1e-12 else d/abs(o)*100; imp=None if d is None or m not in HIGH|LOW else qdelta(m,o,n)>0
        rows.append((m,o,n,d,rel,imp))
    for m in pol.get('required_metrics',[]):
        if old.get(m) is None or new.get(m) is None: fail.append(f'Required metric missing: {m}')
    for m,r in pol.get('regression_rules',{}).items():
        o,n=old.get(m),new.get(m)
        if o is None or n is None: warn.append(f'Gate skipped: {m}'); continue
        q=qdelta(m,o,n); qr=None if abs(o)<1e-12 else q/abs(o)*100; aa=num(r.get('max_absolute_regression')); rr=num(r.get('max_relative_regression_pct'))
        if aa is not None and q < -aa: fail.append(f'{m} absolute regression {q:.4f}')
        if rr is not None and qr is not None and qr < -rr: fail.append(f'{m} relative regression {qr:.2f}%')
    for m,minv in pol.get('v91_minimums',{}).items():
        if new.get(m) is not None and new[m] < float(minv): fail.append(f'{m} below minimum {minv}')
    passed=not fail; a.output_dir.mkdir(parents=True,exist_ok=True)
    lines=['# GPT Quant V9.2 Phase 1 — V9 vs V9.1 Comparison','',f"**Regression Gate:** {'PASS ✅' if passed else 'FAIL ❌'}",'','| Metric | V9 | V9.1 | Absolute Δ | Relative Δ | Result |','|---|---:|---:|---:|---:|:---:|']
    for m,o,n,d,rel,imp in rows:
        s='✅' if imp is True else '⚠️' if imp is False else '—'; ds='N/A' if d is None else fmt(m,d); rs='N/A' if rel is None else f'{rel:+.2f}%'; lines.append(f"| {m.replace('_',' ').title()} | {fmt(m,o)} | {fmt(m,n)} | {ds} | {rs} | {s} |")
    lines+=['','## Gate diagnostics','']+[f'- ❌ {x}' for x in fail]+[f'- ⚠️ {x}' for x in warn]
    if not fail and not warn: lines.append('- No regressions detected.')
    md='\n'.join(lines)+'\n'; (a.output_dir/'v9-vs-v91-report.md').write_text(md,encoding='utf-8'); (a.output_dir/'v9-vs-v91-report.json').write_text(json.dumps({'passed':passed,'failures':fail,'warnings':warn},indent=2)+'\n',encoding='utf-8'); (a.output_dir/'v9-vs-v91-report.html').write_text('<html><body><pre>'+html.escape(md)+'</pre></body></html>',encoding='utf-8')
    if os.getenv('GITHUB_STEP_SUMMARY'): open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8').write(md)
    print(md)
    raise SystemExit(2 if a.fail_on_regression and not passed else 0)
if __name__=='__main__': main()
