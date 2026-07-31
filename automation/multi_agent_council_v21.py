"""GPT Quant V21 Multi-Agent Investment Council.

A deterministic, auditable committee using existing quantitative data.

Agents:
- Technical Analyst
- Momentum Analyst
- Quality Analyst
- Liquidity Analyst
- Risk Officer
- CIO synthesizer

The Risk Officer has veto power. The engine may create PROPOSED PAPER orders
only; it never approves, fills, or sends live broker orders.
"""
from __future__ import annotations

import math
import os
import statistics
from typing import Any
from urllib.parse import quote

import requests

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ACCOUNT = os.environ.get("AUTOTRADER_ACCOUNT", "paper-main")

if not URL or not KEY:
    raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}
RETURN = {**HEADERS, "Prefer": "return=representation"}
UPSERT = {
    **HEADERS,
    "Prefer": "resolution=merge-duplicates,return=representation",
}

def api(table: str, query: str = "") -> str:
    return f"{URL}/rest/v1/{table}" + (f"?{query}" if query else "")

def get_rows(table: str, query: str = "") -> list[dict[str, Any]]:
    response = requests.get(api(table, query), headers=HEADERS, timeout=45)
    response.raise_for_status()
    return response.json()

def insert_rows(table: str, payload: Any) -> list[dict[str, Any]]:
    response = requests.post(api(table), headers=RETURN, json=payload, timeout=45)
    response.raise_for_status()
    return response.json()

def upsert_rows(table: str, payload: Any, conflict: str) -> list[dict[str, Any]]:
    response = requests.post(
        api(table, f"on_conflict={quote(conflict)}"),
        headers=UPSERT,
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()

def number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

def integer(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))

def vote(score: float) -> str:
    if score >= 60:
        return "BULLISH"
    if score >= 40:
        return "NEUTRAL"
    return "BEARISH"

config_rows = get_rows(
    "autotrader_configs_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not config_rows:
    raise SystemExit("No autotrader configuration")
config = config_rows[0]

if not bool(config.get("enabled")):
    raise SystemExit("Autotrader disabled")
if bool(config.get("kill_switch")):
    raise SystemExit("Kill switch enabled")
if str(config.get("mode")) != "PAPER":
    raise SystemExit("V21 supports PAPER mode only")

account_rows = get_rows(
    "paper_accounts_v13",
    f"account_name=eq.{quote(ACCOUNT)}&limit=1",
)
if not account_rows:
    raise SystemExit("No paper account")
account = account_rows[0]

signals = get_rows(
    "signals",
    "select=stock_id,trade_date,strategy_version,total_score,trend_score,"
    "momentum_score,volume_score,risk_score,confidence"
    "&order=trade_date.desc,total_score.desc&limit=500",
)
if not signals:
    raise SystemExit("No signals")

council_date = str(signals[0]["trade_date"])
latest = [row for row in signals if str(row.get("trade_date")) == council_date]

stocks = get_rows("stocks", "select=id,symbol,name&limit=10000")
stock_by_id = {str(row["id"]): row for row in stocks}

stock_ids = sorted({
    str(row["stock_id"]) for row in latest if row.get("stock_id") is not None
})
prices = get_rows(
    "daily_prices",
    "select=stock_id,trade_date,close,volume"
    f"&stock_id=in.({','.join(stock_ids)})"
    "&order=trade_date.desc&limit=5000",
)
price_by_id: dict[str, dict[str, Any]] = {}
for row in prices:
    stock_id = str(row["stock_id"])
    if stock_id not in price_by_id:
        price_by_id[stock_id] = row

positions = get_rows(
    "paper_positions_v13",
    f"account_name=eq.{quote(ACCOUNT)}&select=symbol,market_value&limit=1000",
)
held_symbols = {str(row["symbol"]) for row in positions}

open_orders = get_rows(
    "trade_orders_v13",
    f"account_name=eq.{quote(ACCOUNT)}"
    "&status=in.(PROPOSED,APPROVED)&select=symbol,side&limit=1000",
)
open_buy_symbols = {
    str(row["symbol"])
    for row in open_orders
    if str(row.get("side")) == "BUY"
}

# Keep the best strategy signal for each symbol.
dedup: dict[str, dict[str, Any]] = {}
for signal in latest:
    stock = stock_by_id.get(str(signal.get("stock_id")))
    price = price_by_id.get(str(signal.get("stock_id")))
    if not stock or not price or not stock.get("symbol"):
        continue
    symbol = str(stock["symbol"])
    current = dedup.get(symbol)
    if current is None or number(signal.get("total_score")) > number(
        current["signal"].get("total_score")
    ):
        dedup[symbol] = {"signal": signal, "stock": stock, "price": price}

buy_threshold = number(config.get("council_buy_threshold"), 60)
min_agreement_pct = number(config.get("council_min_agreement_pct"), 66)
risk_veto_score = number(config.get("council_risk_veto_score"), 65)
auto_propose = bool(config.get("council_auto_propose", True))
max_positions = integer(config.get("max_positions"), 5)
max_daily_orders = integer(config.get("max_daily_orders"), 5)
max_position_pct = number(config.get("max_position_pct"), 15)
min_position_pct = number(config.get("min_position_pct"), 3)
lot_size = max(1, integer(config.get("lot_size"), 1))
target_cash_pct = number(config.get("target_cash_pct"), 30)

equity = number(account.get("equity"), number(account.get("cash")))
cash = number(account.get("cash"))
investable_cash = max(0.0, cash - equity * target_cash_pct / 100)
slots = max(0, max_positions - len(held_symbols) - len(open_buy_symbols))
remaining_orders = min(slots, max_daily_orders)

decisions = []

for symbol, item in dedup.items():
    signal = item["signal"]
    stock = item["stock"]
    price_row = item["price"]
    price = number(price_row.get("close"))
    volume_available = number(price_row.get("volume")) > 0

    trend_score = clamp(number(signal.get("trend_score")))
    momentum_score = clamp(number(signal.get("momentum_score")))
    total_score = clamp(number(signal.get("total_score")))
    confidence = clamp(number(signal.get("confidence"), 50))
    volume_score = clamp(number(signal.get("volume_score"), 50))
    raw_risk = clamp(number(signal.get("risk_score"), 50))

    agent_rows = [
        {
            "agent_name": "TECHNICAL_ANALYST",
            "agent_role": "Technical Analyst",
            "score": trend_score,
            "confidence": clamp(0.65 * confidence + 0.35 * trend_score),
            "veto": False,
            "rationale": (
                f"Trend score {trend_score:.1f}; evaluates directional "
                "structure and persistence."
            ),
        },
        {
            "agent_name": "MOMENTUM_ANALYST",
            "agent_role": "Momentum Analyst",
            "score": momentum_score,
            "confidence": clamp(0.60 * confidence + 0.40 * momentum_score),
            "veto": False,
            "rationale": (
                f"Momentum score {momentum_score:.1f}; evaluates recent "
                "price acceleration."
            ),
        },
        {
            "agent_name": "QUALITY_ANALYST",
            "agent_role": "Signal Quality Analyst",
            "score": clamp(0.65 * total_score + 0.35 * confidence),
            "confidence": confidence,
            "veto": False,
            "rationale": (
                f"Total score {total_score:.1f}, confidence {confidence:.1f}; "
                "evaluates signal robustness."
            ),
        },
        {
            "agent_name": "LIQUIDITY_ANALYST",
            "agent_role": "Liquidity Analyst",
            "score": clamp(0.70 * volume_score + (30 if volume_available else 0)),
            "confidence": 75 if volume_available else 30,
            "veto": not volume_available,
            "rationale": (
                f"Volume score {volume_score:.1f}; market volume data "
                f"{'available' if volume_available else 'missing'}."
            ),
        },
        {
            "agent_name": "RISK_OFFICER",
            "agent_role": "Chief Risk Officer",
            "score": clamp(100 - raw_risk),
            "confidence": clamp(50 + abs(raw_risk - 50)),
            "veto": raw_risk > risk_veto_score,
            "rationale": (
                f"Raw risk {raw_risk:.1f}; veto threshold "
                f"{risk_veto_score:.1f}."
            ),
        },
    ]

    scores = [number(row["score"]) for row in agent_rows]
    bullish = sum(1 for score in scores if vote(score) == "BULLISH")
    neutral = sum(1 for score in scores if vote(score) == "NEUTRAL")
    bearish = sum(1 for score in scores if vote(score) == "BEARISH")
    veto_count = sum(1 for row in agent_rows if bool(row["veto"]))
    consensus_score = statistics.fmean(scores) if scores else 0.0
    dispersion = statistics.pstdev(scores) if len(scores) >= 2 else 0.0
    agreement_pct = max(bullish, neutral, bearish) / max(1, len(scores)) * 100

    for row in agent_rows:
        upsert_rows(
            "agent_opinions_v21",
            {
                "account_name": ACCOUNT,
                "council_date": council_date,
                "stock_id": signal.get("stock_id"),
                "symbol": symbol,
                "name": stock.get("name"),
                "agent_name": row["agent_name"],
                "agent_role": row["agent_role"],
                "score": row["score"],
                "vote": vote(number(row["score"])),
                "confidence": row["confidence"],
                "veto": row["veto"],
                "rationale": row["rationale"],
            },
            "account_name,council_date,symbol,agent_name",
        )

    final_decision = "WATCH"
    conviction = "LOW"
    target_weight = 0.0
    cio_reasons = []

    if symbol in held_symbols:
        final_decision = "HOLD"
        conviction = "MEDIUM"
        cio_reasons.append("Existing portfolio position.")
    elif symbol in open_buy_symbols:
        final_decision = "PENDING"
        conviction = "MEDIUM"
        cio_reasons.append("Existing open buy order.")
    elif veto_count > 0:
        final_decision = "VETOED"
        conviction = "AVOID"
        cio_reasons.append(f"{veto_count} agent veto(s), including risk/liquidity controls.")
    elif (
        consensus_score >= buy_threshold
        and agreement_pct >= min_agreement_pct
        and bullish >= 3
    ):
        final_decision = "BUY"
        conviction = "HIGH" if consensus_score >= 70 and dispersion <= 18 else "MEDIUM"
        target_weight = clamp(
            min_position_pct
            + (consensus_score - buy_threshold)
            / max(1, 100 - buy_threshold)
            * (max_position_pct - min_position_pct),
            min_position_pct,
            max_position_pct,
        )
        cio_reasons.append(
            f"Consensus {consensus_score:.1f}, agreement {agreement_pct:.1f}%, "
            f"{bullish} bullish votes."
        )
    elif consensus_score >= 45:
        final_decision = "WATCH"
        conviction = "LOW"
        cio_reasons.append("Mixed or insufficient committee agreement.")
    else:
        final_decision = "AVOID"
        conviction = "AVOID"
        cio_reasons.append("Committee score below investment threshold.")

    order_id = None
    if (
        final_decision == "BUY"
        and auto_propose
        and remaining_orders > 0
        and price > 0
    ):
        target_notional = min(
            equity * target_weight / 100,
            investable_cash / max(1, remaining_orders),
        )
        raw_quantity = math.floor(target_notional / price)
        quantity = (raw_quantity // lot_size) * lot_size

        if quantity > 0:
            key = f"{ACCOUNT}:{council_date}:{symbol}:BUY:V21_COUNCIL"
            existing = get_rows(
                "trade_orders_v13",
                f"idempotency_key=eq.{quote(key)}&select=id&limit=1",
            )
            if existing:
                order_id = existing[0]["id"]
            else:
                rows = insert_rows(
                    "trade_orders_v13",
                    {
                        "account_name": ACCOUNT,
                        "symbol": symbol,
                        "side": "BUY",
                        "quantity": quantity,
                        "reference_price": round(price, 2),
                        "notional": round(quantity * price, 2),
                        "score": total_score,
                        "risk_score": raw_risk,
                        "confidence": confidence,
                        "reason": "V21_MULTI_AGENT_COUNCIL",
                        "mode": "PAPER",
                        "status": "PROPOSED",
                        "signal_date": council_date,
                        "execution_date": council_date,
                        "idempotency_key": key,
                    },
                )
                order_id = rows[0]["id"]
                investable_cash = max(0.0, investable_cash - quantity * price)
                remaining_orders -= 1
                cio_reasons.append(
                    f"Created PROPOSED PAPER order for {quantity} shares."
                )
        else:
            cio_reasons.append("Target budget insufficient for minimum lot.")

    cio_memo = " ".join(cio_reasons)
    decision_row = {
        "account_name": ACCOUNT,
        "council_date": council_date,
        "stock_id": signal.get("stock_id"),
        "symbol": symbol,
        "name": stock.get("name"),
        "consensus_score": consensus_score,
        "agreement_pct": agreement_pct,
        "dispersion": dispersion,
        "bullish_votes": bullish,
        "neutral_votes": neutral,
        "bearish_votes": bearish,
        "veto_count": veto_count,
        "final_decision": final_decision,
        "conviction": conviction,
        "target_weight": target_weight,
        "cio_memo": cio_memo,
        "order_id": order_id,
    }
    upsert_rows(
        "investment_council_decisions_v21",
        decision_row,
        "account_name,council_date,symbol",
    )
    decisions.append(decision_row)

buy_count = sum(1 for row in decisions if row["final_decision"] == "BUY")
hold_count = sum(1 for row in decisions if row["final_decision"] in {"HOLD", "PENDING"})
avoid_count = sum(1 for row in decisions if row["final_decision"] in {"AVOID", "WATCH"})
vetoed_count = sum(1 for row in decisions if row["final_decision"] == "VETOED")
average_consensus = (
    statistics.fmean([number(row["consensus_score"]) for row in decisions])
    if decisions
    else 0
)

if buy_count > 0 and vetoed_count == 0:
    market_posture = "SELECTIVE_RISK_ON"
elif vetoed_count >= max(1, len(decisions) // 2):
    market_posture = "RISK_OFF"
else:
    market_posture = "CAUTIOUS"

dissenting = sorted(
    decisions,
    key=lambda row: number(row["dispersion"]),
    reverse=True,
)[:3]
dissent_summary = "; ".join(
    f"{row['symbol']} dispersion {number(row['dispersion']):.1f}"
    for row in dissenting
) or "No material dissent."

cio_message = (
    f"Council reviewed {len(decisions)} symbols. "
    f"{buy_count} BUY, {hold_count} HOLD/PENDING, "
    f"{avoid_count} WATCH/AVOID, {vetoed_count} VETOED."
)
execution_guidance = (
    "Review all PROPOSED PAPER orders before approval and simulation fill."
    if buy_count
    else "Maintain current portfolio and wait for stronger consensus."
)

upsert_rows(
    "council_reports_v21",
    {
        "account_name": ACCOUNT,
        "report_date": council_date,
        "market_posture": market_posture,
        "symbols_reviewed": len(decisions),
        "buy_decisions": buy_count,
        "hold_decisions": hold_count,
        "avoid_decisions": avoid_count,
        "vetoed_decisions": vetoed_count,
        "average_consensus": average_consensus,
        "chief_investment_officer_message": cio_message,
        "dissent_summary": dissent_summary,
        "execution_guidance": execution_guidance,
    },
    "account_name,report_date",
)

print(cio_message)
print(dissent_summary)
print(execution_guidance)
