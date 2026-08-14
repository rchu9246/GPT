# GPT Quant V9.2 — Phase 3.0 Single Deployment Pack

## Purpose

Phase 3.0 adds the Production Paper Trading Control Center.

It consolidates:

- System Health
- Phase 2.8/2.9 readiness state
- Portfolio / Ledger
- Positions / Signals / Orders
- P&L
- Market freshness
- Risk checks
- Kill Switch
- Go-Live observation state
- Standalone HTML Control Center

Safety remains:

- SHADOW_ONLY_NO_BROKER
- Broker Trading DISABLED
- Real Money DISABLED
- Fail Closed YES

## Install

Extract this ZIP into the root of your local `GPT` repository.

Expected files:

- `.github/workflows/gpt-quant-v92-paper-trading-phase30.yml`
- `automation/v92/paper_trading_phase30_control_center.py`
- `PHASE_3_0_INSTALL.md`
- `PHASE_3_0_MANIFEST.json`

No Supabase SQL migration is required.

## Commit

Suggested GitHub Desktop summary:

`Add Phase 3.0 Production Paper Trading Control Center`

Then:

Commit to main → Push origin

## Run

GitHub → Actions →

`GPT Quant V9.2 Paper Trading Phase 3.0 - Production Paper Trading Control Center`

Select:

`V9.1`

Expected during observation:

- System Health: PASS
- Control State: OBSERVATION
- Consecutive PASS: 1/5 (or current streak)
- Broker Trading: DISABLED
- Real Money: DISABLED
- Kill Switch: ARMED

The generated artifact contains:

`dashboard/phase30_control_center.html`
