"""Post-review attribution, executable paired controls and opportunity cost.

The benchmark index is not an executable asset. Its matched-exposure series is
an attribution counterfactual, never a fill stream or promotion evidence.
"""
from dataclasses import asdict
from datetime import date
from hashlib import sha256
from pathlib import Path
from statistics import mean
import json
from .research import folds,simulate,metrics,DataBlocked
from .specs import SPECS
from .paired_controls import simulate_matched

EXPOSURE_TOLERANCE=0.01
MIN_ACTIVE_SESSIONS=10

def compounded(values):
    value=1.0
    for r in values:value*=1+r
    return value-1

def exposures(result):
    return [max(0.0,1-p['cash']/p['equity']) for p in result['curve']]

def attribution(result,market):
    curve=result['curve'];exposure=exposures(result)
    index=[market.benchmark[date.fromisoformat(p['date'])] for p in curve]
    index_returns=[0.0]+[b/a-1 for a,b in zip(index,index[1:])]
    # The risk budget is yesterday's observed close exposure; never today's
    # exposure inferred using tomorrow's return. This does not model index fills.
    lagged=[0.0]+exposure[:-1]
    matched=[e*r for e,r in zip(lagged,index_returns)]
    gross_stock=[];previous=1_000_000.0;previous_fees=0.0
    for p in curve:
        gross_stock.append((p['equity']-previous+p['fees']-previous_fees)/previous)
        previous=p['equity'];previous_fees=p['fees']
    bm=compounded(index_returns);matched_return=compounded(matched)
    return dict(mode='NON_TRADABLE_LAGGED_CLOSE_EXPOSURE_ATTRIBUTION',
        strategy_net_return=result['net_return'],strategy_gross_return=compounded(gross_stock),
        strategy_cost=result['fees'],cash_return=0.0,benchmark_gross_return=bm,
        matched_index_gross_return=matched_return,
        cash_opportunity_gap=bm-matched_return,
        rising_market=bm>0,mean_observed_exposure=mean(exposure),
        zero_exposure_sessions=sum(e<=1e-9 for e in exposure),
        active_sessions=sum(e>EXPOSURE_TOLERANCE for e in exposure),
        gross_residual_not_alpha=compounded(gross_stock)-matched_return,
        control_cost_assumption='Index attribution has no executable trade cost; never compare as a certified net-cost traded control.',
        limitations=['Index has no certified tradable opening price','Prior-close risk budget differs from intraday/open exposure',
                      'Unadjusted prices and corporate actions remain unverified','No statistical alpha inference'])

def compare_exposure(a,b):
    if [p['date'] for p in a['curve']]!=[p['date'] for p in b['curve']]:raise DataBlocked('PAIRED_DATES_DIVERGE')
    ea,eb=exposures(a),exposures(b);gaps=[abs(x-y) for x,y in zip(ea,eb)]
    active=sum(max(x,y)>EXPOSURE_TOLERANCE for x,y in zip(ea,eb))
    matched=max(gaps,default=0)<=EXPOSURE_TOLERANCE
    return dict(status='MATCHED_DIAGNOSTIC_ONLY' if matched and active>=MIN_ACTIVE_SESSIONS else
                     ('CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS' if active<MIN_ACTIVE_SESSIONS else 'EXPOSURE_NOT_MATCHED'),
        max_absolute_exposure_gap=max(gaps,default=0),mean_absolute_exposure_gap=mean(gaps),
        tolerance=EXPOSURE_TOLERANCE,minimum_active_sessions=MIN_ACTIVE_SESSIONS,active_sessions=active,
        net_return_difference=a['net_return']-b['net_return'],
        control_net_return=b['net_return'],control_max_drawdown=b['max_drawdown'],control_fees=b['fees'],
        promotion_eligible=False)

def analyze(market):
    rows=[];detailed=[]
    for fold in folds(market.sessions):
        for spec in SPECS:
            for stress in (1.0,2.0):
                base=dict(fold=fold['name'],strategy_id=spec.strategy_id,stress=stress)
                try:
                    original=simulate(market,spec,fold['test'],stress=stress)
                    control=simulate_matched(market,spec,fold['test'],stress=stress)
                    rows.append(dict(**base,attribution=attribution(original,market),
                        paired_control=compare_exposure(original,control)))
                    detailed.extend([dict(fold=fold['name'],stress=stress,**original),
                                     dict(fold=fold['name'],stress=stress,**control)])
                except DataBlocked as error:rows.append(dict(**base,status='BLOCKED',reason=str(error)))
    return dict(contract='V101_POST_REVIEW_EXPOSURE_V1',rows=rows,
        parameter_selection_performed=False,forward_sessions=0,promotion_enabled=False,
        exposure_tolerance=EXPOSURE_TOLERANCE,minimum_active_sessions=MIN_ACTIVE_SESSIONS,
        source_v1_registry_unchanged=True),detailed
