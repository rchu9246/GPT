# Phase 3.6.9 evidence date review

Review date: 2026-11-13 (Asia/Taipei). Base: e87c21c5727d311a33a80b20f99a376ccaaa8098.

## Priority finding: stale controller evidence, not a timezone correction

[Phase 3.6.9 run 43302165496](https://github.com/rchu9246/GPT/actions/runs/43302165496), job 131475889204, failed with `Latest controller date mismatch: expected=2026-11-12, actual=2026-09-11`. Its date check correctly stopped before lifecycle upsert/audit writes. A roughly two-month gap cannot be explained by UTC versus Taipei rollover. Do not substitute the old controller date or manufacture today's controller evidence.

The current Phase 3.6.9 workflow comment assumes a scheduled Phase 3.6.8 run at 12:45 UTC. The current Phase 3.6.8 workflow has only workflow_dispatch and requires exact producer_run_id and producer_run_attempt inputs. Its latest listed run was [34623848264](https://github.com/rchu9246/GPT/actions/runs/34623848264), job 103344053484, on September 11. The log reported FAIL_CLOSED, PRECHECK_BLOCKED, SUPERVISION_NOT_CONTINUABLE, AUTONOMOUS_CONTINUATION_NOT_AUTHORIZED, and SAFETY_REVOCATION_ALREADY_TRIGGERED. This supports a stopped upstream controller as the immediate reason no fresh evidence is available; it does not establish why supervision/revocation originally changed.

Runtime recovery is stopped: no new human authorization or exact producer run/attempt was supplied for recovery. Do not dispatch/re-run the controller, restore scheduling, revoke a safety lock, or rewrite history under this review.

## Minimal code correction

Phase 3.6.9 already validates controller_date, but independently reads the latest master cycle without checking cycle_date. A fresh controller could therefore be combined with a stale/future master cycle in a new evidence document. Require a present master cycle with the exact requested evidence date before any lifecycle writes. Preserve the existing controller-date rejection, evaluation rules, evidence chain, and safety flags. This correction closes a related consistency gap; it does **not** resolve the observed stale upstream controller or make production runs pass.

## Phase 3.4.3

[Production evidence run 43271383722](https://github.com/rchu9246/GPT/actions/runs/43271383722), job 131368517164, failed because readiness validation returned `release_not_locked_before_human_approval`. The Phase 3.4 producer intentionally emits AWAITING_HUMAN_APPROVAL when qualification is complete, while Phase 3.4.3 validate_source requires LOCKED. The log reported 60 consecutive pass days and market_stale_days=1. This is a producer/consumer state contract disagreement, not evidence that human approval exists. No readiness/release/Promotion gate is changed in this PR. A follow-up contract decision requires separately authorized scope.

## Phase 3.7.11.1

[Run 43318453703](https://github.com/rchu9246/GPT/actions/runs/43318453703), job 131532509515, captured a baseline of 60 observed/valid/distinct dates and 0 blocked, latest date 2026-11-12. It then dispatched [Phase 3.7.10 run 43318472710](https://github.com/rchu9246/GPT/actions/runs/43318472710), which failed in its ordered daily evidence pipeline. Waiting-state validation was skipped; the final enforcement step correctly blocked the wrapper. This run does not prove a rollover-guard defect. The wrapper can dispatch a pipeline containing automatic promotion transition; it was not re-run during this review. No threshold or Promotion logic changed.

## Validation and limits

`python -m unittest discover -s tests/v92 -p test_phase369_evidence_dates.py -v`: 8 tests passed. Tests use mocked database calls and temporary artifacts. Coverage includes the observed stale controller, missing controller/master, stale/future/missing master date, same-date source hash/safety flags, missing authorization, the existing Phase 3.4.3 block, and Phase 3.7.11.1 same-day counter inflation rejection.

No production database access, workflow dispatch, historical transaction/evidence edits, schedule edits, main updates, Promotion changes, or real trading were performed. Evidence above comes from existing GitHub logs and source inspection. Live recovery and validation remain blocked pending the required human authorization and producer provenance.
