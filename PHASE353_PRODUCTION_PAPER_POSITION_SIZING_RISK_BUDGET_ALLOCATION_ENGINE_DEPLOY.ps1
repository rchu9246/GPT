#requires -Version 5.1
<#
PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET_ALLOCATION_ENGINE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.5.3 — Production Paper Position Sizing + Risk Budget Allocation Engine

Purpose
-------
Create a paper-only position-sizing and risk-budget allocation layer that sits
between canonical V9.1 signal eligibility and simulated paper order creation.

Inputs
------
  - Phase 3.5.2 paper risk-governance state
  - Latest Phase 3.5.0 performance ledger / NAV
  - Existing open paper positions
  - Persisted canonical V9.1 signals
  - Persisted real canonical market prices

Outputs
-------
  - Per-symbol target paper capital
  - Per-symbol paper quantity
  - Portfolio risk-budget utilization
  - Concentration-limit enforcement
  - Risk-reduction-factor enforcement
  - PAPER_HALT / new-entry authorization enforcement
  - Persistent allocation plan in Supabase

Canonical behavior
------------------
  Risk State                     Allocation Factor
  ------------------------------------------------
  INSUFFICIENT_HISTORY_VALID_STATE     1.00
  NORMAL                               1.00
  CAUTION                              0.75
  RISK_REDUCED                         0.50
  PAPER_HALT                           0.00

This phase NEVER submits a broker order. It only produces a paper sizing plan.

Safety boundary
---------------
  Synthetic market data: DISABLED
  Synthetic signals: DISABLED
  Fake prices: DISABLED
  Broker API: NO
  Broker credentials: NO
  Broker order submission: DISABLED
  Real-money trading: DISABLED
  Live-money release: NO
  Fail-closed: ENABLED

Created/overwritten
-------------------
  supabase/PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET.sql
  automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py
  .github/workflows/gpt-quant-v92-paper-trading-phase353-production-paper-position-sizing-risk-budget-allocation-engine.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 114) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 114) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.5.3 Production Paper Position Sizing + Risk Budget Allocation"

$repoRoot = $null
try {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repoRoot = $null
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    Fail "Run this script inside the GPT Git repository."
}

Set-Location $repoRoot
Write-Host "Repository: $repoRoot" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase352_production_paper_risk_governance_drawdown_guard_engine.py",
    "automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py",
    "supabase/PHASE352_PRODUCTION_PAPER_RISK_GOVERNANCE.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$sqlTarget = "supabase/PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET.sql"
$pythonTarget = "automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase353-production-paper-position-sizing-risk-budget-allocation-engine.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase353-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.5.3 Supabase position-sizing schema"

$sql = @'
begin;

create table if not exists public.paper_position_sizing_plans_v92 (
    plan_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    plan_date date not null,

    governance_date date not null,
    risk_state text not null,
    new_paper_entries_authorized boolean not null,
    paper_halt boolean not null,
    risk_reduction_factor numeric not null,

    nav numeric not null,
    cash numeric not null,
    current_market_value numeric not null,
    current_portfolio_exposure numeric not null,

    base_risk_budget_pct numeric not null,
    effective_risk_budget_pct numeric not null,
    max_position_pct numeric not null,
    max_new_capital numeric not null,
    total_allocated_capital numeric not null,
    remaining_risk_budget numeric not null,

    eligible_signals integer not null,
    sized_candidates integer not null,

    synthetic_market_data boolean not null default false,
    synthetic_signals boolean not null default false,
    fake_prices_allowed boolean not null default false,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_position_sizing_plans_v92_portfolio_date
    on public.paper_position_sizing_plans_v92 (portfolio_id, plan_date);

create table if not exists public.paper_position_sizing_items_v92 (
    item_id text primary key,
    plan_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    plan_date date not null,

    symbol text not null,
    rank integer,
    score numeric,
    signal text,

    real_market_price numeric not null,
    existing_position_market_value numeric not null default 0,

    raw_target_capital numeric not null,
    concentration_capital_limit numeric not null,
    risk_budget_capital_limit numeric not null,
    final_target_capital numeric not null,

    round_lot integer not null,
    paper_quantity numeric not null,
    estimated_notional numeric not null,

    allocation_state text not null,
    allocation_reason text,

    synthetic_market_data boolean not null default false,
    synthetic_signal boolean not null default false,
    fake_price boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_position_sizing_items_v92_plan_symbol
    on public.paper_position_sizing_items_v92 (plan_id, symbol);

alter table public.paper_position_sizing_plans_v92 enable row level security;
alter table public.paper_position_sizing_items_v92 enable row level security;

comment on table public.paper_position_sizing_plans_v92 is
'GPT Quant V9.2 paper-only portfolio risk-budget allocation plan. No broker execution authority.';

comment on table public.paper_position_sizing_items_v92 is
'GPT Quant V9.2 per-symbol paper position sizing output based on real canonical signals/prices and Phase 3.5.2 risk governance.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.5.3 Python position-sizing engine"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase353_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE353_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase352_production_paper_risk_governance_drawdown_guard_engine.py"
UPSTREAM_JSON = ROOT / "phase352_output/phase352_risk_governance.json"

GOVERNANCE_TABLE = "paper_risk_governance_v92"
LEDGER_TABLE = "paper_performance_ledger_v92"
POSITIONS_TABLE = "paper_positions_v92"
SIGNALS_TABLE = "paper_canonical_signals_v92"
PRICES_TABLE = "paper_canonical_market_prices_v92"

PLAN_TABLE = "paper_position_sizing_plans_v92"
ITEM_TABLE = "paper_position_sizing_items_v92"

RESULT_JSON = OUT / "phase353_position_sizing.json"

CONTRACT = "PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET_ALLOCATION_ENGINE"

BASE_RISK_BUDGET_PCT = Decimal(os.getenv("PHASE353_BASE_RISK_BUDGET_PCT", "0.60"))
MAX_POSITION_PCT = Decimal(os.getenv("PHASE353_MAX_POSITION_PCT", "0.20"))
MAX_CANDIDATES = int(os.getenv("PHASE353_MAX_CANDIDATES", "3"))
ROUND_LOT = int(os.getenv("PHASE353_ROUND_LOT", "1000"))
SCORE_THRESHOLD = Decimal(os.getenv("PHASE353_SCORE_THRESHOLD", "65"))

VALID_RISK_STATES = {
    "INSUFFICIENT_HISTORY_VALID_STATE",
    "NORMAL",
    "CAUTION",
    "RISK_REDUCED",
    "PAPER_HALT",
}


def D(v: Any) -> Decimal:
    return Decimal(str(v))


def money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def supabase() -> tuple[str, dict[str, str]]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not base or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing")

    return base, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(table: str, params: list[tuple[str, str]]) -> list[dict[str, Any]]:
    base, headers = supabase()
    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:900]}"
        )

    data = response.json()

    if not isinstance(data, list):
        raise RuntimeError(f"{table}: expected list response")

    return [x for x in data if isinstance(x, dict)]


def rest_upsert(
    table: str,
    rows: list[dict[str, Any]],
    on_conflict: str,
) -> None:
    if not rows:
        return

    base, headers = supabase()
    headers = dict(headers)
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    url = f"{base}/rest/v1/{quote(table, safe='')}"

    response = requests.post(
        url,
        headers=headers,
        params={"on_conflict": on_conflict},
        data=json.dumps(rows, ensure_ascii=False, default=str),
        timeout=25,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1200]}"
        )


def run_upstream() -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE352_PORTFOLIO_ID"] = PORTFOLIO_ID

    proc = subprocess.run(
        [sys.executable, str(UPSTREAM)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")

    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if not UPSTREAM_JSON.exists():
        raise RuntimeError(
            f"Phase 3.5.2 evidence missing; upstream exit={proc.returncode}"
        )

    return proc.returncode, load_json(UPSTREAM_JSON)


def validate_governance(data: dict[str, Any]) -> None:
    if data.get("status") != "PASS":
        raise RuntimeError("Phase 3.5.2 governance did not PASS")

    if data.get("risk_state") not in VALID_RISK_STATES:
        raise RuntimeError(f"Invalid risk_state={data.get('risk_state')!r}")

    for key in (
        "synthetic_market_data",
        "synthetic_signals",
        "fake_prices_allowed",
        "broker_api_used",
        "broker_credentials_used",
        "broker_order_submission_enabled",
        "real_money_trading_enabled",
        "live_money_release_authorized",
    ):
        if data.get(key) is not False:
            raise RuntimeError(
                f"Safety contract violation: {key}={data.get(key)!r}"
            )

    if data.get("fail_closed_policy") is not True:
        raise RuntimeError("fail_closed_policy must remain enabled")

    if data.get("paper_halt") is True and data.get("new_paper_entries_authorized") is not False:
        raise RuntimeError("PAPER_HALT cannot authorize new paper entries")


def latest_ledger() -> dict[str, Any]:
    rows = rest_get(
        LEDGER_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("order", "ledger_date.desc"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("No performance-ledger row found")

    return rows[0]


def open_positions() -> list[dict[str, Any]]:
    return rest_get(
        POSITIONS_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("status", "eq.OPEN"),
        ],
    )


def latest_signals(plan_date: str) -> list[dict[str, Any]]:
    queries = [
        [
            ("select", "*"),
            ("strategy_version", f"eq.{STRATEGY}"),
            ("trade_date", f"eq.{plan_date}"),
            ("order", "total_score.desc"),
            ("limit", str(MAX_CANDIDATES * 3)),
        ],
        [
            ("select", "*"),
            ("strategy_version", f"eq.{STRATEGY}"),
            ("signal_date", f"eq.{plan_date}"),
            ("order", "score.desc"),
            ("limit", str(MAX_CANDIDATES * 3)),
        ],
    ]

    last_error = None
    for params in queries:
        try:
            rows = rest_get(SIGNALS_TABLE, params)
            if rows:
                return rows
        except Exception as exc:
            last_error = exc

    if last_error:
        print(f"Signal source diagnostic: {last_error}", file=sys.stderr)

    return []


def signal_symbol(row: dict[str, Any]) -> str:
    return str(
        row.get("symbol")
        or row.get("stock_id")
        or ""
    ).strip()


def signal_score(row: dict[str, Any]) -> Decimal:
    value = (
        row.get("total_score")
        if row.get("total_score") is not None
        else row.get("score")
    )
    return D(value or 0)


def signal_side(row: dict[str, Any]) -> str:
    return str(
        row.get("signal")
        or row.get("side")
        or "BUY"
    ).upper()


def real_price(symbol: str, plan_date: str) -> tuple[str, Decimal]:
    candidate_params = [
        [
            ("select", "*"),
            ("symbol", f"eq.{symbol}"),
            ("trade_date", f"lte.{plan_date}"),
            ("order", "trade_date.desc"),
            ("limit", "1"),
        ],
        [
            ("select", "*"),
            ("stock_id", f"eq.{symbol}"),
            ("date", f"lte.{plan_date}"),
            ("order", "date.desc"),
            ("limit", "1"),
        ],
    ]

    for params in candidate_params:
        try:
            rows = rest_get(PRICES_TABLE, params)
        except Exception:
            continue

        if not rows:
            continue

        row = rows[0]
        date = str(
            row.get("trade_date")
            or row.get("date")
            or row.get("market_date")
            or ""
        )[:10]

        raw = (
            row.get("close")
            or row.get("close_price")
            or row.get("price")
        )

        if not date or raw is None:
            continue

        px = D(raw)

        if px > 0:
            return date, px

    raise RuntimeError(f"NO_REAL_CANONICAL_MARKET_PRICE: {symbol}")


def existing_market_value_by_symbol(
    positions: list[dict[str, Any]],
) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for p in positions:
        symbol = str(p.get("symbol") or "").strip()
        if not symbol:
            continue
        result[symbol] = D(p.get("market_value") or 0)
    return result


def floor_to_lot(capital: Decimal, price: Decimal, round_lot: int) -> Decimal:
    if price <= 0 or capital <= 0:
        return D(0)

    raw_shares = capital / price
    lots = (raw_shares / D(round_lot)).to_integral_value(rounding=ROUND_FLOOR)
    return D(lots) * D(round_lot)


def build_plan(
    governance: dict[str, Any],
    ledger: dict[str, Any],
    positions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan_date = str(ledger["ledger_date"])
    nav = D(ledger.get("nav") or 0)
    cash = D(ledger.get("cash") or 0)
    current_market_value = D(ledger.get("market_value") or 0)

    if nav <= 0:
        raise RuntimeError("NAV must be positive for position sizing")

    risk_state = str(governance["risk_state"])
    risk_factor = D(governance.get("risk_reduction_factor") or 0)

    if risk_state == "PAPER_HALT":
        risk_factor = D(0)

    if risk_factor < 0 or risk_factor > 1:
        raise RuntimeError(f"Invalid risk_reduction_factor={risk_factor}")

    current_exposure = current_market_value / nav
    effective_budget_pct = BASE_RISK_BUDGET_PCT * risk_factor

    max_total_market_value = nav * effective_budget_pct
    theoretical_new_budget = max(D(0), max_total_market_value - current_market_value)
    max_new_capital = min(cash, theoretical_new_budget)

    signals = latest_signals(plan_date)

    eligible: list[dict[str, Any]] = []

    for row in signals:
        symbol = signal_symbol(row)
        score = signal_score(row)
        side = signal_side(row)

        if not symbol:
            continue

        if side != "BUY":
            continue

        if score < SCORE_THRESHOLD:
            continue

        eligible.append(row)

    eligible.sort(
        key=lambda r: signal_score(r),
        reverse=True,
    )
    eligible = eligible[:MAX_CANDIDATES]

    existing_mv = existing_market_value_by_symbol(positions)

    # Fail-safe semantics:
    # If governance authorizes entries but there are no persisted canonical signals,
    # produce a valid zero-allocation plan. Do not manufacture signals.
    items: list[dict[str, Any]] = []

    allocation_available = (
        governance.get("new_paper_entries_authorized") is True
        and risk_state != "PAPER_HALT"
        and max_new_capital > 0
        and len(eligible) > 0
    )

    score_sum = sum((signal_score(r) for r in eligible), D(0))

    remaining_budget = max_new_capital
    concentration_capital_limit = nav * MAX_POSITION_PCT

    for rank, row in enumerate(eligible, start=1):
        symbol = signal_symbol(row)
        score = signal_score(row)
        existing = existing_mv.get(symbol, D(0))

        mark_date, price = real_price(symbol, plan_date)

        if allocation_available and score_sum > 0:
            raw_target = max_new_capital * (score / score_sum)
        else:
            raw_target = D(0)

        remaining_concentration_capacity = max(
            D(0),
            concentration_capital_limit - existing,
        )

        risk_budget_limit = max(D(0), remaining_budget)

        final_capital = min(
            raw_target,
            remaining_concentration_capacity,
            risk_budget_limit,
        )

        quantity = floor_to_lot(
            final_capital,
            price,
            ROUND_LOT,
        )

        estimated_notional = money(quantity * price)

        if governance.get("new_paper_entries_authorized") is not True:
            allocation_state = "BLOCKED_BY_RISK_GOVERNANCE"
            reason = "Phase 3.5.2 does not authorize new paper entries."
            quantity = D(0)
            estimated_notional = D(0)
            final_capital = D(0)

        elif risk_state == "PAPER_HALT":
            allocation_state = "BLOCKED_BY_PAPER_HALT"
            reason = "PAPER_HALT blocks all new paper entries."
            quantity = D(0)
            estimated_notional = D(0)
            final_capital = D(0)

        elif max_new_capital <= 0:
            allocation_state = "ZERO_AVAILABLE_RISK_BUDGET"
            reason = "No remaining portfolio risk budget/cash is available."
            quantity = D(0)
            estimated_notional = D(0)
            final_capital = D(0)

        elif quantity <= 0:
            allocation_state = "BELOW_ROUND_LOT"
            reason = "Risk-budget allocation is below one configured paper round lot."
            quantity = D(0)
            estimated_notional = D(0)

        else:
            allocation_state = "SIZED"
            reason = "Real canonical BUY signal sized within risk budget and concentration limits."

        remaining_budget = max(D(0), remaining_budget - estimated_notional)

        item_seed = {
            "portfolio_id": PORTFOLIO_ID,
            "plan_date": plan_date,
            "symbol": symbol,
            "score": str(score),
            "price": str(price),
            "qty": str(quantity),
            "risk_state": risk_state,
        }

        items.append(
            {
                "symbol": symbol,
                "rank": rank,
                "score": str(score),
                "signal": "BUY",
                "real_market_price": str(price),
                "price_date": mark_date,
                "existing_position_market_value": str(money(existing)),
                "raw_target_capital": str(money(raw_target)),
                "concentration_capital_limit": str(money(remaining_concentration_capacity)),
                "risk_budget_capital_limit": str(money(risk_budget_limit)),
                "final_target_capital": str(money(final_capital)),
                "round_lot": ROUND_LOT,
                "paper_quantity": str(quantity),
                "estimated_notional": str(estimated_notional),
                "allocation_state": allocation_state,
                "allocation_reason": reason,
                "synthetic_market_data": False,
                "synthetic_signal": False,
                "fake_price": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "evidence_sha256": stable_hash(item_seed),
            }
        )

    total_allocated = sum(
        (D(item["estimated_notional"]) for item in items),
        D(0),
    )

    if total_allocated > max_new_capital + D("0.01"):
        raise RuntimeError("Allocation exceeded max_new_capital")

    for item in items:
        symbol_total = existing_mv.get(item["symbol"], D(0)) + D(item["estimated_notional"])
        if symbol_total > concentration_capital_limit + D("0.01"):
            raise RuntimeError(
                f"Concentration limit exceeded for {item['symbol']}"
            )

    plan_seed = {
        "portfolio_id": PORTFOLIO_ID,
        "plan_date": plan_date,
        "risk_state": risk_state,
        "nav": str(nav),
        "cash": str(cash),
        "effective_budget_pct": str(effective_budget_pct),
        "eligible_signals": len(eligible),
        "total_allocated": str(total_allocated),
    }

    plan = {
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "plan_date": plan_date,
        "governance_date": str(governance["governance_date"]),
        "risk_state": risk_state,
        "new_paper_entries_authorized": bool(
            governance["new_paper_entries_authorized"]
        ),
        "paper_halt": bool(governance["paper_halt"]),
        "risk_reduction_factor": str(risk_factor),
        "nav": str(money(nav)),
        "cash": str(money(cash)),
        "current_market_value": str(money(current_market_value)),
        "current_portfolio_exposure": str(current_exposure),
        "base_risk_budget_pct": str(BASE_RISK_BUDGET_PCT),
        "effective_risk_budget_pct": str(effective_budget_pct),
        "max_position_pct": str(MAX_POSITION_PCT),
        "max_new_capital": str(money(max_new_capital)),
        "total_allocated_capital": str(money(total_allocated)),
        "remaining_risk_budget": str(money(max(D(0), max_new_capital - total_allocated))),
        "eligible_signals": len(eligible),
        "sized_candidates": sum(
            1 for item in items if item["allocation_state"] == "SIZED"
        ),
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": stable_hash(plan_seed),
    }

    return plan, items


def persist_plan(
    plan: dict[str, Any],
    items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan_seed = {
        "portfolio_id": plan["portfolio_id"],
        "plan_date": plan["plan_date"],
        "risk_state": plan["risk_state"],
        "evidence_sha256": plan["evidence_sha256"],
    }

    plan_id = "P353P-" + stable_hash(plan_seed)[:28]

    row = {
        "plan_id": plan_id,
        **plan,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    rest_upsert(
        PLAN_TABLE,
        [row],
        "portfolio_id,plan_date",
    )

    persisted_items: list[dict[str, Any]] = []

    for item in items:
        item_seed = {
            "plan_id": plan_id,
            "symbol": item["symbol"],
            "plan_date": plan["plan_date"],
        }

        item_id = "P353I-" + stable_hash(item_seed)[:28]

        item_row = {
            "item_id": item_id,
            "plan_id": plan_id,
            "portfolio_id": PORTFOLIO_ID,
            "strategy_version": STRATEGY,
            "plan_date": plan["plan_date"],
            "symbol": item["symbol"],
            "rank": item["rank"],
            "score": item["score"],
            "signal": item["signal"],
            "real_market_price": item["real_market_price"],
            "existing_position_market_value": item["existing_position_market_value"],
            "raw_target_capital": item["raw_target_capital"],
            "concentration_capital_limit": item["concentration_capital_limit"],
            "risk_budget_capital_limit": item["risk_budget_capital_limit"],
            "final_target_capital": item["final_target_capital"],
            "round_lot": item["round_lot"],
            "paper_quantity": item["paper_quantity"],
            "estimated_notional": item["estimated_notional"],
            "allocation_state": item["allocation_state"],
            "allocation_reason": item["allocation_reason"],
            "synthetic_market_data": False,
            "synthetic_signal": False,
            "fake_price": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "evidence_sha256": item["evidence_sha256"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        persisted_items.append(item_row)

    if persisted_items:
        rest_upsert(
            ITEM_TABLE,
            persisted_items,
            "plan_id,symbol",
        )

    rows = rest_get(
        PLAN_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("plan_date", f"eq.{plan['plan_date']}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Position sizing plan persistence verification failed")

    return rows[0], persisted_items


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.5.3",
        "",
        "## Production Paper Position Sizing + Risk Budget Allocation Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Sizing Status: **{result['status']}**",
        f"- Plan Date: `{result['plan_date']}`",
        "",
        "### Risk Governance Input",
        "",
        f"- Risk State: **{result['risk_state']}**",
        f"- New Paper Entries Authorized: **{'YES' if result['new_paper_entries_authorized'] else 'NO'}**",
        f"- Paper Halt: **{'YES' if result['paper_halt'] else 'NO'}**",
        f"- Risk Reduction Factor: **{result['risk_reduction_factor']:.2f}**",
        "",
        "### Portfolio Risk Budget",
        "",
        f"- NAV: **{result['nav']:.2f}**",
        f"- Cash: **{result['cash']:.2f}**",
        f"- Current Market Value: **{result['current_market_value']:.2f}**",
        f"- Current Portfolio Exposure: **{result['current_portfolio_exposure']:.6%}**",
        f"- Base Risk Budget: **{result['base_risk_budget_pct']:.2%}**",
        f"- Effective Risk Budget: **{result['effective_risk_budget_pct']:.2%}**",
        f"- Max Position Limit: **{result['max_position_pct']:.2%}**",
        f"- Max New Capital: **{result['max_new_capital']:.2f}**",
        f"- Total Allocated Capital: **{result['total_allocated_capital']:.2f}**",
        f"- Remaining Risk Budget: **{result['remaining_risk_budget']:.2f}**",
        "",
        "### Signal / Sizing Result",
        "",
        f"- Eligible Canonical Signals: **{result['eligible_signals']}**",
        f"- Sized Candidates: **{result['sized_candidates']}**",
    ]

    if result["items"]:
        lines.extend(["", "### Allocation Items", ""])
        for item in result["items"]:
            lines.append(
                f"- `{item['symbol']}` rank={item['rank']} score={item['score']} "
                f"price={item['real_market_price']} qty={item['paper_quantity']} "
                f"notional={item['estimated_notional']} state={item['allocation_state']}"
            )
    else:
        lines.extend(
            [
                "",
                "### Allocation Items",
                "",
                "- No eligible persisted canonical BUY signal; zero paper allocation by design.",
            ]
        )

    lines.extend(
        [
            "",
            "### Safety Boundary",
            "",
            "- Synthetic market data: **DISABLED**",
            "- Synthetic signals: **DISABLED**",
            "- Fake prices: **DISABLED**",
            "- Broker API used: **NO**",
            "- Broker credentials used: **NO**",
            "- Broker order submission: **DISABLED**",
            "- Real-money trading: **DISABLED**",
            "- Live-money release authorized: **NO**",
            "- Fail-closed policy: **ENABLED**",
            f"- Evidence SHA256: `{result['evidence_sha256']}`",
        ]
    )

    text = "\n".join(lines) + "\n"

    (OUT / "phase353_position_sizing.md").write_text(
        text,
        encoding="utf-8",
    )

    gh = os.getenv("GITHUB_STEP_SUMMARY")

    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: paper-only mode required")

    upstream_exit, governance = run_upstream()
    validate_governance(governance)

    ledger = latest_ledger()
    positions = open_positions()

    plan, items = build_plan(
        governance,
        ledger,
        positions,
    )

    persisted_plan, persisted_items = persist_plan(
        plan,
        items,
    )

    result = {
        "version": "3.5.3",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "upstream_process_exit_code": upstream_exit,
        "plan_id": persisted_plan["plan_id"],
        "plan_date": str(persisted_plan["plan_date"]),
        "risk_state": persisted_plan["risk_state"],
        "new_paper_entries_authorized": bool(
            persisted_plan["new_paper_entries_authorized"]
        ),
        "paper_halt": bool(persisted_plan["paper_halt"]),
        "risk_reduction_factor": float(
            persisted_plan["risk_reduction_factor"]
        ),
        "nav": float(persisted_plan["nav"]),
        "cash": float(persisted_plan["cash"]),
        "current_market_value": float(
            persisted_plan["current_market_value"]
        ),
        "current_portfolio_exposure": float(
            persisted_plan["current_portfolio_exposure"]
        ),
        "base_risk_budget_pct": float(
            persisted_plan["base_risk_budget_pct"]
        ),
        "effective_risk_budget_pct": float(
            persisted_plan["effective_risk_budget_pct"]
        ),
        "max_position_pct": float(
            persisted_plan["max_position_pct"]
        ),
        "max_new_capital": float(
            persisted_plan["max_new_capital"]
        ),
        "total_allocated_capital": float(
            persisted_plan["total_allocated_capital"]
        ),
        "remaining_risk_budget": float(
            persisted_plan["remaining_risk_budget"]
        ),
        "eligible_signals": int(
            persisted_plan["eligible_signals"]
        ),
        "sized_candidates": int(
            persisted_plan["sized_candidates"]
        ),
        "items": persisted_items,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": persisted_plan["evidence_sha256"],
    }

    if result["risk_state"] == "PAPER_HALT":
        if result["total_allocated_capital"] != 0:
            raise RuntimeError(
                "PAPER_HALT produced non-zero allocation"
            )

    if not result["new_paper_entries_authorized"]:
        if result["total_allocated_capital"] != 0:
            raise RuntimeError(
                "Unauthorized new paper entries produced non-zero allocation"
            )

    if result["total_allocated_capital"] > result["max_new_capital"] + 0.01:
        raise RuntimeError(
            "Total allocation exceeds max new capital"
        )

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE353 PASS: paper position sizing + risk-budget allocation complete. "
        f"state={result['risk_state']}, "
        f"eligible={result['eligible_signals']}, "
        f"sized={result['sized_candidates']}, "
        f"allocated={result['total_allocated_capital']:.2f}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.5.3 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.5.3 - Production Paper Position Sizing Risk Budget Allocation Engine

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string

      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string

      base_risk_budget_pct:
        description: Maximum portfolio market-value budget for paper positions
        required: true
        default: "0.60"
        type: string

      max_position_pct:
        description: Maximum NAV concentration per symbol
        required: true
        default: "0.20"
        type: string

      max_candidates:
        description: Maximum new paper candidates
        required: true
        default: "3"
        type: string

  schedule:
    - cron: "35 9 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase353-production-paper-position-sizing
  cancel-in-progress: false

jobs:
  production-paper-position-sizing:
    runs-on: ubuntu-latest
    timeout-minutes: 50

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE353_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE352_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE351_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE351_MIN_HISTORY: "5"

      PHASE353_BASE_RISK_BUDGET_PCT: ${{ inputs.base_risk_budget_pct || '0.60' }}
      PHASE353_MAX_POSITION_PCT: ${{ inputs.max_position_pct || '0.20' }}
      PHASE353_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}
      PHASE353_ROUND_LOT: "1000"
      PHASE353_SCORE_THRESHOLD: "65"

      PHASE352_CAUTION_DRAWDOWN: "-0.05"
      PHASE352_REDUCE_DRAWDOWN: "-0.10"
      PHASE352_HALT_DRAWDOWN: "-0.15"
      PHASE352_CAUTION_DAILY_LOSS: "-0.025"
      PHASE352_HALT_DAILY_LOSS: "-0.05"
      PHASE352_MAX_EXPOSURE_CAUTION: "0.80"
      PHASE352_MAX_EXPOSURE_HALT: "0.95"
      PHASE352_MAX_CONCENTRATION_CAUTION: "0.35"
      PHASE352_MAX_CONCENTRATION_HALT: "0.50"
      PHASE352_CONSECUTIVE_LOSS_CAUTION: "3"
      PHASE352_CONSECUTIVE_LOSS_HALT: "5"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependencies
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.5.3 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py
          test -f automation/v92/paper_trading_phase352_production_paper_risk_governance_drawdown_guard_engine.py
          test -f supabase/PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET.sql

          grep -q 'PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET_ALLOCATION_ENGINE' \
            automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py

          grep -q 'PAPER_HALT' \
            automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py

          grep -q '"synthetic_market_data": False' \
            automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py

          grep -q '"synthetic_signals": False' \
            automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py

          echo "Phase 3.5.3 safety contract: PASS"

      - name: Execute Phase 3.5.3 position sizing
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine.py

      - name: Validate Phase 3.5.3 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase353_output/phase353_position_sizing.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase353_output/phase353_position_sizing.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.5.3", data
          assert data["status"] == "PASS", data

          assert data["risk_state"] in {
              "INSUFFICIENT_HISTORY_VALID_STATE",
              "NORMAL",
              "CAUTION",
              "RISK_REDUCED",
              "PAPER_HALT",
          }, data

          assert data["nav"] > 0, data
          assert data["cash"] >= 0, data
          assert data["total_allocated_capital"] >= 0, data
          assert data["remaining_risk_budget"] >= 0, data
          assert data["total_allocated_capital"] <= data["max_new_capital"] + 0.01, data

          if data["risk_state"] == "PAPER_HALT":
              assert data["new_paper_entries_authorized"] is False, data
              assert data["total_allocated_capital"] == 0, data

          if data["new_paper_entries_authorized"] is False:
              assert data["total_allocated_capital"] == 0, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          print("Phase 3.5.3 output validation: PASS")
          PY

      - name: Upload Phase 3.5.3 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase353-production-paper-position-sizing-${{ github.run_id }}
          path: |
            phase350_output/
            phase351_output/
            phase352_output/
            phase353_output/
          if-no-files-found: warn
          retention-days: 90
'@

Set-Content -LiteralPath $workflowTarget -Value $workflow -Encoding UTF8
Write-Host "Wrote: $workflowTarget" -ForegroundColor Green

Section "Static validation"

$pythonCmd = $null

if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} else {
    Fail "Python was not found in PATH."
}

if ($pythonCmd -eq "py") {
    & py -3 -m py_compile $pythonTarget
} else {
    & python -m py_compile $pythonTarget
}

if ($LASTEXITCODE -ne 0) {
    Fail "Python compile validation failed."
}

Write-Host "Python compile: PASS" -ForegroundColor Green

$source = Get-Content -LiteralPath $pythonTarget -Raw

$needles = @(
    'PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET_ALLOCATION_ENGINE',
    'paper_position_sizing_plans_v92',
    'paper_position_sizing_items_v92',
    'BASE_RISK_BUDGET_PCT',
    'MAX_POSITION_PCT',
    'risk_reduction_factor',
    'PAPER_HALT',
    'new_paper_entries_authorized',
    'floor_to_lot',
    '"synthetic_market_data": False',
    '"synthetic_signals": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.5.3 token missing: $needle"
    }
}

Write-Host "Phase 3.5.3 position-sizing/risk-budget contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $sqlTarget $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $sqlTarget"
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Risk-state allocation mapping:" -ForegroundColor Cyan
Write-Host "  INSUFFICIENT_HISTORY_VALID_STATE -> 100%"
Write-Host "  NORMAL                           -> 100%"
Write-Host "  CAUTION                          -> 75%"
Write-Host "  RISK_REDUCED                     -> 50%"
Write-Host "  PAPER_HALT                       -> 0%"
Write-Host ""

Write-Host "Default portfolio controls:" -ForegroundColor Cyan
Write-Host "  Base portfolio risk budget: 60% NAV"
Write-Host "  Max position concentration: 20% NAV"
Write-Host "  Max candidates: 3"
Write-Host "  Taiwan round lot: 1000 shares"
Write-Host "  V9.1 score threshold: 65"
Write-Host ""

Write-Host "Supabase SQL required before first Action run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET.sql"
Write-Host ""

Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 35 9 * * 1-5"
Write-Host "  (09:35 UTC = 17:35 Taiwan time, weekdays)"
Write-Host ""

Write-Host "Hard safety locks:" -ForegroundColor Yellow
Write-Host "  Synthetic market data: DISABLED"
Write-Host "  Synthetic signals: DISABLED"
Write-Host "  Fake prices: DISABLED"
Write-Host "  Broker API used: NO"
Write-Host "  Broker credentials used: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run Supabase SQL: PHASE353_PRODUCTION_PAPER_POSITION_SIZING_RISK_BUDGET.sql"
Write-Host "  2) Review GitHub Desktop changes."
Write-Host "  3) Commit and Push origin."
Write-Host "  4) GitHub Actions -> GPT Quant Phase 3.5.3."
Write-Host "  5) Run once manually with defaults."
Write-Host "  6) Confirm risk-state allocation factor / risk budget / sized candidates."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
