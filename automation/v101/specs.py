"""Frozen hypotheses. A new fingerprint requires a new independent account."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

def implementation_digest():
    root=Path(__file__).parent
    return sha256(b"".join((root/name).read_text(encoding="utf-8-sig").replace("\r\n","\n").encode() for name in ("specs.py","research.py","forward.py"))).hexdigest()

@dataclass(frozen=True)
class Spec:
    strategy_id: str
    volatility_managed: bool
    regime_filter: bool
    turnover_band: float
    frequency: str = 'MONTHLY'
    top_n: int = 10
    lookback: int = 60
    volatility_window: int = 20
    target_annual_vol: float = 0.12
    max_weight: float = 0.20
    max_exposure: float = 0.90
    lot: int = 1000
    participation: float = 0.01
    commission: float = 0.001425
    minimum_commission: float = 20.0
    sell_tax: float = 0.003
    slippage: float = 0.001
    code_contract: str = 'V101_PIT_CLOSE_NEXT_OPEN_V1'

    @property
    def fingerprint(self):
        return sha256(json.dumps(dict(asdict(self),implementation_sha256=implementation_digest()),sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @property
    def account_id(self):
        return 'V101_RESEARCH_' + sha256((self.strategy_id+'|'+self.fingerprint).encode()).hexdigest()[:24]

SPECS = (
    Spec('V101_VOL_MOMENTUM_V1',True,False,0.0),
    Spec('V101_REGIME_VOL_V1',True,True,0.0),
    Spec('V101_REGIME_VOL_BAND_V1',True,True,0.03),
)
# Same-period reimplementation control, not a rewrite of any frozen V10 account.
CONTROL = Spec('V101_CONTROL_EQUAL_MOMENTUM_V1',False,False,0.0)
MIN_FORWARD_DAYS = 60
PAPER_ONLY = True
REAL_MONEY_TRADING_ENABLED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
PROMOTION_ENABLED = False

def registry():
    return {'contract':'V101_FROZEN_RESEARCH_REGISTRY_V1','paper_only':True,
            'promotion_enabled':False,'minimum_forward_days':MIN_FORWARD_DAYS,
            'implementation_sha256':implementation_digest(),
            'strategies':[dict(asdict(s),fingerprint=s.fingerprint,account_id=s.account_id) for s in (*SPECS,CONTROL)]}
