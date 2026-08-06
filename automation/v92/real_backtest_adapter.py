from __future__ import annotations
import argparse, csv, json, os, subprocess
from pathlib import Path

REQUIRED_METRICS={"total_return","max_drawdown","sharpe","profit_factor","total_trades"}

def load_metrics(path: Path):
    if not path.exists(): raise FileNotFoundError(path)
    data=json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data,dict): raise ValueError("Metrics JSON must be an object")
    missing=sorted(REQUIRED_METRICS-data.keys())
    if missing: raise ValueError("Missing metrics: "+", ".join(missing))
    return data

def validate_csv(path: Path, required):
    if not path.exists(): raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig",newline="") as f:
        fields=set(csv.DictReader(f).fieldnames or [])
    missing=sorted(set(required)-fields)
    if missing: raise ValueError(path.name+" missing: "+", ".join(missing))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--version",choices=["v9","v91"],required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--command",required=True)
    p.add_argument("--timeout-seconds",type=int,default=1800)
    a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    metrics=a.output_dir/f"{a.version}_metrics.json"
    trades=a.output_dir/f"{a.version}_trades.csv"
    equity=a.output_dir/f"{a.version}_equity_curve.csv"
    env=os.environ.copy()
    env.update({
      "GPTQ_BACKTEST_VERSION":a.version,
      "GPTQ_METRICS_OUTPUT":str(metrics),
      "GPTQ_TRADES_OUTPUT":str(trades),
      "GPTQ_EQUITY_OUTPUT":str(equity),
    })
    result=subprocess.run(a.command,shell=True,text=True,env=env,timeout=a.timeout_seconds)
    if result.returncode!=0: raise SystemExit(result.returncode)
    load_metrics(metrics)
    validate_csv(trades,{"timestamp","side","entry_price","exit_price","pnl"})
    validate_csv(equity,{"timestamp","equity"})
    (a.output_dir/f"{a.version}_manifest.json").write_text(json.dumps({
      "version":a.version,"metrics":str(metrics),"trades":str(trades),"equity_curve":str(equity)
    },indent=2)+"\n",encoding="utf-8")
    print(f"{a.version} real backtest validated")
    return 0
if __name__=="__main__": raise SystemExit(main())
