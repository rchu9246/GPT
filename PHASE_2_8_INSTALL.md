# GPT Quant V9.2 — Phase 2.8 Single Deployment Pack

## Purpose

Phase 2.8 adds Production Readiness + Controlled Go-Live for **Production PAPER only**.

It does **not** enable broker connectivity or real-money trading.

## Install

Extract this ZIP directly into the root of your local `GPT` repository.

After extraction, these files should exist:

- `.github/workflows/gpt-quant-v92-paper-trading-phase28.yml`
- `automation/v92/paper_trading_phase28_readiness.py`

No Supabase SQL migration is required.

## GitHub Desktop

Commit summary:

`Add Phase 2.8 Production Readiness Controlled Go-Live`

Then:

1. Commit to main
2. Push origin

## First Run

GitHub → Actions →

`GPT Quant V9.2 Paper Trading Phase 2.8 - Production Readiness + Controlled Go-Live`

Choose:

- `strategy_version`: `V9.1`
- `action`: `readiness_check`

During the current observation period, expected result is:

`OBSERVATION`

When the Phase 2.7 consecutive PASS streak reaches 5/5, expected result becomes:

`READY_FOR_PRODUCTION_PAPER`

Only after that should you manually run again with:

`action = arm_production_paper`

That produces a release manifest but still keeps:

- Broker execution: DISABLED
- Real money: DISABLED
- Safety mode: SHADOW_ONLY_NO_BROKER
