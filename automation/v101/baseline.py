"""Read-only reproduction of immutable V10 accounts; Decimal reconciliation."""
from decimal import Decimal as D
from pathlib import Path
import hashlib
import json
from zipfile import ZipFile
from automation.v10.ledger import AppendOnlyLedger, replay_account

ARTIFACT_SHA256 = 'e4549609dc3a0f55cc7aead92e53838bfb64566bf5bed4fca7c1eb04c02977c9'
ARTIFACT_RUN = 41494044022
ARTIFACT_ID = 13164239769

def tree_hashes(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob('*')) if p.is_file()}

def audit(root, archive):
    root=Path(root); before=tree_hashes(root)
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest()!=ARTIFACT_SHA256:
        raise ValueError('ARTIFACT_DIGEST_MISMATCH')
    with ZipFile(archive) as z:
        entries=[i for i in z.infolist() if not i.is_dir()]
        if any(Path(i.filename).is_absolute() or '..' in Path(i.filename).parts for i in entries):
            raise ValueError('UNSAFE_ARTIFACT_PATH')
        if len({i.filename for i in entries})!=len(entries):
            raise ValueError('DUPLICATE_ARTIFACT_ENTRY')
        expected={i.filename:hashlib.sha256(z.read(i)).hexdigest() for i in entries}
    if before!=expected:raise ValueError('EXTRACTED_TREE_DOES_NOT_MATCH_IMMUTABLE_ZIP')
    report=json.loads((root/'dashboard_report.json').read_text(encoding='utf-8'))
    registry=json.loads((root/'strategy_registry.json').read_text(encoding='utf-8'))
    if len(registry['strategies'])!=18 or len(report['strategies'])!=18:
        raise ValueError('ORIGINAL_ACCOUNT_COUNT_CHANGED')
    # Verify benchmark chain as well as each account hash chain.
    AppendOnlyLedger.load(root/'benchmark.jsonl')
    days={p.stem:json.loads(p.read_text()) for p in (root/'market_evidence').glob('*.json')}
    summaries=[]
    for account in report['strategies']:
        ledger=AppendOnlyLedger.load(root/'accounts'/(account['account_id']+'.jsonl'))
        curves=[]
        for point in account['curve']:
            session=point['date']; bars={r['symbol']:D(r['close']) for r in days[session]['bars']}
            events=[e for e in ledger.events if e.event_date.isoformat()<=session]
            state=replay_account(events,D('1000000'))
            market=sum((bars[s]*q for s,q in state.positions),D(0))
            equity=state.cash+market
            if abs(equity-D(point['equity']))>D('0.000001'):
                raise ValueError('DAILY_EQUITY_RECONCILIATION_FAILED:'+account['strategy_id'])
            curves.append(equity)
        state=replay_account(ledger.events,D('1000000'))
        prices={r['symbol']:D(r['close']) for r in days[report['data_date']]['bars']}
        unrealized=sum(((prices[s]-dict(state.average_costs)[s])*q for s,q in state.positions),D(0))
        equity=state.cash+sum((prices[s]*q for s,q in state.positions),D(0))
        pnl=state.realized_pnl+unrealized-state.fees
        checks=(equity-D('1000000')-pnl, state.cash-D(account['cash']),
                equity-D(account['equity']), state.fees-D(account['transaction_cost_cumulative']),
                state.realized_pnl-D(account['realized_pnl']), unrealized-D(account['unrealized_pnl']))
        if any(abs(x)>D('0.000001') for x in checks):
            raise ValueError('ACCOUNTING_RECONCILIATION_FAILED')
        peak=D('1000000'); drawdown=D(0)
        for value in curves:
            peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
        fills=[dict(e.payload) for e in ledger.events if e.event_type=='PAPER_FILL']
        summaries.append(dict(strategy_id=account['strategy_id'],equity=str(equity),cash=str(state.cash),
            realized_pnl=str(state.realized_pnl),unrealized_pnl=str(unrealized),fees=str(state.fees),
            net_pnl=str(pnl),net_return=float(equity/D('1000000')-1),max_drawdown=float(drawdown),
            excess_return=float(account['excess_return']),sharpe=float(account['sharpe']),
            turnover=float(account['turnover']),samples=len(curves),fills=len(fills),
            data_date=report['data_date'],freshness_at_capture=report['data_freshness'],reconciled=True))
    if tree_hashes(root)!=before: raise RuntimeError('SEALED_DATA_CHANGED')
    total=sum((D(x['net_pnl']) for x in summaries),D(0))
    return dict(run_id=ARTIFACT_RUN,artifact_id=ARTIFACT_ID,zip_sha256=ARTIFACT_SHA256,
        source_tree_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        accounts=summaries,account_count=18,aggregate_independent_notional='18000000',
        aggregate_pnl=str(total),aggregate_return=float(total/D('18000000')),
        profitable_accounts=sum(D(x['net_pnl'])>0 for x in summaries),
        benchmark_return=float(report['strategies'][0]['benchmark_return']),
        data_date=report['data_date'],forward_days=report['forward_trading_days'],
        sealed_source_unchanged=True,promotion_eligible=False,
        limitation='18 independent accounts, not one portfolio; preliminary 18-day forward evidence.')
