#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.0
Production Paper Trading Control Center

Purpose:
- Aggregate Production Paper operations into one control-center snapshot.
- Read existing Supabase daily snapshots.
- Compute readiness/risk/operations state.
- Generate JSON + Markdown + standalone HTML dashboard.
- Keep broker and real-money execution disabled.

Safety:
- Requires SHADOW_ONLY_NO_BROKER.
- Fail-closed on unhealthy data.
- Does not submit broker orders.
"""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = ROOT / "dashboard"
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")
MODE = os.getenv("PAPER_TRADING_MODE", "SHADOW_ONLY_NO_BROKER")

REQUIRED_PASS_DAYS = max(1, int(os.getenv("PHASE30_REQUIRED_PASS_DAYS", "5")))
MAX_STALE_DAYS = max(0, int(os.getenv("PHASE30_MAX_MARKET_STALE_DAYS", "3")))
MAX_OPEN_POSITIONS = max(0, int(os.getenv("PHASE30_MAX_OPEN_POSITIONS", "10")))
MIN_EQUITY = float(os.getenv("PHASE30_MIN_EQUITY", "0"))
MAX_DAILY_DRAWDOWN = float(os.getenv("PHASE30_MAX_DAILY_DRAWDOWN", "0.08"))


def request(table: str, query: str):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {body}") from exc


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def load_snapshots():
    query = urllib.parse.urlencode(
        {
            "select": (
                "run_key,run_date,strategy_version,mode,status,pipeline_status,"
                "latest_market_date,signals_eligible,orders_created,positions_open,"
                "cash,market_value,equity,realized_pnl,unrealized_pnl,raw_summary,completed_at"
            ),
            "strategy_version": f"eq.{VERSION}",
            "mode": f"eq.{MODE}",
            "order": "run_date.desc,completed_at.desc",
            "limit": str(max(REQUIRED_PASS_DAYS * 8, 60)),
        }
    )
    rows = request("gptq_paper_daily_snapshots", query)
    return rows if isinstance(rows, list) else []


def one_per_day(rows):
    daily, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = str(row.get("run_date") or "")[:10]
        if not d or d in seen:
            continue
        seen.add(d)
        daily.append(row)
    return daily


def health_for(row):
    run_day = parse_day(row.get("run_date"))
    market_day = parse_day(row.get("latest_market_date"))
    stale_days = (run_day - market_day).days if run_day and market_day else None

    checks = {
        "status_completed": row.get("status") == "COMPLETED",
        "pipeline_completed": row.get("pipeline_status") == "COMPLETED",
        "latest_market_date_present": market_day is not None,
        "market_data_fresh": market_day is not None and stale_days is not None and stale_days <= MAX_STALE_DAYS,
        "equity_non_negative": as_float(row.get("equity")) >= MIN_EQUITY,
        "positions_within_limit": 0 <= as_int(row.get("positions_open")) <= MAX_OPEN_POSITIONS,
    }

    raw = row.get("raw_summary")
    if isinstance(raw, dict):
        integrity = raw.get("integrity_checks")
        if isinstance(integrity, dict) and integrity:
            checks["phase26_integrity_all_pass"] = all(bool(v) for v in integrity.values())

    return checks, stale_days


def compute_streak(daily):
    streak = 0
    dates = []
    for row in daily:
        checks, _ = health_for(row)
        if all(checks.values()):
            streak += 1
            dates.append(str(row.get("run_date"))[:10])
        else:
            break
    return streak, dates


def daily_drawdown(daily):
    if len(daily) < 2:
        return 0.0
    today = as_float(daily[0].get("equity"))
    prev = as_float(daily[1].get("equity"))
    if prev <= 0:
        return 0.0
    return max(0.0, (prev - today) / prev)


def pct(value):
    return f"{100.0 * as_float(value):.2f}%"


def money(value):
    return f"{as_float(value):,.2f}"


def build_html(result):
    checks = result["checks"]
    ledger = result["ledger"]
    streak_dates = result["streak_dates"]

    check_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td class='{'pass' if ok else 'fail'}'>{'PASS' if ok else 'FAIL'}</td></tr>"
        for name, ok in checks.items()
    )

    streak = "".join(f"<span class='chip'>✅ {html.escape(d)}</span>" for d in streak_dates) or "<span class='muted'>No PASS streak yet</span>"

    state = html.escape(result["control_state"])
    state_class = "pass" if state == "READY" else ("warn" if state == "OBSERVATION" else "fail")

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPT Quant V9.2 Phase 3.0 Control Center</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;background:#0f172a;color:#e5e7eb;margin:0}}
.wrap{{max-width:1180px;margin:auto;padding:24px}}
h1,h2{{margin:0 0 14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:18px 0}}
.card{{background:#111827;border:1px solid #334155;border-radius:14px;padding:18px}}
.big{{font-size:28px;font-weight:700;margin-top:8px}}
.pass{{color:#4ade80;font-weight:700}}
.warn{{color:#facc15;font-weight:700}}
.fail{{color:#f87171;font-weight:700}}
.muted{{color:#94a3b8}}
table{{width:100%;border-collapse:collapse}}
td,th{{padding:10px;border-bottom:1px solid #334155;text-align:left}}
.chip{{display:inline-block;background:#1e293b;border:1px solid #334155;border-radius:999px;padding:7px 10px;margin:4px}}
.footer{{margin-top:24px;color:#94a3b8;font-size:13px}}
</style>
</head>
<body>
<div class="wrap">
<h1>GPT Quant V9.2 — Phase 3.0 Control Center</h1>
<div class="muted">Production Paper Trading Control Center</div>

<div class="grid">
<div class="card"><div>System Health</div><div class="big {'pass' if result['system_health']=='PASS' else 'fail'}">{result['system_health']}</div></div>
<div class="card"><div>Control State</div><div class="big {state_class}">{state}</div></div>
<div class="card"><div>Observation</div><div class="big">{result['consecutive_pass_days']} / {result['required_consecutive_pass_days']}</div></div>
<div class="card"><div>Safety Mode</div><div class="big">NO BROKER</div></div>
</div>

<div class="grid">
<div class="card"><div>Equity</div><div class="big">{money(ledger.get('equity'))}</div></div>
<div class="card"><div>Cash</div><div class="big">{money(ledger.get('cash'))}</div></div>
<div class="card"><div>Market Value</div><div class="big">{money(ledger.get('market_value'))}</div></div>
<div class="card"><div>Unrealized P&L</div><div class="big">{money(ledger.get('unrealized_pnl'))}</div></div>
</div>

<div class="grid">
<div class="card"><div>Positions Open</div><div class="big">{ledger.get('positions_open')}</div></div>
<div class="card"><div>Eligible Signals</div><div class="big">{ledger.get('signals_eligible')}</div></div>
<div class="card"><div>Orders Created</div><div class="big">{ledger.get('orders_created')}</div></div>
<div class="card"><div>Daily Drawdown</div><div class="big">{pct(result['daily_drawdown'])}</div></div>
</div>

<div class="card">
<h2>Risk / Integrity Checks</h2>
<table><tr><th>Check</th><th>Result</th></tr>{check_rows}</table>
</div>

<div class="card" style="margin-top:14px">
<h2>Observation Streak</h2>
{streak}
</div>

<div class="card" style="margin-top:14px">
<h2>Safety Controls</h2>
<ul>
<li>Production Paper: <b>{'READY' if result['control_state']=='READY' else 'LOCKED'}</b></li>
<li>Broker Trading: <b>DISABLED</b></li>
<li>Real Money: <b>DISABLED</b></li>
<li>Kill Switch: <b>ARMED</b></li>
<li>Fail Closed: <b>YES</b></li>
</ul>
</div>

<div class="footer">
Run key: {html.escape(str(ledger.get('run_key')))} · Latest market date: {html.escape(str(result.get('latest_market_date')))}
</div>
</div>
</body>
</html>"""


def main():
    if MODE != "SHADOW_ONLY_NO_BROKER":
        raise RuntimeError("Safety lock: Phase 3.0 requires SHADOW_ONLY_NO_BROKER")

    rows = load_snapshots()
    daily = one_per_day(rows)

    if not daily:
        raise RuntimeError("No daily snapshots available for Phase 3.0")

    current = daily[0]
    checks, stale_days = health_for(current)
    streak, streak_dates = compute_streak(daily)
    drawdown = daily_drawdown(daily)

    checks["daily_drawdown_within_limit"] = drawdown <= MAX_DAILY_DRAWDOWN
    checks["safety_mode_locked"] = MODE == "SHADOW_ONLY_NO_BROKER"

    healthy = all(checks.values())

    if not healthy:
        state = "BLOCKED"
    elif streak < REQUIRED_PASS_DAYS:
        state = "OBSERVATION"
    else:
        state = "READY"

    result = {
        "version": "3.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy_version": VERSION,
        "mode": MODE,
        "system_health": "PASS" if healthy else "FAIL",
        "control_state": state,
        "required_consecutive_pass_days": REQUIRED_PASS_DAYS,
        "consecutive_pass_days": streak,
        "streak_dates": streak_dates,
        "latest_market_date": current.get("latest_market_date"),
        "market_stale_days": stale_days,
        "daily_drawdown": round(drawdown, 6),
        "checks": checks,
        "ledger": {
            "run_key": current.get("run_key"),
            "cash": current.get("cash"),
            "market_value": current.get("market_value"),
            "equity": current.get("equity"),
            "realized_pnl": current.get("realized_pnl"),
            "unrealized_pnl": current.get("unrealized_pnl"),
            "positions_open": current.get("positions_open"),
            "signals_eligible": current.get("signals_eligible"),
            "orders_created": current.get("orders_created"),
        },
        "safety": {
            "broker_execution_enabled": False,
            "real_money_enabled": False,
            "kill_switch": "ARMED",
            "fail_closed": True,
        },
    }

    (ROOT / "phase30_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.0",
        "",
        "## Production Paper Trading Control Center",
        "",
        f"- System Health: **{result['system_health']}**",
        f"- Control State: **{result['control_state']}**",
        f"- Strategy: `{VERSION}`",
        f"- Trading Mode: `{MODE}`",
        f"- Consecutive PASS days: **{streak} / {REQUIRED_PASS_DAYS}**",
        f"- Latest market date: `{result['latest_market_date']}`",
        f"- Market stale days: `{stale_days}`",
        f"- Daily drawdown: `{result['daily_drawdown']}`",
        "",
        "### Control Center Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| `{name}` | {'✅ PASS' if ok else '❌ FAIL'} |")

    ledger = result["ledger"]
    lines += [
        "",
        "### Portfolio / Ledger",
        "",
        f"- Equity: `{ledger['equity']}`",
        f"- Cash: `{ledger['cash']}`",
        f"- Market value: `{ledger['market_value']}`",
        f"- Realized P&L: `{ledger['realized_pnl']}`",
        f"- Unrealized P&L: `{ledger['unrealized_pnl']}`",
        f"- Positions open: `{ledger['positions_open']}`",
        f"- Signals eligible: `{ledger['signals_eligible']}`",
        f"- Orders created: `{ledger['orders_created']}`",
        "",
        "### Safety",
        "",
        "- Broker Trading: **DISABLED**",
        "- Real Money: **DISABLED**",
        "- Kill Switch: **ARMED**",
        "- Fail Closed: **YES**",
    ]

    (ROOT / "phase30_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (DASHBOARD_DIR / "phase30_control_center.html").write_text(build_html(result), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Phase 3.0 Control Center generated.")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
