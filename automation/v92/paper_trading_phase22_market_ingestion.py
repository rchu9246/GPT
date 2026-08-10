from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

TIMEOUT = 60

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "").strip()
PROVIDER = os.getenv("MARKET_DATA_PROVIDER", "finmind").strip().lower()

RUN_DATE = os.getenv("RUN_DATE", str(date.today())).strip()
LOOKBACK_DAYS = int(os.getenv("MARKET_DATA_LOOKBACK_DAYS", "45"))
MAX_BACKFILL_DAYS = int(os.getenv("MARKET_DATA_MAX_BACKFILL_DAYS", "120"))
REQUEST_SLEEP_SECONDS = float(os.getenv("MARKET_DATA_REQUEST_SLEEP_SECONDS", "0.35"))

ARTIFACT_DIR = Path(
    os.getenv("MARKET_DATA_ARTIFACT_DIR", "artifacts/paper_trading_phase22")
)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

sb = requests.Session()
sb.headers.update({
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "GPT-Quant-V9.2-Phase2.2-MarketIngestion/1.0",
})

market = requests.Session()
market.headers.update({
    "User-Agent": "GPT-Quant-V9.2-Phase2.2-MarketIngestion/1.0"
})
if FINMIND_TOKEN:
    market.headers.update({"Authorization": f"Bearer {FINMIND_TOKEN}"})


def api_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def check(response: requests.Response, context: str) -> None:
    if not response.ok:
        raise RuntimeError(
            f"{context}: HTTP {response.status_code}: {response.text[:1800]}"
        )


def fetch_all(
    table: str,
    params: dict[str, str],
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    offset = 0
    while True:
        p = dict(params)
        p["limit"] = str(page_size)
        p["offset"] = str(offset)
        r = sb.get(api_url(table), params=p, timeout=TIMEOUT)
        check(r, f"fetch {table}")
        batch = r.json()
        result.extend(batch)
        if len(batch) < page_size:
            return result
        offset += page_size


def insert(table: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = sb.post(
        api_url(table),
        headers={"Prefer": "return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"insert {table}")
    rows = r.json()
    return rows[0] if rows else payload


def upsert(
    table: str,
    payload: dict[str, Any],
    on_conflict: str,
) -> dict[str, Any]:
    r = sb.post(
        api_url(table),
        params={"on_conflict": on_conflict},
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"upsert {table}")
    rows = r.json()
    return rows[0] if rows else payload


def patch_where(
    table: str,
    filters: dict[str, str],
    payload: dict[str, Any],
) -> None:
    r = sb.patch(
        api_url(table),
        params=filters,
        headers={"Prefer": "return=minimal"},
        json=payload,
        timeout=TIMEOUT,
    )
    check(r, f"patch {table}")


def parse_float(value: Any) -> float | None:
    if value in (None, "", "--", "---"):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int:
    if value in (None, "", "--", "---"):
        return 0
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def latest_market_date() -> str | None:
    rows = fetch_all("daily_prices", {
        "select": "trade_date",
        "order": "trade_date.desc",
        "limit": "1",
    })
    return rows[0]["trade_date"] if rows else None


def latest_stock_market_date(stock_id: int) -> str | None:
    rows = fetch_all("daily_prices", {
        "select": "trade_date",
        "stock_id": f"eq.{stock_id}",
        "order": "trade_date.desc",
        "limit": "1",
    })
    return rows[0]["trade_date"] if rows else None


def existing_price(stock_id: int, trade_date: str) -> dict[str, Any] | None:
    rows = fetch_all("daily_prices", {
        "select": "stock_id,trade_date,open,high,low,close,volume",
        "stock_id": f"eq.{stock_id}",
        "trade_date": f"eq.{trade_date}",
        "limit": "1",
    })
    return rows[0] if rows else None


def calc_start_date(stock_latest: str | None) -> str:
    run = date.fromisoformat(RUN_DATE)
    if stock_latest:
        next_day = date.fromisoformat(stock_latest) + timedelta(days=1)
        min_allowed = run - timedelta(days=MAX_BACKFILL_DAYS)
        return max(next_day, min_allowed).isoformat()
    return (run - timedelta(days=LOOKBACK_DAYS)).isoformat()


def fetch_finmind(symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": symbol,
        "start_date": start_date,
        "end_date": end_date,
    }
    if FINMIND_TOKEN:
        params["token"] = FINMIND_TOKEN

    r = market.get(FINMIND_URL, params=params, timeout=TIMEOUT)
    check(r, f"FinMind TaiwanStockPrice {symbol}")

    payload = r.json()
    if isinstance(payload, dict) and payload.get("status") not in (None, 200):
        raise RuntimeError(
            f"FinMind {symbol}: status={payload.get('status')} "
            f"msg={payload.get('msg') or payload.get('message')}"
        )

    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(data, list):
        raise RuntimeError(f"FinMind {symbol}: unexpected response format")
    return data


def normalize_finmind_row(stock_id: int, row: dict[str, Any]) -> dict[str, Any] | None:
    trade_date = str(row.get("date") or "").strip()
    if not trade_date:
        return None

    open_price = parse_float(row.get("open"))
    high = parse_float(row.get("max"))
    low = parse_float(row.get("min"))
    close = parse_float(row.get("close"))
    volume = parse_int(row.get("Trading_Volume"))

    if close is None or open_price is None or high is None or low is None:
        return None

    return {
        "stock_id": stock_id,
        "trade_date": trade_date,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def values_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    for key in ("open", "high", "low", "close"):
        try:
            if abs(float(old.get(key) or 0) - float(new.get(key) or 0)) > 0.000001:
                return True
        except (TypeError, ValueError):
            return True
    return int(old.get("volume") or 0) != int(new.get("volume") or 0)


def write_price(row: dict[str, Any]) -> str:
    old = existing_price(int(row["stock_id"]), str(row["trade_date"]))
    if old is None:
        insert("daily_prices", row)
        return "inserted"

    if values_changed(old, row):
        patch_where("daily_prices", {
            "stock_id": f"eq.{row['stock_id']}",
            "trade_date": f"eq.{row['trade_date']}",
        }, {
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        })
        return "updated"

    return "skipped"


def main() -> int:
    if PROVIDER != "finmind":
        raise RuntimeError(
            f"Unsupported MARKET_DATA_PROVIDER={PROVIDER}; "
            "Phase 2.2 v1.0 supports finmind"
        )

    before = latest_market_date()
    run_day = date.fromisoformat(RUN_DATE)
    stale_before = (
        (run_day - date.fromisoformat(before)).days if before else None
    )

    stocks = fetch_all("stocks", {
        "select": "id,symbol,name",
        "is_active": "eq.true",
        "order": "symbol.asc",
    })

    run_row = upsert("gptq_market_ingestion_runs", {
        "run_date": RUN_DATE,
        "provider": PROVIDER,
        "status": "RUNNING",
        "active_stocks": len(stocks),
        "stocks_attempted": 0,
        "stocks_updated": 0,
        "rows_received": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "latest_market_date_before": before,
        "stale_days_before": stale_before,
        "error_count": 0,
        "errors": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }, "run_date,provider")

    totals = {
        "attempted": 0,
        "stocks_updated": 0,
        "received": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
    }
    errors: list[dict[str, Any]] = []
    stock_reports: list[dict[str, Any]] = []

    for stock in stocks:
        sid = int(stock["id"])
        symbol = str(stock.get("symbol") or "").strip()
        if not symbol:
            continue

        totals["attempted"] += 1
        stock_latest = latest_stock_market_date(sid)
        start_date = calc_start_date(stock_latest)

        inserted = updated = skipped = 0
        rows_received = 0
        latest_after = stock_latest
        status = "NO_DATA"
        message = None

        try:
            rows = fetch_finmind(symbol, start_date, RUN_DATE)
            rows_received = len(rows)
            totals["received"] += rows_received

            for raw in rows:
                normalized = normalize_finmind_row(sid, raw)
                if normalized is None:
                    skipped += 1
                    totals["skipped"] += 1
                    continue

                result = write_price(normalized)
                if result == "inserted":
                    inserted += 1
                    totals["inserted"] += 1
                elif result == "updated":
                    updated += 1
                    totals["updated"] += 1
                else:
                    skipped += 1
                    totals["skipped"] += 1

                td = normalized["trade_date"]
                if latest_after is None or td > latest_after:
                    latest_after = td

            if inserted or updated:
                totals["stocks_updated"] += 1
                status = "UPDATED"
            elif rows_received:
                status = "CURRENT"
            else:
                status = "NO_DATA"

        except Exception as exc:
            status = "ERROR"
            message = str(exc)[:1200]
            errors.append({"symbol": symbol, "error": message})

        upsert("gptq_market_ingestion_stock_status", {
            "run_date": RUN_DATE,
            "provider": PROVIDER,
            "stock_id": sid,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": RUN_DATE,
            "rows_received": rows_received,
            "rows_inserted": inserted,
            "rows_updated": updated,
            "latest_market_date": latest_after,
            "status": status,
            "message": message,
        }, "run_date,provider,stock_id")

        stock_reports.append({
            "symbol": symbol,
            "start_date": start_date,
            "rows_received": rows_received,
            "rows_inserted": inserted,
            "rows_updated": updated,
            "rows_skipped": skipped,
            "latest_market_date": latest_after,
            "status": status,
            "message": message,
        })

        if REQUEST_SLEEP_SECONDS > 0:
            time.sleep(REQUEST_SLEEP_SECONDS)

    after = latest_market_date()
    stale_after = (
        (run_day - date.fromisoformat(after)).days if after else None
    )

    final_status = "COMPLETED"
    if errors and len(errors) == totals["attempted"]:
        final_status = "FAILED"
    elif errors:
        final_status = "COMPLETED_WITH_ERRORS"

    patch_where("gptq_market_ingestion_runs", {
        "id": f"eq.{run_row['id']}",
    }, {
        "status": final_status,
        "stocks_attempted": totals["attempted"],
        "stocks_updated": totals["stocks_updated"],
        "rows_received": totals["received"],
        "rows_inserted": totals["inserted"],
        "rows_updated": totals["updated"],
        "rows_skipped": totals["skipped"],
        "latest_market_date_after": after,
        "stale_days_after": stale_after,
        "error_count": len(errors),
        "errors": errors,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    report = {
        "run_date": RUN_DATE,
        "provider": PROVIDER,
        "status": final_status,
        "mode": "MARKET_DATA_ONLY_NO_BROKER",
        "finmind_token_configured": bool(FINMIND_TOKEN),
        "active_stocks": len(stocks),
        "stocks_attempted": totals["attempted"],
        "stocks_updated": totals["stocks_updated"],
        "rows_received": totals["received"],
        "rows_inserted": totals["inserted"],
        "rows_updated": totals["updated"],
        "rows_skipped": totals["skipped"],
        "latest_market_date_before": before,
        "latest_market_date_after": after,
        "stale_days_before": stale_before,
        "stale_days_after": stale_after,
        "errors": errors,
        "stocks": stock_reports,
    }

    (ARTIFACT_DIR / "phase22_market_ingestion_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("# GPT Quant V9.2 Paper Trading Phase 2.2\n\n")
            f.write(f"- **Provider**: `{PROVIDER}`\n")
            f.write(f"- **Status**: `{final_status}`\n")
            f.write(f"- **Latest market date before**: `{before}`\n")
            f.write(f"- **Latest market date after**: `{after}`\n")
            f.write(f"- **Stale days before**: `{stale_before}`\n")
            f.write(f"- **Stale days after**: `{stale_after}`\n")
            f.write(f"- **Stocks attempted**: `{totals['attempted']}`\n")
            f.write(f"- **Stocks updated**: `{totals['stocks_updated']}`\n")
            f.write(f"- **Rows received**: `{totals['received']}`\n")
            f.write(f"- **Rows inserted**: `{totals['inserted']}`\n")
            f.write(f"- **Rows updated**: `{totals['updated']}`\n")
            f.write(f"- **Errors**: `{len(errors)}`\n\n")

            f.write("## Per-stock ingestion\n\n")
            f.write("| Symbol | Status | Received | Inserted | Updated | Latest |\n")
            f.write("|---|---|---:|---:|---:|---|\n")
            for item in stock_reports:
                f.write(
                    f"| {item['symbol']} | {item['status']} | "
                    f"{item['rows_received']} | {item['rows_inserted']} | "
                    f"{item['rows_updated']} | {item['latest_market_date']} |\n"
                )

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if final_status == "FAILED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
