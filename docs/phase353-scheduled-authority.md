# Scheduled canonical authority ownership

The Phase 3.5.3 weekday cron is the only scheduled producer requester. Its first
attempt dispatches the dedicated Phase 3.4.8.4.5.1 with `handoff_consumer=355`.
No producer runs are selected or listed. Rerunning that scheduled requester fails
closed rather than requesting another producer. An ambiguous dispatch response
requires investigation; there is no automatic retry or replacement authority.

The successful producer completion event supplies its exact run ID and attempt.
The handler checks repository, workflow, main branch, success, attempt-specific
artifact, producer SHA and artifact digest, then dispatches 355 with that tuple:

    353 cron -> dedicated producer -> validated completion -> 355 entrypoint
                                                            -> 354 entrypoint
                                                               -> 353 sizing
                                                            <- 354 execution
                                                         <- 355 settlement

The existing subprocesses inherit one tuple. No 354/355 trading Python changes.
All three cron strings and schedules remain enabled. Later 354/355 cron jobs
actively check ownership wiring, failing for a missing owner or another scheduled
producer requester. They do not discover runs, dispatch work, or assert business
cycle success. Execution is completion-bound and may precede the later ticks;
those times are not execution barriers. Inspect producer/consumer results for
cycle success, not the ownership-check result.

## Current completion delivery and durable receipt foundation

The live producer completion trigger remains broken for producers dispatched by
the repository `GITHUB_TOKEN`: those producer runs do not create the expected
`workflow_run` handler run. The existing handler is unchanged and no replacement
completion path is active.

Migration `015_phase353_handoff_receipts.sql` provides a dormant durable receipt
foundation. It atomically claims repository, producer workflow, run ID, attempt,
and consumer with immutable producer SHA and optional authority hash/business
date. Receipt states distinguish `CLAIMED`, `DISPATCH_ACCEPTED`, `COMPLETED`, and
`FAILED`. Dispatch HTTP 204 can mean only `DISPATCH_ACCEPTED`.

The migration is not applied and no production workflow calls its RPCs or Python
adapter. The current live chain therefore has neither reliable completion
delivery nor an integrated exactly-once claim. Completion replay or handler rerun
can still dispatch the same tuple. Concurrency remains execution serialization,
not persistent deduplication or guaranteed delivery.

The future target sequence is:

    producer completion
    -> exact authority validation
    -> atomic receipt claim
    -> dispatch accepted
    -> downstream completion evidence
    -> receipt completed

Only the service role may claim or transition a receipt. A failed dispatch may
leave `CLAIMED` with diagnostic `last_error`; automatic redispatch is prohibited.
A later reconciliation design must decide whether and how that claim can be
retried. `COMPLETED` must require explicit downstream evidence identity and is
not implemented by the dormant adapter.

An identical complete sizing plan returns existing header/items without inserts.
Tests route two completion deliveries through actual 355/354 subprocess environment
construction and full 353 main using a shared mock DB with fractional Decimal
values. They prove one authority, one plan ID, and one header/items insert sequence.
They do not claim live end-to-end settlement or atomic settlement writes.

Changed governance, ledger, positions or other sizing inputs remain fail closed.
Settlement can change those inputs: the same authority alone does not promise
successful re-execution of the whole business cycle. No repair, replacement
authority, historical rewrite or fallback is introduced.

| Invocation | Behavior |
| --- | --- |
| Normal schedule | One producer request for the complete cycle |
| Manual consumer | Explicit valid producer tuple required |
| Producer rerun | Same run ID, new attempt; distinct authority validated exactly |
| New manual producer | New run ID; distinct authority |
| Different authority with existing same-date plan | SAME_DAY_PLAN_AUTHORITY_CONFLICT remains |
| Completion-handler rerun | May redeliver the same tuple; never requests a producer |
| Downstream retry | Identical complete plan is idempotent; changed/incomplete content fails closed |
| Manual producer, target none | No dispatch after valid authority; missing authority still fails closed |

Incomplete historical plans block their own portfolio/plan date. A future plan
date is not selected by that query; ledger/authority date checks still apply.
No schema, history, qualifications, safety flags or trading calculations change.

