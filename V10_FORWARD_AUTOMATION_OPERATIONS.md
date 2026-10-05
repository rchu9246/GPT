# V10 Forward Paper Automation Operations

## Activation

- Workflow: `V10 Forward Shadow Paper Validation`
- File: `.github/workflows/v10-forward-shadow-paper.yml`
- Schedule: `0 8 * * 1-5`
- Interpretation: 08:00 UTC, Monday through Friday, which is 16:00 Asia/Taipei. Taiwan does not observe daylight saving time.
- Manual `workflow_dispatch` remains available and requires `enable_forward_validation=true`.
- Repository permission is read only. Actions artifact read access is used only to restore the latest append-only forward store.

The schedule is intentionally after the TWSE close and the expected publication of the official complete daily table.

## Safety

Every run invokes only `python -m automation.v10.forward_daily_run`. It has no V9, legacy Phase 3.x, Supabase, broker, live execution, margin, leverage, short-selling, or real-money dependency.

The safety constitution remains:

- `PAPER_ONLY=True`
- `BROKER_ORDER_SUBMISSION_ENABLED=False`
- `REAL_MONEY_TRADING_ENABLED=False`
- `PRODUCTION_EXECUTION_AVAILABLE=False`
- `HISTORICAL_REWRITE_ALLOWED=False`

## Frozen state

The immutable forward boundary remains 2026-10-05. The registry contains 18 frozen strategy specifications and 18 independent shadow accounts. Every specification has an immutable fingerprint. A registry mismatch, history conflict, or account hash-chain failure stops the run.

The first automation run restores the committed forward store. Later runs restore the newest non-expired `v10-forward-store` artifact. The workflow uses a concurrency group with cancellation disabled, preventing overlapping daily writers.

## Trading-day behavior

The runner searches only recent official TWSE responses and accepts a date only when the complete daily table and same-date index benchmark are present. On a weekend, holiday, or date whose official data is not complete, it resolves to the latest complete session. If that business date already exists, the immutable manifest is returned unchanged:

- no new targets;
- no fills;
- no synthetic data;
- no forward-day increment.

For a new valid session, pending D-close targets may execute only at that session's actual tradable open. The run then scans the complete eligible universe and records the new close-based targets.

## Observation gates

- Trading days 1–19: `COLLECTING`.
- Trading days 20–59: preliminary observation only, `INSUFFICIENT_EVIDENCE`.
- Trading day 60 onward: qualification evaluation may run.
- Temporary profitability never changes strategy parameters or research promotion state.

Qualification requires positive net and benchmark excess return, Sharpe above 0.5, fixed drawdown compliance, acceptable cost stress, accounting and data integrity, strategy stability, concentration control, and no single-symbol dominance.

## Failure behavior

Market-data integrity failure, accounting reconciliation failure, duplicate risk, fingerprint mismatch, history mutation, or benchmark-date mismatch fails closed. The job exits without trading around the failure. The artifact upload runs even after failure and preserves the forward store plus test and run logs for diagnosis.

## Manual recovery

1. Inspect the failed run logs and downloaded `v10-forward-store` artifact.
2. Correct only the defect that caused the fail-closed result. Never edit existing manifests, account events, the start date, or strategy fingerprints.
3. Rerun the workflow manually with `enable_forward_validation=true`.
4. The run restores the latest store and either returns the existing business date idempotently or appends one new valid trading day.
5. Verify the run manifest, benchmark ledger, all account hash chains, forward-day count, and zero broker orders.

