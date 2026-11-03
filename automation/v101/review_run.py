"""Manual review evidence runner; original ledgers/registry and UI remain read-only."""
import argparse,json
from datetime import date
from pathlib import Path
from .actions import Snapshot,holding_coverage
from .archive import preserve
from .baseline import audit,tree_hashes
from .exposure_analysis import analyze
from .research import Market,load_cache,write_once,DataBlocked
from .specs import registry
from automation.v10.ledger import AppendOnlyLedger

def baseline_holding_scenarios(root):
    report=json.loads((root/'dashboard_report.json').read_text(encoding='utf-8'))
    rows=[]
    for account in report['strategies']:
        ledger=AppendOnlyLedger.load(root/'accounts'/(account['account_id']+'.jsonl'))
        fills=[]
        for e in ledger.events:
            if e.event_type=='PAPER_FILL':
                p=dict(e.payload)
                fills.append(dict(execution_date=e.event_date.isoformat(),symbol=p['symbol'],quantity=int(p['quantity'])))
        rows.append(dict(strategy_id=account['strategy_id'],fold='SEALED_18_DAY_FORWARD',stress=1,
            start=account['curve'][0]['date'],end=report['data_date'],fills=fills))
    return rows

def main():
    p=argparse.ArgumentParser()
    for name in ('cache','original-root','original-zip','previous-comparison','snapshot','snapshot-source','output','archive'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    source=a.original_root.resolve();output=a.output.resolve()
    if not output.name.startswith('v101_') or output==source or source in output.parents or output in source.parents:
        raise DataBlocked('INDEPENDENT_REVIEW_OUTPUT_REQUIRED')
    original_hashes=tree_hashes(source)
    frozen=json.loads(Path('config/v101_frozen_specs.json').read_text(encoding='utf-8-sig'))
    if frozen!=registry():raise DataBlocked('V1_REGISTRY_CHANGED')
    audit(source,a.original_zip)
    archive=preserve(a.original_zip,a.archive)
    meta=json.loads(a.snapshot_source.read_text(encoding='utf-8'))
    snapshot=Snapshot(body=a.snapshot.read_bytes(),**meta)
    inventory=snapshot.reference_inventory()
    market=Market(load_cache(a.cache),expected_end='2026-11-02')
    result,paired=analyze(market)
    original=json.loads(a.previous_comparison.read_text(encoding='utf-8'))
    # Source challenger scenarios already occur in the old comparison; add only
    # newly simulated paired control holdings, not duplicate challenger scenarios.
    scenarios=original['results']+[r for r in paired if '_EXPOSURE_CONTROL_' in r['strategy_id']]
    scenarios+=baseline_holding_scenarios(source)
    coverage=holding_coverage(scenarios,inventory,*snapshot.reference_range())
    write_once(output/'exposure_comparison.json',result)
    write_once(output/'private_holding_coverage.json',coverage)
    write_once(output/'private_paired_ledgers.json',paired)
    if tree_hashes(source)!=original_hashes:raise DataBlocked('SEALED_SOURCE_CHANGED')
    summary=dict(contract=result['contract'],source_v1_registry_unchanged=True,original_source_unchanged=True,
        reference_events=len(inventory),audited_holding_scenarios=coverage['audited_scenarios'],
        affected_holding_intersections=len(coverage['affected_intersections']),
        unique_affected_symbol_dates=len({(x['symbol'],x['ex_date']) for x in coverage['affected_intersections']}),
        corporate_action_gate=coverage['status'],missing_evidence=coverage['global_missing_evidence'],
        comparisons=len(result['rows']),matched_comparisons=sum(x.get('paired_control',{}).get('status')=='MATCHED_DIAGNOSTIC_ONLY' for x in result['rows']),
        source_sha256=snapshot.digest,source_url=snapshot.url,retrieved_at=snapshot.retrieved_at,
        archive_digest=archive.stem,archive_mode='LOCAL_PRIVATE_ONLY',forward_sessions=0,promotion_enabled=False)
    write_once(output/'summary.json',summary)
    lines=['# PR #22 post-review evidence','',
        'Draft retained. Original 18 accounts, V10.1 V1 frozen registry, website and production schedules are unchanged. No forward run, broker order or promotion has been started.','',
        '## Corporate-action coverage','',
        f"Official reference events: **{summary['reference_events']}**. Audited actual holding scenarios: **{summary['audited_holding_scenarios']}**. Held-event intersections: **{summary['affected_holding_intersections']}** across **{summary['unique_affected_symbol_dates']}** unique symbol/ex-date pairs. The complete per-holding audit remains private/local.",
        'All scenarios remain **BLOCKED** for certified total-return/forward eligibility. The official reference table does not provide complete historical announcement availability, record/pay dates, stock entitlement delivery, split/rights elections or delisting cash settlement. Zero intersections cannot certify a no-event period. No reference adjustment was invented as a dividend or settlement.',
        '',f"Source: [TWSE TWT49U]({snapshot.url}); retrieved {snapshot.retrieved_at}; SHA-256 `{snapshot.digest}`.",
        '', 'The adapter verifies HTTPS official-source provenance, payload digest and schema, preserves signed reference adjustments, and audits holdings immediately BEFORE the ex-open. Entitlement primitives separate receivables from cash, pay only on settlement, deliver verified stock/split terms, block unsupported rights elections, fractional-share terms and missing delisting settlement. These tested primitives do not certify missing historical fields or unlock forward.','',
        '## Exposure and rising-market diagnostics','',
        'Fixed paired control: reuse each challenger\'s known T-close gross target, divide equally over its same ranked basket; preserve next-open, whole-lot, trailing-liquidity, commission/tax/slippage and band rules. No parameters were selected using returns. Post-trade exposure must remain within **1 percentage point on every date**, with **at least 10 active sessions**, to label a matched diagnostic. Otherwise report UNMATCHED or insufficient activity. Even a match remains unverified-price research, not alpha proof.',
        '', '| Block | Challenger | Stress | Strategy net | Paired net | Max exposure gap | Pair status | TWSE gross | Cash opportunity gap* |',
        '|---|---|---:|---:|---:|---:|---|---:|---:|']
    for row in result['rows']:
        if row.get('status')=='BLOCKED':continue
        at=row['attribution'];pair=row['paired_control']
        lines.append(f"|{row['fold']}|{row['strategy_id']}|{row['stress']}|{at['strategy_net_return']*100:.4f}%|{pair['control_net_return']*100:.4f}%|{pair['max_absolute_exposure_gap']*100:.3f} pp|{pair['status']}|{at['benchmark_gross_return']*100:.4f}%|{at['cash_opportunity_gap']*100:.4f} pp|")
    lines+=['','*Cash opportunity gap is the compounded TWSE index path minus an index-return path scaled by PREVIOUS-close observed exposure. It is a non-tradable attribution control with no index fills or executable index costs, NOT an equal-cost traded comparison. Positive gap means foregone index upside; negative means avoided index downside. Cash control assumes zero interest. Stock net returns and executable paired controls include unchanged calibration-free 1x/2x commission/slippage stress and statutory tax.',
        '', '## Archival and gate','',
        'The original artifact is now preserved locally in a content-addressed, digest-verified private archive. Replays verify SHA-256 continuity and reject changed bytes. No remote archival destination has been authorized and no raw file was published. Existing CI continues to require the original artifact; expiration fails closed rather than selecting a newer run.',
        '', 'Remaining blockers: verified point-in-time corporate-action/payment/delisting evidence; sufficiently active realized-exposure matches; genuine independent 60-session forward observation after data gates pass. Historical backfill never counts as forward.']
    (output/'POST_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__':main()
