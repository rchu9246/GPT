from __future__ import annotations
import argparse,csv,json,math,os,subprocess
from pathlib import Path
from statistics import mean,pstdev

def n(v):
 try:
  x=float(str(v).replace(',','').replace('%','').strip());return x if math.isfinite(x) else None
 except:return None

def pick(fields,candidates):
 m={x.lower().strip():x for x in fields or []}
 for c in candidates:
  if c in m:return m[c]
 raise ValueError('Missing column: '+candidates[0])

def trades(src,dst):
 with Path(src).open(encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f); t=pick(r.fieldnames,['timestamp','time','datetime','date','exit_time']);s=pick(r.fieldnames,['side','direction','position','signal']);e=pick(r.fieldnames,['entry_price','entry','open_price']);x=pick(r.fieldnames,['exit_price','exit','close_price']);p=pick(r.fieldnames,['pnl','profit','net_profit','realized_pnl']);rows=[{'timestamp':q[t],'side':q[s].upper(),'entry_price':n(q[e]),'exit_price':n(q[x]),'pnl':n(q[p])} for q in r]
 if any(q['pnl'] is None for q in rows):raise ValueError('Invalid pnl')
 with Path(dst).open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
 return rows

def equity(src,dst):
 with Path(src).open(encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f);t=pick(r.fieldnames,['timestamp','time','datetime','date']);e=pick(r.fieldnames,['equity','balance','nav','account_value','portfolio_value']);rows=[{'timestamp':q[t],'equity':n(q[e])} for q in r]
 if any(q['equity'] is None for q in rows):raise ValueError('Invalid equity')
 with Path(dst).open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=['timestamp','equity']);w.writeheader();w.writerows(rows)
 return rows

def mdd(v):
 peak=v[0];worst=0
 for x in v:peak=max(peak,x);worst=min(worst,(x/peak-1)*100)
 return worst

def derive(ts,eq):
 ev=[q['equity'] for q in eq];pn=[q['pnl'] for q in ts];ret=[ev[i]/ev[i-1]-1 for i in range(1,len(ev)) if ev[i-1]];sd=pstdev(ret) if len(ret)>1 else 0;pos=sum(x for x in pn if x>0);neg=abs(sum(x for x in pn if x<0))
 return {'total_return':(ev[-1]/ev[0]-1)*100,'max_drawdown':mdd(ev),'sharpe':0 if sd==0 else mean(ret)/sd*math.sqrt(len(ret)),'profit_factor':pos/neg if neg else (999 if pos else 0),'total_trades':len(pn),'win_rate':sum(x>0 for x in pn)/len(pn)*100 if pn else 0,'average_trade':mean(pn) if pn else 0}

def diag(out,p):
 out.mkdir(parents=True,exist_ok=True);(out/'production_evidence_diagnostic.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');md='# Production Evidence Diagnostic\n\n'+f"- Version: `{p['version']}`\n- Status: **{p['status']}**\n- Exit code: `{p['returncode']}`\n\n"+'\n'.join(f"- {'✅' if x['exists'] else '❌'} `{x['path']}`" for x in p['files'])
 if p.get('error'):md+='\n\n## Error\n\n```text\n'+p['error']+'\n```\n'
 (out/'production_evidence_diagnostic.md').write_text(md,encoding='utf-8')
 if os.getenv('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(md)

def main():
 a=argparse.ArgumentParser();a.add_argument('--version',choices=['v9','v91'],required=True);a.add_argument('--command',required=True);a.add_argument('--output-dir',type=Path,required=True);a.add_argument('--min-trades',type=int,default=20);a.add_argument('--min-equity-rows',type=int,default=30);q=a.parse_args();raw=q.output_dir/'raw';raw.mkdir(parents=True,exist_ok=True);rm=raw/f'{q.version}_raw_metrics.json';rt=raw/f'{q.version}_raw_trades.csv';re=raw/f'{q.version}_raw_equity.csv';env=os.environ.copy();env.update({'GPTQ_METRICS_OUTPUT':str(rm),'GPTQ_TRADES_OUTPUT':str(rt),'GPTQ_EQUITY_OUTPUT':str(re),'GPTQ_RAW_METRICS_OUTPUT':str(rm),'GPTQ_RAW_TRADES_OUTPUT':str(rt),'GPTQ_RAW_EQUITY_OUTPUT':str(re),'GPTQ_BACKTEST_VERSION':q.version});r=subprocess.run(q.command,shell=True,text=True,capture_output=True,env=env);p={'adapter_version':'3.4.1','version':q.version,'status':'ERROR','returncode':r.returncode,'stdout':r.stdout[-4000:],'stderr':r.stderr[-4000:]}
 try:
  if r.returncode:raise RuntimeError(f'Backtest command failed with exit code {r.returncode}')
  miss=[str(x) for x in [rt,re] if not x.exists()]
  if miss:raise FileNotFoundError('Missing required outputs: '+', '.join(miss))
  to=q.output_dir/f'{q.version}_trades.csv';eo=q.output_dir/f'{q.version}_equity_curve.csv';ts=trades(rt,to);eq=equity(re,eo);mt=derive(ts,eq)
  if rm.exists():
   try:
    for k,v in json.loads(rm.read_text(encoding='utf-8-sig')).items():
     z=n(v)
     if z is not None:mt[k]=z
   except:pass
  mo=q.output_dir/f'{q.version}_metrics.json';mo.write_text(json.dumps(mt,indent=2)+'\n');checks={'minimum_trades':len(ts)>=q.min_trades,'minimum_equity_rows':len(eq)>=q.min_equity_rows};ok=all(checks.values());man={'adapter_version':'3.4.1','version':q.version,'production_evidence':ok,'metrics_source':'provided_plus_derived' if rm.exists() else 'derived_from_trades_and_equity','counts':{'trade_rows':len(ts),'equity_rows':len(eq)},'checks':checks};(q.output_dir/f'{q.version}_production_evidence_manifest.json').write_text(json.dumps(man,indent=2)+'\n');p.update(status='PASS' if ok else 'QUALITY_GATE_FAIL',manifest=man);p['files']=[{'path':str(x),'exists':x.exists()} for x in [rm,rt,re,mo]];diag(q.output_dir,p);return 0 if ok else 2
 except Exception as e:p['error']=f'{type(e).__name__}: {e}';p['files']=[{'path':str(x),'exists':x.exists()} for x in [rm,rt,re]];diag(q.output_dir,p);return 1
if __name__=='__main__':raise SystemExit(main())
