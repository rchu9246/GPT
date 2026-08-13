#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 2.6.4 Data Integrity Fix
Automatic Daily Trading Cycle + Dashboard Data Integrity

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


def upsert_snapshot(payload):
    query = urllib.parse.urlencode({"on_conflict": "run_key"})

    return rest(
        "POST",
        "gptq_paper_daily_snapshots",
        query=query,
        payload=payload,
        prefer="resolution=merge-duplicates,return=representation",
    )


def require_dict(name, value):
    if not isinstance(value, dict):
        raise RuntimeError(
            f"{name} summary parser returned {type(value).__name__}, expected dict"
        )
    return value


def _first_dict(value):
    """Normalize PostgREST/list/dict payloads to one dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], dict) else {}
    return {}


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _num(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _latest_row(table, fields="*", extra_query=""):
    query = f"select={urllib.parse.quote(fields, safe='*,')}"
    if extra_query:
        query += "&" + extra_query.lstrip("&")
    query += "&order=created_at.desc&limit=1"
    try:
        return _first_dict(rest("GET", table, query=query))
    except Exception:
        return {}


def _latest_market_date():
    # Prefer the actual market-data table used by the paper engine.
    candidates = [
        ("gptq_paper_market_data", "market_date"),
        ("paper_market_data", "market_date"),
        ("market_data", "market_date"),
    ]
    for table, col in candidates:
        try:
            rows = rest(
                "GET",
                table,
                query=f"select={col}&order={col}.desc&limit=1",
            )
            row = _first_dict(rows)
            if row.get(col):
                return str(row[col])
        except Exception:
            pass
    return None


def _load_phase25_result():
    p = ROOT / "phase25_result.json"
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _extract_json_from_log(path):
    """Best-effort extraction of the last JSON object printed by a child phase."""
    p = ROOT / path
    if not p.exists():
        return {}
    raw = p.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    found = []
    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[i:])
            if isinstance(obj, dict):
                found.append(obj)
        except Exception:
            continue
    return found[-1] if found else {}


def _phase_payloads(p25):
    by_phase = {}
    for item in _as_list(p25.get("phases")):
        if not isinstance(item, dict):
            continue
        phase = str(item.get("phase", ""))
        log = item.get("log")
        if phase and log:
            by_phase[phase] = _extract_json_from_log(log)
    return by_phase


def _integrity_snapshot(p25, payloads):
    p22 = payloads.get("2.2", {})
    p21 = payloads.get("2.1", {})
    p23 = payloads.get("2.3", {})
    p24 = payloads.get("2.4", {})

    latest_market_date = (
        p22.get("latest_market_date_after")
        or (p21.get("market_data") or {}).get("latest_market_date")
        or _latest_market_date()
    )

    signal_engine = p21.get("signal_engine") or {}
    eligible_signals = _int(
        signal_engine.get("signals_eligible"),
        _int(p23.get("eligible_signals"), 0),
    )

    top_candidates = _as_list(p21.get("top_candidates"))
    top = top_candidates[0] if top_candidates and isinstance(top_candidates[0], dict) else {}

    orders_created = _int(p23.get("orders_created"), 0)
    positions_open = _int(
        p24.get("positions_open"),
        _int(p23.get("positions_open"), 0),
    )
    cash = _num(
        p24.get("ending_cash"),
        _num(p23.get("ending_cash"), 0.0),
    )
    market_value = _num(
        p24.get("ending_market_value"),
        _num(p23.get("market_value"), 0.0),
    )
    equity = _num(
        p24.get("ending_equity"),
        _num(p23.get("ending_equity"), cash + market_value),
    )
    realized_pnl = _num(p24.get("realized_pnl_today"), 0.0)
    unrealized_pnl = _num(
        p24.get("unrealized_pnl"),
        _num(p23.get("unrealized_pnl"), 0.0),
    )

    checks = {
        "phase25_completed": p25.get("pipeline") == "COMPLETED",
        "phase22_payload_present": bool(p22),
        "phase21_payload_present": bool(p21),
        "phase23_payload_present": bool(p23),
        "phase24_payload_present": bool(p24),
        "latest_market_date_present": bool(latest_market_date),
        "eligible_signal_consistency": (
            not p23
            or eligible_signals == _int(p23.get("eligible_signals"), eligible_signals)
        ),
        "equity_non_negative": equity >= 0,
        "positions_non_negative": positions_open >= 0,
    }

    critical = [
        "phase25_completed",
        "phase22_payload_present",
        "phase21_payload_present",
        "phase23_payload_present",
        "phase24_payload_present",
        "latest_market_date_present",
    ]
    integrity_ok = all(checks[k] for k in critical)

    return {
        "latest_market_date": latest_market_date,
        "eligible_signals": eligible_signals,
        "top_symbol": top.get("symbol"),
        "top_score": top.get("score"),
        "orders_created": orders_created,
        "positions_open": positions_open,
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "equity": round(equity, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "top_candidates": top_candidates,
        "positions": _as_list(p24.get("decisions")),
        "integrity_checks": checks,
        "integrity_status": "PASS" if integrity_ok else "FAIL",
    }


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    started_at = datetime.now(timezone.utc).isoformat()

    # Run the proven Phase 2.5 orchestrator unchanged.
    proc = subprocess.run(
        [sys.executable, str(PHASE25)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    p25 = _load_phase25_result()
    payloads = _phase_payloads(p25)
    snap = _integrity_snapshot(p25, payloads)

    status = "COMPLETED" if proc.returncode == 0 and p25.get("pipeline") == "COMPLETED" else "FAILED"
    if snap["integrity_status"] != "PASS":
        status = "DATA_INTEGRITY_FAILED"

    result = {
        "version": "2.6.4",
        "run_key": p25.get("run_key") or RUN_KEY,
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "mode": MODE,
        "status": status,
        "pipeline": p25.get("pipeline", "UNKNOWN"),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        **snap,
    }

    # Upsert dashboard snapshot. Keep payload restricted to Phase 2.6 schema fields.
    db_payload = {
        "run_key": result["run_key"],
        "run_date": RUN_DATE,
        "strategy_version": STRATEGY_VERSION,
        "mode": MODE,
        "status": status,
        "pipeline_status": result["pipeline"],
        "phase21_status": (payloads.get("2.1") or {}).get("status"),
        "phase22_status": (payloads.get("2.2") or {}).get("status"),
        "phase23_status": (payloads.get("2.3") or {}).get("status"),
        "phase24_status": (payloads.get("2.4") or {}).get("status"),
        "latest_market_date": result["latest_market_date"],
        "signals_eligible": result["eligible_signals"],
        "top_symbol": result["top_symbol"],
        "top_score": result["top_score"],
        "orders_created": result["orders_created"],
        "positions_open": result["positions_open"],
        "cash": result["cash"],
        "market_value": result["market_value"],
        "equity": result["equity"],
        "realized_pnl": result["realized_pnl"],
        "unrealized_pnl": result["unrealized_pnl"],
        "positions": result["positions"],
        "top_candidates": result["top_candidates"],
        "raw_summary": {
            "version": "2.6.4",
            "integrity_status": result["integrity_status"],
            "integrity_checks": result["integrity_checks"],
        },
        "completed_at": result["completed_at"],
    }

    try:
        rest(
            "POST",
            "gptq_paper_daily_snapshots",
            query="on_conflict=run_key",
            payload=db_payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        result["dashboard_snapshot"] = "UPSERTED"
    except Exception as exc:
        result["dashboard_snapshot"] = "ERROR"
        result["dashboard_snapshot_error"] = str(exc)
        status = "DATA_INTEGRITY_FAILED"
        result["status"] = status

    (ROOT / "phase26_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    checks_md = "\n".join(
        f"| {k} | {'PASS' if v else 'FAIL'} |"
        for k, v in result["integrity_checks"].items()
    )
    candidates_md = "\n".join(
        f"| {c.get('rank','')} | {c.get('symbol','')} | {c.get('score','')} | "
        f"{'YES' if c.get('eligible') else 'NO'} |"
        for c in result["top_candidates"]
        if isinstance(c, dict)
    ) or "| - | - | - | - |"

    summary = f"""# GPT Quant V9.2 Paper Trading — Phase 2.6.4 Daily Dashboard

## Daily Cycle
- **run_key:** `{result['run_key']}`
- **strategy:** `{STRATEGY_VERSION}`
- **mode:** `{MODE}`
- **status:** **{result['status']}**
- **pipeline:** **{result['pipeline']}**
- **data integrity:** **{result['integrity_status']}**
- **latest_market_date:** `{result['latest_market_date'] or 'MISSING'}`
- **eligible_signals:** **{result['eligible_signals']}**
- **orders_created:** **{result['orders_created']}**
- **positions_open:** **{result['positions_open']}**

## Portfolio Snapshot
- **cash:** {result['cash']:.2f}
- **market_value:** {result['market_value']:.2f}
- **equity:** {result['equity']:.2f}
- **realized_pnl:** {result['realized_pnl']:.2f}
- **unrealized_pnl:** {result['unrealized_pnl']:.2f}

## Top Candidates
| Rank | Symbol | Score | Eligible |
|---:|---|---:|:---:|
{candidates_md}

## Dashboard Data Integrity
| Check | Result |
|---|---|
{checks_md}

- **dashboard_snapshot:** `{result.get('dashboard_snapshot')}`
"""
    if result.get("dashboard_snapshot_error"):
        summary += f"\n> Snapshot error: `{result['dashboard_snapshot_error']}`\n"

    (ROOT / "phase26_summary.md").write_text(summary, encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Fail closed: never show a green cycle when critical dashboard data is missing.
    if proc.returncode != 0 or result["status"] != "COMPLETED":
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
