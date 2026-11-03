"""Manual-only isolated forward store. Unverified corporate actions block execution."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from .research import DataBlocked, simulate, write_once
from .specs import SPECS, registry

def root_guard(root):
    root=Path(root).resolve()
    if not root.name.startswith('v101_') or root.is_symlink():
        raise DataBlocked('V101_INDEPENDENT_STORE_REQUIRED')
    if any(p.name in {'v10_forward_store','v10-original-readonly','.git'} for p in (root,*root.parents)):
        raise DataBlocked('PROTECTED_ORIGINAL_STORE')
    return root

def run_forward(root,market,business_date,corporate_actions_verified=False):
    # There is intentionally no broker adapter, scheduler, secret or live switch.
    root=root_guard(root)
    if business_date!=date.today(): raise DataBlocked('FORWARD_BACKFILL_OR_FUTURE_FORBIDDEN')
    if market.sessions[-1]!=business_date: raise DataBlocked('STALE_FORWARD_FEED')
    if not corporate_actions_verified:
        raise DataBlocked('CORPORATE_ACTIONS_NOT_VERIFIED')
    # A boolean supplied by a caller is never sufficient evidence of actions.
    # Until a provenance-verified event adapter exists, activation is fail-closed.
    raise DataBlocked('VERIFIED_CORPORATE_ACTION_ADAPTER_NOT_AVAILABLE')

def freeze(root,start_date):
    root=root_guard(root)
    if start_date<date.today(): raise DataBlocked('HISTORICAL_FORWARD_BOUNDARY_FORBIDDEN')
    write_once(root/'registry.json',registry())
    write_once(root/'boundary.json',dict(start_date=start_date.isoformat(),mode='PAPER_RESEARCH_ONLY',
        historical_backfill_allowed=False,broker_orders_enabled=False,promotion_enabled=False))
    return root
