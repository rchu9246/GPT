"""Chronological, net-cost research on actual daily OHLCV. Never broker capable."""
from bisect import bisect_right
from dataclasses import asdict, replace
from datetime import date
from hashlib import sha256
import gzip
import json
import math
from pathlib import Path
from statistics import mean, pstdev, median
from automation.v10.forward_validation import ForwardMarketData
from .specs import SPECS, CONTROL, Spec

class DataBlocked(ValueError): pass

class Market:
    def __init__(self, days, expected_end=None):
        if not days: raise DataBlocked('EMPTY_FEED')
        dates=[x['date'] for x in days]
        if len(set(dates))!=len(dates): raise DataBlocked('DUPLICATE_SESSION')
        if any(date.fromisoformat(x)>date.today() for x in dates): raise DataBlocked('FUTURE_FEED')
        self.days=sorted(days,key=lambda x:x['date'])
        if expected_end and self.days[-1]['date']!=expected_end: raise DataBlocked('STALE_FEED')
        for d in self.days:
            if not d.get('source_sha256') or not d.get('bars') or float(d.get('benchmark') or 0)<=0:
                raise DataBlocked('INCOMPLETE_FEED')
            symbols=[r['symbol'] for r in d['bars']]
            if len(set(symbols))!=len(symbols): raise DataBlocked('DUPLICATE_SYMBOL')
        self.forward=ForwardMarketData(self.days)
        self.sessions=sorted(self.forward.days)
        self.rows=self.forward.bars_by_date
        self.benchmark={date.fromisoformat(d['date']):float(d['benchmark']) for d in self.days}
        self._rank={}

    def history(self,symbol,through):
        return [b for b in self.forward.history.get(symbol,[]) if b.session_date<=through]

    def ranked(self,session,hypothesis='H2_TREND_MOMENTUM'):
        key=(session,hypothesis)
        if key not in self._rank:
            from automation.v10.factors import HYPOTHESIS_WEIGHTS
            eligible,_=self.forward.eligibility(session)
            # Existing eligibility is computed from this day's full official security table,
            # not an intersection of survivors at the end of the sample.
            factors=self.forward.normalized_factors(session,eligible)
            weights=HYPOTHESIS_WEIGHTS[hypothesis]
            self._rank[key]=sorted(eligible,key=lambda s:(-sum(float(factors[s][k])*float(v) for k,v in weights.items()),s))
        return self._rank[key]

    def manifest(self):
        return dict(first_session=self.sessions[0].isoformat(),last_session=self.sessions[-1].isoformat(),
            sessions=len(self.sessions),source='TWSE_MI_INDEX_ALLBUT0999',
            source_hashes=[dict(date=d['date'],source_sha256=d['source_sha256']) for d in self.days],
            corporate_actions_complete=False,
            limitation='Unadjusted daily prices; complete cash-dividend, split and delisting settlement evidence is unavailable. Diagnostic price-return results cannot qualify promotion.')

def costs(notional,side,spec,stress=1.0):
    commission=max(spec.minimum_commission,notional*spec.commission*stress)
    tax=notional*spec.sell_tax if side=='SELL' else 0.0
    slippage=notional*spec.slippage*stress
    return commission+tax+slippage

def targets(market,session,spec,hypothesis='H2_TREND_MOMENTUM'):
    if bisect_right(market.sessions,session)<spec.lookback: return {}
    ranked=market.ranked(session,hypothesis)[:spec.top_n]
    if not ranked: return {}
    benchmark=[market.benchmark[d] for d in market.sessions if d<=session][-spec.lookback:]
    if spec.regime_filter and benchmark[-1]<=mean(benchmark): return {}
    raw={}
    for s in ranked:
        hist=market.history(s,session)[-spec.volatility_window-1:]
        returns=[float(b.close/a.close)-1 for a,b in zip(hist,hist[1:])]
        vol=pstdev(returns)*math.sqrt(252) if len(returns)>1 else 0
        raw[s]=1/max(vol,0.05) if spec.volatility_managed else 1.0
    exposure=spec.max_exposure
    if spec.volatility_managed:
        returns=[b/a-1 for a,b in zip(benchmark[-21:],benchmark[-20:])]
        vol=pstdev(returns)*math.sqrt(252)
        exposure=min(exposure,spec.target_annual_vol/max(vol,0.05))
    denominator=sum(raw.values())
    return {s:min(spec.max_weight,exposure*v/denominator) for s,v in raw.items()}

def metrics(curve,benchmark,notional,fees,fills):
    values=[1_000_000.0]+[p['equity'] for p in curve]
    changes=[b/a-1 for a,b in zip(values,values[1:])]
    peak=values[0];dd=0
    for v in values:
        peak=max(peak,v);dd=max(dd,1-v/peak)
    vol=pstdev(changes) if len(changes)>1 else 0
    net=values[-1]/values[0]-1
    bm=benchmark[-1]/benchmark[0]-1
    return dict(net_return=net,benchmark_return=bm,excess_return=net-bm,max_drawdown=dd,
        sharpe=mean(changes)/vol*math.sqrt(252) if vol else None,
        turnover=notional/mean(values),fees=fees,trade_count=len(fills),samples=len(curve),
        sharpe_annualization='252; unstable for short samples, zero risk-free assumption',
        turnover_definition='gross traded notional / mean equity',accounting_reconciled=True)

def simulate(market,spec,sessions,hypothesis='H2_TREND_MOMENTUM',stress=1.0):
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
    return result

def folds(sessions):
    # Fixed anchored training, five-session embargo, disjoint 30-session tests.
    if len(sessions)<190: return []
    output=[]
    cursor=100
    final_start=len(sessions)-30
    while cursor+5+30<=final_start:
        output.append(dict(name='WF_'+str(len(output)+1),train=sessions[:cursor],embargo=sessions[cursor:cursor+5],test=sessions[cursor+5:cursor+35]))
        cursor+=35
    output.append(dict(name='FINAL_HOLDOUT',train=sessions[:final_start-5],embargo=sessions[final_start-5:final_start],test=sessions[final_start:]))
    return output

def evaluate(market):
    from automation.v10.factors import HYPOTHESIS_WEIGHTS
    controls=[(replace(CONTROL,strategy_id=f'V101_MATCHED_{h}_TOP{n}_{freq}_V1',
                       top_n=n,frequency=freq),h) for h in HYPOTHESIS_WEIGHTS
              for n in (5,10,20) for freq in ('WEEKLY','MONTHLY')]
    specs=[(s,'H2_TREND_MOMENTUM') for s in (*SPECS,CONTROL)]+controls
    output=[]
    for fold in folds(market.sessions):
        for spec,hypothesis in specs:
            for stress in (1.0,2.0):
                try:
                    r=simulate(market,spec,fold['test'],hypothesis=hypothesis,stress=stress)
                    output.append(dict(fold=fold['name'],stress=stress,family='MATCHED_V10_CONTROL' if 'MATCHED_' in spec.strategy_id else 'V101',**r))
                except DataBlocked as e:
                    output.append(dict(fold=fold['name'],strategy_id=spec.strategy_id,stress=stress,status='BLOCKED',reason=str(e)))
    return dict(contract='V101_RESEARCH_COMPARISON_V1',paper_only=True,promotion_enabled=False,
        forward_sessions=0,mode='RETROSPECTIVE_PRICE_DIAGNOSTIC',
        blockers=['CORPORATE_ACTIONS_NOT_VERIFIED','FORWARD_OBSERVATION_BELOW_60',
                  'HISTORICAL_RESEARCH_DESIGNED_AFTER_SAMPLE_PERIOD'],
        market=market.manifest(),folds=[dict(name=f['name'],train_end=f['train'][-1].isoformat(),
            embargo=[d.isoformat() for d in f['embargo']],test_start=f['test'][0].isoformat(),test_end=f['test'][-1].isoformat()) for f in folds(market.sessions)],results=output)

def load_cache(cache):
    days=[]
    for path in sorted(Path(cache).glob('*.json.gz')):
        with gzip.open(path,'rt',encoding='utf-8') as f: day=json.load(f)
        if day.get('bars') and day.get('benchmark'):days.append(day)
    return days

def write_once(path,payload):
    path=Path(path);text=json.dumps(payload,sort_keys=True,indent=2,allow_nan=False)+'\n'
    if path.exists():
        if path.read_text(encoding='utf-8')!=text: raise DataBlocked('REPLAY_OR_FINGERPRINT_CONFLICT')
        return
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
