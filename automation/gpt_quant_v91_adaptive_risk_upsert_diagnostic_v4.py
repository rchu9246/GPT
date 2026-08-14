#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "automation" / "gpt_quant_v91_adaptive_risk_manager.py"

def main():
    env = os.environ.copy()

    proc = subprocess.run(
        [
            sys.executable,
            str(TARGET),
            "--base-risk-budget",
            env.get("V91_BASE_RISK_BUDGET", "0.60"),
        ],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    print("=== ADAPTIVE RISK STDOUT ===")
    print(proc.stdout or "")
    print("=== ADAPTIVE RISK STDERR ===")
    print(proc.stderr or "")

    if proc.returncode != 0:
        print("=== V4 RESULT: FAILED ===")
        print("Copy the complete error above; v4 preserves the real Supabase response.")
        return proc.returncode

    print("=== V4 RESULT: PASS ===")
    print("Real Adaptive Risk execution completed successfully.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())