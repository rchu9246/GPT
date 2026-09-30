-- Phase 3.5.3 durable handoff receipt live validation.
-- Run only after 015_phase353_handoff_receipts.sql succeeds, in one fresh Supabase SQL Editor query.
-- Any unexpected error is rethrown as PHASE353_LIVE_VALIDATION_LNN [SQLSTATE] message.
-- No persistent validation table is created.
--
-- Exact recovery before a run or after any failure:
-- delete from public.phase353_handoff_receipts
-- where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
--   and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
--   and producer_run_id in (935300001, 935300002, 935300003)
--   and producer_run_attempt = 1
--   and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';

begin;

create or replace function pg_temp.phase353_assert(p_condition boolean, p_message text)
returns void language plpgsql set search_path = pg_catalog as $function$
begin
  if not coalesce(p_condition, false) then
    raise exception 'PHASE353_LIVE_VALIDATION_FAILED: %', p_message;
  end if;
end;
$function$;

-- L01-L08 reproduce every catalog preflight unique to the failing live file.
do $checkpoint$
begin
  perform pg_temp.phase353_assert(to_regclass('public.phase353_handoff_receipts') is not null, 'table missing');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L01_TABLE [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
begin
  perform pg_temp.phase353_assert(not exists (
    select 1 from unnest(array['repository','producer_workflow','producer_run_id',
      'producer_run_attempt','consumer','producer_sha','business_date','authority_hash',
      'status','claimed_at','dispatched_at','consumer_run_id','last_error','created_at','updated_at']) required(column_name)
    where not exists (select 1 from information_schema.columns actual
      where actual.table_schema='public' and actual.table_name='phase353_handoff_receipts'
        and actual.column_name=required.column_name)), 'columns missing');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L02_COLUMNS [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
begin
  perform pg_temp.phase353_assert(exists (select 1 from pg_catalog.pg_constraint c
    join pg_catalog.pg_class t on t.oid=c.conrelid join pg_catalog.pg_namespace n on n.oid=t.relnamespace
    where n.nspname='public' and t.relname='phase353_handoff_receipts'
      and c.conname='phase353_handoff_receipts_identity_key' and c.contype='u'), 'constraint missing');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L03_UNIQUE_CONSTRAINT [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
begin
  perform pg_temp.phase353_assert((select c.relrowsecurity from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relname='phase353_handoff_receipts'), 'RLS disabled');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L04_RLS [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
begin
  perform pg_temp.phase353_assert(
    to_regprocedure('public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)') is not null
    and to_regprocedure('public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)') is not null
    and to_regprocedure('public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)') is not null,
    'RPC missing');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L05_RPC_EXISTENCE [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
begin
  perform pg_temp.phase353_assert(not exists (select 1 from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid=p.pronamespace where n.nspname='public'
      and p.proname like '%phase353%handoff%complet%'), 'completion RPC exists');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L06_COMPLETION_RPC [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
begin
  perform pg_temp.phase353_assert(
    not has_function_privilege('anon','public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)','EXECUTE')
    and not has_function_privilege('authenticated','public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)','EXECUTE')
    and not has_function_privilege('anon','public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)','EXECUTE')
    and not has_function_privilege('authenticated','public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)','EXECUTE')
    and not has_function_privilege('anon','public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)','EXECUTE')
    and not has_function_privilege('authenticated','public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)','EXECUTE'),
    'untrusted function privilege exists');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L07_UNTRUSTED_PRIVILEGES [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
begin
  perform pg_temp.phase353_assert(
    has_function_privilege('service_role','public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)','EXECUTE')
    and has_function_privilege('service_role','public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)','EXECUTE')
    and has_function_privilege('service_role','public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)','EXECUTE')
    and not has_table_privilege('service_role','public.phase353_handoff_receipts','UPDATE'),
    'service role privilege mismatch');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L08_SERVICE_PRIVILEGES [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

delete from public.phase353_handoff_receipts
where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
  and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
  and producer_run_id in (935300001, 935300002, 935300003)
  and producer_run_attempt = 1
  and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';

create temporary table phase353_validation_results (
  check_name text primary key,
  result text not null,
  receipt_id bigint,
  receipt_status text
) on commit preserve rows;
grant select, insert on pg_temp.phase353_validation_results to service_role;

set local role service_role;
insert into pg_temp.phase353_validation_results
select 'first_claim', claim_result, receipt_id, receipt_status
from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300001, 1,
  'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111', date '2099-01-01',
  'VALIDATION_ONLY_PHASE353_AUTHORITY_HASH'
);
insert into pg_temp.phase353_validation_results
select 'identical_replay', claim_result, receipt_id, receipt_status
from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300001, 1,
  'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111', date '2099-01-01',
  'VALIDATION_ONLY_PHASE353_AUTHORITY_HASH'
);
reset role;

-- Preserve the original claim/replay assertions before any state transition.
do $checkpoint$
begin
  perform pg_temp.phase353_assert(
    exists (select 1 from pg_temp.phase353_validation_results
      where check_name='first_claim' and result='CLAIM_ACQUIRED' and receipt_status='CLAIMED'),
    'first claim did not return CLAIM_ACQUIRED/CLAIMED');
  perform pg_temp.phase353_assert(
    exists (select 1 from pg_temp.phase353_validation_results
      where check_name='identical_replay' and result='ALREADY_CLAIMED' and receipt_status='CLAIMED'),
    'identical replay did not return ALREADY_CLAIMED/CLAIMED');
  perform pg_temp.phase353_assert(
    (select count(*)=1 from public.phase353_handoff_receipts
      where repository='VALIDATION_ONLY_PHASE353_REPOSITORY'
        and producer_workflow='VALIDATION_ONLY_PHASE353_WORKFLOW'
        and producer_run_id=935300001 and producer_run_attempt=1
        and consumer='VALIDATION_ONLY_PHASE353_CONSUMER'),
    'identical replay created more than one row');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L09_CLAIM_REPLAY [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY','VALIDATION_ONLY_PHASE353_WORKFLOW',935300001,1,
      'VALIDATION_ONLY_PHASE353_CONSUMER','2222222222222222222222222222222222222222',
      date '2099-01-01','VALIDATION_ONLY_PHASE353_AUTHORITY_HASH');
  exception when integrity_constraint_violation then
    v_rejected := sqlerrm like '%IMMUTABLE_IDENTITY_CONFLICT%';
  end;
  perform pg_temp.phase353_assert(v_rejected, 'conflicting producer SHA did not fail closed');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L10_SHA_CONFLICT [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY','VALIDATION_ONLY_PHASE353_WORKFLOW',935300001,1,
      'VALIDATION_ONLY_PHASE353_CONSUMER','1111111111111111111111111111111111111111',
      date '2099-01-01','VALIDATION_ONLY_PHASE353_CONFLICTING_HASH');
  exception when integrity_constraint_violation then
    v_rejected := sqlerrm like '%IMMUTABLE_IDENTITY_CONFLICT%';
  end;
  perform pg_temp.phase353_assert(v_rejected, 'conflicting authority hash did not fail closed');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L11_AUTHORITY_CONFLICT [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY','VALIDATION_ONLY_PHASE353_WORKFLOW',935300001,1,
      'VALIDATION_ONLY_PHASE353_CONSUMER','1111111111111111111111111111111111111111',
      date '2099-01-02','VALIDATION_ONLY_PHASE353_AUTHORITY_HASH');
  exception when integrity_constraint_violation then
    v_rejected := sqlerrm like '%IMMUTABLE_IDENTITY_CONFLICT%';
  end;
  perform pg_temp.phase353_assert(v_rejected, 'conflicting business date did not fail closed');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L12_DATE_CONFLICT [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

set local role service_role;
insert into pg_temp.phase353_validation_results
select 'dispatch_accepted', transition_result, receipt_id, receipt_status
from public.mark_phase353_handoff_dispatch_accepted(
  (select receipt_id from pg_temp.phase353_validation_results where check_name = 'first_claim'),
  'VALIDATION_ONLY_PHASE353_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300001, 1,
  'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111'
);
insert into pg_temp.phase353_validation_results
select 'dispatch_replay', transition_result, receipt_id, receipt_status
from public.mark_phase353_handoff_dispatch_accepted(
  (select receipt_id from pg_temp.phase353_validation_results where check_name = 'first_claim'),
  'VALIDATION_ONLY_PHASE353_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300001, 1,
  'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111'
);
reset role;

do $checkpoint$
begin
  perform pg_temp.phase353_assert(
    exists (select 1 from pg_temp.phase353_validation_results
      where check_name='dispatch_accepted' and result='DISPATCH_ACCEPTED'
        and receipt_status='DISPATCH_ACCEPTED'),
    'CLAIMED to DISPATCH_ACCEPTED failed');
  perform pg_temp.phase353_assert(
    exists (select 1 from pg_temp.phase353_validation_results
      where check_name='dispatch_replay' and result='ALREADY_DISPATCH_ACCEPTED'
        and receipt_status='DISPATCH_ACCEPTED'),
    'dispatch acceptance replay was not idempotent');
  perform pg_temp.phase353_assert(
    exists (select 1 from public.phase353_handoff_receipts
      where id=(select receipt_id from pg_temp.phase353_validation_results where check_name='first_claim')
        and status='DISPATCH_ACCEPTED' and status<>'COMPLETED'),
    'HTTP acceptance state was not preserved as DISPATCH_ACCEPTED');
exception when others then raise exception 'PHASE353_LIVE_VALIDATION_L13_DISPATCH_ACCEPTANCE [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

commit;

begin;
create or replace function pg_temp.phase353_assert(p_condition boolean, p_message text)
returns void language plpgsql set search_path = pg_catalog as $function$
begin
  if not coalesce(p_condition, false) then
    raise exception 'PHASE353_LIVE_VALIDATION_FAILED: %', p_message;
  end if;
end;
$function$;

-- D01: temporary collector across the first COMMIT.
do $checkpoint$
begin
  perform pg_temp.phase353_assert(
    to_regclass('pg_temp.phase353_validation_results') is not null
    and (select count(*) = 4 from pg_temp.phase353_validation_results),
    'temporary result collector did not survive the validation transaction boundary');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L17_COLLECTOR [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D02: transaction-local marker isolation.
do $checkpoint$
begin
  perform pg_temp.phase353_assert(
    coalesce(current_setting('app.phase353_handoff_transition', true), '') = '',
    'transition marker leaked');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L18_MARKER_ISOLATION [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D03: direct DISPATCH_ACCEPTED -> COMPLETED rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set status = 'COMPLETED'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'COMPLETED update was allowed');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L19_COMPLETED_REJECTION [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D04: reverse status transition rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set status = 'CLAIMED'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'reverse status update was allowed');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L20_REVERSE_STATUS [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D05: direct last_error update rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts
    set last_error = 'VALIDATION_ONLY_DIRECT_ERROR'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'direct last_error update was allowed');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L21_LAST_ERROR [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D06: immutable producer identity rejection.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set producer_sha = repeat('3', 40)
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when integrity_constraint_violation then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'producer SHA update was allowed');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L22_IMMUTABLE_IDENTITY [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D07: actual anon RPC denial.
set local role anon;
do $checkpoint$
declare v_denied boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY',
      'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300003, 1,
      'VALIDATION_ONLY_PHASE353_CONSUMER',
      '3333333333333333333333333333333333333333', null, null);
  exception when insufficient_privilege then v_denied := true;
  end;
  if not v_denied then
    raise exception 'anon executed mutation RPC';
  end if;
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L23_ANON_DENIAL [%] %', sqlstate, sqlerrm;
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
      'VALIDATION_ONLY_PHASE353_REPOSITORY',
      'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300003, 1,
      'VALIDATION_ONLY_PHASE353_CONSUMER',
      '3333333333333333333333333333333333333333', null, null);
  exception when insufficient_privilege then v_denied := true;
  end;
  if not v_denied then
    raise exception 'authenticated executed mutation RPC';
  end if;
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L24_AUTHENTICATED_DENIAL [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;
reset role;

-- D09: service_role CLAIMED -> FAILED.
set local role service_role;
do $checkpoint$
declare v_claim record; v_failed record;
begin
  select * into strict v_claim from public.claim_phase353_handoff(
    'VALIDATION_ONLY_PHASE353_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300003, 1,
    'VALIDATION_ONLY_PHASE353_CONSUMER',
    '3333333333333333333333333333333333333333', null, null);
  perform pg_temp.phase353_assert(v_claim.claim_result = 'CLAIM_ACQUIRED', 'service claim failed');
  select * into strict v_failed from public.mark_phase353_handoff_failed(
    v_claim.receipt_id, 'VALIDATION_ONLY_PHASE353_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300003, 1,
    'VALIDATION_ONLY_PHASE353_CONSUMER',
    '3333333333333333333333333333333333333333', 'CLAIMED',
    'VALIDATION_ONLY_PHASE353_CLAIM_FAILURE');
  perform pg_temp.phase353_assert(
    v_failed.transition_result = 'FAILED' and v_failed.receipt_status = 'FAILED',
    'CLAIMED to FAILED failed');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L25_CLAIMED_FAILED [%] %', sqlstate, sqlerrm;
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
     where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
       and producer_run_id = 935300001),
    'VALIDATION_ONLY_PHASE353_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300001, 1,
    'VALIDATION_ONLY_PHASE353_CONSUMER',
    '1111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
    'VALIDATION_ONLY_PHASE353_DISPATCH_FAILURE');
  perform pg_temp.phase353_assert(
    v_failed.transition_result = 'FAILED' and v_failed.receipt_status = 'FAILED',
    'DISPATCH_ACCEPTED to FAILED failed');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L26_ACCEPTED_FAILED [%] %', sqlstate, sqlerrm;
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
     where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
       and producer_run_id = 935300001),
    'VALIDATION_ONLY_PHASE353_REPOSITORY',
    'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300001, 1,
    'VALIDATION_ONLY_PHASE353_CONSUMER',
    '1111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
    'VALIDATION_ONLY_PHASE353_DISPATCH_FAILURE');
  perform pg_temp.phase353_assert(
    v_replay.transition_result = 'ALREADY_FAILED' and v_replay.receipt_status = 'FAILED',
    'identical failure replay was not idempotent');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L27_FAILURE_REPLAY [%] %', sqlstate, sqlerrm;
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
       where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
         and producer_run_id = 935300001),
      'VALIDATION_ONLY_PHASE353_REPOSITORY',
      'VALIDATION_ONLY_PHASE353_WORKFLOW', 935300001, 1,
      'VALIDATION_ONLY_PHASE353_CONSUMER',
      '1111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
      'VALIDATION_ONLY_PHASE353_CONFLICTING_FAILURE');
  exception when integrity_constraint_violation then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'conflicting failure replay was allowed');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L28_CONFLICTING_REPLAY [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D13: FAILED terminal state.
do $checkpoint$
declare v_rejected boolean := false;
begin
  begin
    update public.phase353_handoff_receipts set status = 'CLAIMED'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'FAILED was not terminal');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L29_FAILED_TERMINAL [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

-- D14: exact cleanup.
do $checkpoint$
begin
  delete from public.phase353_handoff_receipts
  where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
    and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
    and producer_run_id in (935300001, 935300002, 935300003)
    and producer_run_attempt = 1
    and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';
  perform pg_temp.phase353_assert(
    not exists (
      select 1 from public.phase353_handoff_receipts
      where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
        and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
        and producer_run_id in (935300001, 935300002, 935300003)
        and producer_run_attempt = 1
        and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER'),
    'exact cleanup left validation rows');
exception when others then
  raise exception 'PHASE353_LIVE_VALIDATION_L30_CLEANUP [%] %', sqlstate, sqlerrm;
end;
$checkpoint$;

commit;

select 'PHASE353_HANDOFF_RECEIPT_LIVE_VALIDATION_PASS' as validation_result;

