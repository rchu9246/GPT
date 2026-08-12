# GPT Quant V9.2 — Paper Trading Phase 2.5

## Purpose
Phase 2.5 coordinates the existing successful Paper Trading modules in this order:

2.2 Market Data Ingestion → 2.1 Signal Generation → 2.3 Signal Execution → 2.4 Position Management.

It remains locked to `SHADOW_ONLY_NO_BROKER`.

## Install
1. Copy this pack into the root of the GPT repository and overwrite/merge the matching folders.
2. In Supabase SQL Editor, run:
   `supabase/GPT_QUANT_V92_PAPER_TRADING_PHASE25_UPGRADE.sql`
3. Commit the files to `main`.
4. Open GitHub → Actions → **GPT Quant V9.2 Paper Trading Phase 2.5 - Automatic Trading Orchestrator**.
5. Choose **Run workflow**, strategy `V9.1`.
6. Confirm the job is green and the Summary reports:
   - status = COMPLETED
   - pipeline = HEALTHY
   - Phase 2.2 = PASS
   - Phase 2.1 = PASS
   - Phase 2.3 = PASS
   - Phase 2.4 = PASS

## Required GitHub Secrets
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `FINMIND_TOKEN`

## Safety
This phase intentionally does not integrate with a broker and will stop if the mode is changed from `SHADOW_ONLY_NO_BROKER`.

## Important
The orchestrator expects the existing Phase 2.1–2.4 Python files at:
- automation/v92/paper_trading_phase22_market_ingestion.py
- automation/v92/paper_trading_phase21_signal_engine.py
- automation/v92/paper_trading_phase23_signal_execution.py
- automation/v92/paper_trading_phase24_position_management.py

If your repository uses different filenames, rename those existing files or update `PHASES` in the orchestrator before running.
