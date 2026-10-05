from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import sqrt
from statistics import median, pstdev


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: Decimal
    cagr: Decimal
    sharpe: Decimal
    max_drawdown: Decimal
    profit_factor: Decimal
    turnover: Decimal
    average_exposure: Decimal


def performance(equity: tuple[tuple[date, Decimal], ...], turnover: Decimal,
                exposures: tuple[Decimal, ...]) -> PerformanceMetrics:
    if len(equity) < 2 or equity[0][1] <= 0:
        raise ValueError("insufficient equity history")
    values = [value for _, value in equity]
    returns = [float(values[i] / values[i - 1] - 1) for i in range(1, len(values))]
    total = values[-1] / values[0] - 1
    years = max(Decimal("1") / Decimal("252"), Decimal((equity[-1][0] - equity[0][0]).days) / Decimal("365.25"))
    cagr = Decimal(str(float(values[-1] / values[0]) ** (1 / float(years)) - 1))
    deviation = pstdev(returns) if len(returns) > 1 else 0.0
    sharpe = Decimal(str((sum(returns) / len(returns)) / deviation * sqrt(252))) if deviation else Decimal("0")
    peak, maximum_drawdown = values[0], Decimal("0")
    gains = losses = Decimal("0")
    for index, value in enumerate(values):
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, Decimal("1") - value / peak)
        if index:
            change = value - values[index - 1]
            gains += max(change, Decimal("0"))
            losses += max(-change, Decimal("0"))
    profit_factor = gains / losses if losses else (Decimal("Infinity") if gains else Decimal("0"))
    exposure = sum(exposures, Decimal("0")) / len(exposures) if exposures else Decimal("0")
    return PerformanceMetrics(total, cagr, sharpe, maximum_drawdown, profit_factor, turnover, exposure)


@dataclass(frozen=True)
class ChronologicalSplit:
    train: tuple[date, ...]
    validation: tuple[date, ...]
    test: tuple[date, ...]


def chronological_split(dates: tuple[date, ...], train_fraction: Decimal = Decimal("0.6"),
                        validation_fraction: Decimal = Decimal("0.2")) -> ChronologicalSplit:
    unique = tuple(sorted(set(dates)))
    if len(unique) < 5 or train_fraction <= 0 or validation_fraction <= 0 or train_fraction + validation_fraction >= 1:
        raise ValueError("invalid chronological split")
    train_end = int(len(unique) * train_fraction)
    validation_end = train_end + int(len(unique) * validation_fraction)
    return ChronologicalSplit(unique[:train_end], unique[train_end:validation_end], unique[validation_end:])


@dataclass(frozen=True)
class PromotionEvidence:
    oos_return: Decimal
    benchmark_excess_return: Decimal
    sharpe: Decimal
    max_drawdown: Decimal
    turnover: Decimal
    cost_sensitive: bool
    cross_symbol_robust: bool
    cross_period_robust: bool
    parameter_stable: bool


def promotion_allowed(evidence: PromotionEvidence) -> bool:
    return all((evidence.oos_return > 0, evidence.benchmark_excess_return > 0,
                evidence.sharpe >= Decimal("1"), evidence.max_drawdown <= Decimal("0.25"),
                evidence.cost_sensitive, evidence.cross_symbol_robust,
                evidence.cross_period_robust, evidence.parameter_stable))


@dataclass(frozen=True)
class WalkForwardSummary:
    windows: int
    positive_return_windows_pct: Decimal
    benchmark_beating_windows_pct: Decimal
    median_return_pct: Decimal
    median_excess_return_pct: Decimal
    median_sharpe: Decimal
    median_max_drawdown_pct: Decimal
    profitable_symbols_pct: Decimal
    benchmark_beating_symbols_pct: Decimal
    robustness_gate: str


SEALED_STEP8 = WalkForwardSummary(
    windows=15,
    positive_return_windows_pct=Decimal("80.0000"),
    benchmark_beating_windows_pct=Decimal("20.0000"),
    median_return_pct=Decimal("38.604329"),
    median_excess_return_pct=Decimal("-20.945139"),
    median_sharpe=Decimal("1.512317"),
    median_max_drawdown_pct=Decimal("19.121100"),
    profitable_symbols_pct=Decimal("100.0000"),
    benchmark_beating_symbols_pct=Decimal("0.0000"),
    robustness_gate="FAIL",
)

# Repository-controlled promotion registry. It remains empty until independent,
# point-in-time OOS evidence passes the complete promotion gate in a future change.
PROMOTED_PAPER_STRATEGIES: tuple[str, ...] = ()


def summarize_windows(returns: tuple[Decimal, ...], excess: tuple[Decimal, ...],
                      sharpes: tuple[Decimal, ...], drawdowns: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    if not returns or not (len(returns) == len(excess) == len(sharpes) == len(drawdowns)):
        raise ValueError("window evidence mismatch")
    return (Decimal(str(median(returns))), Decimal(str(median(excess))),
            Decimal(str(median(sharpes))), Decimal(str(median(drawdowns))))
