from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def find_file(root: Path, name: str) -> Path | None:
    matches = sorted(root.rglob(name))
    return matches[0] if matches else None


def copy_existing(source_root: Path, output_dir: Path) -> dict[str, Any]:
    names = {
        "v9_metrics.json": None,
        "v91_metrics.json": None,
        "v9_trades.csv": None,
        "v91_trades.csv": None,
        "v9_equity_curve.csv": None,
        "v91_equity_curve.csv": None,
        "v9-vs-v91-report.json": None,
    }
    for name in names:
        found = find_file(source_root, name)
        if found:
            target = output_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found, target)
            names[name] = str(found)
    return names


def run_real_backtest(
    version: str,
    command: str,
    output_dir: Path,
    timeout_seconds: int,
) -> None:
    if not command.strip():
        raise ValueError(f"Missing real backtest command for {version}")

    metrics = output_dir / f"{version}_metrics.json"
    trades = output_dir / f"{version}_trades.csv"
    equity = output_dir / f"{version}_equity_curve.csv"

    env = os.environ.copy()
    env.update({
        "GPTQ_BACKTEST_VERSION": version,
        "GPTQ_METRICS_OUTPUT": str(metrics),
        "GPTQ_TRADES_OUTPUT": str(trades),
        "GPTQ_EQUITY_OUTPUT": str(equity),
    })

    result = subprocess.run(
        command,
        shell=True,
        text=True,
        env=env,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{version} production backtest failed with exit code "
            f"{result.returncode}"
        )


def validate_outputs(output_dir: Path, min_equity_rows: int, min_trade_rows: int) -> dict[str, Any]:
    required = [
        output_dir / "v9_metrics.json",
        output_dir / "v91_metrics.json",
        output_dir / "v9_trades.csv",
        output_dir / "v91_trades.csv",
        output_dir / "v9_equity_curve.csv",
        output_dir / "v91_equity_curve.csv",
    ]
    missing = [str(path) for path in required if not path.exists()]

    counts = {
        "v9_trade_rows": csv_row_count(output_dir / "v9_trades.csv"),
        "v91_trade_rows": csv_row_count(output_dir / "v91_trades.csv"),
        "v9_equity_rows": csv_row_count(output_dir / "v9_equity_curve.csv"),
        "v91_equity_rows": csv_row_count(output_dir / "v91_equity_curve.csv"),
    }

    sufficient = (
        not missing
        and counts["v9_trade_rows"] >= min_trade_rows
        and counts["v91_trade_rows"] >= min_trade_rows
        and counts["v9_equity_rows"] >= min_equity_rows
        and counts["v91_equity_rows"] >= min_equity_rows
    )
    return {
        "sufficient": sufficient,
        "missing": missing,
        "counts": counts,
    }


def generate_extended_smoke(output_dir: Path, points: int = 120, trades: int = 60) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for version, return_pct, drawdown, sharpe, pf in [
        ("v9", 24.0, -12.0, 1.48, 1.62),
        ("v91", 27.0, -8.0, 1.83, 1.89),
    ]:
        metrics = {
            "total_return": return_pct,
            "annual_return": 18.2 if version == "v9" else 20.1,
            "max_drawdown": drawdown,
            "sharpe": sharpe,
            "sortino": 2.10 if version == "v9" else 2.80,
            "win_rate": 55.0 if version == "v9" else 57.0,
            "profit_factor": pf,
            "total_trades": trades,
            "average_trade": 3200 if version == "v9" else 3500,
            "exposure": 62.0 if version == "v9" else 55.0,
            "volatility": 14.5 if version == "v9" else 11.8,
            "calmar": 1.52 if version == "v9" else 2.51,
        }
        (output_dir / f"{version}_metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with (output_dir / f"{version}_equity_curve.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "equity"])
            writer.writeheader()
            equity = 1_000_000.0
            for index in range(points):
                cycle = ((index % 11) - 4) * (65 if version == "v91" else 55)
                drift = 950 if version == "v91" else 800
                equity += drift + cycle
                writer.writerow({
                    "timestamp": f"2026-01-{1 + index // 24:02d}T{index % 24:02d}:00:00Z",
                    "equity": round(equity, 2),
                })

        with (output_dir / f"{version}_trades.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            fields = ["timestamp", "side", "entry_price", "exit_price", "pnl"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index in range(trades):
                winner = index % (7 if version == "v91" else 6) != 0
                pnl = (4200 if version == "v91" else 3600) if winner else -2200
                writer.writerow({
                    "timestamp": f"2026-02-{1 + index // 20:02d}T{index % 20:02d}:00:00Z",
                    "side": "LONG" if index % 2 == 0 else "SHORT",
                    "entry_price": 100 + index,
                    "exit_price": 101 + index,
                    "pnl": pnl,
                })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=["auto", "production", "smoke"],
        default="auto",
    )
    parser.add_argument("--min-equity-rows", type=int, default=30)
    parser.add_argument("--min-trade-rows", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    copied = copy_existing(args.source_dir, args.output_dir)
    initial = validate_outputs(
        args.output_dir,
        args.min_equity_rows,
        args.min_trade_rows,
    )

    v9_command = os.environ.get("V9_REAL_BACKTEST_COMMAND", "")
    v91_command = os.environ.get("V91_REAL_BACKTEST_COMMAND", "")
    production_commands_ready = bool(v9_command.strip() and v91_command.strip())

    source_type = "phase2_artifact"
    action = "use_existing"

    if args.mode == "production":
        if not production_commands_ready:
            raise ValueError(
                "Production mode requires V9_REAL_BACKTEST_COMMAND and "
                "V91_REAL_BACKTEST_COMMAND repository variables"
            )
        run_real_backtest("v9", v9_command, args.output_dir, args.timeout_seconds)
        run_real_backtest("v91", v91_command, args.output_dir, args.timeout_seconds)
        source_type = "production_backtest"
        action = "rerun_production"

    elif args.mode == "auto" and not initial["sufficient"]:
        if production_commands_ready:
            run_real_backtest("v9", v9_command, args.output_dir, args.timeout_seconds)
            run_real_backtest("v91", v91_command, args.output_dir, args.timeout_seconds)
            source_type = "production_backtest"
            action = "auto_rerun_production"
        else:
            generate_extended_smoke(args.output_dir)
            source_type = "synthetic_smoke_validation"
            action = "auto_generate_extended_smoke"

    elif args.mode == "smoke":
        generate_extended_smoke(args.output_dir)
        source_type = "synthetic_smoke_validation"
        action = "generate_extended_smoke"

    final = validate_outputs(
        args.output_dir,
        args.min_equity_rows,
        args.min_trade_rows,
    )
    if not final["sufficient"]:
        raise ValueError(
            "Research input remains insufficient after resolution: "
            + json.dumps(final, ensure_ascii=False)
        )

    manifest = {
        "requested_mode": args.mode,
        "source_type": source_type,
        "production_evidence": source_type == "production_backtest",
        "action": action,
        "initial_validation": initial,
        "final_validation": final,
        "copied_sources": copied,
    }
    (args.output_dir / "research_input_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
