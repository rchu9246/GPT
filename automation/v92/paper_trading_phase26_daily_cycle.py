#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 2.7.3 Schema-Compatible Snapshot Fix
Automatic Daily Trading Cycle + Schema-Compatible Dashboard Snapshot

Hotfix:
- Fixes: AttributeError: 'list' object has no attribute 'get'
- JSON log parser now accepts only dict/object summaries, not JSON arrays.
- Keeps Phase 2.5 -> 2.2 -> 2.1 -> 2.3 -> 2.4 orchestration unchanged.
- Keeps SHADOW_ONLY_NO_BROKER safety mode.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = os.getenv("PAPER_TRADING_MODE", "SHADOW_ONLY_NO_BROKER")

RUN_DATE = datetime.now(timezone.utc).astimezone().date().isoformat()
RUN_KEY = f"{RUN_DATE}-{STRATEGY_VERSION}"

PHASE25 = ROOT / "automation/v92/paper_trading_phase25_orchestrator.py"


def rest(method, table, query="", payload=None, prefer=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url += "?" + query

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    data = None if payload is None else json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Supabase {method} {table}: HTTP {e.code}: {body}"
        ) from e


def last_json_object(path: Path):
    """
    Return the last valid JSON OBJECT found in a log.

    Phase 2.6 v1.0 incorrectly accepted both dict and list:
        isinstance(x, (dict, list))

    This hotfix intentionally accepts dict only.
    """
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    objects = []

    for index, char in enumerate(text):
        if char != "{":
            continue

        try:
            obj, _ = decoder.raw_decode(text[index:])
        except Exception:
            continue

        if isinstance(obj, dict):
            objects.append(obj)

    return objects[-1] if objects else {}



def latest_market_date_source_of_truth():
    """
    Phase 2.7.2: resolve latest persisted market date directly from Supabase.
    Never invent a date. Missing tables/columns are tolerated for compatibility.
    """
    candidates = [
        ("market_data", "trade_date"),
        ("market_data", "date"),
        ("daily_market_data", "trade_date"),
        ("daily_market_data", "date"),
        ("stock_prices", "trade_date"),
        ("stock_prices", "date"),
        ("prices", "trade_date"),
        ("prices", "date"),
        ("signals", "trade_date"),
        ("signals", "date"),
    ]

    for table, column in candidates:
        try:
            query = (
                f"select={urllib.parse.quote(column)}"
                f"&{urllib.parse.quote(column)}=not.is.null"
                f"&order={urllib.parse.quote(column)}.desc"
                "&limit=1"
            )
            rows = rest("GET", table, query=query)
            if isinstance(rows, list) and rows:
                row = rows[0]
                if isinstance(row, dict) and row.get(column):
                    print(
                        f"[Phase 2.7.2] latest_market_date source: "
                        f"{table}.{column}={row[column]}"
                    )
                    return str(row[column]), f"{table}.{column}"
        except Exception as exc:
            print(
                f"[Phase 2.7.2] source skipped: {table}.{column}: "
                f"{type(exc).__name__}"
            )

    return None, None

def upsert_snapshot(payload):
    """
    Phase 2.7.3 schema-compatible snapshot upsert.

    Monitoring fields can exist in Python before the Supabase table has been
    migrated. When PostgREST returns PGRST204 for an optional monitoring
    column, remove only that optional field and retry the same upsert.

    Core accounting/trading snapshot fields remain mandatory and are never
    silently removed.
    """
    query = urllib.parse.urlencode({"on_conflict": "run_key"})
    working = dict(payload)

    optional_monitor_fields = {
        "market_date_integrity",
        "market_date_source",
    }

    while True:
        try:
            return rest(
                "POST",
                "gptq_paper_daily_snapshots",
                query=query,
                payload=working,
                prefer="resolution=merge-duplicates,return=representation",
            )
        except RuntimeError as exc:
            message = str(exc)

            missing = None
            marker = "Could not find the '"
            suffix = "' column of 'gptq_paper_daily_snapshots'"

            if marker in message and suffix in message:
                missing = message.split(marker, 1)[1].split(suffix, 1)[0]

            if (
                missing
                and missing in optional_monitor_fields
                and missing in working
            ):
                print(
                    "[Phase 2.7.3] Optional Supabase snapshot column "
                    f"'{missing}' is unavailable; retrying without it."
                )
                working.pop(missing, None)
                continue

            raise


def require_dict(name, value):
    if not isinstance(value, dict):
        raise RuntimeError(
            f"{name} summary parser returned {type(value).__name__}, expected dict"
        )
    return value


def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(
            f"Safety lock: PAPER_TRADING_MODE must be SHADOW_ONLY_NO_BROKER, got {MODE}"
        )

    if not PHASE25.exists():
        raise RuntimeError(f"Missing Phase 2.5 orchestrator: {PHASE25}")

    print("=== GPT Quant V9.2 Phase 2.7.3 Schema-Compatible Snapshot Fix ===")
    print("=== Running Phase 2.5 automatic trading pipeline ===")

    process = subprocess.run(
        [sys.executable, str(PHASE25)],
        cwd=ROOT,
        env=os.environ.copy(),
    )

    if process.returncode != 0:
        raise RuntimeError(
            "Phase 2.5 failed; Phase 2.7.2 dashboard snapshot blocked"
        )

    phase25_result_path = ROOT / "phase25_result.json"
    if not phase25_result_path.exists():
        raise RuntimeError("Missing phase25_result.json")

    phase25 = json.loads(
        phase25_result_path.read_text(encoding="utf-8")
    )

    phase21 = require_dict(
        "Phase 2.1",
        last_json_object(ROOT / "phase25_logs/phase2_1.log"),
    )

    phase23 = require_dict(
        "Phase 2.3",
        last_json_object(ROOT / "phase25_logs/phase2_3.log"),
    )

    phase24 = require_dict(
        "Phase 2.4",
        last_json_object(ROOT / "phase25_logs/phase2_4.log"),
    )

    phase_status = {
        row.get("phase"): row.get("status")
        for row in phase25.get("phases", [])
        if isinstance(row, dict)
    }

    market_data = phase21.get("market_data") or {}
    if not isinstance(market_data, dict):
        market_data = {}

    signal_engine = phase21.get("signal_engine") or {}
    if not isinstance(signal_engine, dict):
        signal_engine = {}

    persisted_market_date, market_date_source = latest_market_date_source_of_truth()
    latest_market_date = (
        persisted_market_date
        or market_data.get("latest_market_date")
    )

    snapshot = {
        "run_key": RUN_KEY,
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "mode": MODE,

        "status": phase25.get("status", "UNKNOWN"),
        "pipeline_status": phase25.get("pipeline", "UNKNOWN"),

        "phase22_status": phase_status.get("2.2", "UNKNOWN"),
        "phase21_status": phase_status.get("2.1", "UNKNOWN"),
        "phase23_status": phase_status.get("2.3", "UNKNOWN"),
        "phase24_status": phase_status.get("2.4", "UNKNOWN"),

        "latest_market_date": latest_market_date,
        "market_date_source": market_date_source or "phase21.market_data",
        "market_date_integrity": "PASS" if latest_market_date else "FAIL",

        "signals_eligible": signal_engine.get("signals_eligible", 0),
        "top_symbol": signal_engine.get("top_symbol"),
        "top_score": signal_engine.get("top_score"),

        "orders_created": phase23.get("orders_created", 0),
        "positions_open": phase24.get(
            "positions_open",
            phase23.get("positions_open", 0),
        ),

        "cash": phase24.get(
            "ending_cash",
            phase23.get("ending_cash", 0),
        ),

        "market_value": phase24.get(
            "ending_market_value",
            phase23.get("market_value", 0),
        ),

        "equity": phase24.get(
            "ending_equity",
            phase23.get("ending_equity", 0),
        ),

        "realized_pnl": phase24.get(
            "realized_pnl_today",
            0,
        ),

        "unrealized_pnl": phase24.get(
            "unrealized_pnl",
            phase23.get("unrealized_pnl", 0),
        ),

        "positions": phase24.get("decisions", []),
        "top_candidates": phase21.get("top_candidates", []),

        "raw_summary": {
            "phase25": phase25,
            "phase21": phase21,
            "phase23": phase23,
            "phase24": phase24,
        },

        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    upsert_snapshot(snapshot)

    result_path = ROOT / "phase26_result.json"
    result_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = f"""# GPT Quant V9.2 Paper Trading Phase 2.7.3

- run_key: `{RUN_KEY}`
- mode: `{MODE}`
- status: **{snapshot['status']}**
- pipeline: **{snapshot['pipeline_status']}**
- latest_market_date: `{snapshot['latest_market_date']}`
- eligible_signals: **{snapshot['signals_eligible']}**
- orders_created: **{snapshot['orders_created']}**
- positions_open: **{snapshot['positions_open']}**
- cash: **{snapshot['cash']}**
- market_value: **{snapshot['market_value']}**
- equity: **{snapshot['equity']}**
- realized_pnl: **{snapshot['realized_pnl']}**
- unrealized_pnl: **{snapshot['unrealized_pnl']}**

## Pipeline Health

| Stage | Status |
|---|---|
| Phase 2.2 Market Data | {snapshot['phase22_status']} |
| Phase 2.1 Signal Generation | {snapshot['phase21_status']} |
| Phase 2.3 Signal Execution | {snapshot['phase23_status']} |
| Phase 2.4 Position Management | {snapshot['phase24_status']} |

## Hotfix

`Phase 2.7.3 schema-compatible snapshot retry: ENABLED`

> Safety mode remains SHADOW_ONLY_NO_BROKER.
"""

    (ROOT / "phase26_summary.md").write_text(
        summary,
        encoding="utf-8",
    )

    print(json.dumps(snapshot, ensure_ascii=False, indent=2))

    success = (
        snapshot["status"] == "COMPLETED"
        and snapshot["pipeline_status"] == "COMPLETED"
        and snapshot["latest_market_date"] is not None
        and all(
            snapshot[key] == "PASS"
            for key in (
                "phase22_status",
                "phase21_status",
                "phase23_status",
                "phase24_status",
            )
        )
    )

    if not success:
        raise RuntimeError(
            "Phase 2.7.3 snapshot created, but pipeline/data integrity is not fully PASS"
        )

    print("Phase 2.7.3: COMPLETED")
    print("Dashboard snapshot upsert: COMPLETED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
