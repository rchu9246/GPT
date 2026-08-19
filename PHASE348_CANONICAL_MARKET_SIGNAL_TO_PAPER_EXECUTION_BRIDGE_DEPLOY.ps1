#requires -Version 5.1
<#
PHASE348_CANONICAL_MARKET_SIGNAL_TO_PAPER_EXECUTION_BRIDGE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8 — Canonical Market Signal -> Paper Execution Bridge

Purpose
-------
Replace Phase 3.4.7 synthetic infrastructure fallback with a strict,
production-paper-only bridge that requires REAL canonical signal evidence
and REAL market-price evidence from the repository/runtime artifacts.

Execution chain:
  canonical market data
  -> V9.1 canonical signal evidence
  -> qualification / runtime gate
  -> strict market-price bridge
  -> paper order candidates
  -> Phase 3.4.7-compatible simulated execution artifacts

Hard rules
----------
- NO synthetic fallback.
- NO fixed fake prices.
- NO order if canonical signal evidence is missing.
- NO order if market price is missing or invalid.
- NO order if Phase 3.4.6 runtime gate is not OPEN.
- NO broker API.
- NO broker credentials.
- NO real order submission.
- NO real-money trading.
- Missing/inconsistent evidence => BLOCKED or ZERO_ORDERS, fail-closed.

This deployer creates/overwrites:
  automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py
  .github/workflows/gpt-quant-v92-paper-trading-phase348-canonical-market-signal-to-paper-execution-bridge.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 88) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 88) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Write-Section "GPT Quant V9.2 — Phase 3.4.8 Canonical Market Signal -> Paper Execution Bridge"

$repoRoot = $null
try {
    $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repoRoot = $null
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    Fail "This script must be run inside the GPT Git repository."
}

Set-Location $repoRoot
Write-Host "Repository: $repoRoot" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py",
    "automation/v92/paper_trading_phase347_production_paper_simulated_execution_engine.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase348-canonical-market-signal-to-paper-execution-bridge.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase348-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Write-Section "Writing Phase 3.4.8 Python bridge"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase348_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"

SCORE_THRESHOLD = float(os.getenv("PHASE348_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE348_MAX_CANDIDATES", "3"))
INITIAL_CASH = float(os.getenv("PHASE348_INITIAL_CASH", "1000000"))
MAX_POSITION_PCT = float(os.getenv("PHASE348_MAX_POSITION_PCT", "0.20"))
ROUND_LOT = int(os.getenv("PHASE348_ROUND_LOT", "1000"))

PHASE346 = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase346_production_paper_runtime_execution_gate.py"
)

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"

CONTRACT = "PHASE348_CANONICAL_MARKET_SIGNAL_TO_PAPER_EXECUTION_BRIDGE"
SAFETY_CONTRACT = "REAL_CANONICAL_EVIDENCE_ONLY_ZERO_SYNTHETIC_ZERO_BROKER"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_payload(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def run_gate(approver: str) -> None:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    proc = subprocess.run(
        [
            sys.executable,
            str(PHASE346),
            "--approver",
            approver,
            "--note",
            "Phase 3.4.8 same-run canonical signal bridge gate reconstruction",
        ],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")

    if proc.returncode != 0:
        raise RuntimeError(f"Phase 3.4.6 runtime gate failed with exit code {proc.returncode}")


def extract_rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if isinstance(raw, dict):
        for key in (
            "signals",
            "top_candidates",
            "candidates",
            "items",
            "data",
            "rows",
            "results",
        ):
            value = raw.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

    return []


def candidate_signal_paths() -> list[Path]:
    explicit = os.getenv("PHASE348_SIGNAL_JSON", "").strip()
    paths: list[Path] = []

    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = ROOT / p
        paths.append(p)

    paths.extend(
        [
            ROOT / "phase21_output/signals.json",
            ROOT / "phase21_output/phase21_signals.json",
            ROOT / "phase28_output/signals.json",
            ROOT / "phase29_output/signals.json",
            ROOT / "phase30_output/signals.json",
            ROOT / "phase31_output/signals.json",
            ROOT / "phase32_output/signals.json",
            ROOT / "phase33_output/signals.json",
            ROOT / "output/signals.json",
            ROOT / "output/latest_signals.json",
            ROOT / "artifacts/signals.json",
            ROOT / "artifacts/latest_signals.json",
        ]
    )

    return paths


def normalize_signal(item: dict[str, Any], source: Path) -> dict[str, Any] | None:
    symbol = str(
        item.get("symbol")
        or item.get("stock_id")
        or item.get("ticker")
        or item.get("stock_symbol")
        or ""
    ).strip()

    if not symbol:
        return None

    signal = str(item.get("signal") or item.get("action") or "").strip().upper()
    if signal not in ("BUY", "LONG"):
        return None

    score_raw = (
        item.get("total_score")
        if item.get("total_score") is not None
        else item.get("score")
    )
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        return None

    if score < SCORE_THRESHOLD:
        return None

    trade_date = str(
        item.get("trade_date")
        or item.get("market_date")
        or item.get("date")
        or ""
    ).strip()

    strategy = str(
        item.get("strategy_version")
        or item.get("strategy")
        or STRATEGY
    ).strip()

    # If a strategy version is explicitly present, it must match.
    if strategy and strategy.upper() != STRATEGY.upper():
        return None

    return {
        "symbol": symbol,
        "signal": "BUY",
        "score": round(score, 4),
        "trade_date": trade_date,
        "strategy_version": STRATEGY,
        "signal_source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        "synthetic_evidence": False,
    }


def load_real_canonical_signals() -> tuple[list[dict[str, Any]], str | None]:
    for path in candidate_signal_paths():
        if not path.exists():
            continue

        try:
            raw = load_json(path)
        except Exception:
            continue

        rows = extract_rows(raw)
        normalized: list[dict[str, Any]] = []

        for item in rows:
            n = normalize_signal(item, path)
            if n:
                normalized.append(n)

        if normalized:
            normalized.sort(key=lambda x: (-float(x["score"]), x["symbol"]))
            return normalized[:MAX_CANDIDATES], str(path.relative_to(ROOT))

    return [], None


def collect_market_price_maps() -> list[tuple[Path, dict[str, float]]]:
    """
    Discover real market-price evidence already produced by repository/runtime artifacts.

    Accepted evidence must:
    - exist as JSON,
    - contain a symbol/ticker key,
    - contain a strictly positive price-like field,
    - never come from Phase 3.4.7 synthetic fallback artifacts.
    """

    explicit = os.getenv("PHASE348_MARKET_JSON", "").strip()
    paths: list[Path] = []

    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = ROOT / p
        paths.append(p)

    paths.extend(
        [
            ROOT / "market_data/latest_market.json",
            ROOT / "market_data/market_snapshot.json",
            ROOT / "output/latest_market.json",
            ROOT / "output/market_snapshot.json",
            ROOT / "artifacts/latest_market.json",
            ROOT / "artifacts/market_snapshot.json",
            ROOT / "phase22_output/market_data.json",
            ROOT / "phase22_output/latest_market.json",
            ROOT / "phase28_output/market_data.json",
            ROOT / "phase29_output/market_data.json",
            ROOT / "phase30_output/market_data.json",
            ROOT / "phase31_output/market_data.json",
            ROOT / "phase32_output/market_data.json",
            ROOT / "phase33_output/market_data.json",
        ]
    )

    maps: list[tuple[Path, dict[str, float]]] = []

    for path in paths:
        if not path.exists():
            continue

        try:
            raw = load_json(path)
        except Exception:
            continue

        rows = extract_rows(raw)
        if not rows and isinstance(raw, dict):
            # Also support dict keyed by symbol.
            candidate_rows = []
            for key, value in raw.items():
                if isinstance(value, dict):
                    row = dict(value)
                    row.setdefault("symbol", key)
                    candidate_rows.append(row)
            rows = candidate_rows

        price_map: dict[str, float] = {}

        for item in rows:
            symbol = str(
                item.get("symbol")
                or item.get("stock_id")
                or item.get("ticker")
                or item.get("stock_symbol")
                or ""
            ).strip()

            if not symbol:
                continue

            price = None
            for key in (
                "close",
                "price",
                "last_price",
                "market_price",
                "close_price",
                "reference_price",
            ):
                if item.get(key) is not None:
                    try:
                        p = float(item[key])
                    except (TypeError, ValueError):
                        continue
                    if p > 0:
                        price = p
                        break

            if price is not None:
                price_map[symbol] = price

        if price_map:
            maps.append((path, price_map))

    return maps


def attach_real_market_prices(
    signals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    maps = collect_market_price_maps()
    errors: list[str] = []
    bridged: list[dict[str, Any]] = []

    for signal in signals:
        symbol = signal["symbol"]
        matched = None

        for source_path, price_map in maps:
            if symbol in price_map:
                matched = {
                    **signal,
                    "market_price": float(price_map[symbol]),
                    "market_price_source": (
                        str(source_path.relative_to(ROOT))
                        if source_path.is_relative_to(ROOT)
                        else str(source_path)
                    ),
                    "synthetic_evidence": False,
                }
                break

        if matched:
            bridged.append(matched)
        else:
            errors.append(f"No real market price evidence found for {symbol}")

    return bridged, errors


def round_lot_quantity(target_notional: float, price: float) -> int:
    if price <= 0:
        return 0

    raw_qty = int(target_notional // price)
    if raw_qty <= 0:
        return 0

    if ROUND_LOT <= 1:
        return raw_qty

    board_lot = (raw_qty // ROUND_LOT) * ROUND_LOT
    if board_lot > 0:
        return board_lot

    # Production-paper bridge permits odd-lot simulation when portfolio capital
    # is insufficient for a board lot. Price must still be real evidence.
    return raw_qty


def simulate_real_evidence_execution(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    cash = INITIAL_CASH
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []

    per_position_cap = INITIAL_CASH * MAX_POSITION_PCT

    for rank, c in enumerate(candidates[:MAX_CANDIDATES], start=1):
        price = float(c["market_price"])
        budget = min(per_position_cap, cash)
        qty = round_lot_quantity(budget, price)

        if qty <= 0:
            continue

        notional = round(qty * price, 4)
        if notional > cash:
            qty = int(cash // price)
            notional = round(qty * price, 4)

        if qty <= 0 or notional <= 0:
            continue

        order_id = f"P348-{rank:02d}-{c['symbol']}"
        fill_id = f"{order_id}-FILL"

        order = {
            "order_id": order_id,
            "symbol": c["symbol"],
            "side": "BUY",
            "order_type": "PAPER_MARKET",
            "quantity": qty,
            "reference_price": price,
            "signal_score": c["score"],
            "signal_source": c["signal_source"],
            "market_price_source": c["market_price_source"],
            "status": "SIMULATED_FILLED",
            "broker_submitted": False,
            "real_money": False,
            "synthetic_evidence": False,
        }

        fill = {
            "fill_id": fill_id,
            "order_id": order_id,
            "symbol": c["symbol"],
            "side": "BUY",
            "quantity": qty,
            "fill_price": price,
            "gross_notional": notional,
            "commission": 0.0,
            "tax": 0.0,
            "slippage": 0.0,
            "execution_venue": "GPT_QUANT_PAPER_SIMULATOR_REAL_EVIDENCE",
            "broker_submitted": False,
            "real_money": False,
            "synthetic_evidence": False,
        }

        cash = round(cash - notional, 4)

        positions.append(
            {
                "symbol": c["symbol"],
                "quantity": qty,
                "average_cost": price,
                "mark_price": price,
                "market_value": notional,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "signal_score": c["score"],
                "signal_source": c["signal_source"],
                "market_price_source": c["market_price_source"],
                "synthetic_evidence": False,
            }
        )

        orders.append(order)
        fills.append(fill)

    market_value = round(sum(float(p["market_value"]) for p in positions), 4)
    realized = round(sum(float(p["realized_pnl"]) for p in positions), 4)
    unrealized = round(sum(float(p["unrealized_pnl"]) for p in positions), 4)
    nav = round(cash + market_value, 4)

    portfolio = {
        "initial_cash": INITIAL_CASH,
        "cash": cash,
        "market_value": market_value,
        "nav": nav,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
    }

    return orders, fills, positions, portfolio


def write_outputs(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = sha256_payload(result)

    files = {
        "phase348_execution.json": result,
        "phase348_candidates.json": result["canonical_candidates"],
        "phase348_orders.json": result["orders"],
        "phase348_fills.json": result["fills"],
        "phase348_positions.json": result["positions"],
        "phase348_portfolio.json": result["portfolio"],
    }

    for name, payload in files.items():
        (OUT / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8",
        "",
        "## Canonical Market Signal -> Paper Execution Bridge",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Bridge Contract: **{result['bridge_contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        (
            "- Paper Execution Authorized: "
            f"**{'YES' if result['paper_execution_authorized'] else 'NO'}**"
        ),
        "",
        "### Canonical Evidence",
        "",
        f"- Canonical Signal Source: `{result['canonical_signal_source'] or 'NONE'}`",
        f"- Canonical Signals Found: **{result['canonical_signals_found']}**",
        f"- Signals With Real Market Price: **{result['signals_with_real_market_price']}**",
        "- Synthetic fallback allowed: **NO**",
        "- Synthetic evidence present: **NO**",
        "",
        "### Paper Execution",
        "",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
        f"- Execution State: **{result['execution_state']}**",
        "",
        "### Portfolio",
        "",
        f"- Initial Cash: **{result['portfolio']['initial_cash']:.2f}**",
        f"- Ending Cash: **{result['portfolio']['cash']:.2f}**",
        f"- Market Value: **{result['portfolio']['market_value']:.2f}**",
        f"- NAV: **{result['portfolio']['nav']:.2f}**",
        f"- Realized P&L: **{result['portfolio']['realized_pnl']:.2f}**",
        f"- Unrealized P&L: **{result['portfolio']['unrealized_pnl']:.2f}**",
        "",
        "### Safety Boundary",
        "",
        "- Broker API used: **NO**",
        "- Broker credentials used: **NO**",
        "- Broker order submission: **DISABLED**",
        "- Real-money trading: **DISABLED**",
        "- Live-money release authorized: **NO**",
        "- Fail-closed policy: **ENABLED**",
        (
            "- Fail-closed triggered: "
            f"**{'YES' if result['fail_closed_triggered'] else 'NO'}**"
        ),
        f"- Evidence SHA256: `{result['evidence_sha256']}`",
    ]

    if result.get("errors"):
        lines.extend(["", "### Evidence Notes / Errors", ""])
        lines.extend(f"- {e}" for e in result["errors"])

    md = "\n".join(lines) + "\n"
    (OUT / "phase348_execution.md").write_text(md, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(md)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE348_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety violation: mode must remain SHADOW_ONLY_NO_BROKER")

    run_gate(approver)
    gate = load_json(GATE_JSON)

    gate_errors: list[str] = []

    if gate.get("status") != "PASS":
        gate_errors.append("Phase 3.4.6 status is not PASS")
    if gate.get("runtime_execution_gate") != "OPEN":
        gate_errors.append("Runtime Execution Gate is not OPEN")
    if gate.get("paper_execution_authorized") is not True:
        gate_errors.append("Paper Execution Authorized is not true")
    if gate.get("production_paper_release_state") != "ACTIVE":
        gate_errors.append("Production Paper Release is not ACTIVE")
    if gate.get("broker_trading_enabled") is not False:
        gate_errors.append("Broker trading safety lock is not disabled")
    if gate.get("broker_order_submission_enabled") is not False:
        gate_errors.append("Broker order submission safety lock is not disabled")
    if gate.get("real_money_trading_enabled") is not False:
        gate_errors.append("Real-money trading safety lock is not disabled")
    if gate.get("live_money_release_authorized") is not False:
        gate_errors.append("Live-money release must remain unauthorized")

    empty_portfolio = {
        "initial_cash": INITIAL_CASH,
        "cash": INITIAL_CASH,
        "market_value": 0.0,
        "nav": INITIAL_CASH,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }

    if gate_errors:
        result = {
            "version": "3.4.8",
            "status": "BLOCKED",
            "checked_at": now_iso(),
            "strategy_version": STRATEGY,
            "trading_mode": MODE,
            "bridge_contract": CONTRACT,
            "safety_contract": SAFETY_CONTRACT,
            "runtime_execution_gate": gate.get("runtime_execution_gate", "BLOCKED"),
            "paper_execution_authorized": False,
            "canonical_signal_source": None,
            "canonical_signals_found": 0,
            "signals_with_real_market_price": 0,
            "canonical_candidates": [],
            "paper_orders_created": 0,
            "simulated_fills": 0,
            "open_positions": 0,
            "orders": [],
            "fills": [],
            "positions": [],
            "portfolio": empty_portfolio,
            "execution_state": "BLOCKED_FAIL_CLOSED",
            "synthetic_fallback_allowed": False,
            "synthetic_evidence_present": False,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "fail_closed_triggered": True,
            "errors": gate_errors,
        }
        write_outputs(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("PHASE348 BLOCKED / FAIL-CLOSED: " + "; ".join(gate_errors), file=sys.stderr)
        return 2

    signals, signal_source = load_real_canonical_signals()

    if not signals:
        result = {
            "version": "3.4.8",
            "status": "PASS",
            "checked_at": now_iso(),
            "strategy_version": STRATEGY,
            "trading_mode": MODE,
            "bridge_contract": CONTRACT,
            "safety_contract": SAFETY_CONTRACT,
            "runtime_execution_gate": "OPEN",
            "paper_execution_authorized": True,
            "canonical_signal_source": signal_source,
            "canonical_signals_found": 0,
            "signals_with_real_market_price": 0,
            "canonical_candidates": [],
            "paper_orders_created": 0,
            "simulated_fills": 0,
            "open_positions": 0,
            "orders": [],
            "fills": [],
            "positions": [],
            "portfolio": empty_portfolio,
            "execution_state": "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
            "synthetic_fallback_allowed": False,
            "synthetic_evidence_present": False,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "fail_closed_triggered": False,
            "errors": ["No eligible real canonical signal evidence found; zero orders by design."],
        }
        write_outputs(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("PHASE348 PASS: no canonical signal -> zero orders. Synthetic fallback disabled.")
        return 0

    bridged, price_errors = attach_real_market_prices(signals)

    if not bridged:
        result = {
            "version": "3.4.8",
            "status": "PASS",
            "checked_at": now_iso(),
            "strategy_version": STRATEGY,
            "trading_mode": MODE,
            "bridge_contract": CONTRACT,
            "safety_contract": SAFETY_CONTRACT,
            "runtime_execution_gate": "OPEN",
            "paper_execution_authorized": True,
            "canonical_signal_source": signal_source,
            "canonical_signals_found": len(signals),
            "signals_with_real_market_price": 0,
            "canonical_candidates": [],
            "paper_orders_created": 0,
            "simulated_fills": 0,
            "open_positions": 0,
            "orders": [],
            "fills": [],
            "positions": [],
            "portfolio": empty_portfolio,
            "execution_state": "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
            "synthetic_fallback_allowed": False,
            "synthetic_evidence_present": False,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "fail_closed_triggered": False,
            "errors": price_errors or ["No real market-price evidence found; zero orders by design."],
        }
        write_outputs(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("PHASE348 PASS: no real market price -> zero orders. Synthetic fallback disabled.")
        return 0

    orders, fills, positions, portfolio = simulate_real_evidence_execution(bridged)

    result = {
        "version": "3.4.8",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "bridge_contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": "OPEN",
        "paper_execution_authorized": True,
        "canonical_signal_source": signal_source,
        "canonical_signals_found": len(signals),
        "signals_with_real_market_price": len(bridged),
        "canonical_candidates": bridged,
        "paper_orders_created": len(orders),
        "simulated_fills": len(fills),
        "open_positions": len(positions),
        "orders": orders,
        "fills": fills,
        "positions": positions,
        "portfolio": portfolio,
        "execution_state": (
            "REAL_CANONICAL_EVIDENCE_EXECUTED"
            if orders
            else "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS"
        ),
        "risk_limits": {
            "score_threshold": SCORE_THRESHOLD,
            "max_candidates": MAX_CANDIDATES,
            "initial_cash": INITIAL_CASH,
            "max_position_pct": MAX_POSITION_PCT,
            "round_lot": ROUND_LOT,
        },
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": False,
        "errors": price_errors,
    }

    write_outputs(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE348 PASS: real canonical evidence bridge complete. "
        f"signals={len(signals)}, priced={len(bridged)}, "
        f"orders={len(orders)}, fills={len(fills)}. "
        "Synthetic fallback disabled; zero broker orders."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Write-Section "Writing Phase 3.4.8 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8 - Canonical Market Signal to Paper Execution Bridge

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string

      approver:
        description: Human approver/operator ID for same-run gate reconstruction
        required: true
        default: rchu9246
        type: string

      initial_cash:
        description: Production Paper initial cash
        required: true
        default: "1000000"
        type: string

      max_position_pct:
        description: Max allocation per new paper position
        required: true
        default: "0.20"
        type: string

      max_candidates:
        description: Max canonical signals processed per run
        required: true
        default: "3"
        type: string

      score_threshold:
        description: Minimum V9.1 canonical signal score
        required: true
        default: "65"
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase348-canonical-market-signal-paper-execution
  cancel-in-progress: false

jobs:
  canonical-market-signal-paper-execution:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}

      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER

      PHASE3421_REQUIRED_PASS_DAYS: "5"
      PHASE344_REQUIRED_PASS_DAYS: "5"
      PHASE345_REQUIRED_PASS_DAYS: "5"
      PHASE346_REQUIRED_PASS_DAYS: "5"

      PHASE348_INITIAL_CASH: ${{ inputs.initial_cash || '1000000' }}
      PHASE348_MAX_POSITION_PCT: ${{ inputs.max_position_pct || '0.20' }}
      PHASE348_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}
      PHASE348_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE348_ROUND_LOT: "1000"

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install runtime dependency
        run: python -m pip install --upgrade pip requests

      - name: Validate Phase 3.4.8 strict evidence contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py
          test -f automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py

          grep -q 'REAL_CANONICAL_EVIDENCE_ONLY_ZERO_SYNTHETIC_ZERO_BROKER' \
            automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          grep -q '"synthetic_fallback_allowed": False' \
            automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          grep -q '"synthetic_evidence_present": False' \
            automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          grep -q '"broker_api_used": False' \
            automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py

          echo "Phase 3.4.8 strict evidence contract: PASS"

      - name: Execute Phase 3.4.8 canonical market signal bridge
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase348_output/phase348_execution.json
          test -f phase348_output/phase348_candidates.json
          test -f phase348_output/phase348_orders.json
          test -f phase348_output/phase348_fills.json
          test -f phase348_output/phase348_positions.json
          test -f phase348_output/phase348_portfolio.json

          python - <<'PY'
          import json
          from pathlib import Path

          data = json.loads(
              Path("phase348_output/phase348_execution.json").read_text(
                  encoding="utf-8"
              )
          )

          assert data["version"] == "3.4.8", data
          assert data["status"] == "PASS", data
          assert data["runtime_execution_gate"] == "OPEN", data
          assert data["paper_execution_authorized"] is True, data

          # Phase 3.4.8 must never reintroduce synthetic fallback.
          assert data["synthetic_fallback_allowed"] is False, data
          assert data["synthetic_evidence_present"] is False, data

          assert data["broker_api_used"] is False, data
          assert data["broker_credentials_used"] is False, data
          assert data["broker_order_submission_enabled"] is False, data
          assert data["real_money_trading_enabled"] is False, data
          assert data["live_money_release_authorized"] is False, data
          assert data["fail_closed_policy"] is True, data
          assert data["fail_closed_triggered"] is False, data

          for candidate in data["canonical_candidates"]:
              assert candidate["synthetic_evidence"] is False, candidate
              assert float(candidate["market_price"]) > 0, candidate
              assert candidate["market_price_source"], candidate
              assert candidate["signal_source"], candidate

          for order in data["orders"]:
              assert order["synthetic_evidence"] is False, order
              assert order["broker_submitted"] is False, order
              assert order["real_money"] is False, order
              assert order["order_type"] == "PAPER_MARKET", order

          for fill in data["fills"]:
              assert fill["synthetic_evidence"] is False, fill
              assert fill["broker_submitted"] is False, fill
              assert fill["real_money"] is False, fill
              assert (
                  fill["execution_venue"]
                  == "GPT_QUANT_PAPER_SIMULATOR_REAL_EVIDENCE"
              ), fill

          # Zero orders is a valid PASS when no real canonical signal/price exists.
          if data["paper_orders_created"] == 0:
              assert data["simulated_fills"] == 0, data
              assert data["execution_state"] in {
                  "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
                  "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
                  "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
              }, data
          else:
              assert (
                  data["execution_state"]
                  == "REAL_CANONICAL_EVIDENCE_EXECUTED"
              ), data
              assert data["simulated_fills"] == data["paper_orders_created"], data
              assert data["signals_with_real_market_price"] > 0, data

          print("Phase 3.4.8 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8 canonical execution evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase348-canonical-paper-execution-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
            phase345_output/
            phase3451_output/
            phase346_output/
            phase348_output/
          if-no-files-found: warn
          retention-days: 90
'@

Set-Content -LiteralPath $workflowTarget -Value $workflow -Encoding UTF8
Write-Host "Wrote: $workflowTarget" -ForegroundColor Green

Write-Section "Static validation"

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
    'PHASE348_CANONICAL_MARKET_SIGNAL_TO_PAPER_EXECUTION_BRIDGE',
    'REAL_CANONICAL_EVIDENCE_ONLY_ZERO_SYNTHETIC_ZERO_BROKER',
    '"synthetic_fallback_allowed": False',
    '"synthetic_evidence_present": False',
    '"broker_api_used": False',
    '"broker_credentials_used": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False',
    '"live_money_release_authorized": False',
    'NO_CANONICAL_SIGNAL_ZERO_ORDERS',
    'NO_REAL_MARKET_PRICE_ZERO_ORDERS',
    'REAL_CANONICAL_EVIDENCE_EXECUTED'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8 strict evidence scan: PASS" -ForegroundColor Green

Write-Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Write-Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Expected PASS modes:" -ForegroundColor Cyan
Write-Host "  A) REAL_CANONICAL_EVIDENCE_EXECUTED"
Write-Host "     -> real canonical signals + real market prices -> paper orders/fills"
Write-Host ""
Write-Host "  B) NO_CANONICAL_SIGNAL_ZERO_ORDERS"
Write-Host "     -> no real eligible signal -> 0 orders by design"
Write-Host ""
Write-Host "  C) NO_REAL_MARKET_PRICE_ZERO_ORDERS"
Write-Host "     -> signal exists but real price missing -> 0 orders by design"
Write-Host ""

Write-Host "Hard safety / data-integrity locks:" -ForegroundColor Yellow
Write-Host "  Synthetic fallback: DISABLED"
Write-Host "  Fixed fake prices: DISABLED"
Write-Host "  Broker API used: NO"
Write-Host "  Broker credentials used: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Review GitHub Desktop changes."
Write-Host "  2) Commit and Push origin."
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8."
Write-Host "  4) Run workflow with defaults first."
Write-Host "  5) Confirm Synthetic fallback allowed = NO."
Write-Host "  6) Confirm either real-evidence execution OR zero orders by design."
Write-Host ""
Write-Host "Backup folder (only if prior targets existed): $backupRoot" -ForegroundColor DarkGray
