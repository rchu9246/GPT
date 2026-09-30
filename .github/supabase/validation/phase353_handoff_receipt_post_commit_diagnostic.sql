-- Phase 3.5.3 post-COMMIT live diagnostic.
-- Run this file in one fresh Supabase SQL Editor query.
-- Any unexpected error is rethrown as PHASE353_DIAG_DNN [SQLSTATE] message.
-- No persistent diagnostic table is created.
--
-- Exact recovery before a run or after any failure:
-- delete from public.phase353_handoff_receipts
-- where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
--   and producer_workflow = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW'
--   and producer_run_id in (935302001, 935302003)
--   and producer_run_attempt = 1
--   and consumer = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER';

begin;

create or replace function pg_temp.phase353_diag_assert(p_condition boolean, p_message text)
returns void language plpgsql set search_path = pg_catalog as $function$
begin
  if not coalesce(p_condition, false) then
    raise exception 'PHASE353_DIAGNOSTIC_ASSERTION_FAILED: %', p_message;
  end if;
end;
$function$;

delete from public.phase353_handoff_receipts
where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
  and producer_workflow = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW'
  and producer_run_id in (935302001, 935302003)
  and producer_run_attempt = 1
  and consumer = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER';

create temporary table phase353_diagnostic_results (
  check_name text primary key,
  result text not null,
  receipt_id bigint,
  receipt_status text
) on commit preserve rows;
grant select, insert on pg_temp.phase353_diagnostic_results to service_role;

set local role service_role;
insert into pg_temp.phase353_diagnostic_results
select 'first_claim', claim_result, receipt_id, receipt_status
from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302001, 1,
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
  '4111111111111111111111111111111111111111', date '2099-02-01',
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_AUTHORITY'
);
insert into pg_temp.phase353_diagnostic_results
select 'identical_claim', claim_result, receipt_id, receipt_status
from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302001, 1,
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
  '4111111111111111111111111111111111111111', date '2099-02-01',
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_AUTHORITY'
);
insert into pg_temp.phase353_diagnostic_results
select 'dispatch_accepted', transition_result, receipt_id, receipt_status
from public.mark_phase353_handoff_dispatch_accepted(
  (select receipt_id from pg_temp.phase353_diagnostic_results where check_name = 'first_claim'),
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302001, 1,
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
  '4111111111111111111111111111111111111111'
);
insert into pg_temp.phase353_diagnostic_results
select 'dispatch_replay', transition_result, receipt_id, receipt_status
from public.mark_phase353_handoff_dispatch_accepted(
  (select receipt_id from pg_temp.phase353_diagnostic_results where check_name = 'first_claim'),
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302001, 1,
  'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
  '4111111111111111111111111111111111111111'
);
reset role;

commit;

begin;
create or replace function pg_temp.phase353_diag_assert(p_condition boolean, p_message text)
returns void language plpgsql set search_path = pg_catalog as $function$
begin
  if not coalesce(p_condition, false) then
    raise exception 'PHASE353_DIAGNOSTIC_ASSERTION_FAILED: %', p_message;
  end if;
end;
$function$;

-- D01: temporary collector across the first COMMIT.
do $checkpoint$
begin
  perform pg_temp.phase353_diag_assert(
    to_regclass('pg_temp.phase353_diagnostic_results') is not null
    and (select count(*) = 4 from pg_temp.phase353_diagnostic_results),
    'collector missing or wrong row count');
exception when others then
  raise exception 'PHASE353_DIAG_D01_COLLECTOR [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D02: transaction-local marker isolation.
do $checkpoint$
begin
  perform pg_temp.phase353_diag_assert(
    coalesce(current_setting('app.phase353_handoff_transition', true), '') = '',
    'transition marker leaked');
exception when others then
  raise exception 'PHASE353_DIAG_D02_MARKER_ISOLATION [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D03: direct DISPATCH_ACCEPTED -> COMPLETED rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set status = 'COMPLETED'
    where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
      and producer_run_id = 935302001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_diag_assert(v_rejected, 'COMPLETED update was allowed');
exception when others then
  raise exception 'PHASE353_DIAG_D03_COMPLETED_REJECTION [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D04: reverse status transition rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set status = 'CLAIMED'
    where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
      and producer_run_id = 935302001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_diag_assert(v_rejected, 'reverse status update was allowed');
exception when others then
  raise exception 'PHASE353_DIAG_D04_REVERSE_STATUS [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D05: direct last_error update rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts
    set last_error = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_DIRECT_ERROR'
    where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
      and producer_run_id = 935302001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_diag_assert(v_rejected, 'direct last_error update was allowed');
exception when others then
  raise exception 'PHASE353_DIAG_D05_LAST_ERROR [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D06: immutable producer identity rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set producer_sha = repeat('5', 40)
    where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
      and producer_run_id = 935302001;
  exception when integrity_constraint_violation then v_rejected := true;
  end;
  perform pg_temp.phase353_diag_assert(v_rejected, 'producer SHA update was allowed');
exception when others then
  raise exception 'PHASE353_DIAG_D06_IMMUTABLE_IDENTITY [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D07: actual anon RPC denial.
set local role anon;
do $checkpoint$
declare v_denied boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302003, 1,
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
      '4333333333333333333333333333333333333333', null, null);
  exception when insufficient_privilege then v_denied := true;
  end;
  if not v_denied then
    raise exception 'anon executed mutation RPC';
  end if;
exception when others then
  raise exception 'PHASE353_DIAG_D07_ANON_DENIAL [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;
reset role;

-- D08: actual authenticated RPC denial.
set local role authenticated;
do $checkpoint$
declare v_denied boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302003, 1,
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
      '4333333333333333333333333333333333333333', null, null);
  exception when insufficient_privilege then v_denied := true;
  end;
  if not v_denied then
    raise exception 'authenticated executed mutation RPC';
  end if;
exception when others then
  raise exception 'PHASE353_DIAG_D08_AUTHENTICATED_DENIAL [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;
reset role;

-- D09: service_role CLAIMED -> FAILED.
set local role service_role;
do $checkpoint$
declare v_claim record; v_failed record;
begin
  select * into strict v_claim from public.claim_phase353_handoff(
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302003, 1,
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
    '4333333333333333333333333333333333333333', null, null);
  perform pg_temp.phase353_diag_assert(v_claim.claim_result = 'CLAIM_ACQUIRED', 'service claim failed');
  select * into strict v_failed from public.mark_phase353_handoff_failed(
    v_claim.receipt_id, 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302003, 1,
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
    '4333333333333333333333333333333333333333', 'CLAIMED',
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CLAIM_FAILURE');
  perform pg_temp.phase353_diag_assert(
    v_failed.transition_result = 'FAILED' and v_failed.receipt_status = 'FAILED',
    'CLAIMED to FAILED failed');
exception when others then
  raise exception 'PHASE353_DIAG_D09_CLAIMED_FAILED [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;
reset role;

-- D10: service_role DISPATCH_ACCEPTED -> FAILED.
set local role service_role;
do $checkpoint$
declare v_failed record;
begin
  select * into strict v_failed from public.mark_phase353_handoff_failed(
    (select id from public.phase353_handoff_receipts
     where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
       and producer_run_id = 935302001),
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302001, 1,
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
    '4111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_DISPATCH_FAILURE');
  perform pg_temp.phase353_diag_assert(
    v_failed.transition_result = 'FAILED' and v_failed.receipt_status = 'FAILED',
    'DISPATCH_ACCEPTED to FAILED failed');
exception when others then
  raise exception 'PHASE353_DIAG_D10_ACCEPTED_FAILED [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;
reset role;

-- D11: identical FAILED replay.
set local role service_role;
do $checkpoint$
declare v_replay record;
begin
  select * into strict v_replay from public.mark_phase353_handoff_failed(
    (select id from public.phase353_handoff_receipts
     where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
       and producer_run_id = 935302001),
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302001, 1,
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
    '4111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
    'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_DISPATCH_FAILURE');
  perform pg_temp.phase353_diag_assert(
    v_replay.transition_result = 'ALREADY_FAILED' and v_replay.receipt_status = 'FAILED',
    'identical failure replay was not idempotent');
exception when others then
  raise exception 'PHASE353_DIAG_D11_FAILURE_REPLAY [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;
reset role;

-- D12: conflicting FAILED replay rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    perform public.mark_phase353_handoff_failed(
      (select id from public.phase353_handoff_receipts
       where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
         and producer_run_id = 935302001),
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY',
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW', 935302001, 1,
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER',
      '4111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
      'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONFLICTING_FAILURE');
  exception when integrity_constraint_violation then v_rejected := true;
  end;
  perform pg_temp.phase353_diag_assert(v_rejected, 'conflicting failure replay was allowed');
exception when others then
  raise exception 'PHASE353_DIAG_D12_CONFLICTING_REPLAY [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D13: FAILED terminal state.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set status = 'CLAIMED'
    where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
      and producer_run_id = 935302001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_diag_assert(v_rejected, 'FAILED was not terminal');
exception when others then
  raise exception 'PHASE353_DIAG_D13_FAILED_TERMINAL [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D14: exact cleanup.
do $checkpoint$
begin
  delete from public.phase353_handoff_receipts
  where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
    and producer_workflow = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW'
    and producer_run_id in (935302001, 935302003)
    and producer_run_attempt = 1
    and consumer = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER';
  perform pg_temp.phase353_diag_assert(
    not exists (
      select 1 from public.phase353_handoff_receipts
      where repository = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_REPOSITORY'
        and producer_workflow = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_WORKFLOW'
        and producer_run_id in (935302001, 935302003)
        and producer_run_attempt = 1
        and consumer = 'VALIDATION_ONLY_PHASE353_DIAGNOSTIC_CONSUMER'),
    'exact cleanup left validation rows');
exception when others then
  raise exception 'PHASE353_DIAG_D14_CLEANUP [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

commit;

select 'PHASE353_POST_COMMIT_DIAGNOSTIC_PASS' as diagnostic_result;
