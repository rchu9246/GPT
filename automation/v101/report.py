"""Publish only derived comparison metrics; raw accounts/market/fills stay local."""
import argparse,csv,json
from datetime import date
from pathlib import Path
from statistics import mean,median
from .research import Market,load_cache,simulate
from .specs import SPECS,CONTROL

def summarize(x):
    keys=('fold','family','stress','strategy_id','fingerprint','account_id','start','end','status','reason',
          'net_return','benchmark_return','excess_return','max_drawdown','sharpe','turnover','fees',
          'trade_count','samples','max_concentration','concentration_gate','forward_sessions','mode','promotion_eligible')
    r={k:x[k] for k in keys if k in x}
    curve=x.get('curve',[])
    r['average_exposure']=mean(1-p['cash']/p['equity'] for p in curve) if curve else None
    r['no_trade_cash_only']=x.get('trade_count')==0
    return r

def export(result,market,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=[summarize(x) for x in result['results']]
    same=[d for d in market.sessions if result['baseline']['accounts'][0]['data_date']>=d.isoformat()>= '2026-10-05']
    for s in (*SPECS,CONTROL):
        for stress in (1.0,2.0):
            rows.append(summarize(dict(fold='SEALED_FORWARD_PERIOD_REPLAY',stress=stress,
                **simulate(market,s,same,stress=stress))))
    baseline=result['baseline']
    payload=dict(contract=result['contract'],generated_at=result['generated_at'],
        data_date=result['market']['last_session'],forward_sessions=0,
        baseline_run_id=baseline['run_id'],baseline=baseline,results=rows,
        registry=result['registry'],market=result['market'],folds=result['folds'],
        blockers=result['blockers'],promotion_enabled=False,real_money_trading_enabled=False)
    (output/'comparison_summary.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for name,values in [('historical_comparison.csv',rows),('original_18_accounts.csv',baseline['accounts'])]:
        keys=sorted({k for row in values for k in row})
        with (output/name).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(values)
    pct=lambda v:f'{v*100:.4f}%'
    money=lambda v:f'{float(v):,.2f}'
    text=['# V10.1 verification and complete performance comparison','',
        '**Research-only; no promotion; no trading activation.** Historical outputs are unadjusted-price diagnostics, not validated total returns or genuine ex-ante OOS evidence. New V10.1 forward sessions: **0 / 60**.','',
        '## Reproduced immutable V10 baseline','',
        f"Run [{baseline['run_id']}](https://github.com/rchu9246/GPT/actions/runs/{baseline['run_id']}), artifact {baseline['artifact_id']}, ZIP SHA-256 `{baseline['zip_sha256']}`.",
        f"18 independent NT$1m accounts, {baseline['forward_days']} days, data through {baseline['data_date']}. Profitable accounts: {baseline['profitable_accounts']}/18. Total net PnL: NT${money(baseline['aggregate_pnl'])}; average return: {pct(baseline['aggregate_return'])}; TWSE: {pct(baseline['benchmark_return'])}.",
        'Every daily equity and final cash/equity/realized/unrealized/fee total was independently replayed from hash-verified ledgers with Decimal accounting. Source tree is unchanged. Aggregation is not one NT$18m portfolio. Freshness was CURRENT_COMPLETE_SESSION at capture, not a claim of a current live feed.','',
        '| Strategy | Equity NT$ | Cash NT$ | Realized gross | Unrealized gross | Costs | Net return | Max DD | Excess pp | Samples |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in baseline['accounts']:
        text.append('|'+ '|'.join([x['strategy_id'],money(x['equity']),money(x['cash']),money(x['realized_pnl']),money(x['unrealized_pnl']),money(x['fees']),pct(x['net_return']),pct(x['max_drawdown']),pct(x['excess_return']),str(x['samples'])])+'|')
    text+=['','## Historical design','',
        f"Official full daily TWSE tables: {len(market.sessions)} sessions, {result['market']['first_session']} to {result['market']['last_session']}. Fixed 60-session eligibility; 100-session initial expanding history, five-session embargo, three disjoint 30-session test blocks and a final 30-session block. No parameter selection was performed on any block. Source hashes and all {len(rows)} metric rows are in the companion JSON/CSV.",
        'All candidates use NT$1m independent capital, 1,000-share regular lots, actual subsequent open, maximum 1% trailing-volume participation, 0.1425% commission (NT$20 minimum), 0.3% sell tax and 10bp slippage. Stress doubles commission/slippage, not tax. Legacy matched controls reuse the 18 hypothesis/top-N/frequency combinations with these same execution/cost rules; they are not edits of sealed V10 accounts.','',
        '| Block | Training end | Embargo | Test interval |','|---|---|---|---|']
    for f in result['folds']:text.append(f"|{f['name']}|{f['train_end']}|{f['embargo'][0]} – {f['embargo'][-1]}|{f['test_start']} – {f['test_end']}|")
    text+=['','## Challenger and equal-weight control, all blocks','',
        '| Block | Strategy | Stress | Net return | Excess | Max DD | Sharpe | Turnover | Costs NT$ | Trades | Avg exposure |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in rows:
        if 'MATCHED_' in x['strategy_id']:continue
        if x.get('status')=='BLOCKED':text.append(f"|{x['fold']}|{x['strategy_id']}|{x['stress']}|BLOCKED: {x['reason']}||||||||");continue
        text.append('|'+ '|'.join([x['fold'],x['strategy_id'],str(x['stress']),pct(x['net_return']),pct(x['excess_return']),pct(x['max_drawdown']),f"{x['sharpe']:.3f}" if x['sharpe'] is not None else 'N/A',f"{x['turnover']:.3f}",money(x['fees']),str(x['trade_count']),pct(x['average_exposure'])])+'|')
    text+=['','## Interpretation and validation boundaries','',
        '- Zero-trade blocks are cash-only outcomes, not profitable strategy evidence. Whole-lot affordability and volatility scaling leave the three challengers entirely in cash during the original 18-day period. They miss substantial rising-market benchmark returns in earlier blocks. Do not call cash-only drawdown reduction alpha.',
        '- The band variant is reported as one frozen hypothesis, not selected for deployment after seeing the final block. Final-block improvements relative to an equal-weight control remain losses, are strongly exposure-dependent, and do not demonstrate statistical significance.',
        '- Complete historical corporate-action, cash-dividend payment, rights/split and delisting settlement evidence is unverified. TWSE TWT49U historical results were inspected, but reference-price adjustments alone do not establish announcement-time availability or complete cash/share entitlement settlement. Promotion and forward activation remain blocked.',
        '- New forward tracking has not started. No existing production schedule, 18-account historical ledger or V9/V10 dashboard was changed. New dashboard is a separate V10.1 route showing provenance, historical mode and no successful forward session.',
        '- Sharpe uses 252-day annualization, zero risk-free rate; 30-session estimates are unstable. Turnover is gross buys plus sells divided by mean equity. Costs include slippage. Corporate-action omissions can materially distort results.',
        '', '## Reproduction','',
        'Download artifact 13164239769 from Run 41494044022; verify the ZIP digest above; extract to an independent read-only directory. Keep raw data local.',
        '```powershell',
        'python -m automation.v101.acquire --cache local-v101-cache --start 2025-10-01 --end 2026-11-02',
        'python -m automation.v101.run --cache local-v101-cache --baseline-root v10-original-readonly --baseline-zip v10-forward.zip --output v101_research_new_run --expected-end 2026-11-02',
        'python -m automation.v101.report --comparison v101_research_new_run/comparison.json --cache local-v101-cache --output v101_summary',
        '```',
        'Repeated immutable outputs must match exactly; use a new research output directory for a new capture timestamp. A historical analysis can never be written as a forward session.']
    (output/'PERFORMANCE.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    return payload

def main():
    p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.output.resolve().name.startswith('v101_'):raise ValueError('INDEPENDENT_SUMMARY_OUTPUT_REQUIRED')
    export(json.loads(a.comparison.read_text()),Market(load_cache(a.cache)),a.output)

if __name__=='__main__':main()
