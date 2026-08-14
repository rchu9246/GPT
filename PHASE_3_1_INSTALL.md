# GPT Quant V9.2 — Phase 3.1 Single Deployment Pack

## Purpose

Phase 3.1 adds:

- Production Operations Automation
- Incident Guard
- Fail-Closed operational protection
- Incident/Audit artifacts
- Recovery readiness evaluation
- Kill Switch state
- Automatic Phase 3.0 Control Center refresh

Safety remains:

- SHADOW_ONLY_NO_BROKER
- Broker Trading DISABLED
- Real Money DISABLED
- Automatic broker resume DISABLED
- Manual review required

## Install

Extract this ZIP into the root of your local `GPT` repository.

Expected files:

- `.github/workflows/gpt-quant-v92-paper-trading-phase31.yml`
- `automation/v92/paper_trading_phase31_incident_guard.py`
- `PHASE_3_1_INSTALL.md`
- `PHASE_3_1_MANIFEST.json`

Phase 3.0 must already be installed.

No Supabase SQL migration is required.

## GitHub Desktop

Suggested commit summary:

`Add Phase 3.1 Production Operations Automation Incident Guard`

Then:

Commit to main → Push origin

## Run

GitHub → Actions →

`GPT Quant V9.2 Paper Trading Phase 3.1 - Production Operations Automation + Incident Guard`

Select:

`V9.1`

Expected during healthy observation:

- Status: PASS
- Operations State: OBSERVATION
- Incident State: CLEAR
- Kill Switch: ARMED
- Broker Trading: DISABLED
- Real Money: DISABLED

If an operational or risk check fails:

- Incident State: ACTIVE
- Operations State: LOCKED
- Workflow fails closed
- Diagnostic artifact contains `phase31_incidents.json`

Recovery evaluation is advisory only and never auto-enables broker execution.
