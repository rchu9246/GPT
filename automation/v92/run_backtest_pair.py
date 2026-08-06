from __future__ import annotations
import argparse,json,os,subprocess
from pathlib import Path
REQ={"total_return","max_drawdown","sharpe","profit_factor","total_trades"}
def validate(p,label):
    if not p.exists(): raise FileNotFoundError(f"{label} metrics missing: {p}")
    d=json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(d,dict): raise ValueError(f"{label} metrics must be JSON object")
    miss=sorted(REQ-set(d))
    if miss: raise ValueError(f"{label} metrics missing: {', '.join(miss)}")
    return d
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=['smoke','production'],default='smoke'); ap.add_argument('--output-dir',type=Path,required=True); a=ap.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True); v9=a.output_dir/'v9_metrics.json'; v91=a.output_dir/'v91_metrics.json'
    if a.mode=='smoke':
        v9.write_bytes(Path('backtest/examples/v9_metrics.example.json').read_bytes()); v91.write_bytes(Path('backtest/examples/v91_metrics.example.json').read_bytes())
    else:
        env=os.environ.copy(); env['V92_V9_METRICS_OUTPUT']=str(v9); env['V92_V91_METRICS_OUTPUT']=str(v91)
        c9=os.environ.get('V9_BACKTEST_COMMAND',''); c91=os.environ.get('V91_BACKTEST_COMMAND','')
        if not c9 or not c91: raise RuntimeError('Configure V9_BACKTEST_COMMAND and V91_BACKTEST_COMMAND repository variables')
        subprocess.run(c9,shell=True,check=True,env=env); subprocess.run(c91,shell=True,check=True,env=env)
    validate(v9,'V9'); validate(v91,'V9.1')
    (a.output_dir/'backtest_manifest.json').write_text(json.dumps({'mode':a.mode,'v9':str(v9),'v91':str(v91)},indent=2)+'\n',encoding='utf-8')
    print('Backtest pair completed')
if __name__=='__main__': main()
