from __future__ import annotations
import argparse,json,os,subprocess,sys,traceback
from pathlib import Path

def mask(name,value):
    if not value:return '<EMPTY>'
    if any(x in name.upper() for x in ('KEY','TOKEN','SECRET')):
        return value[:4]+'***'+value[-4:] if len(value)>8 else '***'
    return value

def tree(path):
    p=Path(path)
    if not p.exists():return [f'{p} <MISSING>']
    return [str(x) for x in sorted(p.rglob('*'))][:500]

def write_report(out,report):
    out.mkdir(parents=True,exist_ok=True)
    (out/'production_evidence_debug_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Production Evidence Debug Report v3.4.2','',f"- Status: **{report['status']}**",f"- Version: `{report['version']}`",f"- Return code: `{report.get('returncode')}`",'','## Expected files']
    lines += [f"- {'✅' if x['exists'] else '❌'} `{x['path']}`" for x in report['expected_files']]
    lines += ['','## stdout','```text',report.get('stdout','') or '<EMPTY>','```','','## stderr','```text',report.get('stderr','') or '<EMPTY>','```','','## traceback','```text',report.get('traceback','') or '<NONE>','```','','## artifact tree','```text',*report.get('artifact_tree',[]),'```']
    md='\n'.join(lines)+'\n'
    (out/'production_evidence_debug_report.md').write_text(md,encoding='utf-8')
    s=os.getenv('GITHUB_STEP_SUMMARY')
    if s:
        with open(s,'a',encoding='utf-8') as f:f.write(md)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--version',choices=['v9','v91'],required=True);ap.add_argument('--command',required=True);ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--timeout-seconds',type=int,default=3600);a=ap.parse_args()
    out=a.output_dir;raw=out/'raw';raw.mkdir(parents=True,exist_ok=True)
    m=raw/f'{a.version}_raw_metrics.json';t=raw/f'{a.version}_raw_trades.csv';e=raw/f'{a.version}_raw_equity.csv'
    env=os.environ.copy();env.update({'GPTQ_BACKTEST_VERSION':a.version,'GPTQ_RAW_METRICS_OUTPUT':str(m),'GPTQ_RAW_TRADES_OUTPUT':str(t),'GPTQ_RAW_EQUITY_OUTPUT':str(e),'GPTQ_METRICS_OUTPUT':str(m),'GPTQ_TRADES_OUTPUT':str(t),'GPTQ_EQUITY_OUTPUT':str(e)})
    report={'version':a.version,'status':'STARTED','cwd':os.getcwd(),'python':sys.version,'environment':{k:mask(k,env.get(k,'')) for k in ['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','FINMIND_TOKEN','GPTQ_BACKTEST_VERSION','GPTQ_RAW_METRICS_OUTPUT','GPTQ_RAW_TRADES_OUTPUT','GPTQ_RAW_EQUITY_OUTPUT']},'expected_files':[],'artifact_tree':[]}
    try:
        print('='*80);print('GPT Quant v3.4.2 DEBUG');print('COMMAND:',a.command);print('ENV:',json.dumps(report['environment'],indent=2))
        r=subprocess.run(a.command,shell=True,text=True,capture_output=True,env=env,timeout=a.timeout_seconds)
        report.update(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        print('RETURN CODE:', r.returncode); print('STDOUT:'); print(r.stdout or '<EMPTY>'); print('STDERR:'); print(r.stderr or '<EMPTY>')
        report['expected_files']=[{'path':str(p),'exists':p.exists(),'size':p.stat().st_size if p.exists() else 0} for p in (m,t,e)]
        report['artifact_tree']=tree('artifacts')
        for x in report['expected_files']:print(('FOUND' if x['exists'] else 'MISSING'),x['path'])
        if r.returncode!=0:raise RuntimeError(f'backtest exit code {r.returncode}')
        missing=[x['path'] for x in report['expected_files'] if not x['exists']]
        if missing:raise FileNotFoundError('missing outputs: '+', '.join(missing))
        report['status']='DEBUG_PASS';write_report(out,report);return 0
    except Exception:
        report['status']='DEBUG_FAIL';report['traceback']=traceback.format_exc();report['artifact_tree']=tree('artifacts');print(report['traceback']);write_report(out,report);return 1

if __name__=='__main__':
    rc=main();print('FINAL RETURN CODE:',rc);raise SystemExit(rc)
