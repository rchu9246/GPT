"""Frozen post-review exposure control, independent of the V1 registry/engine.

No parameter tuning: use the challenger's known T-close gross target, distribute
it equally over its same ranked top-N basket, retain its cost/lot/band rules.
Realized exposure differences are measured rather than assumed equal.
"""
from hashlib import sha256
from pathlib import Path
from statistics import median
from .research import DataBlocked, costs, metrics, targets as source_targets


def targets(market,session,spec,hypothesis):
    original=source_targets(market,session,spec,hypothesis)
    if not original:return {}
    gross=sum(original.values())
    return {symbol:gross/len(original) for symbol in original}


def simulate_matched(market,spec,sessions,hypothesis='H2_TREND_MOMENTUM',stress=1.0):
    if not sessions or sessions!=sorted(set(sessions)): raise DataBlocked('INVALID_TEST_SESSIONS')
    indexes=[market.sessions.index(d) for d in sessions]
    if any(b!=a+1 for a,b in zip(indexes,indexes[1:])):
        raise DataBlocked('MISSING_INTERMEDIATE_SESSION')
    cash=1_000_000.0; holdings={}; pending=None; previous=None
    fees=notional=0.0;fills=[];curve=[];peak=cash;max_concentration=0
    for session in sessions:
        day=market.rows[session]
        if any(s not in day for s in holdings): raise DataBlocked('MISSING_HELD_PRICE_OR_DELISTING_SETTLEMENT')
        if pending:
            signal,wanted,capacities=pending
            if not signal<session: raise DataBlocked('SAME_DAY_FILL_FORBIDDEN')
            equity=cash+sum(float(day[s].open)*q for s,q in holdings.items())
            quantities={}
            for s in set(holdings)|set(wanted):
                if s not in day:
                    if s in holdings: raise DataBlocked('MISSING_HELD_OPEN')
                    continue
                target=int(equity*wanted.get(s,0)/float(day[s].open)//spec.lot)*spec.lot
                old=holdings.get(s,0)
                delta=target-old
                if wanted and abs(delta*float(day[s].open)/equity)<spec.turnover_band: continue
                capacity=int(capacities.get(s,0)*spec.participation//spec.lot)*spec.lot
                quantities[s]=max(-capacity,min(delta,capacity))
            # Sales release cash before purchases; daily volume is never used to size at the open.
            for s,q in sorted(quantities.items(),key=lambda kv:(kv[1]>0,kv[0])):
                if not q: continue
                price=float(day[s].open)
                if q>0:
                    while q>0 and q*price+costs(q*price,'BUY',spec,stress)>cash:
                        q-=spec.lot
                if not q:continue
                amount=abs(q)*price;fee=costs(amount,'BUY' if q>0 else 'SELL',spec,stress)
                cash-=q*price+fee;fees+=fee;notional+=amount
                holdings[s]=holdings.get(s,0)+q
                if not holdings[s]: del holdings[s]
                if cash < -1e-6 or any(v<0 for v in holdings.values()): raise DataBlocked('ACCOUNTING_UNDERFLOW')
                fills.append(dict(signal_date=signal.isoformat(),execution_date=session.isoformat(),symbol=s,
                    quantity=q,actual_open=price,cost=fee,observation_id=day[s].provider_observation_id))
            pending=None
        equity=cash+sum(float(day[s].close)*q for s,q in holdings.items())
        if equity<=0:raise DataBlocked('INSOLVENT')
        peak=max(peak,equity)
        concentration=max((float(day[s].close)*q/equity for s,q in holdings.items()),default=0)
        max_concentration=max(max_concentration,concentration)
        curve.append(dict(date=session.isoformat(),equity=equity,cash=cash,fees=fees))
        due=previous is None or ((session.year,session.month)!=(previous.year,previous.month) if spec.frequency=='MONTHLY' else session.isocalendar()[:2]!=previous.isocalendar()[:2])
        # Defensive exits can occur between rebalances, but still only at a subsequent actual open.
        drawdown_exit=1-equity/peak>0.25
        if due or drawdown_exit:
            wanted={} if drawdown_exit else targets(market,session,spec,hypothesis)
            capacities={s:median([b.volume for b in market.history(s,session)[-20:]])
                        for s in set(holdings)|set(wanted)}
            pending=(session,wanted,capacities)
        previous=session
    result=metrics(curve,[market.benchmark[d] for d in sessions],notional,fees,fills)
    result.update(strategy_id=spec.strategy_id,fingerprint=spec.fingerprint,account_id=spec.account_id,
        start=sessions[0].isoformat(),end=sessions[-1].isoformat(),max_concentration=max_concentration,
        concentration_gate=max_concentration<=0.25,curve=curve,fills=fills,
        mode='RETROSPECTIVE_PRICE_DIAGNOSTIC',promotion_eligible=False,forward_sessions=0)
    digest=sha256(Path(__file__).read_text(encoding='utf-8-sig').replace('\r\n','\n').encode()).hexdigest()
    result['source_spec_fingerprint']=spec.fingerprint
    result['fingerprint']=sha256((spec.fingerprint+'|'+digest).encode()).hexdigest()
    result['account_id']='V101_EXPOSURE_CONTROL_'+result['fingerprint'][:24]
    result['strategy_id']=spec.strategy_id+'_EXPOSURE_CONTROL_V1'
    result['control_implementation_sha256']=digest
    return result
