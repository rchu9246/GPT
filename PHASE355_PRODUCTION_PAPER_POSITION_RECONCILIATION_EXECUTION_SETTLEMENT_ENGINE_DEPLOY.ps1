#requires -Version 5.1
<#
PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT_ENGINE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.5.5 — Production Paper Position Reconciliation + Execution Settlement Engine

Purpose
-------
Close the production-paper execution loop by reconciling Phase 3.5.4 simulated fills
into the persistent paper portfolio and position ledgers.

Inputs
------
  - Phase 3.5.4 paper execution lifecycle
  - paper_simulated_fills_v92
  - paper_portfolios_v92
  - paper_positions_v92
  - paper_position_events_v92
  - paper_portfolio_snapshots_v92
  - real canonical market prices only

Outputs
-------
  - Idempotent settlement cycles
  - Fill-to-position reconciliation
  - Cash updates
  - Position quantity / average cost updates
  - Realized / unrealized P&L updates
  - Mark-to-market refresh
  - Daily portfolio snapshot refresh
  - Settlement evidence SHA256

Canonical settlement states
---------------------------
  ZERO_FILL_VALID_STATE
  SETTLEMENT_COMPLETED
  PAPER_HALT_ZERO_SETTLEMENT
  ALREADY_SETTLED_IDEMPOTENT

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
  supabase/PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT.sql
  automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py
  .github/workflows/gpt-quant-v92-paper-trading-phase355-production-paper-position-reconciliation-execution-settlement-engine.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 116) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 116) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.5.5 Position Reconciliation + Execution Settlement"

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
    "automation/v92/paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine.py",
    "automation/v92/paper_trading_phase349_production_paper_portfolio_lifecycle_daily_mark_to_market_engine.py",
    "supabase/PHASE354_PRODUCTION_PAPER_ORDER_INTENT_SIMULATED_EXECUTION.sql",
    "supabase/PHASE349_PRODUCTION_PAPER_PORTFOLIO_LIFECYCLE.sql"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$sqlTarget = "supabase/PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT.sql"
$pythonTarget = "automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase355-production-paper-position-reconciliation-execution-settlement-engine.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $sqlTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase355-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($sqlTarget, $pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.5.5 Supabase settlement schema"

$sql = @'
begin;

create table if not exists public.paper_settlement_cycles_v92 (
    settlement_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    settlement_date date not null,

    execution_cycle_id text,
    execution_state text not null,
    settlement_state text not null,

    fills_discovered integer not null,
    fills_settled integer not null,
    fills_already_settled integer not null,

    cash_before numeric not null,
    cash_after numeric not null,
    market_value_after numeric not null,
    nav_after numeric not null,
    realized_pnl_after numeric not null,
    unrealized_pnl_after numeric not null,
    open_positions_after integer not null,

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

create unique index if not exists uq_paper_settlement_cycles_v92_portfolio_date
    on public.paper_settlement_cycles_v92 (portfolio_id, settlement_date);

create table if not exists public.paper_fill_settlements_v92 (
    fill_settlement_id text primary key,
    settlement_id text not null,
    fill_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    settlement_date date not null,

    symbol text not null,
    side text not null,
    quantity numeric not null,
    fill_price numeric not null,
    fill_notional numeric not null,

    cash_delta numeric not null,
    realized_pnl_delta numeric not null default 0,
    position_quantity_after numeric not null,
    position_avg_entry_price_after numeric not null,
    settlement_state text not null,

    synthetic_market_data boolean not null default false,
    synthetic_signal boolean not null default false,
    fake_price boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,

    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_fill_settlements_v92_fill
    on public.paper_fill_settlements_v92 (fill_id);

alter table public.paper_settlement_cycles_v92 enable row level security;
alter table public.paper_fill_settlements_v92 enable row level security;

comment on table public.paper_settlement_cycles_v92 is
'GPT Quant V9.2 paper-only settlement-cycle ledger. Reconciles simulated fills into persistent paper cash/positions/NAV.';

comment on table public.paper_fill_settlements_v92 is
'GPT Quant V9.2 idempotent per-fill paper settlement audit log. No broker or real-money settlement.';

commit;
'@

Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.5.5 Python reconciliation/settlement engine"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase355_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE355_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()

UPSTREAM = ROOT / "automation/v92/paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine.py"
UPSTREAM_JSON = ROOT / "phase354_output/phase354_execution_lifecycle.json"

PORTFOLIO_TABLE = "paper_portfolios_v92"
POSITIONS_TABLE = "paper_positions_v92"
POSITION_EVENTS_TABLE = "paper_position_events_v92"
SNAPSHOT_TABLE = "paper_portfolio_snapshots_v92"
FILL_TABLE = "paper_simulated_fills_v92"
EXECUTION_CYCLE_TABLE = "paper_execution_cycles_v92"
SETTLEMENT_TABLE = "paper_settlement_cycles_v92"
FILL_SETTLEMENT_TABLE = "paper_fill_settlements_v92"
MARKET_TABLE = "daily_prices"

RESULT_JSON = OUT / "phase355_settlement.json"

CONTRACT = "PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT_ENGINE"

ZERO_FILL = "ZERO_FILL_VALID_STATE"
SETTLED = "SETTLEMENT_COMPLETED"
HALT_ZERO = "PAPER_HALT_ZERO_SETTLEMENT"
IDEMPOTENT = "ALREADY_SETTLED_IDEMPOTENT"


def D(value: Any) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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

    response = requests.get(url, headers=headers, params=params, timeout=25)

    if response.status_code >= 400:
        raise RuntimeError(
            f"{table}: GET HTTP {response.status_code}: {response.text[:1000]}"
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
            f"{table}: UPSERT HTTP {response.status_code}: {response.text[:1400]}"
        )


def run_upstream() -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY
    env["PHASE354_PORTFOLIO_ID"] = PORTFOLIO_ID

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
            f"Phase 3.5.4 evidence missing; upstream exit={proc.returncode}"
        )

    return proc.returncode, load_json(UPSTREAM_JSON)


def validate_execution(data: dict[str, Any]) -> None:
    if data.get("status") != "PASS":
        raise RuntimeError("Phase 3.5.4 execution lifecycle did not PASS")

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


def ensure_portfolio() -> dict[str, Any]:
    rows = rest_get(
        PORTFOLIO_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Persistent paper portfolio missing")

    row = rows[0]

    if row.get("broker_trading_enabled") is True:
        raise RuntimeError("Broker trading must remain disabled")

    if row.get("real_money_trading_enabled") is True:
        raise RuntimeError("Real-money trading must remain disabled")

    return row


def open_positions() -> list[dict[str, Any]]:
    return rest_get(
        POSITIONS_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
        ],
    )


def fills_for_cycle(cycle_date: str) -> list[dict[str, Any]]:
    return rest_get(
        FILL_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("fill_date", f"eq.{cycle_date}"),
            ("order", "created_at.asc"),
        ],
    )


def already_settled(fill_id: str) -> dict[str, Any] | None:
    rows = rest_get(
        FILL_SETTLEMENT_TABLE,
        [
            ("select", "*"),
            ("fill_id", f"eq.{fill_id}"),
            ("limit", "1"),
        ],
    )
    return rows[0] if rows else None


def latest_real_price(symbol: str) -> tuple[str, Decimal]:
    candidates = [
        [
            ("select", "*"),
            ("symbol", f"eq.{symbol}"),
            ("order", "date.desc"),
            ("limit", "1"),
        ],
        [
            ("select", "*"),
            ("stock_id", f"eq.{symbol}"),
            ("order", "date.desc"),
            ("limit", "1"),
        ],
    ]

    for params in candidates:
        try:
            rows = rest_get(MARKET_TABLE, params)
        except Exception:
            continue

        if not rows:
            continue

        row = rows[0]
        market_date = str(
            row.get("date")
            or row.get("trade_date")
            or row.get("market_date")
            or ""
        )[:10]

        raw_price = (
            row.get("close")
            or row.get("close_price")
            or row.get("price")
        )

        if market_date and raw_price is not None:
            px = D(raw_price)
            if px > 0:
                return market_date, px

    raise RuntimeError(f"NO_REAL_MARKET_PRICE: {symbol}")


def position_map(positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(p.get("symbol")): dict(p)
        for p in positions
        if p.get("symbol")
    }


def settle_fills(
    portfolio: dict[str, Any],
    positions: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    settlement_date: str,
) -> tuple[
    Decimal,
    Decimal,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
]:
    cash = D(portfolio.get("cash") or 0)
    realized_total = D(portfolio.get("realized_pnl") or 0)

    by_symbol = position_map(positions)

    fill_settlement_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    settled_count = 0
    already_count = 0

    for fill in fills:
        fill_id = str(fill["fill_id"])

        prior = already_settled(fill_id)
        if prior is not None:
            already_count += 1
            continue

        symbol = str(fill["symbol"])
        side = str(fill["side"]).upper()
        qty = D(fill["quantity"])
        fill_price = D(fill["fill_price"])
        fill_notional = money(D(fill["fill_notional"]))

        if qty <= 0 or fill_price <= 0 or fill_notional <= 0:
            raise RuntimeError(f"Invalid fill payload: {fill_id}")

        if side not in {"BUY", "SELL"}:
            raise RuntimeError(f"Unsupported simulated fill side: {side}")

        pos = by_symbol.get(symbol)
        realized_delta = D(0)

        if side == "BUY":
            if fill_notional > cash:
                raise RuntimeError(
                    f"PAPER_CASH_INSUFFICIENT: {symbol}, "
                    f"need={fill_notional}, cash={cash}"
                )

            old_qty = D(pos.get("quantity") or 0) if pos else D(0)
            old_avg = D(pos.get("avg_entry_price") or 0) if pos else D(0)

            new_qty = old_qty + qty
            new_avg = money(
                ((old_qty * old_avg) + (qty * fill_price)) / new_qty
            )

            cash = money(cash - fill_notional)

            by_symbol[symbol] = {
                "portfolio_id": PORTFOLIO_ID,
                "strategy_version": STRATEGY,
                "symbol": symbol,
                "quantity": str(new_qty),
                "avg_entry_price": str(new_avg),
                "last_market_price": str(fill_price),
                "market_value": str(money(new_qty * fill_price)),
                "unrealized_pnl": str(money((fill_price - new_avg) * new_qty)),
                "realized_pnl": str(
                    D(pos.get("realized_pnl") or 0) if pos else D(0)
                ),
                "opened_date": (
                    pos.get("opened_date") if pos else settlement_date
                ),
                "last_mark_date": settlement_date,
                "status": "OPEN",
                "synthetic_evidence": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "evidence_sha256": stable_hash(
                    {
                        "fill_id": fill_id,
                        "symbol": symbol,
                        "side": side,
                        "qty": str(qty),
                        "fill_price": str(fill_price),
                    }
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            cash_delta = -fill_notional

        else:
            if pos is None or str(pos.get("status")) != "OPEN":
                raise RuntimeError(f"PAPER_SELL_WITHOUT_OPEN_POSITION: {symbol}")

            old_qty = D(pos.get("quantity") or 0)
            avg = D(pos.get("avg_entry_price") or 0)

            if qty > old_qty:
                raise RuntimeError(
                    f"PAPER_SELL_EXCEEDS_POSITION: {symbol}, "
                    f"sell={qty}, held={old_qty}"
                )

            proceeds = fill_notional
            realized_delta = money((fill_price - avg) * qty)
            realized_total = money(realized_total + realized_delta)
            cash = money(cash + proceeds)

            new_qty = old_qty - qty
            pos = dict(pos)

            if new_qty == 0:
                pos["quantity"] = "0"
                pos["market_value"] = "0"
                pos["unrealized_pnl"] = "0"
                pos["status"] = "CLOSED"
            else:
                pos["quantity"] = str(new_qty)
                pos["market_value"] = str(money(new_qty * fill_price))
                pos["unrealized_pnl"] = str(
                    money((fill_price - avg) * new_qty)
                )

            pos["last_market_price"] = str(fill_price)
            pos["last_mark_date"] = settlement_date
            pos["realized_pnl"] = str(
                money(D(pos.get("realized_pnl") or 0) + realized_delta)
            )
            pos["synthetic_evidence"] = False
            pos["broker_order_submission_enabled"] = False
            pos["real_money_trading_enabled"] = False
            pos["updated_at"] = datetime.now(timezone.utc).isoformat()
            by_symbol[symbol] = pos

            cash_delta = proceeds

        position_after = by_symbol[symbol]

        settlement_seed = {
            "fill_id": fill_id,
            "portfolio_id": PORTFOLIO_ID,
            "settlement_date": settlement_date,
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "fill_price": str(fill_price),
        }

        fill_settlement_id = "P355F-" + stable_hash(settlement_seed)[:28]

        fill_settlement_rows.append(
            {
                "fill_settlement_id": fill_settlement_id,
                "settlement_id": "__PENDING__",
                "fill_id": fill_id,
                "portfolio_id": PORTFOLIO_ID,
                "strategy_version": STRATEGY,
                "settlement_date": settlement_date,
                "symbol": symbol,
                "side": side,
                "quantity": str(qty),
                "fill_price": str(fill_price),
                "fill_notional": str(fill_notional),
                "cash_delta": str(cash_delta),
                "realized_pnl_delta": str(realized_delta),
                "position_quantity_after": str(
                    D(position_after.get("quantity") or 0)
                ),
                "position_avg_entry_price_after": str(
                    D(position_after.get("avg_entry_price") or 0)
                ),
                "settlement_state": "SETTLED",
                "synthetic_market_data": False,
                "synthetic_signal": False,
                "fake_price": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "evidence_sha256": stable_hash(settlement_seed),
            }
        )

        event_seed = {
            "fill_id": fill_id,
            "event_type": side,
            "portfolio_id": PORTFOLIO_ID,
        }

        event_rows.append(
            {
                "event_id": "P355E-" + stable_hash(event_seed)[:28],
                "portfolio_id": PORTFOLIO_ID,
                "strategy_version": STRATEGY,
                "event_date": settlement_date,
                "event_type": side,
                "symbol": symbol,
                "quantity": str(qty),
                "price": str(fill_price),
                "cash_delta": str(cash_delta),
                "realized_pnl_delta": str(realized_delta),
                "source_contract": CONTRACT,
                "synthetic_evidence": False,
                "broker_order_submission_enabled": False,
                "real_money_trading_enabled": False,
                "evidence_sha256": stable_hash(event_seed),
            }
        )

        settled_count += 1

    return (
        cash,
        realized_total,
        list(by_symbol.values()),
        fill_settlement_rows,
        event_rows,
        already_count,
    )


def mark_to_market(
    positions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Decimal, Decimal, str | None]:
    market_value = D(0)
    unrealized = D(0)
    latest_date: str | None = None
    updated: list[dict[str, Any]] = []

    for pos in positions:
        pos = dict(pos)

        if str(pos.get("status")) != "OPEN":
            updated.append(pos)
            continue

        symbol = str(pos["symbol"])
        mark_date, price = latest_real_price(symbol)

        qty = D(pos.get("quantity") or 0)
        avg = D(pos.get("avg_entry_price") or 0)

        mv = money(qty * price)
        upnl = money((price - avg) * qty)

        pos["last_market_price"] = str(price)
        pos["market_value"] = str(mv)
        pos["unrealized_pnl"] = str(upnl)
        pos["last_mark_date"] = mark_date
        pos["synthetic_evidence"] = False
        pos["broker_order_submission_enabled"] = False
        pos["real_money_trading_enabled"] = False
        pos["updated_at"] = datetime.now(timezone.utc).isoformat()

        market_value += mv
        unrealized += upnl

        if latest_date is None or mark_date > latest_date:
            latest_date = mark_date

        updated.append(pos)

    return updated, money(market_value), money(unrealized), latest_date


def persist_positions(
    portfolio: dict[str, Any],
    positions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    cash: Decimal,
    realized: Decimal,
) -> None:
    portfolio_row = {
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "initial_cash": str(D(portfolio.get("initial_cash") or 0)),
        "cash": str(money(cash)),
        "realized_pnl": str(money(realized)),
        "status": "ACTIVE",
        "broker_trading_enabled": False,
        "real_money_trading_enabled": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    rest_upsert(PORTFOLIO_TABLE, [portfolio_row], "portfolio_id")

    if positions:
        rest_upsert(
            POSITIONS_TABLE,
            positions,
            "portfolio_id,symbol",
        )

    if events:
        rest_upsert(
            POSITION_EVENTS_TABLE,
            events,
            "event_id",
        )


def persist_snapshot(
    settlement_date: str,
    execution_state: str,
    cash: Decimal,
    realized: Decimal,
    market_value: Decimal,
    unrealized: Decimal,
    open_positions: int,
    mark_date: str,
) -> dict[str, Any]:
    nav = money(cash + market_value)

    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "snapshot_date": mark_date,
        "cash": str(cash),
        "market_value": str(market_value),
        "nav": str(nav),
        "realized": str(realized),
        "unrealized": str(unrealized),
        "execution_state": execution_state,
    }

    row = {
        "snapshot_id": "P355S-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "snapshot_date": mark_date,
        "cash": str(money(cash)),
        "market_value": str(market_value),
        "nav": str(nav),
        "realized_pnl": str(money(realized)),
        "unrealized_pnl": str(money(unrealized)),
        "open_positions": open_positions,
        "canonical_runtime_state": execution_state,
        "daily_cycle_status": "COMPLETED",
        "market_data_source": "daily_prices",
        "latest_market_date": mark_date,
        "synthetic_evidence": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "evidence_sha256": stable_hash(seed),
    }

    rest_upsert(
        SNAPSHOT_TABLE,
        [row],
        "portfolio_id,snapshot_date",
    )

    return row


def persist_settlement_cycle(
    execution: dict[str, Any],
    settlement_date: str,
    fills_discovered: int,
    fills_settled: int,
    fills_already_settled: int,
    cash_before: Decimal,
    cash_after: Decimal,
    market_value_after: Decimal,
    nav_after: Decimal,
    realized_after: Decimal,
    unrealized_after: Decimal,
    open_positions_after: int,
    settlement_state: str,
) -> dict[str, Any]:
    seed = {
        "portfolio_id": PORTFOLIO_ID,
        "settlement_date": settlement_date,
        "execution_cycle_id": execution.get("cycle_id"),
        "execution_state": execution.get("execution_state"),
        "settlement_state": settlement_state,
        "fills_discovered": fills_discovered,
        "fills_settled": fills_settled,
        "fills_already_settled": fills_already_settled,
        "cash_after": str(cash_after),
        "nav_after": str(nav_after),
    }

    row = {
        "settlement_id": "P355C-" + stable_hash(seed)[:28],
        "portfolio_id": PORTFOLIO_ID,
        "strategy_version": STRATEGY,
        "settlement_date": settlement_date,
        "execution_cycle_id": execution.get("cycle_id"),
        "execution_state": execution.get("execution_state"),
        "settlement_state": settlement_state,
        "fills_discovered": fills_discovered,
        "fills_settled": fills_settled,
        "fills_already_settled": fills_already_settled,
        "cash_before": str(money(cash_before)),
        "cash_after": str(money(cash_after)),
        "market_value_after": str(market_value_after),
        "nav_after": str(nav_after),
        "realized_pnl_after": str(money(realized_after)),
        "unrealized_pnl_after": str(unrealized_after),
        "open_positions_after": open_positions_after,
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": stable_hash(seed),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    rest_upsert(
        SETTLEMENT_TABLE,
        [row],
        "portfolio_id,settlement_date",
    )

    rows = rest_get(
        SETTLEMENT_TABLE,
        [
            ("select", "*"),
            ("portfolio_id", f"eq.{PORTFOLIO_ID}"),
            ("settlement_date", f"eq.{settlement_date}"),
            ("limit", "1"),
        ],
    )

    if not rows:
        raise RuntimeError("Settlement-cycle persistence verification failed")

    return rows[0]


def write_summary(result: dict[str, Any]) -> None:
    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.5.5",
        "",
        "## Production Paper Position Reconciliation + Execution Settlement Engine",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Contract: **{result['contract']}**",
        f"- Portfolio ID: `{result['portfolio_id']}`",
        f"- Settlement Status: **{result['status']}**",
        f"- Settlement Date: `{result['settlement_date']}`",
        "",
        "### Execution Input",
        "",
        f"- Execution State: **{result['execution_state']}**",
        f"- Fills Discovered: **{result['fills_discovered']}**",
        f"- Fills Settled: **{result['fills_settled']}**",
        f"- Fills Already Settled: **{result['fills_already_settled']}**",
        f"- Settlement State: **{result['settlement_state']}**",
        "",
        "### Portfolio Settlement",
        "",
        f"- Cash Before: **{result['cash_before']:.2f}**",
        f"- Cash After: **{result['cash_after']:.2f}**",
        f"- Market Value After: **{result['market_value_after']:.2f}**",
        f"- NAV After: **{result['nav_after']:.2f}**",
        f"- Realized P&L After: **{result['realized_pnl_after']:.2f}**",
        f"- Unrealized P&L After: **{result['unrealized_pnl_after']:.2f}**",
        f"- Open Positions After: **{result['open_positions_after']}**",
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

    text = "\n".join(lines) + "\n"

    (OUT / "phase355_settlement.md").write_text(
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

    upstream_exit, execution = run_upstream()
    validate_execution(execution)

    settlement_date = str(execution["cycle_date"])

    portfolio = ensure_portfolio()
    cash_before = D(portfolio.get("cash") or 0)

    positions = open_positions()
    fills = fills_for_cycle(settlement_date)

    if execution.get("paper_halt") is True and fills:
        raise RuntimeError("PAPER_HALT cannot carry simulated fills")

    (
        cash_after,
        realized_after,
        positions_after,
        fill_settlement_rows,
        event_rows,
        already_count,
    ) = settle_fills(
        portfolio,
        positions,
        fills,
        settlement_date,
    )

    mtm_positions, market_value_after, unrealized_after, latest_mark_date = mark_to_market(
        positions_after
    )

    persist_positions(
        portfolio,
        mtm_positions,
        event_rows,
        cash_after,
        realized_after,
    )

    open_count = sum(
        1 for p in mtm_positions if str(p.get("status")) == "OPEN"
    )

    snapshot_date = latest_mark_date or settlement_date

    snapshot = persist_snapshot(
        settlement_date,
        str(execution.get("execution_state")),
        cash_after,
        realized_after,
        market_value_after,
        unrealized_after,
        open_count,
        snapshot_date,
    )

    nav_after = D(snapshot["nav"])

    if execution.get("paper_halt") is True:
        settlement_state = HALT_ZERO
    elif len(fills) == 0:
        settlement_state = ZERO_FILL
    elif len(fill_settlement_rows) == 0 and already_count == len(fills):
        settlement_state = IDEMPOTENT
    else:
        settlement_state = SETTLED

    cycle = persist_settlement_cycle(
        execution,
        settlement_date,
        len(fills),
        len(fill_settlement_rows),
        already_count,
        cash_before,
        cash_after,
        market_value_after,
        nav_after,
        realized_after,
        unrealized_after,
        open_count,
        settlement_state,
    )

    settlement_id = cycle["settlement_id"]

    for row in fill_settlement_rows:
        row["settlement_id"] = settlement_id

    if fill_settlement_rows:
        rest_upsert(
            FILL_SETTLEMENT_TABLE,
            fill_settlement_rows,
            "fill_id",
        )

    result = {
        "version": "3.5.5",
        "status": "PASS",
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "contract": CONTRACT,
        "portfolio_id": PORTFOLIO_ID,
        "upstream_process_exit_code": upstream_exit,
        "settlement_id": settlement_id,
        "settlement_date": str(cycle["settlement_date"]),
        "execution_cycle_id": cycle.get("execution_cycle_id"),
        "execution_state": cycle["execution_state"],
        "settlement_state": cycle["settlement_state"],
        "fills_discovered": int(cycle["fills_discovered"]),
        "fills_settled": int(cycle["fills_settled"]),
        "fills_already_settled": int(cycle["fills_already_settled"]),
        "cash_before": float(cycle["cash_before"]),
        "cash_after": float(cycle["cash_after"]),
        "market_value_after": float(cycle["market_value_after"]),
        "nav_after": float(cycle["nav_after"]),
        "realized_pnl_after": float(cycle["realized_pnl_after"]),
        "unrealized_pnl_after": float(cycle["unrealized_pnl_after"]),
        "open_positions_after": int(cycle["open_positions_after"]),
        "synthetic_market_data": False,
        "synthetic_signals": False,
        "fake_prices_allowed": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": cycle["evidence_sha256"],
    }

    if result["fills_discovered"] == 0:
        if result["settlement_state"] not in {ZERO_FILL, HALT_ZERO}:
            raise RuntimeError("Zero-fill cycle has invalid settlement state")

    if result["cash_after"] < 0:
        raise RuntimeError("Paper cash became negative")

    if result["nav_after"] < 0:
        raise RuntimeError("Paper NAV became negative")

    dump_json(RESULT_JSON, result)
    write_summary(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE355 PASS: paper fill reconciliation + execution settlement complete. "
        f"state={result['settlement_state']}, "
        f"fills={result['fills_discovered']}, "
        f"settled={result['fills_settled']}, "
        f"nav={result['nav_after']:.2f}."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.5.5 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.5.5 - Production Paper Position Reconciliation Execution Settlement Engine

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

  schedule:
    - cron: "5 10 * * 1-5"

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase355-production-paper-settlement
  cancel-in-progress: false

jobs:
  production-paper-settlement:
    runs-on: ubuntu-latest
    timeout-minutes: 50

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE355_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE354_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE353_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE352_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE351_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}

      PHASE351_MIN_HISTORY: "5"

      PHASE353_BASE_RISK_BUDGET_PCT: "0.60"
      PHASE353_MAX_POSITION_PCT: "0.20"
      PHASE353_MAX_CANDIDATES: "3"
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

      - name: Validate Phase 3.5.5 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py
          test -f automation/v92/paper_trading_phase354_production_paper_order_intent_simulated_execution_lifecycle_engine.py
          test -f supabase/PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT.sql

          grep -q 'PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT_ENGINE' \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

          grep -q 'ZERO_FILL_VALID_STATE' \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

          grep -q 'SETTLEMENT_COMPLETED' \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

          grep -q '"synthetic_market_data": False' \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

          grep -q '"synthetic_signals": False' \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

          echo "Phase 3.5.5 safety contract: PASS"

      - name: Execute Phase 3.5.5 settlement
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase355_production_paper_position_reconciliation_execution_settlement_engine.py

      - name: Validate Phase 3.5.5 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase355_output/phase355_settlement.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase355_output/phase355_settlement.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.5.5", data
          assert data["status"] == "PASS", data

          assert data["settlement_state"] in {
              "ZERO_FILL_VALID_STATE",
              "SETTLEMENT_COMPLETED",
              "PAPER_HALT_ZERO_SETTLEMENT",
              "ALREADY_SETTLED_IDEMPOTENT",
          }, data

          assert data["cash_after"] >= 0, data
          assert data["nav_after"] >= 0, data
          assert data["fills_settled"] >= 0, data
          assert data["fills_already_settled"] >= 0, data

          if data["fills_discovered"] == 0:
              assert data["settlement_state"] in {
                  "ZERO_FILL_VALID_STATE",
                  "PAPER_HALT_ZERO_SETTLEMENT",
              }, data
              assert data["fills_settled"] == 0, data

          assert data["synthetic_market_data"] is False, data
          assert data["synthetic_signals"] is False, data
          assert data["fake_prices_allowed"] is False, data
          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data

          print("Phase 3.5.5 output validation: PASS")
          PY

      - name: Upload Phase 3.5.5 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase355-production-paper-settlement-${{ github.run_id }}
          path: |
            phase350_output/
            phase351_output/
            phase352_output/
            phase353_output/
            phase354_output/
            phase355_output/
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
    'PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT_ENGINE',
    'paper_settlement_cycles_v92',
    'paper_fill_settlements_v92',
    'ZERO_FILL_VALID_STATE',
    'SETTLEMENT_COMPLETED',
    'ALREADY_SETTLED_IDEMPOTENT',
    'settle_fills',
    'mark_to_market',
    '"synthetic_market_data": False',
    '"synthetic_signals": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.5.5 token missing: $needle"
    }
}

Write-Host "Phase 3.5.5 reconciliation/settlement contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $sqlTarget $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $sqlTarget"
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Canonical settlement states:" -ForegroundColor Cyan
Write-Host "  ZERO_FILL_VALID_STATE"
Write-Host "  SETTLEMENT_COMPLETED"
Write-Host "  PAPER_HALT_ZERO_SETTLEMENT"
Write-Host "  ALREADY_SETTLED_IDEMPOTENT"
Write-Host ""

Write-Host "Settlement lifecycle:" -ForegroundColor Cyan
Write-Host "  Phase 3.5.4 simulated fill"
Write-Host "      -> fill reconciliation"
Write-Host "      -> cash update"
Write-Host "      -> position update"
Write-Host "      -> real-price MTM"
Write-Host "      -> NAV / P&L refresh"
Write-Host "      -> persistent portfolio snapshot"
Write-Host ""

Write-Host "Supabase SQL required before first Action run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT.sql"
Write-Host ""

Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  GitHub Actions cron: 5 10 * * 1-5"
Write-Host "  (10:05 UTC = 18:05 Taiwan time, weekdays)"
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
Write-Host "  1) Run Supabase SQL: PHASE355_PRODUCTION_PAPER_POSITION_RECONCILIATION_EXECUTION_SETTLEMENT.sql"
Write-Host "  2) Review GitHub Desktop changes."
Write-Host "  3) Commit and Push origin."
Write-Host "  4) GitHub Actions -> GPT Quant Phase 3.5.5."
Write-Host "  5) Run once manually with defaults."
Write-Host "  6) Confirm zero-fill valid state OR settlement/NAV reconciliation."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
