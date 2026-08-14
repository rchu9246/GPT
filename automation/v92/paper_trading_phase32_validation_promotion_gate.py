#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.2
Production Validation + Promotion Gate

Safety:
- Read-only validation against Supabase.
- Never sends broker orders.
- Never changes PAPER_TRADING_MODE.
- Promotion means OBSERVATION -> QUALIFIED only.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

VERSION = "3.2"
EXPECTED_MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY_VERSION = os.getenv("PAPER_STRATEGY_VERSION", "V9.1")

REQUIRED_CONSECUTIVE_PASS_DAYS = int(
    os.getenv("PHASE32_REQUIRED_CONSECUTIVE_PASS_DAYS", "5")
)
MAX_MARKET_STALE_DAYS = int(os.getenv("PHASE32_MAX_MARKET_STALE_DAYS", "3"))
MAX_DAILY_DRAWDOWN = float(os.getenv("PHASE32_MAX_DAILY_DRAWDOWN", "0.03"))

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SNAPSHOT_TABLE = os.getenv("PHASE32_SNAPSHOT_TABLE", "gptq_paper_daily_snapshots")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def request(method, table, query="", payload=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url += "?" + query

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Supabase {method} {table}: HTTP {exc.code}: {body}"
        ) from exc


def first_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {
            "true", "1", "yes", "pass", "passed", "completed", "clear"
        }
    return False


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def get_latest_snapshot():
    query = urllib.parse.urlencode({
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "run_date.desc",
        "limit": "1",
    })
    return first_dict(request("GET", SNAPSHOT_TABLE, query))


def get_recent_snapshots(limit=30):
    query = urllib.parse.urlencode({
        "strategy_version": f"eq.{STRATEGY_VERSION}",
        "order": "run_date.desc",
        "limit": str(limit),
    })
    rows = request("GET", SNAPSHOT_TABLE, query)
    return rows if isinstance(rows, list) else []


def extract_mode(snapshot):
    return (
        snapshot.get("mode")
        or snapshot.get("trading_mode")
        or snapshot.get("paper_trading_mode")
        or EXPECTED_MODE
    )


def extract_status(snapshot):
    return str(
        snapshot.get("status")
        or snapshot.get("monitor_status")
        or snapshot.get("pipeline_status")
        or snapshot.get("pipeline")
        or ""
    ).upper()


def snapshot_passed(snapshot):
    status = extract_status(snapshot)

    explicit = snapshot.get("integrity_status")
    if explicit is not None and str(explicit).upper() in {"FAIL", "FAILED"}:
        return False

    if status in {"COMPLETED", "PASS", "PASSED", "SUCCESS"}:
        return True

    checks = snapshot.get("integrity_checks") or snapshot.get("checks")
    if isinstance(checks, dict) and checks:
        return all(as_bool(v) for v in checks.values())

    raw = snapshot.get("raw_summary")
    if isinstance(raw, dict):
        integrity = raw.get("integrity_checks")
        if isinstance(integrity, dict) and integrity:
            return all(as_bool(v) for v in integrity.values())

    return False


def one_per_day(rows):
    result = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        run_day = str(row.get("run_date") or "")[:10]
        if not run_day or run_day in seen:
            continue

        seen.add(run_day)
        result.append(row)

    return result


def consecutive_pass_days(rows):
    count = 0

    for row in one_per_day(rows):
        if snapshot_passed(row):
            count += 1
        else:
            break

    return count


def extract_latest_market_date(snapshot):
    candidates = [
        snapshot.get("latest_market_date"),
        snapshot.get("market_date"),
    ]

    raw = snapshot.get("raw_summary")
    if isinstance(raw, dict):
        candidates.append(raw.get("latest_market_date"))

    market_data = snapshot.get("market_data")
    if isinstance(market_data, dict):
        candidates.extend([
            market_data.get("latest_market_date"),
            market_data.get("market_date"),
        ])

    for value in candidates:
        parsed = parse_date(value)
        if parsed:
            return parsed

    return None


def extract_stale_days(snapshot, market_date):
    for key in ("market_stale_days", "stale_days"):
        if snapshot.get(key) is not None:
            try:
                return int(snapshot[key])
            except (TypeError, ValueError):
                pass

    raw = snapshot.get("raw_summary")
    if isinstance(raw, dict):
        for key in ("market_stale_days", "stale_days"):
            if raw.get(key) is not None:
                try:
                    return int(raw[key])
                except (TypeError, ValueError):
                    pass

    if market_date:
        run_date = parse_date(snapshot.get("run_date"))
        base_date = run_date or date.today()
        return max(0, (base_date - market_date).days)

    return None


def extract_drawdown(snapshot):
    for key in ("daily_drawdown", "drawdown", "drawdown_pct"):
        if snapshot.get(key) is not None:
            return abs(as_float(snapshot[key]))

    raw = snapshot.get("raw_summary")
    if isinstance(raw, dict):
        for key in ("daily_drawdown", "drawdown", "drawdown_pct"):
            if raw.get(key) is not None:
                return abs(as_float(raw[key]))

    return 0.0


def incident_clear(snapshot):
    state = str(
        snapshot.get("incident_state")
        or snapshot.get("incident_status")
        or "CLEAR"
    ).upper()

    return state in {"CLEAR", "NONE", "OK", "PASS"}


def write_summary(result):
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    checks = result["checks"]

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.2",
        "",
        "## Production Validation + Promotion Gate",
        "",
        f"- Status: **{result['status']}**",
        f"- Promotion State: **{result['promotion_state']}**",
        f"- Strategy: `{result['strategy_version']}`",
        f"- Trading Mode: `{result['trading_mode']}`",
        f"- Consecutive PASS days: **{result['consecutive_pass_days']} / {result['required_consecutive_pass_days']}**",
        f"- Latest market date: `{result['latest_market_date']}`",
        f"- Market stale days: **{result['market_stale_days']}**",
        f"- Daily drawdown: **{result['daily_drawdown']:.4%}**",
        "",
        "### Promotion Checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]

    for name, passed in checks.items():
        lines.append(
            f"| `{name}` | {'✅ PASS' if passed else '🟡 WAIT / ❌ FAIL'} |"
        )

    lines += [
        "",
        "### Safety",
        "",
        "- Broker Trading: **DISABLED**",
        "- Real Money: **DISABLED**",
        f"- Required Safety Mode: `{EXPECTED_MODE}`",
        "",
        "> Phase 3.2 only qualifies the paper-trading environment. "
        "It does not enable broker or real-money execution.",
    ]

    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    print("=== GPT Quant V9.2 Phase 3.2 Production Validation + Promotion Gate ===")

    latest = get_latest_snapshot()
    recent = get_recent_snapshots()

    if not latest:
        result = {
            "version": VERSION,
            "checked_at": now_iso(),
            "strategy_version": STRATEGY_VERSION,
            "status": "FAIL",
            "promotion_state": "BLOCKED",
            "alerts": ["no_daily_snapshot"],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    mode = extract_mode(latest)
    market_date = extract_latest_market_date(latest)
    stale_days = extract_stale_days(latest, market_date)
    drawdown = extract_drawdown(latest)
    pass_days = consecutive_pass_days(recent)

    checks = {
        "latest_snapshot_pass": snapshot_passed(latest),
        "pipeline_completed": extract_status(latest)
        in {"COMPLETED", "PASS", "PASSED", "SUCCESS"},
        "safety_mode_locked": mode == EXPECTED_MODE,
        "incident_clear": incident_clear(latest),
        "latest_market_date_present": market_date is not None,
        "market_data_fresh": (
            stale_days is not None and stale_days <= MAX_MARKET_STALE_DAYS
        ),
        "drawdown_within_limit": drawdown <= MAX_DAILY_DRAWDOWN,
        "consecutive_pass_requirement": (
            pass_days >= REQUIRED_CONSECUTIVE_PASS_DAYS
        ),
    }

    hard_checks = {
        key: value
        for key, value in checks.items()
        if key != "consecutive_pass_requirement"
    }

    health_pass = all(hard_checks.values())
    qualified = all(checks.values())

    if not health_pass:
        status = "FAIL"
        promotion_state = "BLOCKED"
    elif qualified:
        status = "PASS"
        promotion_state = "QUALIFIED"
    else:
        status = "PASS"
        promotion_state = "OBSERVATION"

    result = {
        "version": VERSION,
        "checked_at": now_iso(),
        "strategy_version": STRATEGY_VERSION,
        "trading_mode": mode,
        "status": status,
        "promotion_state": promotion_state,
        "required_consecutive_pass_days": REQUIRED_CONSECUTIVE_PASS_DAYS,
        "consecutive_pass_days": pass_days,
        "latest_market_date": (
            market_date.isoformat() if market_date else None
        ),
        "market_stale_days": stale_days,
        "daily_drawdown": round(drawdown, 6),
        "max_daily_drawdown": MAX_DAILY_DRAWDOWN,
        "checks": checks,
        "alerts": [
            name for name, passed in checks.items() if not passed
        ],
        "current_snapshot": {
            "run_date": latest.get("run_date"),
            "equity": latest.get("equity"),
            "cash": latest.get("cash"),
            "market_value": latest.get("market_value"),
            "positions_open": latest.get("positions_open"),
            "signals_eligible": latest.get("signals_eligible"),
            "orders_created": latest.get("orders_created"),
        },
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    write_summary(result)

    return 0 if health_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
