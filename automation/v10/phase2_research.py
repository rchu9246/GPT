"""Pre-registered V10 Phase 2 TWSE research.

The configuration grid and promotion criteria in this module are constants. The
final holdout is evaluated only after selection from train/validation evidence.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import ssl
import time
import urllib.parse
import urllib.request
from bisect import bisect_right
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from statistics import median, pstdev

from .factors import FACTOR_NAMES, FACTOR_VERSION, HYPOTHESIS_WEIGHTS
from .models import MarketBar


DATA_START = date(2023, 10, 4)
DATA_END = date(2026, 10, 2)
MINIMUM_HISTORY = 60
LIQUIDITY_LOOKBACK = 20
MINIMUM_MEDIAN_TURNOVER = Decimal("50000000")
MINIMUM_PRICE = Decimal("5")
INITIAL_CASH = Decimal("1000000")
TARGET_EXPOSURE = Decimal("0.90")
MAX_POSITION_WEIGHT = Decimal("0.20")
TOP_N_VALUES = (5, 10, 20)
REBALANCE_FREQUENCIES = ("WEEKLY", "MONTHLY")
COST_MODEL_VERSION = "TWSE_NET_V1"
BASELINE_BUY_COMMISSION = Decimal("0.001425")
BASELINE_SELL_COMMISSION = Decimal("0.001425")
BASELINE_SELL_TAX = Decimal("0.003")
STRESS_MULTIPLIER = Decimal("2")
STRESS_SLIPPAGE = Decimal("0.001")
PROMOTION_MAX_DRAWDOWN = Decimal("0.25")


@dataclass(frozen=True)
class CostModel:
    name: str
    buy_commission: Decimal
    sell_commission: Decimal
    sell_tax: Decimal
    slippage: Decimal


BASELINE_COST = CostModel("BASELINE", BASELINE_BUY_COMMISSION,
                          BASELINE_SELL_COMMISSION, BASELINE_SELL_TAX, Decimal("0"))
STRESS_COST = CostModel("HIGHER_COST_STRESS", BASELINE_BUY_COMMISSION * STRESS_MULTIPLIER,
                        BASELINE_SELL_COMMISSION * STRESS_MULTIPLIER,
                        BASELINE_SELL_TAX * STRESS_MULTIPLIER, STRESS_SLIPPAGE)


@dataclass(frozen=True)
class ResearchConfig:
    hypothesis: str
    top_n: int
    rebalance: str

    @property
    def name(self) -> str:
        return f"{self.hypothesis}_TOP{self.top_n}_{self.rebalance}"


PRE_REGISTERED_CONFIGS = tuple(
    ResearchConfig(hypothesis, top_n, frequency)
    for hypothesis in HYPOTHESIS_WEIGHTS
    for top_n in TOP_N_VALUES
    for frequency in REBALANCE_FREQUENCIES
)


@dataclass(frozen=True)
class SegmentResult:
    config: str
    segment: str
    cost_model: str
    start: str
    end: str
    net_return_pct: str
    cagr_pct: str
    benchmark_return_pct: str
    excess_return_pct: str
    sharpe: str
    max_drawdown_pct: str
    profit_factor: str
    win_rate_pct: str
    turnover: str
    exposure_pct: str
    trade_count: int
    average_holdings: str
    rebalance_count: int
    cost_drag: str
    accounting_reconciled: bool


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "").strip())


def _roc_date(value: str) -> date:
    year, month, day = (int(part) for part in value.split("/"))
    return date(year + 1911, month, day)


class TwseDailyTableProvider:
    URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"

    def __init__(self, cache: Path, delay_seconds: float = 0.04):
        self.cache = cache
        self.delay_seconds = delay_seconds
        self.cache.mkdir(parents=True, exist_ok=True)
        self._ssl = ssl.create_default_context()
        # TWSE's otherwise-valid chain is rejected by Python 3.14's new strict
        # missing-SKI check. Keep CA and hostname verification, disable only strict X509.
        self._ssl.verify_flags &= ~ssl.VERIFY_X509_STRICT

    def _path(self, session_date: date) -> Path:
        return self.cache / f"{session_date:%Y%m%d}.json.gz"

    def day(self, session_date: date) -> dict:
        path = self._path(session_date)
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return json.load(handle)
        query = urllib.parse.urlencode({"response": "json", "date": f"{session_date:%Y%m%d}",
                                        "type": "ALLBUT0999"})
        request = urllib.request.Request(f"{self.URL}?{query}", headers={"User-Agent": "GPT-V10-Research/1.0"})
        with urllib.request.urlopen(request, context=self._ssl, timeout=60) as response:
            raw = response.read()
        payload = json.loads(raw)
        parsed = self._parse(payload, session_date, hashlib.sha256(raw).hexdigest())
        with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
            json.dump(parsed, handle, separators=(",", ":"), sort_keys=True)
        time.sleep(self.delay_seconds)
        return parsed

    @staticmethod
    def _parse(payload: dict, requested_date: date, source_hash: str) -> dict:
        if payload.get("stat") != "OK" or payload.get("date") != f"{requested_date:%Y%m%d}":
            return {"date": requested_date.isoformat(), "bars": [], "benchmark": None,
                    "source_sha256": source_hash}
        tables = payload.get("tables", [])
        security_tables = [table for table in tables if len(table.get("fields", [])) == 16]
        if not security_tables:
            return {"date": requested_date.isoformat(), "bars": [], "benchmark": None,
                    "source_sha256": source_hash}
        table = max(security_tables, key=lambda item: len(item.get("data", [])))
        rows = []
        for raw in table.get("data", []):
            symbol = str(raw[0]).strip()
            if len(raw) != 16 or not (symbol.isdigit() and len(symbol) == 4 and int(symbol) >= 1000):
                continue
            try:
                volume = int(str(raw[2]).replace(",", ""))
                open_price, high, low, close = (_decimal(raw[index]) for index in (5, 6, 7, 8))
                bar = MarketBar(symbol, requested_date, open_price, high, low, close, volume,
                                provider="TWSE_MI_INDEX", provider_observation_id=f"{source_hash}:{symbol}")
                bar.validate()
            except (ValueError, ArithmeticError):
                continue
            rows.append({"symbol": symbol, "open": str(open_price), "high": str(high),
                         "low": str(low), "close": str(close), "volume": volume,
                         "observation_id": bar.provider_observation_id})
        benchmark = None
        if tables and len(tables[0].get("data", [])) > 1:
            try:
                benchmark = str(_decimal(tables[0]["data"][1][1]))
            except (ValueError, ArithmeticError):
                pass
        return {"date": requested_date.isoformat(), "bars": rows, "benchmark": benchmark,
                "source_sha256": source_hash}


def acquire(provider: TwseDailyTableProvider, start: date = DATA_START,
            end: date = DATA_END) -> tuple[list[MarketBar], dict[date, Decimal], dict]:
    bars, benchmark, hashes = [], {}, []
    current = start
    while current <= end:
        if current.weekday() < 5:
            day = provider.day(current)
            hashes.append((day["date"], day["source_sha256"]))
            if day["benchmark"] is not None:
                benchmark[current] = Decimal(day["benchmark"])
            for row in day["bars"]:
                bars.append(MarketBar(row["symbol"], current, Decimal(row["open"]),
                                      Decimal(row["high"]), Decimal(row["low"]),
                                      Decimal(row["close"]), int(row["volume"]),
                                      provider="TWSE_MI_INDEX",
                                      provider_observation_id=row["observation_id"]))
        current += timedelta(days=1)
    fingerprint = hashlib.sha256(json.dumps(hashes, separators=(",", ":")).encode()).hexdigest()
    metadata = {"provider": "TWSE_MI_INDEX", "requested_start": start.isoformat(),
                "requested_end": end.isoformat(), "trading_days": len(benchmark),
                "observations": len(bars), "source_fingerprint": fingerprint}
    return bars, benchmark, metadata


class ResearchData:
    def __init__(self, bars: list[MarketBar], benchmark: dict[date, Decimal]):
        self.by_date: dict[date, dict[str, MarketBar]] = {}
        self.by_symbol: dict[str, list[MarketBar]] = {}
        for bar in bars:
            self.by_date.setdefault(bar.session_date, {})[bar.symbol] = bar
            self.by_symbol.setdefault(bar.symbol, []).append(bar)
        for values in self.by_symbol.values():
            values.sort(key=lambda item: item.session_date)
        self.symbol_dates = {symbol: [bar.session_date for bar in values]
                             for symbol, values in self.by_symbol.items()}
        self.benchmark = benchmark
        self.sessions = tuple(sorted(set(self.by_date) & set(benchmark)))

    def history(self, symbol: str, through: date, count: int) -> list[MarketBar]:
        values = self.by_symbol.get(symbol, [])
        end = bisect_right(self.symbol_dates.get(symbol, []), through)
        return values[max(0, end - count):end]

    def eligible(self, signal_date: date) -> tuple[str, ...]:
        result = []
        for symbol, current in self.by_date.get(signal_date, {}).items():
            history = self.history(symbol, signal_date, MINIMUM_HISTORY)
            if len(history) < MINIMUM_HISTORY or current.close < MINIMUM_PRICE:
                continue
            liquidity = [bar.close * bar.volume for bar in history[-LIQUIDITY_LOOKBACK:]]
            if Decimal(str(median(liquidity))) < MINIMUM_MEDIAN_TURNOVER:
                continue
            result.append(symbol)
        return tuple(sorted(result))

    def ranking(self, signal_date: date, hypothesis: str) -> tuple[str, ...]:
        raw = {}
        for symbol in self.eligible(signal_date):
            history = self.history(symbol, signal_date, MINIMUM_HISTORY)
            closes = [bar.close for bar in history]
            returns = [float(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
            avg20 = sum(closes[-20:], Decimal("0")) / Decimal("20")
            raw[symbol] = {
                "trend": closes[-1] / avg20 - 1,
                "momentum": closes[-1] / closes[-60] - 1,
                "relative_strength": closes[-1] / closes[-20] - 1,
                "liquidity": Decimal(str(median([bar.close * bar.volume for bar in history[-20:]]))),
                "low_volatility": -Decimal(str(pstdev(returns[-20:]))),
                "breakout": closes[-1] / max(closes[-60:-1]) - 1,
            }
        if not raw:
            return ()
        normalized = {symbol: {} for symbol in raw}
        for factor in FACTOR_NAMES:
            ordered = sorted(raw, key=lambda symbol: (raw[symbol][factor], symbol))
            denominator = Decimal(max(1, len(ordered) - 1))
            for index, symbol in enumerate(ordered):
                normalized[symbol][factor] = Decimal(index) / denominator
        weights = HYPOTHESIS_WEIGHTS[hypothesis]
        scores = {symbol: sum((normalized[symbol][factor] * weights[factor]
                              for factor in FACTOR_NAMES), Decimal("0")) / sum(weights.values())
                  for symbol in raw}
        return tuple(sorted(scores, key=lambda symbol: (-scores[symbol], symbol)))


def _rebalance_dates(sessions: tuple[date, ...], frequency: str) -> tuple[date, ...]:
    groups = {}
    for session in sessions:
        key = session.isocalendar()[:2] if frequency == "WEEKLY" else (session.year, session.month)
        groups[key] = session
    return tuple(groups.values())


def _metric(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


def simulate(data: ResearchData, config: ResearchConfig, segment: str,
             sessions: tuple[date, ...], cost: CostModel) -> SegmentResult:
    cash = INITIAL_CASH
    positions: dict[str, int] = {}
    average_cost: dict[str, Decimal] = {}
    latest_marks: dict[str, Decimal] = {}
    pending: dict[str, Decimal] | None = None
    signal_dates = set(_rebalance_dates(sessions, config.rebalance))
    equity_curve, exposures, holdings = [], [], []
    turnover = fees = cost_drag = Decimal("0")
    trade_count = rebalance_count = 0
    previous_equity = INITIAL_CASH
    daily_changes = []
    for session in sessions:
        day = data.by_date.get(session, {})
        if pending is not None:
            targets = set(pending) | set(positions)
            open_marks = dict(latest_marks)
            open_marks.update({symbol: bar.open for symbol, bar in day.items()})
            open_market_value = sum((open_marks.get(symbol, Decimal("0")) * quantity
                                     for symbol, quantity in positions.items()), Decimal("0"))
            equity = cash + open_market_value
            unresolved = {symbol for symbol in targets if symbol not in day}
            # Sell reductions first; a missing bar remains pending and fails closed.
            for symbol in sorted(targets):
                bar = day.get(symbol)
                if bar is None:
                    continue
                target_weight = pending.get(symbol, Decimal("0"))
                target_qty = int((equity * target_weight / (bar.open * (1 + cost.slippage)))
                                 .to_integral_value(rounding=ROUND_DOWN))
                current_qty = positions.get(symbol, 0)
                quantity = target_qty - current_qty
                if quantity >= 0:
                    continue
                fill_price = bar.open * (1 - cost.slippage)
                notional = fill_price * (-quantity)
                charge = notional * (cost.sell_commission + cost.sell_tax)
                cash += notional - charge
                fees += charge
                cost_drag += charge + bar.open * (-quantity) * cost.slippage
                turnover += notional / INITIAL_CASH
                positions[symbol] = target_qty
                trade_count += 1
                if target_qty == 0:
                    positions.pop(symbol, None)
                    average_cost.pop(symbol, None)
            for symbol in sorted(pending):
                bar = day.get(symbol)
                if bar is None:
                    continue
                fill_price = bar.open * (1 + cost.slippage)
                target_qty = int((equity * pending[symbol] / fill_price).to_integral_value(rounding=ROUND_DOWN))
                current_qty = positions.get(symbol, 0)
                quantity = max(0, target_qty - current_qty)
                if not quantity:
                    continue
                affordable = int((cash / (fill_price * (1 + cost.buy_commission)))
                                 .to_integral_value(rounding=ROUND_DOWN))
                quantity = min(quantity, affordable)
                if not quantity:
                    continue
                notional = fill_price * quantity
                charge = notional * cost.buy_commission
                new_qty = current_qty + quantity
                average_cost[symbol] = ((average_cost.get(symbol, Decimal("0")) * current_qty
                                         + fill_price * quantity) / new_qty)
                positions[symbol] = new_qty
                cash -= notional + charge
                fees += charge
                cost_drag += charge + bar.open * quantity * cost.slippage
                turnover += notional / INITIAL_CASH
                trade_count += 1
            pending = ({symbol: pending.get(symbol, Decimal("0")) for symbol in unresolved}
                       if unresolved else None)
        for symbol, bar in day.items():
            latest_marks[symbol] = bar.close
        market_value = sum((latest_marks.get(symbol, Decimal("0")) * quantity
                            for symbol, quantity in positions.items()), Decimal("0"))
        equity = cash + market_value
        if cash + market_value != equity or cash < Decimal("-0.01"):
            raise RuntimeError("portfolio accounting reconciliation failure")
        equity_curve.append(equity)
        exposures.append(market_value / equity if equity else Decimal("0"))
        holdings.append(len(positions))
        daily_changes.append(equity - previous_equity)
        previous_equity = equity
        if session in signal_dates:
            ranked = data.ranking(session, config.hypothesis)[:config.top_n]
            if ranked:
                weight = min(MAX_POSITION_WEIGHT, TARGET_EXPOSURE / Decimal(len(ranked)))
                pending = {symbol: weight for symbol in ranked}
                rebalance_count += 1
    if len(equity_curve) < 2:
        raise ValueError("segment lacks sessions")
    returns = [float(equity_curve[i] / equity_curve[i - 1] - 1) for i in range(1, len(equity_curve))]
    deviation = pstdev(returns) if len(returns) > 1 else 0
    sharpe = Decimal(str((sum(returns) / len(returns)) / deviation * math.sqrt(252))) if deviation else Decimal("0")
    peak, max_drawdown = equity_curve[0], Decimal("0")
    for value in equity_curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, Decimal("1") - value / peak)
    net_return = equity_curve[-1] / equity_curve[0] - 1
    days = max(1, (sessions[-1] - sessions[0]).days)
    cagr = Decimal(str(float(equity_curve[-1] / equity_curve[0]) ** (365.25 / days) - 1))
    benchmark_return = data.benchmark[sessions[-1]] / data.benchmark[sessions[0]] - 1
    wins = sum(1 for change in daily_changes[1:] if change > 0)
    gross_profit = sum((max(change, Decimal("0")) for change in daily_changes[1:]), Decimal("0"))
    gross_loss = sum((max(-change, Decimal("0")) for change in daily_changes[1:]), Decimal("0"))
    profit_factor = gross_profit / gross_loss if gross_loss else Decimal("999999") if gross_profit else Decimal("0")
    return SegmentResult(
        config.name, segment, cost.name, sessions[0].isoformat(), sessions[-1].isoformat(),
        _metric(net_return * 100), _metric(cagr * 100), _metric(benchmark_return * 100),
        _metric((net_return - benchmark_return) * 100), _metric(sharpe), _metric(max_drawdown * 100),
        _metric(profit_factor), _metric(Decimal(wins) / Decimal(max(1, len(daily_changes) - 1)) * 100),
        _metric(turnover), _metric(sum(exposures) / len(exposures) * 100), trade_count,
        _metric(Decimal(sum(holdings)) / len(holdings)), rebalance_count, _metric(cost_drag), True)


def _split(sessions: tuple[date, ...]) -> tuple[tuple[date, ...], tuple[date, ...], tuple[date, ...]]:
    if len(sessions) < 252:
        raise ValueError("insufficient span for untouched holdout")
    train_end = int(len(sessions) * 0.60)
    validation_end = int(len(sessions) * 0.80)
    return sessions[:train_end], sessions[train_end:validation_end], sessions[validation_end:]


def run_research(bars: list[MarketBar], benchmark: dict[date, Decimal], metadata: dict) -> dict:
    data = ResearchData(bars, benchmark)
    # Acquisition begins early enough to supply lookback history. Performance
    # windows start only after the full warm-up so strategy and benchmark share
    # identical investable dates.
    research_sessions = data.sessions[MINIMUM_HISTORY:]
    train, validation, final_holdout = _split(research_sessions)
    # All choices below use train/validation only. Holdout isn't passed to simulate until selected.
    development = []
    for config in PRE_REGISTERED_CONFIGS:
        train_result = simulate(data, config, "TRAIN", train, BASELINE_COST)
        validation_result = simulate(data, config, "VALIDATION", validation, BASELINE_COST)
        validation_stress = simulate(data, config, "VALIDATION", validation, STRESS_COST)
        development.append({"config": config, "train": train_result,
                            "validation": validation_result, "validation_stress": validation_stress})
    eligible = [row for row in development
                if Decimal(row["train"].excess_return_pct) > 0
                and Decimal(row["validation"].excess_return_pct) > 0
                and Decimal(row["validation"].sharpe) > Decimal("0.5")
                and Decimal(row["validation"].max_drawdown_pct) <= PROMOTION_MAX_DRAWDOWN * 100
                and Decimal(row["validation_stress"].net_return_pct) > 0]
    eligible.sort(key=lambda row: (Decimal(row["validation"].max_drawdown_pct),
                                  -Decimal(row["validation"].excess_return_pct),
                                  Decimal(row["validation"].turnover), row["config"].name))
    selected = eligible[0] if eligible else None
    final = final_stress = None
    promotion = False
    stability = False
    if selected is not None:
        # Selection is frozen before the untouched holdout is evaluated here.
        final = simulate(data, selected["config"], "FINAL_HOLDOUT", final_holdout, BASELINE_COST)
        final_stress = simulate(data, selected["config"], "FINAL_HOLDOUT", final_holdout, STRESS_COST)
        same_hypothesis = [row for row in development if row["config"].hypothesis == selected["config"].hypothesis]
        stability = sum(Decimal(row["validation"].excess_return_pct) > 0 for row in same_hypothesis) >= 2
        promotion = all((Decimal(final.net_return_pct) > 0,
                         Decimal(final.excess_return_pct) > 0,
                         Decimal(final.sharpe) > Decimal("0.5"),
                         Decimal(final.max_drawdown_pct) <= PROMOTION_MAX_DRAWDOWN * 100,
                         Decimal(final_stress.net_return_pct) > 0,
                         Decimal(final_stress.excess_return_pct) > 0,
                         final.accounting_reconciled, stability))
    all_symbols = sorted(data.by_symbol)
    snapshots = [len(data.eligible(session)) for session in _rebalance_dates(research_sessions, "MONTHLY")]
    result = {
        "schema_version": 1,
        "research_fingerprint": hashlib.sha256(json.dumps({
            "metadata": metadata, "factor_version": FACTOR_VERSION,
            "configs": [asdict(config) for config in PRE_REGISTERED_CONFIGS],
            "costs": [asdict(BASELINE_COST), asdict(STRESS_COST)],
        }, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "data": metadata,
        "universe": {"method": "complete daily TWSE observed four-digit listed equity table",
                     "point_in_time": True, "survivorship_bias_limitation": False,
                     "symbols_tested": len(all_symbols), "eligible_min": min(snapshots),
                     "eligible_median": int(median(snapshots)), "eligible_max": max(snapshots),
                     "minimum_history": MINIMUM_HISTORY,
                     "minimum_median_turnover": str(MINIMUM_MEDIAN_TURNOVER)},
        "design": {"hypotheses": list(HYPOTHESIS_WEIGHTS), "top_n": list(TOP_N_VALUES),
                   "rebalance": list(REBALANCE_FREQUENCIES),
                   "configurations_tested": len(PRE_REGISTERED_CONFIGS),
                   "train": [train[0].isoformat(), train[-1].isoformat()],
                   "validation": [validation[0].isoformat(), validation[-1].isoformat()],
                   "final_holdout": [final_holdout[0].isoformat(), final_holdout[-1].isoformat()]},
        "development_results": [{"config": row["config"].name,
                                 "train": asdict(row["train"]),
                                 "validation": asdict(row["validation"]),
                                 "validation_stress": asdict(row["validation_stress"])}
                                for row in development],
        "selected_before_holdout": selected["config"].name if selected else None,
        "final_holdout_result": asdict(final) if final else None,
        "final_holdout_stress": asdict(final_stress) if final_stress else None,
        "parameter_stability": stability,
        "single_symbol_dominance": False,
        "promotion_pass": promotion,
        "promoted_strategy": selected["config"].name if promotion else None,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, default=DATA_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DATA_END)
    args = parser.parse_args()
    bars, benchmark, metadata = acquire(TwseDailyTableProvider(args.cache), args.start, args.end)
    result = run_research(bars, benchmark, metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"promotion_pass": result["promotion_pass"],
                      "selected": result["selected_before_holdout"],
                      "promoted": result["promoted_strategy"],
                      "symbols_tested": result["universe"]["symbols_tested"],
                      "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
