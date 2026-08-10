from __future__ import annotations
import argparse,csv,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--version',required=True);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--min-trades',type=int,default=20);p.add_argument('--min-equity-rows',type=int,default=30);a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    metrics=json.loads((a.raw_dir/f'{a.version}_raw_metrics.json').read_text(encoding='utf-8'))
    with (a.raw_dir/f'{a.version}_raw_trades.csv').open(encoding='utf-8-sig',newline='') as f: trades=list(csv.DictReader(f))
    with (a.raw_dir/f'{a.version}_raw_equity.csv').open(encoding='utf-8-sig',newline='') as f: equity=list(csv.DictReader(f))
    if len(trades)<a.min_trades: raise ValueError(f'{a.version}: only {len(trades)} trades; need {a.min_trades}')
    if len(equity)<a.min_equity_rows: raise ValueError(f'{a.version}: only {len(equity)} equity rows; need {a.min_equity_rows}')
    required={'total_return','max_drawdown','sharpe','profit_factor','total_trades'};missing=sorted(required-set(metrics))
    if missing: raise ValueError(f'{a.version} metrics missing: {", ".join(missing)}')
    (a.output_dir/f'{a.version}_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (a.output_dir/f'{a.version}_trades.csv').write_bytes((a.raw_dir/f'{a.version}_raw_trades.csv').read_bytes())
    (a.output_dir/f'{a.version}_equity_curve.csv').write_bytes((a.raw_dir/f'{a.version}_raw_equity.csv').read_bytes())
    (a.output_dir/f'{a.version}_production_evidence_manifest.json').write_text(json.dumps({'adapter_version':'3.4.3','version':a.version,'production_evidence':True,'trade_rows':len(trades),'equity_rows':len(equity)},indent=2)+'\n',encoding='utf-8')
if __name__=='__main__': main()
