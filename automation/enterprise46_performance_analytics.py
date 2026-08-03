from __future__ import annotations

import math
import os
from datetime import date
from statistics import mean, pstdev
from typing import Any

from enterprise2.client import SupabaseRestClient

RUN_DATE = os.environ.get("QUANT_RUN_DATE", date.today().isoformat())


def n(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback


def latest(
    client: SupabaseRestClient,
    table: str,
    field: str,
    where: str = "",
) -> dict[str, Any]:
    query = (
        f"{where}&order={field}.desc&limit=1"
        if where
        else f"order={field}.desc&limit=1"
    )
    rows = client.get(table, query)
    return rows[0] if rows else {}


def safe_get(
    client: SupabaseRestClient,
    table: str,
    query: str,
) -> list[dict[str, Any]]:
    """
    Read an optional compatibility source without terminating the pipeline.

    portfolio_snapshots_v40 does not exist in some upgraded deployments.
    In that case Performance Analytics falls back to compat_portfolios_v40.
    """
    try:
        rows = client.get(table, query)
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        print(f"Optional source unavailable: {table}: {exc}")
        return []


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def main() -> None:
    client = SupabaseRestClient()
    portfolios = client.get(
        "enterprise_portfolios_v40",
        "lifecycle_status=eq.ACTIVE&portfolio_type=eq.PAPER&limit=100",
    )
    generated = 0

    for portfolio in portfolios:
        portfolio_id = str(portfolio["id"])

        snapshot_rows = safe_get(
            client,
            "portfolio_snapshots_v40",
            (
                f"portfolio_id=eq.{portfolio_id}"
                "&order=snapshot_date.asc&limit=500"
            ),
        )

        compat = latest(
            client,
            "compat_portfolios_v40",
            "latest_snapshot_date",
            f"portfolio_id=eq.{portfolio_id}",
        )
        risk = latest(
            client,
            "portfolio_risk_v41",
            "risk_date",
            f"portfolio_id=eq.{portfolio_id}",
        )

        equities = [
            n(row.get("equity"))
            for row in snapshot_rows
            if n(row.get("equity")) > 0
        ]

        starting_cash = n(portfolio.get("starting_cash"), 1_000_000)
        current_equity = n(
            compat.get("latest_equity"),
            equities[-1] if equities else starting_cash,
        )

        source = "portfolio_snapshots_v40"
        if not equities:
            # Compatibility fallback for deployments without snapshot history.
            equities = [starting_cash, current_equity]
            source = "compat_portfolios_v40_fallback"
        elif equities[-1] != current_equity:
            equities.append(current_equity)

        returns = [
            (equities[index] / equities[index - 1] - 1) * 100
            for index in range(1, len(equities))
            if equities[index - 1] > 0
        ]

        average_return = mean(returns) if returns else 0.0
        volatility = (
            pstdev(returns) * math.sqrt(252)
            if len(returns) >= 2
            else 0.0
        )

        downside_returns = [value for value in returns if value < 0]
        downside_deviation = (
            pstdev(downside_returns) * math.sqrt(252)
            if len(downside_returns) >= 2
            else 0.0
        )
        annualized_return = average_return * 252

        peak = equities[0]
        drawdowns: list[float] = []
        for equity in equities:
            peak = max(peak, equity)
            drawdowns.append((equity / peak - 1) * 100 if peak else 0.0)

        max_drawdown = abs(min(drawdowns)) if drawdowns else 0.0
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        gross_exposure = n(risk.get("gross_exposure_pct"))

        client.upsert(
            "performance_daily_v46",
            {
                "performance_date": RUN_DATE,
                "portfolio_id": portfolio_id,
                "equity": current_equity,
                "daily_return_pct": returns[-1] if returns else 0,
                "cumulative_return_pct": (
                    (equities[-1] / equities[0] - 1) * 100
                    if equities[0] > 0
                    else 0
                ),
                "rolling_volatility_pct": volatility,
                "sharpe_ratio": (
                    (annualized_return - 1.5) / volatility
                    if volatility > 0
                    else 0
                ),
                "sortino_ratio": (
                    (annualized_return - 1.5) / downside_deviation
                    if downside_deviation > 0
                    else 0
                ),
                "calmar_ratio": (
                    annualized_return / max_drawdown
                    if max_drawdown > 0
                    else 0
                ),
                "max_drawdown_pct": max_drawdown,
                "win_rate": (
                    len(wins) / len(returns) * 100 if returns else 0
                ),
                "profit_factor": (
                    gross_profit / gross_loss
                    if gross_loss > 0
                    else gross_profit
                ),
                "expectancy_pct": average_return,
                "gross_exposure_pct": gross_exposure,
                "cash_ratio_pct": clamp(100 - gross_exposure),
                "sample_count": len(returns),
                "diagnostics": {
                    "source": source,
                    "snapshot_history_available": bool(snapshot_rows),
                    "compatibility_hotfix": "4.6.1",
                },
            },
            "performance_date,portfolio_id",
        )
        generated += 1

    print(
        f"Enterprise 4.6.1 generated {generated} "
        "performance record(s)."
    )


if __name__ == "__main__":
    main()
