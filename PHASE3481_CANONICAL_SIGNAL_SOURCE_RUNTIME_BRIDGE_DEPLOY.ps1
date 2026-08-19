#requires -Version 5.1
<#
PHASE3481_CANONICAL_SIGNAL_SOURCE_RUNTIME_BRIDGE_DEPLOY.ps1

GPT Quant V9.2
Phase 3.4.8.1 — Canonical Signal Source Runtime Bridge

Goal
----
Fix the missing runtime signal source observed in Phase 3.4.8:

    Canonical Signal Source: NONE
    Canonical Signals Found: 0
    Execution State: NO_CANONICAL_SIGNAL_ZERO_ORDERS

This phase reconstructs canonical V9.1 signal + market-price evidence in the SAME
GitHub Actions runner, then hands the resulting evidence directly to Phase 3.4.8.

Source priority
---------------
1. Existing same-run repository JSON artifacts, if already present.
2. Supabase canonical signal / market-data tables through read-only REST queries.
3. If no valid real evidence exists -> zero orders by design.

Absolutely forbidden
--------------------
- Synthetic fallback
- Fixed fake prices
- Invented signals
- Broker API
- Broker credentials
- Real order submission
- Real-money trading

Created/overwritten
-------------------
  automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py
  .github/workflows/gpt-quant-v92-paper-trading-phase3481-canonical-signal-source-runtime-bridge.yml
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 92) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 92) -ForegroundColor DarkCyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.4.8.1 Canonical Signal Source Runtime Bridge"

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
    "automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py",
    "automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"
)

foreach ($item in $required) {
    if (-not (Test-Path $item)) {
        Fail "Required upstream file not found: $item"
    }
}

$pythonTarget = "automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase3481-canonical-signal-source-runtime-bridge.yml"

New-Item -ItemType Directory -Force -Path (Split-Path $pythonTarget) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $workflowTarget) | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase3481-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

foreach ($target in @($pythonTarget, $workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.4.8.1 Python runtime bridge"

$python = @'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase3481_output"
OUT.mkdir(exist_ok=True)

MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
SCORE_THRESHOLD = float(os.getenv("PHASE3481_SCORE_THRESHOLD", "65"))
MAX_CANDIDATES = int(os.getenv("PHASE3481_MAX_CANDIDATES", "3"))

PHASE346 = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase346_production_paper_runtime_execution_gate.py"
)

PHASE348 = (
    ROOT
    / "automation/v92/"
      "paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py"
)

GATE_JSON = ROOT / "phase346_output/phase346_runtime_gate.json"
P348_JSON = ROOT / "phase348_output/phase348_execution.json"

BRIDGE_SIGNAL_JSON = OUT / "canonical_signals.json"
BRIDGE_MARKET_JSON = OUT / "canonical_market_prices.json"
BRIDGE_EVIDENCE_JSON = OUT / "phase3481_runtime_bridge.json"

CONTRACT = "PHASE3481_CANONICAL_SIGNAL_SOURCE_RUNTIME_BRIDGE"
SAFETY_CONTRACT = "REAL_SOURCE_ONLY_NO_SYNTHETIC_NO_BROKER_NO_REAL_MONEY"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_python(script: Path, args: list[str], env: dict[str, str]) -> None:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
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
        raise RuntimeError(
            f"{script.name} failed with exit code {proc.returncode}"
        )


def run_gate(approver: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    run_python(
        PHASE346,
        [
            "--approver",
            approver,
            "--note",
            "Phase 3.4.8.1 same-run runtime bridge gate reconstruction",
        ],
        env,
    )

    if not GATE_JSON.exists():
        raise RuntimeError("Phase 3.4.6 gate evidence was not generated")

    gate = load_json(GATE_JSON)

    required = {
        "status": "PASS",
        "runtime_execution_gate": "OPEN",
        "paper_execution_authorized": True,
        "production_paper_release_state": "ACTIVE",
        "broker_trading_enabled": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
    }

    errors = []
    for key, expected in required.items():
        if gate.get(key) != expected:
            errors.append(f"{key}={gate.get(key)!r}, expected {expected!r}")

    if errors:
        raise RuntimeError(
            "Phase 3.4.6 runtime gate safety validation failed: "
            + "; ".join(errors)
        )

    return gate


def extract_rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if isinstance(raw, dict):
        for key in (
            "signals",
            "top_candidates",
            "candidates",
            "items",
            "rows",
            "data",
            "results",
        ):
            value = raw.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

    return []


def normalize_signal(
    row: dict[str, Any],
    source: str,
) -> dict[str, Any] | None:
    symbol = str(
        row.get("symbol")
        or row.get("stock_id")
        or row.get("ticker")
        or row.get("stock_symbol")
        or ""
    ).strip()

    if not symbol:
        return None

    signal = str(
        row.get("signal")
        or row.get("action")
        or row.get("recommendation")
        or ""
    ).strip().upper()

    if signal not in {"BUY", "LONG"}:
        return None

    score_value = (
        row.get("total_score")
        if row.get("total_score") is not None
        else row.get("score")
    )

    try:
        score = float(score_value)
    except (TypeError, ValueError):
        return None

    if score < SCORE_THRESHOLD:
        return None

    explicit_strategy = row.get("strategy_version") or row.get("strategy")
    if explicit_strategy:
        if str(explicit_strategy).strip().upper() != STRATEGY.upper():
            return None

    trade_date = str(
        row.get("trade_date")
        or row.get("market_date")
        or row.get("date")
        or ""
    ).strip()

    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "strategy_version": STRATEGY,
        "total_score": round(score, 4),
        "signal": "BUY",
        "source": source,
        "synthetic_evidence": False,
    }


def normalize_market_row(
    row: dict[str, Any],
    source: str,
) -> dict[str, Any] | None:
    symbol = str(
        row.get("symbol")
        or row.get("stock_id")
        or row.get("ticker")
        or row.get("stock_symbol")
        or ""
    ).strip()

    if not symbol:
        return None

    price = None
    for key in (
        "close",
        "price",
        "last_price",
        "market_price",
        "close_price",
        "reference_price",
    ):
        if row.get(key) is None:
            continue
        try:
            candidate = float(row[key])
        except (TypeError, ValueError):
            continue
        if candidate > 0:
            price = candidate
            break

    if price is None:
        return None

    market_date = str(
        row.get("trade_date")
        or row.get("market_date")
        or row.get("date")
        or ""
    ).strip()

    return {
        "symbol": symbol,
        "close": price,
        "market_date": market_date,
        "source": source,
        "synthetic_evidence": False,
    }


def repo_signal_paths() -> list[Path]:
    return [
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


def repo_market_paths() -> list[Path]:
    return [
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


def read_repo_signals() -> tuple[list[dict[str, Any]], str | None]:
    for path in repo_signal_paths():
        if not path.exists():
            continue
        try:
            rows = extract_rows(load_json(path))
        except Exception:
            continue

        normalized = []
        source = str(path.relative_to(ROOT))

        for row in rows:
            item = normalize_signal(row, source)
            if item:
                normalized.append(item)

        if normalized:
            normalized.sort(
                key=lambda x: (-float(x["total_score"]), x["symbol"])
            )
            return normalized[:MAX_CANDIDATES], source

    return [], None


def read_repo_market(
    symbols: set[str],
) -> tuple[list[dict[str, Any]], str | None]:
    for path in repo_market_paths():
        if not path.exists():
            continue

        try:
            raw = load_json(path)
        except Exception:
            continue

        rows = extract_rows(raw)

        if not rows and isinstance(raw, dict):
            keyed = []
            for key, value in raw.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("symbol", key)
                    keyed.append(item)
            rows = keyed

        normalized = []
        source = str(path.relative_to(ROOT))

        for row in rows:
            item = normalize_market_row(row, source)
            if item and item["symbol"] in symbols:
                normalized.append(item)

        if normalized:
            return normalized, source

    return [], None


def supabase_headers() -> dict[str, str] | None:
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
    )
    if not key:
        return None

    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def supabase_get(
    table: str,
    params: list[tuple[str, str]],
) -> tuple[list[dict[str, Any]], str | None]:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    headers = supabase_headers()

    if not base or not headers:
        return [], "Supabase URL/key not configured"

    url = f"{base}/rest/v1/{quote(table, safe='')}"

    try:
        resp = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15,
        )
    except requests.RequestException as exc:
        return [], f"{table}: request error: {exc}"

    if resp.status_code >= 400:
        return [], f"{table}: HTTP {resp.status_code}"

    try:
        data = resp.json()
    except ValueError:
        return [], f"{table}: invalid JSON response"

    if not isinstance(data, list):
        return [], f"{table}: response was not a row list"

    return [x for x in data if isinstance(x, dict)], None


def fetch_supabase_signals() -> tuple[list[dict[str, Any]], str | None, list[str]]:
    """
    Try known/likely signal tables without assuming one schema is guaranteed.
    A missing table is treated as discovery information, not a fatal error.
    """
    tables = [
        "signals",
        "stock_signals",
        "trading_signals",
        "signal_history",
        "signals_v91",
        "strategy_signals",
    ]

    diagnostics: list[str] = []

    for table in tables:
        rows, error = supabase_get(
            table,
            [
                ("select", "*"),
                ("order", "trade_date.desc"),
                ("limit", "50"),
            ],
        )

        if error:
            diagnostics.append(error)
            continue

        normalized = []
        source = f"supabase:{table}"

        for row in rows:
            item = normalize_signal(row, source)
            if item:
                normalized.append(item)

        if normalized:
            # Keep only the latest non-empty trade date when available.
            dated = [x for x in normalized if x.get("trade_date")]
            if dated:
                latest = max(x["trade_date"] for x in dated)
                normalized = [
                    x for x in normalized
                    if not x.get("trade_date") or x["trade_date"] == latest
                ]

            normalized.sort(
                key=lambda x: (-float(x["total_score"]), x["symbol"])
            )

            return normalized[:MAX_CANDIDATES], source, diagnostics

    return [], None, diagnostics


def fetch_supabase_market(
    symbols: set[str],
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    tables = [
        "market_data",
        "stock_prices",
        "daily_prices",
        "market_daily",
        "market_data_daily",
        "ohlcv_daily",
    ]

    diagnostics: list[str] = []

    for table in tables:
        rows, error = supabase_get(
            table,
            [
                ("select", "*"),
                ("order", "trade_date.desc"),
                ("limit", "500"),
            ],
        )

        if error:
            diagnostics.append(error)
            continue

        normalized = []
        source = f"supabase:{table}"

        for row in rows:
            item = normalize_market_row(row, source)
            if item and item["symbol"] in symbols:
                normalized.append(item)

        if not normalized:
            continue

        # Keep latest row per symbol where date exists.
        by_symbol: dict[str, dict[str, Any]] = {}
        for item in normalized:
            symbol = item["symbol"]
            existing = by_symbol.get(symbol)

            if existing is None:
                by_symbol[symbol] = item
                continue

            old_date = existing.get("market_date", "")
            new_date = item.get("market_date", "")

            if new_date and (not old_date or new_date > old_date):
                by_symbol[symbol] = item

        return list(by_symbol.values()), source, diagnostics

    return [], None, diagnostics


def align_signals_and_prices(
    signals: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    price_map = {row["symbol"]: row for row in market_rows}
    aligned_signals = []
    aligned_market = []
    errors = []

    for signal in signals:
        market = price_map.get(signal["symbol"])
        if not market:
            errors.append(
                f"No real market-price evidence for canonical signal {signal['symbol']}"
            )
            continue

        aligned_signals.append(signal)
        aligned_market.append(market)

    return aligned_signals, aligned_market, errors


def run_phase348(
    approver: str,
    signal_path: Path,
    market_path: Path,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = MODE
    env["PAPER_STRATEGY_VERSION"] = STRATEGY
    env["STRATEGY_VERSION"] = STRATEGY

    env["PHASE348_SIGNAL_JSON"] = str(signal_path)
    env["PHASE348_MARKET_JSON"] = str(market_path)
    env["PHASE348_SCORE_THRESHOLD"] = str(SCORE_THRESHOLD)
    env["PHASE348_MAX_CANDIDATES"] = str(MAX_CANDIDATES)

    run_python(
        PHASE348,
        ["--approver", approver],
        env,
    )

    if not P348_JSON.exists():
        raise RuntimeError("Phase 3.4.8 execution evidence was not generated")

    result = load_json(P348_JSON)

    if result.get("status") != "PASS":
        raise RuntimeError(
            "Phase 3.4.8 did not PASS after runtime evidence bridge"
        )

    if result.get("synthetic_fallback_allowed") is not False:
        raise RuntimeError("Synthetic fallback safety violation")

    if result.get("synthetic_evidence_present") is not False:
        raise RuntimeError("Synthetic evidence safety violation")

    return result


def write_summary(result: dict[str, Any]) -> None:
    result["evidence_sha256"] = stable_hash(result)
    dump_json(BRIDGE_EVIDENCE_JSON, result)

    lines = [
        "# GPT Quant V9.2 Paper Trading - Phase 3.4.8.1",
        "",
        "## Canonical Signal Source Runtime Bridge",
        "",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Bridge Contract: **{result['bridge_contract']}**",
        f"- Runtime Execution Gate: **{result['runtime_execution_gate']}**",
        "",
        "### Runtime Source Bridge",
        "",
        f"- Signal Source: `{result['signal_source'] or 'NONE'}`",
        f"- Market Price Source: `{result['market_price_source'] or 'NONE'}`",
        f"- Canonical Signals Found: **{result['canonical_signals_found']}**",
        f"- Canonical Signals With Real Price: **{result['canonical_signals_with_real_price']}**",
        "- Synthetic fallback allowed: **NO**",
        "- Synthetic evidence present: **NO**",
        "",
        "### Phase 3.4.8 Result",
        "",
        f"- Phase 3.4.8 Execution State: **{result['phase348_execution_state']}**",
        f"- Paper Orders Created: **{result['paper_orders_created']}**",
        f"- Simulated Fills: **{result['simulated_fills']}**",
        f"- Open Paper Positions: **{result['open_positions']}**",
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

    if result.get("diagnostics"):
        lines.extend(["", "### Source Diagnostics", ""])
        lines.extend(f"- {x}" for x in result["diagnostics"][:20])

    if result.get("errors"):
        lines.extend(["", "### Evidence Notes / Errors", ""])
        lines.extend(f"- {x}" for x in result["errors"])

    text = "\n".join(lines) + "\n"
    (OUT / "phase3481_runtime_bridge.md").write_text(text, encoding="utf-8")

    gh = os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as handle:
            handle.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approver",
        default=os.getenv("PHASE3481_APPROVER", "rchu9246"),
    )
    args = parser.parse_args()

    approver = args.approver.strip()
    if not approver:
        raise RuntimeError("Approver must not be empty")

    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            "Safety violation: mode must remain SHADOW_ONLY_NO_BROKER"
        )

    gate = run_gate(approver)

    diagnostics: list[str] = []
    errors: list[str] = []

    # 1) Prefer same-run/repository real canonical evidence.
    signals, signal_source = read_repo_signals()

    if not signals:
        signals, signal_source, diag = fetch_supabase_signals()
        diagnostics.extend(diag)

    if not signals:
        # No canonical signal is a safe zero-order state.
        dump_json(BRIDGE_SIGNAL_JSON, [])
        dump_json(BRIDGE_MARKET_JSON, [])

        phase348 = run_phase348(
            approver,
            BRIDGE_SIGNAL_JSON,
            BRIDGE_MARKET_JSON,
        )

        result = {
            "version": "3.4.8.1",
            "status": "PASS",
            "checked_at": now_iso(),
            "strategy_version": STRATEGY,
            "trading_mode": MODE,
            "bridge_contract": CONTRACT,
            "safety_contract": SAFETY_CONTRACT,
            "runtime_execution_gate": gate["runtime_execution_gate"],
            "signal_source": None,
            "market_price_source": None,
            "canonical_signals_found": 0,
            "canonical_signals_with_real_price": 0,
            "phase348_execution_state": phase348.get("execution_state"),
            "paper_orders_created": phase348.get("paper_orders_created", 0),
            "simulated_fills": phase348.get("simulated_fills", 0),
            "open_positions": phase348.get("open_positions", 0),
            "synthetic_fallback_allowed": False,
            "synthetic_evidence_present": False,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
            "fail_closed_triggered": False,
            "diagnostics": diagnostics,
            "errors": [
                "No eligible real canonical signal source found; zero orders by design."
            ],
        }

        write_summary(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            "PHASE3481 PASS: no real canonical signal source -> zero orders. "
            "Synthetic fallback remains disabled."
        )
        return 0

    symbols = {x["symbol"] for x in signals}

    market_rows, market_source = read_repo_market(symbols)

    if not market_rows:
        market_rows, market_source, diag = fetch_supabase_market(symbols)
        diagnostics.extend(diag)

    aligned_signals, aligned_market, price_errors = align_signals_and_prices(
        signals,
        market_rows,
    )
    errors.extend(price_errors)

    dump_json(BRIDGE_SIGNAL_JSON, {"signals": aligned_signals})
    dump_json(BRIDGE_MARKET_JSON, {"data": aligned_market})

    phase348 = run_phase348(
        approver,
        BRIDGE_SIGNAL_JSON,
        BRIDGE_MARKET_JSON,
    )

    result = {
        "version": "3.4.8.1",
        "status": "PASS",
        "checked_at": now_iso(),
        "strategy_version": STRATEGY,
        "trading_mode": MODE,
        "bridge_contract": CONTRACT,
        "safety_contract": SAFETY_CONTRACT,
        "runtime_execution_gate": gate["runtime_execution_gate"],
        "signal_source": signal_source,
        "market_price_source": market_source,
        "canonical_signals_found": len(signals),
        "canonical_signals_with_real_price": len(aligned_signals),
        "phase348_execution_state": phase348.get("execution_state"),
        "paper_orders_created": phase348.get("paper_orders_created", 0),
        "simulated_fills": phase348.get("simulated_fills", 0),
        "open_positions": phase348.get("open_positions", 0),
        "synthetic_fallback_allowed": False,
        "synthetic_evidence_present": False,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "fail_closed_triggered": False,
        "diagnostics": diagnostics,
        "errors": errors,
    }

    # If real signals exist but no real price could be attached, Phase 3.4.8
    # must remain zero-order. That is a valid PASS, not a synthetic fallback.
    if not aligned_signals:
        if phase348.get("paper_orders_created", 0) != 0:
            raise RuntimeError(
                "Safety violation: orders created without real signal+price alignment"
            )

    # If Phase 3.4.8 executed orders, every order must be real-evidence paper only.
    for order in phase348.get("orders", []):
        if order.get("synthetic_evidence") is not False:
            raise RuntimeError("Synthetic order evidence detected")
        if order.get("broker_submitted") is not False:
            raise RuntimeError("Broker submission safety violation")
        if order.get("real_money") is not False:
            raise RuntimeError("Real-money safety violation")

    write_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "PHASE3481 PASS: runtime canonical source bridge complete. "
        f"signals={len(signals)}, real-priced={len(aligned_signals)}, "
        f"orders={result['paper_orders_created']}, fills={result['simulated_fills']}. "
        "Synthetic fallback disabled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.4.8.1 GitHub Actions workflow"

$workflow = @'
name: GPT Quant Phase 3.4.8.1 - Canonical Signal Source Runtime Bridge

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

      score_threshold:
        description: Minimum canonical signal score
        required: true
        default: "65"
        type: string

      max_candidates:
        description: Maximum canonical signals bridged per run
        required: true
        default: "3"
        type: string

permissions:
  contents: read

concurrency:
  group: gpt-quant-phase3481-canonical-signal-runtime-bridge
  cancel-in-progress: false

jobs:
  canonical-signal-runtime-bridge:
    runs-on: ubuntu-latest
    timeout-minutes: 25

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

      PHASE3481_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE3481_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}

      PHASE348_SCORE_THRESHOLD: ${{ inputs.score_threshold || '65' }}
      PHASE348_MAX_CANDIDATES: ${{ inputs.max_candidates || '3' }}
      PHASE348_INITIAL_CASH: "1000000"
      PHASE348_MAX_POSITION_PCT: "0.20"
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

      - name: Validate Phase 3.4.8.1 safety contract
        shell: bash
        run: |
          set -euo pipefail

          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"

          test -f automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py
          test -f automation/v92/paper_trading_phase348_canonical_market_signal_to_paper_execution_bridge.py
          test -f automation/v92/paper_trading_phase346_production_paper_runtime_execution_gate.py

          grep -q 'REAL_SOURCE_ONLY_NO_SYNTHETIC_NO_BROKER_NO_REAL_MONEY' \
            automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py

          grep -q '"synthetic_fallback_allowed": False' \
            automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py

          grep -q '"synthetic_evidence_present": False' \
            automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py

          grep -q '"broker_api_used": False' \
            automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py

          grep -q '"broker_order_submission_enabled": False' \
            automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py

          grep -q '"real_money_trading_enabled": False' \
            automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py

          echo "Phase 3.4.8.1 safety contract: PASS"

      - name: Execute Phase 3.4.8.1 runtime source bridge
        shell: bash
        run: |
          set -euo pipefail

          python automation/v92/paper_trading_phase3481_canonical_signal_source_runtime_bridge.py \
            --approver "${{ inputs.approver }}"

      - name: Validate Phase 3.4.8.1 output
        shell: bash
        run: |
          set -euo pipefail

          test -f phase3481_output/phase3481_runtime_bridge.json
          test -f phase3481_output/canonical_signals.json
          test -f phase3481_output/canonical_market_prices.json
          test -f phase348_output/phase348_execution.json

          python - <<'PY'
          import json
          from pathlib import Path

          bridge = json.loads(
              Path("phase3481_output/phase3481_runtime_bridge.json").read_text(
                  encoding="utf-8"
              )
          )

          phase348 = json.loads(
              Path("phase348_output/phase348_execution.json").read_text(
                  encoding="utf-8"
              )
          )

          assert bridge["version"] == "3.4.8.1", bridge
          assert bridge["status"] == "PASS", bridge
          assert bridge["runtime_execution_gate"] == "OPEN", bridge

          assert bridge["synthetic_fallback_allowed"] is False, bridge
          assert bridge["synthetic_evidence_present"] is False, bridge
          assert bridge["broker_api_used"] is False, bridge
          assert bridge["broker_credentials_used"] is False, bridge
          assert bridge["broker_order_submission_enabled"] is False, bridge
          assert bridge["real_money_trading_enabled"] is False, bridge
          assert bridge["live_money_release_authorized"] is False, bridge

          assert phase348["status"] == "PASS", phase348
          assert phase348["synthetic_fallback_allowed"] is False, phase348
          assert phase348["synthetic_evidence_present"] is False, phase348

          if bridge["paper_orders_created"] > 0:
              assert bridge["canonical_signals_found"] > 0, bridge
              assert bridge["canonical_signals_with_real_price"] > 0, bridge
              assert (
                  bridge["phase348_execution_state"]
                  == "REAL_CANONICAL_EVIDENCE_EXECUTED"
              ), bridge
              assert bridge["simulated_fills"] == bridge["paper_orders_created"], bridge
          else:
              assert bridge["phase348_execution_state"] in {
                  "NO_CANONICAL_SIGNAL_ZERO_ORDERS",
                  "NO_REAL_MARKET_PRICE_ZERO_ORDERS",
                  "REAL_EVIDENCE_BUT_ZERO_SIZED_ORDERS",
              }, bridge

          for order in phase348.get("orders", []):
              assert order["synthetic_evidence"] is False, order
              assert order["broker_submitted"] is False, order
              assert order["real_money"] is False, order

          print("Phase 3.4.8.1 output validation: PASS")
          PY

      - name: Upload Phase 3.4.8.1 runtime bridge evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase3481-runtime-source-bridge-${{ github.run_id }}
          path: |
            phase3421_output/
            phase342_output/
            phase3442_output/
            phase344_output/
            phase345_output/
            phase3451_output/
            phase346_output/
            phase348_output/
            phase3481_output/
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
    'PHASE3481_CANONICAL_SIGNAL_SOURCE_RUNTIME_BRIDGE',
    'REAL_SOURCE_ONLY_NO_SYNTHETIC_NO_BROKER_NO_REAL_MONEY',
    '"synthetic_fallback_allowed": False',
    '"synthetic_evidence_present": False',
    '"broker_api_used": False',
    '"broker_credentials_used": False',
    '"broker_order_submission_enabled": False',
    '"real_money_trading_enabled": False',
    '"live_money_release_authorized": False',
    'PHASE348_SIGNAL_JSON',
    'PHASE348_MARKET_JSON'
)

foreach ($needle in $needles) {
    if (-not $source.Contains($needle)) {
        Fail "Required Phase 3.4.8.1 token missing: $needle"
    }
}

Write-Host "Phase 3.4.8.1 static contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"

Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""

Write-Host "Runtime source priority:" -ForegroundColor Cyan
Write-Host "  1) Existing real same-run repository JSON artifacts"
Write-Host "  2) Supabase canonical signal tables"
Write-Host "  3) Supabase market-price tables"
Write-Host "  4) If unavailable -> 0 orders (NO synthetic fallback)"
Write-Host ""

Write-Host "Desired result:" -ForegroundColor Cyan
Write-Host "  Signal Source: repository:* OR supabase:*"
Write-Host "  Canonical Signals Found: > 0"
Write-Host "  Canonical Signals With Real Price: > 0"
Write-Host "  Phase 3.4.8 Execution State: REAL_CANONICAL_EVIDENCE_EXECUTED"
Write-Host "  Paper Orders Created: > 0"
Write-Host "  Simulated Fills: > 0"
Write-Host ""

Write-Host "Safe zero-order results are also valid:" -ForegroundColor Yellow
Write-Host "  NO_CANONICAL_SIGNAL_ZERO_ORDERS"
Write-Host "  NO_REAL_MARKET_PRICE_ZERO_ORDERS"
Write-Host ""

Write-Host "Hard safety locks:" -ForegroundColor Yellow
Write-Host "  Synthetic fallback: DISABLED"
Write-Host "  Synthetic evidence: DISABLED"
Write-Host "  Broker API used: NO"
Write-Host "  Broker credentials used: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release authorized: NO"
Write-Host ""

Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Review GitHub Desktop changes."
Write-Host "  2) Commit and Push origin."
Write-Host "  3) GitHub Actions -> GPT Quant Phase 3.4.8.1."
Write-Host "  4) Run workflow with defaults."
Write-Host "  5) Inspect Signal Source / Market Price Source / execution state."
Write-Host ""
Write-Host "Backup folder (only if prior targets existed): $backupRoot" -ForegroundColor DarkGray
