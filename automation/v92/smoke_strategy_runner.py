from __future__ import annotations
import argparse,csv,json,os
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--version",choices=["v9","v91"],required=True); a=p.parse_args()
    m=Path(os.environ["GPTQ_METRICS_OUTPUT"]); t=Path(os.environ["GPTQ_TRADES_OUTPUT"]); e=Path(os.environ["GPTQ_EQUITY_OUTPUT"])
    m.parent.mkdir(parents=True,exist_ok=True)
    metrics={"total_return":24.0,"max_drawdown":-12.0,"sharpe":1.48,"profit_factor":1.62,"total_trades":340}
    if a.version=="v91": metrics.update({"total_return":27.0,"max_drawdown":-8.0,"sharpe":1.83,"profit_factor":1.89,"total_trades":315})
    m.write_text(json.dumps(metrics,indent=2)+"\n",encoding="utf-8")
    with t.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["timestamp","side","entry_price","exit_price","pnl"]); w.writeheader(); w.writerow({"timestamp":"2026-01-01T00:00:00Z","side":"LONG","entry_price":100,"exit_price":105,"pnl":5000})
    with e.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["timestamp","equity"]); w.writeheader(); w.writerow({"timestamp":"2026-01-01T00:00:00Z","equity":1000000}); w.writerow({"timestamp":"2026-01-01T00:05:00Z","equity":1005000})
    return 0
if __name__=="__main__": raise SystemExit(main())
