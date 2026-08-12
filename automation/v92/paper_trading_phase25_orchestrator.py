#!/usr/bin/env python3
"""GPT Quant V9.2 Paper Trading Phase 2.5 - Automatic Trading Orchestrator.

Fail-closed coordinator for the already deployed Phase 2.2 -> 2.1 -> 2.3 -> 2.4
paper-trading scripts. No broker orders are sent by this module.
"""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "phase25_logs"
LOG_DIR.mkdir(exist_ok=True)
RESULT = ROOT / "phase25_result.json"
SUMMARY = ROOT / "phase25_summary.md"

MODE = os.getenv("PAPER_TRADING_MODE", "SHADOW_ONLY_NO_BROKER")
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
FAIL_CLOSED = os.getenv("PHASE25_FAIL_CLOSED", "true").lower() == "true"

PHASES = [
    ("2.2", "Market Data Ingestion", ROOT/"automation/v92/paper_trading_phase22_market_ingestion.py"),
    ("2.1", "Signal Generation", ROOT/"automation/v92/paper_trading_phase21_signal_engine.py"),
    ("2.3", "Automatic Signal Execution", ROOT/"automation/v92/paper_trading_phase23_signal_execution.py"),
    ("2.4", "Automatic Position Management", ROOT/"automation/v92/paper_trading_phase24_position_management.py"),
]

def require_env():
    missing = [x for x in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY") if not os.getenv(x)]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError(f"Safety lock: PAPER_TRADING_MODE must be SHADOW_ONLY_NO_BROKER, got {MODE!r}")

def rest_get(table, query):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(
        f"{base}/rest/v1/{table}?{query}",
        headers={"apikey":key, "Authorization":f"Bearer {key}", "Accept":"application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "[]")
    except Exception:
        return []

def rest_post(table, payload):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base}/rest/v1/{table}", data=body, method="POST",
        headers={"apikey":key, "Authorization":f"Bearer {key}",
                 "Content-Type":"application/json", "Prefer":"return=representation"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "[]")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase insert {table}: HTTP {e.code}: {e.read().decode()[:1000]}")

def rest_patch(table, query, payload):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(
        f"{base}/rest/v1/{table}?{query}", data=json.dumps(payload).encode(), method="PATCH",
        headers={"apikey":key, "Authorization":f"Bearer {key}",
                 "Content-Type":"application/json", "Prefer":"return=representation"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "[]")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase update {table}: HTTP {e.code}: {e.read().decode()[:1000]}")

def run_phase(code, name, path):
    if not path.exists():
        raise RuntimeError(f"Missing Phase {code} script: {path.relative_to(ROOT)}")
    started = time.time()
    p = subprocess.run([sys.executable, str(path)], cwd=ROOT, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = p.stdout or ""
    (LOG_DIR/f"phase_{code.replace('.','')}.log").write_text(log, encoding="utf-8")
    return {"phase":code, "name":name, "status":"PASS" if p.returncode == 0 else "FAIL",
            "exit_code":p.returncode, "duration_seconds":round(time.time()-started,2),
            "log":str((LOG_DIR/f"phase_{code.replace('.','')}.log").relative_to(ROOT))}

def latest_market_date():
    rows = rest_get("gptq_market_data_health", "select=latest_market_date,data_status&order=created_at.desc&limit=1")
    if not rows: return None, None
    return rows[0].get("latest_market_date"), rows[0].get("data_status")

def snapshot():
    rows = rest_get("gptq_paper_positions", "select=*&status=eq.OPEN")
    positions = len(rows)
    mv = sum(float(r.get("market_value") or 0) for r in rows)
    upnl = sum(float(r.get("unrealized_pnl") or 0) for r in rows)
    return {"positions_open":positions, "market_value":round(mv,2), "unrealized_pnl":round(upnl,2)}

def write_summary(state):
    checks = "\n".join(f"- Phase {p['phase']} {p['name']}: **{p['status']}**" for p in state["phases"])
    s = state.get("portfolio", {})
    text = f"""# GPT Quant V9.2 Paper Trading Phase 2.5

- mode: `{state['mode']}`
- strategy_version: `{state['strategy_version']}`
- status: **{state['status']}**
- pipeline: **{state['pipeline']}**
- market_data_status: `{state.get('market_data_status')}`
- latest_market_date: `{state.get('latest_market_date')}`
- positions_open: `{s.get('positions_open','n/a')}`
- market_value: `{s.get('market_value','n/a')}`
- unrealized_pnl: `{s.get('unrealized_pnl','n/a')}`

## Pipeline checks
{checks}

> Safety lock: SHADOW_ONLY_NO_BROKER. Phase 2.5 does not submit real broker orders.
"""
    SUMMARY.write_text(text, encoding="utf-8")

def main():
    require_env()
    now = datetime.now(timezone.utc)
    run_key = f"{now.strftime('%Y-%m-%d')}-{STRATEGY}"
    state = {"run_key":run_key, "started_at":now.isoformat(), "mode":MODE,
             "strategy_version":STRATEGY, "status":"RUNNING", "pipeline":"STARTING", "phases":[]}

    # DB-level run lock: unique run_key prevents accidental duplicate daily orchestration.
    try:
        rest_post("gptq_paper_orchestrator_runs", {
            "run_key":run_key, "strategy_version":STRATEGY, "mode":MODE,
            "status":"RUNNING", "pipeline_status":"STARTING", "started_at":now.isoformat()
        })
    except Exception as e:
        state.update(status="BLOCKED", pipeline="DUPLICATE_OR_LOCK_ERROR", error=str(e))
        RESULT.write_text(json.dumps(state, indent=2), encoding="utf-8")
        write_summary(state)
        raise

    try:
        for code, name, path in PHASES:
            result = run_phase(code, name, path)
            state["phases"].append(result)

            if code == "2.2" and result["status"] == "PASS":
                mdate, mstatus = latest_market_date()
                state["latest_market_date"], state["market_data_status"] = mdate, mstatus
                # Fail closed if the health table explicitly reports stale/bad data.
                if mstatus and str(mstatus).upper() not in ("FRESH","COMPLETED","OK","HEALTHY"):
                    result["status"] = "FAIL"
                    result["reason"] = f"MARKET_DATA_{mstatus}"

            if result["status"] != "PASS" and FAIL_CLOSED:
                raise RuntimeError(f"Phase {code} failed; downstream trading blocked")

        state["portfolio"] = snapshot()
        state.update(status="COMPLETED", pipeline="HEALTHY")
    except Exception as e:
        state.update(status="FAILED", pipeline="BLOCKED", error=str(e))
    finally:
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        RESULT.write_text(json.dumps(state, indent=2), encoding="utf-8")
        write_summary(state)
        try:
            rest_patch("gptq_paper_orchestrator_runs", f"run_key=eq.{run_key}", {
                "status":state["status"], "pipeline_status":state["pipeline"],
                "latest_market_date":state.get("latest_market_date"),
                "market_data_status":state.get("market_data_status"),
                "result":state, "finished_at":state["finished_at"]
            })
        except Exception as e:
            print(f"[WARN] Could not finalize orchestrator DB row: {e}", file=sys.stderr)

    print(json.dumps(state, indent=2))
    return 0 if state["status"] == "COMPLETED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
