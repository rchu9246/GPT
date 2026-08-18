#!/usr/bin/env python3
"""
GPT Quant V9.2 Paper Trading Phase 3.4.4
Human Approval Readiness Gate
Patched by Phase 3.4.4.3 v2 Runtime Canonical State Reconstruction.

This gate rebuilds canonical state in the same runner.
It NEVER authorizes release and NEVER enables broker/live-money trading.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "automation/v92/paper_trading_phase3443_runtime_canonical_state_reconstruction.py"

def main():
    if not BRIDGE.exists():
        raise RuntimeError(f"Missing runtime reconstruction engine: {BRIDGE}")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = "SHADOW_ONLY_NO_BROKER"

    p = subprocess.run(
        [sys.executable, str(BRIDGE)],
        cwd=str(ROOT),
        env=env,
        text=True,
    )

    return p.returncode

if __name__ == "__main__":
    raise SystemExit(main())