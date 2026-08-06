from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any

METRIC_ALIASES = {
    "total_return": ["total_return", "return", "return_pct", "net_return"],
    "annual_return": ["annual_return", "annualized_return", "cagr"],
    "max_drawdown": ["max_drawdown", "mdd", "max_dd", "drawdown"],
    "sharpe": ["sharpe", "sharpe_ratio"],
    "sortino": ["sortino", "sortino_ratio"],
    "win_rate": ["win_rate", "winrate", "winning_rate"],
    "profit_factor": ["profit_factor", "pf"],
    "total_trades": ["total_trades", "trades", "trade_count"],
    "average_trade": ["average_trade", "avg_trade", "expectancy"],
    "exposure": ["exposure", "market_exposure"],
    "volatility": ["volatility", "annual_volatility"],
    "calmar": ["calmar", "calmar_ratio"],
}

TRADE_ALIASES = {
    "timestamp": ["timestamp", "time", "datetime", "date", "exit_time"],
    "side": ["side", "direction", "position", "signal"],
    "entry_price": ["entry_price", "entry", "open_price"],
    "exit_price": ["exit_price", "exit", "close_price"],
    "pnl": ["pnl", "profit", "net_profit", "realized_pnl"],
}

EQUITY_ALIASES = {
    "timestamp": ["timestamp", "time", "datetime", "date"],
    "equity": ["equity", "balance", "nav", "account_value", "portfolio_value"],
}

REQUIRED_METRICS = {
    "total_return",
    "max_drawdown",
    "sharpe",
    "profit_factor",
    "total_trades",
}


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def read_single_row_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"Metrics CSV must contain exactly one row: {path}")
    return rows[0]


def source_metrics(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return read_json(path)
    if path.suffix.lower() == ".csv":
        return read_single_row_csv(path)
    raise ValueError(f"Unsupported metrics source: {path}")


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", "").strip())
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def find_value(source: dict[str, Any], aliases: list[str]) -> Any:
    lowered = {str(key).lower().strip(): value for key, value in source.items()}
    for alias in aliases:
        if alias in lowered:
            return lowered[alias]
    return None


def normalize_metrics(source: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}

    for target, aliases in METRIC_ALIASES.items():
        value = numeric(find_value(source, aliases))
        if value is None:
            continue

        if target in {
            "total_return",
            "annual_return",
            "max_drawdown",
            "win_rate",
            "exposure",
            "volatility",
        } and abs(value) <= 1.5:
            value *= 100.0

        normalized[target] = value

    missing = sorted(REQUIRED_METRICS.difference(normalized))
    if missing:
        raise ValueError(
            "Normalized metrics missing required fields: "
            + ", ".join(missing)
        )

    return normalized


def resolve_columns(fieldnames: list[str] | None, aliases: dict[str, list[str]]) -> dict[str, str]:
    fields = {name.lower().strip(): name for name in (fieldnames or [])}
    resolved: dict[str, str] = {}

    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in fields:
                resolved[target] = fields[candidate]
                break

    missing = sorted(set(aliases).difference(resolved))
    if missing:
        raise ValueError("Missing source columns: " + ", ".join(missing))

    return resolved


def normalize_trades(source: Path, output: Path) -> int:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = resolve_columns(reader.fieldnames, TRADE_ALIASES)
        rows = list(reader)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "side", "entry_price", "exit_price", "pnl"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "timestamp": row[columns["timestamp"]],
                "side": str(row[columns["side"]]).upper(),
                "entry_price": numeric(row[columns["entry_price"]]),
                "exit_price": numeric(row[columns["exit_price"]]),
                "pnl": numeric(row[columns["pnl"]]),
            })
    return len(rows)


def normalize_equity(source: Path, output: Path) -> int:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = resolve_columns(reader.fieldnames, EQUITY_ALIASES)
        rows = list(reader)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "equity"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "timestamp": row[columns["timestamp"]],
                "equity": numeric(row[columns["equity"]]),
            })
    return len(rows)


def run_command(command: str, env: dict[str, str], timeout: int) -> None:
    if not command.strip():
        raise ValueError("Production backtest command is empty")
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Production backtest command failed with exit code "
            f"{result.returncode}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=["v9", "v91"], required=True)
    parser.add_argument("--command", default="")
    parser.add_argument("--metrics-source", type=Path)
    parser.add_argument("--trades-source", type=Path)
    parser.add_argument("--equity-source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--min-equity-rows", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(exist_ok=True)

    metrics_source = args.metrics_source
    trades_source = args.trades_source
    equity_source = args.equity_source

    if args.command.strip():
        metrics_source = raw_dir / f"{args.version}_raw_metrics.json"
        trades_source = raw_dir / f"{args.version}_raw_trades.csv"
        equity_source = raw_dir / f"{args.version}_raw_equity.csv"

        env = os.environ.copy()
        env.update({
            "GPTQ_BACKTEST_VERSION": args.version,
            "GPTQ_RAW_METRICS_OUTPUT": str(metrics_source),
            "GPTQ_RAW_TRADES_OUTPUT": str(trades_source),
            "GPTQ_RAW_EQUITY_OUTPUT": str(equity_source),
            "GPTQ_METRICS_OUTPUT": str(metrics_source),
            "GPTQ_TRADES_OUTPUT": str(trades_source),
            "GPTQ_EQUITY_OUTPUT": str(equity_source),
        })
        run_command(args.command, env, args.timeout_seconds)

    if not metrics_source or not trades_source or not equity_source:
        raise ValueError(
            "Provide --command or all three source files: "
            "--metrics-source, --trades-source, --equity-source"
        )

    for path in [metrics_source, trades_source, equity_source]:
        if not path.exists():
            raise FileNotFoundError(path)

    metrics = normalize_metrics(source_metrics(metrics_source))
    metrics_output = args.output_dir / f"{args.version}_metrics.json"
    trades_output = args.output_dir / f"{args.version}_trades.csv"
    equity_output = args.output_dir / f"{args.version}_equity_curve.csv"

    metrics_output.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    trade_rows = normalize_trades(trades_source, trades_output)
    equity_rows = normalize_equity(equity_source, equity_output)

    checks = {
        "required_metrics": True,
        "minimum_trades": trade_rows >= args.min_trades,
        "minimum_equity_rows": equity_rows >= args.min_equity_rows,
        "metrics_finite": all(math.isfinite(value) for value in metrics.values()),
    }
    production_evidence = all(checks.values())

    manifest = {
        "adapter_version": "3.4",
        "version": args.version,
        "production_evidence": production_evidence,
        "source": {
            "metrics": str(metrics_source),
            "trades": str(trades_source),
            "equity": str(equity_source),
            "command_used": bool(args.command.strip()),
        },
        "outputs": {
            "metrics": str(metrics_output),
            "trades": str(trades_output),
            "equity": str(equity_output),
        },
        "counts": {
            "trade_rows": trade_rows,
            "equity_rows": equity_rows,
        },
        "checks": checks,
    }

    manifest_output = args.output_dir / f"{args.version}_production_evidence_manifest.json"
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    if not production_evidence:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
