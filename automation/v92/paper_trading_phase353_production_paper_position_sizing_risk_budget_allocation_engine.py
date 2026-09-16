#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
import io
import re
import zipfile
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from paper_trading_phase348451_v91_runtime_market_data_source_discovery_signal_input_contract_fix import (
    AUTHORITY_REPOSITORY, AUTHORITY_WORKFLOW, AUTHORITY_SCHEMA_VERSION,
    canonical_rows, normalized_symbol, unique_symbols, validate_authority, finite_number,
    stable_hash as authority_hash,
)

PAPER_ONLY = True
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
HISTORICAL_REWRITE_ALLOWED = False

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

    data = response.json(parse_float=Decimal)

    if not isinstance(data, list):
        raise RuntimeError(f"{table}: expected list response")

    if any(not isinstance(x, dict) for x in data):
        raise RuntimeError(f"{table}: non-object row in response")
    return data


def explicit_producer_reference() -> tuple[str, str]:
    run_id = os.getenv("PHASE353_PRODUCER_RUN_ID", "").strip()
    attempt = os.getenv("PHASE353_PRODUCER_RUN_ATTEMPT", "").strip()
    if not all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run_id, attempt)):
        raise RuntimeError("EXPLICIT_PRODUCER_RUN_ID_AND_ATTEMPT_REQUIRED")
    if os.getenv("GITHUB_REPOSITORY") != AUTHORITY_REPOSITORY:
        raise RuntimeError("AUTHORITY_WRONG_REPOSITORY")
    return run_id, attempt


def load_explicit_authority() -> dict[str, Any]:
    run_id, attempt = explicit_producer_reference()
    token = os.getenv("GH_TOKEN", "")
    if not token:
        raise RuntimeError("AUTHORITY_ARTIFACT_READ_TOKEN_REQUIRED")
    base = f"https://api.github.com/repos/{AUTHORITY_REPOSITORY}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}

    def get_json(path: str, params=None):
        response = requests.get(base + path, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"AUTHORITY_METADATA_UNAVAILABLE HTTP={response.status_code}")
        return response.json()

    run = get_json(f"/actions/runs/{run_id}/attempts/{attempt}")
    if (str(run.get("id")) != run_id or str(run.get("run_attempt")) != attempt
            or run.get("repository", {}).get("full_name") != AUTHORITY_REPOSITORY
            or run.get("head_repository", {}).get("full_name") != AUTHORITY_REPOSITORY
            or str(run.get("path", "")).split("@", 1)[0] != AUTHORITY_WORKFLOW
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or not re.fullmatch(r"[0-9a-f]{40}", str(run.get("head_sha", "")))):
        raise RuntimeError("INVALID_PRODUCER_RUN_IDENTITY_OR_STATE")
    artifact_name = f"phase348451-market-source-discovery-{run_id}-attempt-{attempt}"
    artifacts = []
    for page in range(1, 1001):
        listing = get_json(f"/actions/runs/{run_id}/artifacts", {"per_page": 100, "page": page})
        entries = listing["artifacts"]
        artifacts.extend(entries)
        if len(artifacts) == listing["total_count"]:
            break
        if not entries or len(artifacts) > listing["total_count"]:
            raise RuntimeError("AMBIGUOUS_ARTIFACT_LIST")
    else:
        raise RuntimeError("INCOMPLETE_ARTIFACT_LIST")
    matches = [a for a in artifacts if a.get("name") == artifact_name]
    if len(matches) != 1 or matches[0].get("expired") is not False:
        raise RuntimeError("MISSING_EXPIRED_OR_AMBIGUOUS_AUTHORITY_ARTIFACT")
    artifact = matches[0]
    provenance = artifact.get("workflow_run", {})
    if str(provenance.get("id")) != run_id or provenance.get("head_sha") != run["head_sha"]:
        raise RuntimeError("ARTIFACT_PRODUCER_MISMATCH")
    if not isinstance(artifact.get("id"), int):
        raise RuntimeError("INVALID_ARTIFACT_ID")
    response = requests.get(base + f"/actions/artifacts/{artifact['id']}/zip", headers=headers, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"AUTHORITY_ARTIFACT_UNAVAILABLE HTTP={response.status_code}")
    digest = "sha256:" + hashlib.sha256(response.content).hexdigest()
    if artifact.get("digest") != digest:
        raise RuntimeError("INVALID_ARTIFACT_DIGEST")
    result_path = "phase348451_output/phase348451_signal_input_contract_fix.json"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        matches = [entry for entry in archive.infolist() if entry.filename == result_path]
        if len(matches) != 1 or matches[0].file_size > 16 * 1024 * 1024:
            raise RuntimeError("MISSING_OR_AMBIGUOUS_PRODUCER_RESULT")
        result = json.loads(archive.read(matches[0]))
    if result.get("status") != "PASS" or result.get("version") != "3.4.8.4.5.1":
        raise RuntimeError("INVALID_PRODUCER_RESULT")
    if result.get("evidence_sha256") != authority_hash({k: v for k, v in result.items() if k != "evidence_sha256"}):
        raise RuntimeError("INVALID_PRODUCER_RESULT_HASH")
    authority = result.get("canonical_authority")
    evidence = result.get("canonical_authority_evidence")
    if not isinstance(authority, dict) or not isinstance(evidence, dict):
        raise RuntimeError("PRODUCER_DID_NOT_EMIT_SIZING_AUTHORITY")
    validate_authority(authority, evidence, run_id, attempt, run["head_sha"])
    if (result.get("canonical_batch_id") != authority["canonical_batch_id"]
            or result.get("strategy_version") != "V9.1"
            or result.get("execution_state") != authority["bridge_execution_state"]):
        raise RuntimeError("PRODUCER_RESULT_AUTHORITY_MISMATCH")
    return authority


def complete_rows(table: str, params: list[tuple[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_pages = set()
    while True:
        page = rest_get(table, params + [("order", "id.asc"), ("limit", "500"), ("offset", str(len(rows)))])
        if not page:
            return rows
        signature = stable_hash(page)
        if signature in seen_pages:
            raise RuntimeError(f"INCOMPLETE_PAGINATION {table}")
        seen_pages.add(signature)
        rows.extend(page)


def same_batch_inputs(authority: dict, plan_date: str) -> tuple[list[dict], dict[str, tuple[str, Decimal]]]:
    if STRATEGY != "V9.1" or authority.get("strategy_version") != "V9.1":
        raise RuntimeError("AUTHORITY_WRONG_STRATEGY")
    if authority.get("trade_date") != plan_date:
        raise RuntimeError("AUTHORITY_TRADE_DATE_DOES_NOT_MATCH_LEDGER")
    if authority.get("authority_schema_version") != AUTHORITY_SCHEMA_VERSION or authority.get("authority_hash") != authority_hash(
            {k: v for k, v in authority.items() if k != "authority_hash"}):
        raise RuntimeError("INVALID_AUTHORITY_HASH")
    batch = authority["canonical_batch_id"]
    signals = complete_rows(SIGNALS_TABLE, [("select", "*"), ("canonical_batch_id", f"eq.{batch}"),
                                          ("strategy_version", "eq.V9.1"), ("trade_date", f"eq.{plan_date}")])
    canonical_signals = canonical_rows(signals, "signal", batch, plan_date)
    if (len(signals) != authority["signal_count"] or authority_hash(canonical_signals) != authority["signal_rows_hash"]
            or [s["symbol"] for s in canonical_signals] != authority["validated_symbol_set"]):
        raise RuntimeError(f"SIGNAL_AUTHORITY_PROVENANCE_MISMATCH batch={batch}")
    prices = []
    for signal in canonical_signals:
        rows = complete_rows(PRICES_TABLE, [("select", "*"), ("canonical_batch_id", f"eq.{batch}"),
                                            ("trade_date", f"eq.{plan_date}"), ("symbol", f"eq.{signal['symbol']}")])
        if len(rows) != 1:
            raise RuntimeError(f"EXACTLY_ONE_SAME_BATCH_PRICE_REQUIRED batch={batch} symbol={signal['symbol']} row_ids={[r.get('id') for r in rows]}")
        if normalized_symbol(rows[0].get("symbol")) != signal["symbol"]:
            raise RuntimeError(f"PRICE_SYMBOL_MISMATCH batch={batch}")
        prices.extend(rows)
    canonical_prices = canonical_rows(prices, "price", batch, plan_date)
    if len(prices) != authority["price_count"] or authority_hash(canonical_prices) != authority["price_rows_hash"]:
        raise RuntimeError(f"PRICE_AUTHORITY_PROVENANCE_MISMATCH batch={batch}")
    return canonical_signals, {r["symbol"]: (plan_date, D(r["close"])) for r in canonical_prices}


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


def signal_symbol(row: dict[str, Any]) -> str:
    return normalized_symbol(row.get("symbol"))


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
    authority: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan_date = str(ledger["ledger_date"])
    # Validate ALL selected-batch rows before sorting, truncation or allocation.
    signals, prices = same_batch_inputs(authority, plan_date)
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

    eligible.sort(key=lambda r: (-signal_score(r), signal_symbol(r)))
    eligible = eligible[:MAX_CANDIDATES]

    existing_mv = existing_market_value_by_symbol(positions)

    # Only validated authority can reach allocation; governance may still size zero.
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

        mark_date, price = prices[symbol]

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
            "canonical_authority_hash": authority["authority_hash"],
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
                "canonical_authority_hash": authority["authority_hash"],
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

    plan = {
        "canonical_authority": authority,
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
    }

    plan["evidence_sha256"] = stable_hash({
        "plan": {k: v for k, v in plan.items() if k != "evidence_sha256"}, "items": items,
    })
    return plan, items


def persist_plan(
    plan: dict[str, Any],
    items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    authority = plan["canonical_authority"]
    # Bind the immutable producer identity into the existing ID; no schema change.
    plan_id = "P353P-" + stable_hash({
        "portfolio_id": plan["portfolio_id"], "plan_date": plan["plan_date"],
        "canonical_authority_hash": authority["authority_hash"],
    })[:28]
    unique_symbols(items, authority["canonical_batch_id"])
    for item in items:
        if (item.get("canonical_authority_hash") != authority["authority_hash"]
                or normalized_symbol(item["symbol"]) not in authority["validated_symbol_set"]
                or item["symbol"] != normalized_symbol(item["symbol"])):
            raise RuntimeError("ITEM_AUTHORITY_MISMATCH")
    row = {
        "plan_id": plan_id,
        **{k: v for k, v in plan.items() if k != "canonical_authority"},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

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

    if (len({(r["plan_id"], normalized_symbol(r["symbol"])) for r in persisted_items}) != len(persisted_items)
            or len({r["item_id"] for r in persisted_items}) != len(persisted_items)):
        raise RuntimeError("DUPLICATE_PLAN_ITEM_IDENTITY")

    # All item validation precedes EITHER write. Legacy/different-authority plans
    # are never rewritten. Inserts (not merge-upserts) also close the race between
    # simultaneous callers: the existing portfolio/date UNIQUE key is the arbiter.
    existing = rest_get(PLAN_TABLE, [("select", "*"), ("portfolio_id", f"eq.{plan['portfolio_id']}"),
                                    ("plan_date", f"eq.{plan['plan_date']}")])
    if existing:
        if len(existing) != 1 or existing[0].get("plan_id") != plan_id:
            raise RuntimeError("SAME_DAY_PLAN_AUTHORITY_CONFLICT: historical provenance will not be overwritten")
        if existing[0].get("evidence_sha256") != plan["evidence_sha256"]:
            raise RuntimeError("SAME_AUTHORITY_PLAN_CONTENT_CONFLICT")
        if not persisted_row_matches(row, existing[0]):
            raise RuntimeError("EXISTING_PLAN_CONTENT_DOES_NOT_MATCH_EVIDENCE")
        old_items = complete_rows_by_plan(plan_id)
        expected = {(r["item_id"], r["symbol"], r["evidence_sha256"]) for r in persisted_items}
        actual = {(r.get("item_id"), r.get("symbol"), r.get("evidence_sha256")) for r in old_items}
        if len(old_items) != len(persisted_items) or actual != expected:
            raise RuntimeError("EXISTING_PLAN_ITEMS_INCOMPLETE_OR_CONFLICTING")
        by_id = {r["item_id"]: r for r in old_items}
        if any(not persisted_row_matches(r, by_id[r["item_id"]]) for r in persisted_items):
            raise RuntimeError("EXISTING_ITEM_CONTENT_DOES_NOT_MATCH_EVIDENCE")
        return existing[0], old_items

    rest_insert_only(PLAN_TABLE, [row])
    rest_insert_only(ITEM_TABLE, persisted_items)
    return row, persisted_items


def complete_rows_by_plan(plan_id: str) -> list[dict[str, Any]]:
    # Item tables have item_id rather than a numeric id.
    rows = []
    seen = set()
    while True:
        page = rest_get(ITEM_TABLE, [("select", "*"), ("plan_id", f"eq.{plan_id}"),
                                    ("order", "item_id.asc"), ("limit", "500"), ("offset", str(len(rows)))])
        if not page:
            return rows
        digest = stable_hash(page)
        if digest in seen:
            raise RuntimeError("INCOMPLETE_PLAN_ITEM_PAGINATION")
        seen.add(digest)
        rows.extend(page)


def rest_insert_only(table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    base, headers = supabase()
    response = requests.post(f"{base}/rest/v1/{quote(table, safe='')}",
                             headers={**headers, "Prefer": "return=minimal"},
                             data=json.dumps(rows, ensure_ascii=False, default=str), timeout=25)
    if response.status_code >= 400:
        raise RuntimeError(f"PLAN_INSERT_FAILED_CLOSED {table} HTTP={response.status_code}")


def persisted_row_matches(expected: dict, actual: dict) -> bool:
    # PostgREST returns numeric columns as numbers, while the sizing engine uses
    # decimal strings. Compare these semantically, never coercing identifiers.
    numbers = {"risk_reduction_factor", "nav", "cash", "current_market_value", "current_portfolio_exposure",
               "base_risk_budget_pct", "effective_risk_budget_pct", "max_position_pct", "max_new_capital",
               "total_allocated_capital", "remaining_risk_budget", "eligible_signals", "sized_candidates",
               "rank", "score", "real_market_price", "existing_position_market_value", "raw_target_capital",
               "concentration_capital_limit", "risk_budget_capital_limit", "final_target_capital", "round_lot",
               "paper_quantity", "estimated_notional"}
    for key, value in expected.items():
        if key == "updated_at":
            continue
        if key in numbers:
            try:
                if finite_number(value) != finite_number(actual.get(key)):
                    return False
            except RuntimeError:
                return False
        elif actual.get(key) != value:
            return False
    return True


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

    authority = load_explicit_authority()
    ledger = latest_ledger()
    # Date/provenance failures must precede upstream execution and allocation.
    same_batch_inputs(authority, str(ledger["ledger_date"]))
    upstream_exit, governance = run_upstream()
    validate_governance(governance)

    ledger = latest_ledger()
    positions = open_positions()

    plan, items = build_plan(
        governance,
        ledger,
        positions,
        authority,
    )

    persisted_plan, persisted_items = persist_plan(
        plan,
        items,
    )

    result = {
        "version": "3.5.3",
        "canonical_authority": authority,
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
