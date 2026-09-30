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

The enforced transition graph is:

    CLAIMED -> DISPATCH_ACCEPTED -> FAILED
       |                              (terminal)
       +-----------> FAILED

`COMPLETED` is also terminal but deliberately unreachable: this foundation has no
completion RPC. A future `DISPATCH_ACCEPTED -> COMPLETED` transition must require
the exact receipt identity, consumer run identity, and explicit downstream
evidence identity/hash. Dispatch acceptance alone can never set `COMPLETED`.

A database trigger rejects direct status changes, reverse transitions, terminal
state exits, and direct `last_error` edits. Approved RPCs set a transaction-local
transition marker immediately before their guarded update. Failure requires the
exact immutable receipt identity, caller-expected current status, and a non-empty
diagnostic. An identical failure replay is idempotent; a conflicting replay fails
closed. `last_error` is writable only by that failure RPC and is cleared by a
successful dispatch-acceptance transition.

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

Only the service role may claim or transition a receipt. A failed dispatch is
recorded as terminal `FAILED`; automatic redispatch is prohibited. A later
reconciliation design must explicitly define any retry behavior. `COMPLETED`
requires downstream evidence and is not implemented by the dormant adapter.

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

## Live database validation procedure

The receipt migration and its RPC behavior must be proven in Supabase before any
workflow integration. Use the SQL Editor in this exact order:

Live validation found that the deployed Supabase default privileges had left
`service_role` with direct table mutation privileges even though migration 015
granted only `SELECT`. The database was manually corrected to `SELECT` only.
Migration 015 now explicitly revokes all table privileges from `service_role`
before granting `SELECT`, so fresh and repeated deployments converge on the same
least-privilege state. This source hardening does not reapply the migration.

1. Execute `.github/supabase/migrations/015_phase353_handoff_receipts.sql` once.
2. Confirm the migration transaction commits without error.
3. Execute `.github/supabase/validation/phase353_handoff_receipt_live_validation.sql`
   in full. Its final row must be `PHASE353_HANDOFF_RECEIPT_LIVE_VALIDATION_PASS`.
4. Open two independent SQL Editor sessions and run the concurrency steps below.
5. Record results without copying database credentials into logs or artifacts.

If the validation script stops after its first commit, run this exact recovery:

```sql
delete from public.phase353_handoff_receipts
where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
  and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
  and producer_run_id in (935300001, 935300002, 935300003)
  and producer_run_attempt = 1
  and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';
```

### Controlled two-session concurrency validation

First run the exact recovery statement above. In session A, run:

```sql
begin;
select * from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
  935300002, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
  '2222222222222222222222222222222222222222', null, null
);
select pg_sleep(20);
commit;
```

Immediately after session A returns `CLAIM_ACQUIRED` and begins sleeping, run in
session B:

```sql
select * from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
  935300002, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
  '2222222222222222222222222222222222222222', null, null
);
```

Session B must wait for session A and then return `ALREADY_CLAIMED`. Verify and
clean up with:

```sql
select count(*) as exact_row_count
from public.phase353_handoff_receipts
where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
  and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
  and producer_run_id = 935300002
  and producer_run_attempt = 1
  and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';

delete from public.phase353_handoff_receipts
where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
  and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
  and producer_run_id = 935300002
  and producer_run_attempt = 1
  and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';
```

`exact_row_count` must be `1`. This is a manual live database gate; offline mocks
or sequential calls do not satisfy it. The validation does not activate or call
any production workflow.

### Post-COMMIT diagnostic checkpoints

If the full validation fails after its first commit without a PostgreSQL line or
context, run `.github/supabase/validation/phase353_handoff_receipt_post_commit_diagnostic.sql`
as one fresh SQL Editor query. It recreates all temporary/helper state and uses
only `VALIDATION_ONLY_PHASE353_DIAGNOSTIC_*` receipt identities.

Success returns `PHASE353_POST_COMMIT_DIAGNOSTIC_PASS`. Failure is rethrown as:

    PHASE353_DIAG_DNN_CHECK_NAME [SQLSTATE] original message

The checkpoint ID identifies the exact logical statement block. Before rerunning
after a failure, execute the exact recovery statement in the diagnostic file's
header. No diagnostic table persists outside that SQL Editor session.

For a differential audit covering catalog preflight and post-commit operations
in one request, run `.github/supabase/validation/phase353_handoff_receipt_full_live_diagnostic.sql`.
It uses only `VALIDATION_ONLY_PHASE353_LIVE_DIAG_*` identities. Success returns
`PHASE353_FULL_LIVE_DIAGNOSTIC_PASS`; failures begin with
`PHASE353_LIVE_DIAG_LNN_CHECK_NAME` and preserve SQLSTATE and the original error.
