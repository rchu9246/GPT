"""Official reference-event inventory and fail-closed entitlement coverage audit.

A reference-price adjustment is never converted into an invented dividend,
payment date, publication timestamp, share ratio, or delisting proceeds.
"""
from dataclasses import dataclass
from datetime import date,datetime,timezone,timedelta
from decimal import Decimal
from hashlib import sha256
import json,re
from urllib.parse import urlparse
from .research import DataBlocked

OFFICIAL_HOSTS={'www.twse.com.tw','wwwc.twse.com.tw','mops.twse.com.tw'}
KINDS=('CASH_DIVIDEND','STOCK_DIVIDEND','SPLIT','RIGHTS','DELIST_SETTLEMENT')

def aware(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise DataBlocked('PUBLICATION_TIMEZONE_MISSING')
    return t

def roc_date(value):
    m=re.fullmatch(r'(\d+)年(\d+)月(\d+)日',value)
    if not m:raise DataBlocked('UNKNOWN_OFFICIAL_DATE_FORMAT')
    y,m,d=map(int,m.groups());return date(y+1911,m,d)

@dataclass(frozen=True)
class Snapshot:
    url:str
    retrieved_at:str
    body:bytes
    digest:str

    def verify(self):
        url=urlparse(self.url)
        if url.scheme!='https' or url.hostname not in OFFICIAL_HOSTS or url.username or url.password or url.port not in (None,443):
            raise DataBlocked('UNTRUSTED_CORPORATE_ACTION_SOURCE')
        if sha256(self.body).hexdigest()!=self.digest:raise DataBlocked('SOURCE_DIGEST_MISMATCH')
        if aware(self.retrieved_at)>datetime.now(timezone.utc):raise DataBlocked('FUTURE_SOURCE_CAPTURE')

    def reference_inventory(self):
        self.verify()
        if urlparse(self.url).path!='/rwd/zh/exRight/TWT49U':
            raise DataBlocked('UNSUPPORTED_REFERENCE_SOURCE_SCHEMA')
        payload=json.loads(self.body)
        if payload.get('stat')!='OK':raise DataBlocked('OFFICIAL_REFERENCE_FEED_NOT_OK')
        fields=payload.get('fields',[])
        expected={0:'資料日期',1:'股票代號',5:'權值+息值',6:'權/息'}
        if any(i>=len(fields) or fields[i]!=name for i,name in expected.items()):
            raise DataBlocked('OFFICIAL_REFERENCE_SCHEMA_CHANGED')
        rows=[];seen=set()
        for line in payload.get('data',[]):
            if len(line)!=len(fields):raise DataBlocked('OFFICIAL_REFERENCE_ROW_TRUNCATED')
            ex=roc_date(line[0]);symbol=line[1];kind=line[6]
            if kind not in {'息','權','權息'}:raise DataBlocked('UNKNOWN_REFERENCE_EVENT_KIND')
            adjustment=Decimal(line[5].replace(',',''))
            if not adjustment.is_finite():raise DataBlocked('INVALID_REFERENCE_ADJUSTMENT')
            key=(symbol,ex.isoformat(),kind)
            if key in seen:raise DataBlocked('DUPLICATE_REFERENCE_EVENT')
            seen.add(key)
            rows.append(dict(symbol=symbol,ex_date=ex.isoformat(),reference_kind=kind,
                reference_adjustment=str(adjustment),source_sha256=self.digest,
                # Retrieval time is NOT a historical publication timestamp.
                retrieved_at=self.retrieved_at,announced_at=None,payment_date=None,
                entitlement_verified=False,source_url=self.url))
        return rows

@dataclass(frozen=True)
class Entitlement:
    """Normalized terms for deterministic settlement tests, not admission proof."""
    event_id:str
    symbol:str
    kind:str
    announced_at:str
    available_at:str
    ex_date:date
    settlement_date:date
    cash_per_share:Decimal=Decimal(0)
    share_multiplier:Decimal=Decimal(1)
    subscription_price:Decimal=Decimal(0)

    def validate(self,as_of):
        if as_of.tzinfo is None:raise DataBlocked('ASOF_TIMEZONE_MISSING')
        if self.kind not in KINDS:raise DataBlocked('UNSUPPORTED_ACTION_KIND')
        if not self.event_id or not self.symbol:raise DataBlocked('ACTION_ID_OR_SYMBOL_MISSING')
        announced=aware(self.announced_at);available=aware(self.available_at)
        if announced>available or available>as_of:raise DataBlocked('ACTION_NOT_POINT_IN_TIME_AVAILABLE')
        # Announcement must precede the event day; intraday cases need a finer calendar.
        if announced.astimezone(timezone(timedelta(hours=8))).date()>=self.ex_date:raise DataBlocked('LATE_ACTION_ANNOUNCEMENT')
        if self.settlement_date<self.ex_date:raise DataBlocked('PAYMENT_PRECEDES_ENTITLEMENT')
        amounts=(self.cash_per_share,self.share_multiplier,self.subscription_price)
        if any(not x.is_finite() or x<0 for x in amounts):raise DataBlocked('INVALID_ACTION_AMOUNT')
        if self.kind in {'STOCK_DIVIDEND','SPLIT','RIGHTS'} and self.share_multiplier<=0:
            raise DataBlocked('INVALID_SHARE_MULTIPLIER')
        if self.kind=='SPLIT' and self.settlement_date!=self.ex_date:
            raise DataBlocked('SPLIT_EFFECTIVE_DATE_AMBIGUOUS')

class EntitlementBook:
    """Cash and receivables stay separate. Rights never auto-subscribe."""
    def __init__(self):self.claims={};self.paid=set()

    def accrue(self,event,shares_before_ex,session,as_of):
        event.validate(as_of)
        if session!=event.ex_date or shares_before_ex<0:raise DataBlocked('INVALID_ENTITLEMENT_SNAPSHOT')
        if event.kind=='RIGHTS':raise DataBlocked('RIGHTS_ELECTION_AND_FINANCING_EVIDENCE_REQUIRED')
        body=(event,shares_before_ex)
        if event.event_id in self.claims:
            if self.claims[event.event_id]!=body:raise DataBlocked('CONFLICTING_ACTION_REPLAY')
            return
        quantity=Decimal(shares_before_ex)*(event.share_multiplier-1)
        if event.kind in {'STOCK_DIVIDEND','SPLIT'} and quantity!=quantity.to_integral_value():
            raise DataBlocked('FRACTIONAL_SHARE_CASH_IN_LIEU_TERMS_REQUIRED')
        self.claims[event.event_id]=body

    def receivable(self,session):
        return sum((Decimal(q)*e.cash_per_share for key,(e,q) in self.claims.items()
            if key not in self.paid and e.ex_date<=session),Decimal(0))

    def settle(self,session):
        cash=Decimal(0);shares={};retired={}
        for key,(event,q) in self.claims.items():
            if key in self.paid or event.settlement_date>session:continue
            cash+=Decimal(q)*event.cash_per_share
            if event.kind in {'STOCK_DIVIDEND','SPLIT'}:
                shares[event.symbol]=shares.get(event.symbol,0)+int(Decimal(q)*(event.share_multiplier-1))
            if event.kind=='DELIST_SETTLEMENT':retired[event.symbol]=retired.get(event.symbol,0)+q
            self.paid.add(key)
        return dict(cash=cash,share_delta=shares,retired_shares=retired)

def holding_coverage(results,inventory,coverage_start,coverage_end):
    """Audit actual holdings immediately before ex-open, not candidate lists."""
    affected=[];gaps=[];audited=0
    for result in results:
        if result.get('status')=='BLOCKED':continue
        start=date.fromisoformat(result['start']);end=date.fromisoformat(result['end'])
        if start<coverage_start or end>coverage_end:
            gaps.append(dict(reason='REFERENCE_DATE_COVERAGE_GAP',strategy_id=result['strategy_id']))
        fills=result['fills'];held={}
        events={}
        for item in inventory:
            ex=date.fromisoformat(item['ex_date'])
            if start<=ex<=end:events.setdefault(ex,[]).append(item)
        for session in sorted(set(events)|{date.fromisoformat(f['execution_date']) for f in fills}):
            # Event entitlement precedes buys/sells on ex-date.
            for event in events.get(session,[]):
                q=held.get(event['symbol'],0)
                if q>0:
                    affected.append(dict(strategy_id=result['strategy_id'],fold=result.get('fold'),
                        stress=result.get('stress'),symbol=event['symbol'],ex_date=event['ex_date'],shares=q))
                    gaps.append(dict(reason='HELD_ACTION_TERMS_OR_ASOF_PROOF_MISSING',strategy_id=result['strategy_id'],
                        symbol=event['symbol'],ex_date=event['ex_date']))
            for f in fills:
                if date.fromisoformat(f['execution_date'])==session:
                    held[f['symbol']]=held.get(f['symbol'],0)+f['quantity']
                    if held[f['symbol']]<0:raise DataBlocked('SHORT_HOLDING_IN_COVERAGE_AUDIT')
        audited+=1
    # A reference table cannot prove absent split/rights/delist events or a complete
    # no-event interval. Zero observed intersections is NEVER a completeness pass.
    missing=['ANNOUNCEMENT_AND_ASOF_ARCHIVE','CASH_PAYMENT_AND_RECORD_DATES',
             'STOCK_DELIVERY_SPLIT_RIGHTS_TERMS','DELISTING_SETTLEMENT',
             'NEGATIVE_EVENT_COVERAGE_ATTESTATION']
    return dict(status='BLOCKED',audited_scenarios=audited,affected_intersections=affected,
        holding_gaps=gaps,global_missing_evidence=missing,promotion_eligible=False,
        forward_ready=False,reference_events=len(inventory))
