# GPT Quant V9.2 — Phase 3.3 Single Deployment Pack

## Purpose

Phase 3.3 adds Production Promotion + Release Governance.

It provides:

- Promotion eligibility
- Release governance
- Explicit human approval
- Explicit human rejection
- Release audit artifacts
- Production PAPER release manifest

It does NOT enable broker execution or real-money trading.

## Install

Extract this ZIP directly into the root of the local `GPT` repository.

Expected files:

- `.github/workflows/gpt-quant-v92-paper-trading-phase33.yml`
- `automation/v92/paper_trading_phase33_release_governance.py`
- `PHASE_3_3_INSTALL.md`
- `PHASE_3_3_MANIFEST.json`

No Supabase SQL migration is required.

## GitHub Desktop

Suggested commit summary:

`Add Phase 3.3 Production Promotion Release Governance`

Then:

Commit to main → Push origin

## First Run

GitHub → Actions →

`GPT Quant V9.2 Paper Trading Phase 3.3 - Production Promotion + Release Governance`

Choose:

- strategy_version = V9.1
- action = evaluate
- approval_token = leave blank

During observation, expected:

- Status: PASS
- Promotion State: OBSERVATION
- Release State: LOCKED

At 5/5 qualified, expected:

- Promotion State: QUALIFIED
- Release State: AWAITING_HUMAN_APPROVAL

Only then run:

- action = approve_release
- approval_token = enter an explicit approval value

Expected:

- Release State: APPROVED_FOR_PRODUCTION_PAPER

This still keeps:

- SHADOW_ONLY_NO_BROKER
- Broker Trading DISABLED
- Real Money DISABLED
