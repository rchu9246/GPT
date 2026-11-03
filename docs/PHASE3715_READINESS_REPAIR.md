# Phase 3.7.15 readiness synchronization repair

## Observed evidence (2026-11-03 UTC)

- Phase 3.7.14 run 41549775681, commit e87c21c5727d311a33a80b20f99a376ccaaa8098: workflow success means operational waiting, NOT promotion. Captured 00:01:31: canonical 52 valid distinct dates, readiness 52, promotion false, qualification_state MULTI_CYCLE_STABILITY_OBSERVING. Canonical threshold passed; promotion_finalized and activation_ready were false.
- Phase 3.7.15 run 41549970626, same commit: captured 00:03:02: canonical 53 valid distinct dates, readiness 52, promotion false. Sole blocker READINESS_COUNTERS_DIVERGE_FROM_CANONICAL_LEDGER. All recorded broker, real-money and historical-rewrite locks passed. Original artifact files remain local and are excluded from the public PR; only the incident counters needed to explain this repair are summarized here.

## Root cause and change

Phase 3.7.9 reconciled ledger counts but still required old Phase 3.7.5/3.7.6 artifacts for qualification and authorization. Its workflow selected successful runs (which may be OBSERVING), not a fresh qualification chain. Phase 3.7.5 counted a separate daily-evidence source, not the persisted cross-run qualification ledger. Independently scheduled writers could advance the ledger after readiness was captured.

Use the scoped persisted ledger for Phase 3.7.5 cycle counts, with pagination, explicit boolean safety fields, distinct non-future dates, and no writes to qualification or transaction history. Keep live activation, master-cycle, runtime and unsafe daily-source checks mandatory. Recompute 375 -> 376 -> 379 in the 379/3714/3715 job, use local output paths, and serialize readiness writers. Any intervening ledger change still blocks; no counter mismatch is waived. Readiness synchronization writes only the existing readiness projection through its existing upsert API.

Fail closed for missing readiness and missing/ambiguous safety locks. A validation-only 3715 result cannot assert runtime execution. No order or broker execution path is added.

## Validation and deployment boundary

12 isolated unittest regressions passed locally, including the 52/53 incident, duplicate/malformed safety evidence, failed current runtime, missing or enabled locks, fresh promotion chain, and a concurrent ledger change. Fixtures and mocks are test inputs only and never reach Supabase. Secret-free PR CI repeats the regression suite on Python 3.12.

Production eligibility remains UNVERIFIED after this patch until the PR is reviewed/merged and the existing secret-bearing workflow executes against current control data. No production secrets were requested or read locally. Do not rerun the old main workflow and call it validation of this branch.

## Alert review

- KEEP: 3715 counter divergence and all current safety-lock / blocked-cycle / runtime failures. The observed failed run is a real safe rejection, not a dispensable alert.
- CORRECT: 3715 Runtime Active could previously become true solely from validation. It now stays false and exposes validation_only / runtime_execution_observed.
- REPLACE: historical successful 375/376 artifact lookup in 379; it can select OBSERVING outputs and hide newer failed runs. Current evaluation now replaces that lookup.
- INFORMATIONAL: the failed job logs contain Node 20 action-runtime deprecation warnings. They did not cause this incident. No platform-wide notification preference or security alert is suppressed.
- No historical Actions runs, trade records, safety alerts, or workflow schedules were deleted. No other old failure was present in the inspected 50 most recent runs. Wider historical-alert retirement requires provenance and replacement coverage; it is not safe to disable versioned safety workflows merely by age.

## Trading status

The incident artifacts explicitly report runtime_active=false and first_live_paper_session_ready=false. This repair neither starts paper trading nor proves that another independent workflow has never traded. Actual execution requires runtime/session/order evidence; eligibility is not execution. Real-money trading remains disabled.
