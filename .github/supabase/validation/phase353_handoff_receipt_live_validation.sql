-- Phase 3.5.3 durable handoff receipt live validation.
-- Run only after 015_phase353_handoff_receipts.sql succeeds.
-- All persistent rows use the exact validation repository below and are deleted.
-- This script never calls a trading workflow or touches a financial table.
--
-- Exact recovery SQL if execution stops before cleanup:
-- delete from public.phase353_handoff_receipts
-- where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
--   and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
--   and producer_run_id in (935300001, 935300002, 935300003)
--   and producer_run_attempt = 1
--   and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';

begin;

create or replace function pg_temp.phase353_assert(p_condition boolean, p_message text)
returns void
language plpgsql
set search_path = pg_catalog
as $function$
begin
  if not coalesce(p_condition, false) then
    raise exception 'PHASE353_LIVE_VALIDATION_FAILED: %', p_message;
  end if;
end;
$function$;

select pg_temp.phase353_assert(
  to_regclass('public.phase353_handoff_receipts') is not null,
  'receipt table is missing'
);

select pg_temp.phase353_assert(
  not exists (
    select 1
    from unnest(array[
      'repository', 'producer_workflow', 'producer_run_id', 'producer_run_attempt',
      'consumer', 'producer_sha', 'business_date', 'authority_hash', 'status',
      'claimed_at', 'dispatched_at', 'consumer_run_id', 'last_error', 'created_at',
      'updated_at'
    ]) required(column_name)
    where not exists (
      select 1 from information_schema.columns actual
      where actual.table_schema = 'public'
        and actual.table_name = 'phase353_handoff_receipts'
        and actual.column_name = required.column_name
    )
  ),
  'one or more required receipt columns are missing'
);

select pg_temp.phase353_assert(
  exists (
    select 1
    from pg_catalog.pg_constraint c
    join pg_catalog.pg_class t on t.oid = c.conrelid
    join pg_catalog.pg_namespace n on n.oid = t.relnamespace
    where n.nspname = 'public'
      and t.relname = 'phase353_handoff_receipts'
      and c.conname = 'phase353_handoff_receipts_identity_key'
      and c.contype = 'u'
  ),
  'unique receipt identity constraint is missing'
);

select pg_temp.phase353_assert(
  (select c.relrowsecurity
   from pg_catalog.pg_class c
   join pg_catalog.pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relname = 'phase353_handoff_receipts'),
  'row level security is not enabled'
);

select pg_temp.phase353_assert(
  to_regprocedure('public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)') is not null
  and to_regprocedure('public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)') is not null
  and to_regprocedure('public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)') is not null,
  'one or more mutation RPCs are missing'
);

select pg_temp.phase353_assert(
  not exists (
    select 1 from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname like '%phase353%handoff%complet%'
  ),
  'a completion transition RPC unexpectedly exists'
);

select pg_temp.phase353_assert(
  not has_function_privilege('anon', 'public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)', 'EXECUTE')
  and not has_function_privilege('authenticated', 'public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)', 'EXECUTE')
  and not has_function_privilege('anon', 'public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)', 'EXECUTE')
  and not has_function_privilege('authenticated', 'public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)', 'EXECUTE')
  and not has_function_privilege('anon', 'public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)', 'EXECUTE')
  and not has_function_privilege('authenticated', 'public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)', 'EXECUTE'),
  'anon/authenticated has mutation RPC execution privilege, including through PUBLIC'
);

select pg_temp.phase353_assert(
  has_function_privilege('service_role', 'public.claim_phase353_handoff(text,text,bigint,integer,text,text,date,text)', 'EXECUTE')
  and has_function_privilege('service_role', 'public.mark_phase353_handoff_dispatch_accepted(bigint,text,text,bigint,integer,text,text)', 'EXECUTE')
  and has_function_privilege('service_role', 'public.mark_phase353_handoff_failed(bigint,text,text,bigint,integer,text,text,text,text)', 'EXECUTE')
  and not has_table_privilege('service_role', 'public.phase353_handoff_receipts', 'UPDATE'),
  'service_role RPC grants or direct table UPDATE denial are incorrect'
);

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
) on commit drop;
grant select, insert on phase353_validation_results to service_role;

set local role service_role;
insert into phase353_validation_results
select 'first_claim', claim_result, receipt_id, receipt_status
from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_WORKFLOW',
  935300001, 1,
  'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111',
  date '2099-01-01',
  'VALIDATION_ONLY_PHASE353_AUTHORITY_HASH'
);

insert into phase353_validation_results
select 'identical_replay', claim_result, receipt_id, receipt_status
from public.claim_phase353_handoff(
  'VALIDATION_ONLY_PHASE353_REPOSITORY',
  'VALIDATION_ONLY_PHASE353_WORKFLOW',
  935300001, 1,
  'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111',
  date '2099-01-01',
  'VALIDATION_ONLY_PHASE353_AUTHORITY_HASH'
);
reset role;

select pg_temp.phase353_assert(
  (select result = 'CLAIM_ACQUIRED' and receipt_status = 'CLAIMED'
   from phase353_validation_results where check_name = 'first_claim'),
  'first claim did not return CLAIM_ACQUIRED/CLAIMED'
);
select pg_temp.phase353_assert(
  (select result = 'ALREADY_CLAIMED' and receipt_status = 'CLAIMED'
   from phase353_validation_results where check_name = 'identical_replay'),
  'identical replay did not return ALREADY_CLAIMED/CLAIMED'
);
select pg_temp.phase353_assert(
  (select count(*) = 1 from public.phase353_handoff_receipts
   where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
     and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
     and producer_run_id = 935300001 and producer_run_attempt = 1
     and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER'),
  'identical replay created more than one row'
);

do $block$
declare v_failed_closed boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
      935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
      '2222222222222222222222222222222222222222', date '2099-01-01',
      'VALIDATION_ONLY_PHASE353_AUTHORITY_HASH');
  exception when integrity_constraint_violation then
    v_failed_closed := sqlerrm like '%IMMUTABLE_IDENTITY_CONFLICT%';
  end;
  perform pg_temp.phase353_assert(v_failed_closed, 'conflicting producer SHA did not fail closed');

  v_failed_closed := false;
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
      935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
      '1111111111111111111111111111111111111111', date '2099-01-01',
      'VALIDATION_ONLY_PHASE353_CONFLICTING_HASH');
  exception when integrity_constraint_violation then
    v_failed_closed := sqlerrm like '%IMMUTABLE_IDENTITY_CONFLICT%';
  end;
  perform pg_temp.phase353_assert(v_failed_closed, 'conflicting authority hash did not fail closed');

  v_failed_closed := false;
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
      935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
      '1111111111111111111111111111111111111111', date '2099-01-02',
      'VALIDATION_ONLY_PHASE353_AUTHORITY_HASH');
  exception when integrity_constraint_violation then
    v_failed_closed := sqlerrm like '%IMMUTABLE_IDENTITY_CONFLICT%';
  end;
  perform pg_temp.phase353_assert(v_failed_closed, 'conflicting business date did not fail closed');
end;
$block$;

set local role service_role;
insert into phase353_validation_results
select 'dispatch_accepted', transition_result, receipt_id, receipt_status
from public.mark_phase353_handoff_dispatch_accepted(
  (select receipt_id from phase353_validation_results where check_name = 'first_claim'),
  'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
  935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111'
);
insert into phase353_validation_results
select 'dispatch_replay', transition_result, receipt_id, receipt_status
from public.mark_phase353_handoff_dispatch_accepted(
  (select receipt_id from phase353_validation_results where check_name = 'first_claim'),
  'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
  935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
  '1111111111111111111111111111111111111111'
);
reset role;

select pg_temp.phase353_assert(
  (select result = 'DISPATCH_ACCEPTED' and receipt_status = 'DISPATCH_ACCEPTED'
   from phase353_validation_results where check_name = 'dispatch_accepted'),
  'CLAIMED to DISPATCH_ACCEPTED failed'
);
select pg_temp.phase353_assert(
  (select result = 'ALREADY_DISPATCH_ACCEPTED' and receipt_status = 'DISPATCH_ACCEPTED'
   from phase353_validation_results where check_name = 'dispatch_replay'),
  'dispatch acceptance replay was not idempotent'
);
select pg_temp.phase353_assert(
  (select status = 'DISPATCH_ACCEPTED' and status <> 'COMPLETED'
   from public.phase353_handoff_receipts
   where id = (select receipt_id from phase353_validation_results where check_name = 'first_claim')),
  'HTTP acceptance state was not preserved as DISPATCH_ACCEPTED'
);

-- Commit the approved RPC transition so marker isolation can be checked in a new transaction.
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

select pg_temp.phase353_assert(
  coalesce(current_setting('app.phase353_handoff_transition', true), '') = '',
  'transaction-local handoff marker leaked into a later transaction'
);

do $block$
declare v_rejected boolean;
begin
  v_rejected := false;
  begin
    update public.phase353_handoff_receipts set status = 'COMPLETED'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'direct DISPATCH_ACCEPTED to COMPLETED was allowed');

  v_rejected := false;
  begin
    update public.phase353_handoff_receipts set status = 'CLAIMED'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'direct or reverse status update was allowed');

  v_rejected := false;
  begin
    update public.phase353_handoff_receipts set last_error = 'VALIDATION_ONLY_DIRECT_ERROR'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'direct last_error update was allowed');

  v_rejected := false;
  begin
    update public.phase353_handoff_receipts set producer_sha = repeat('3', 40)
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_run_id = 935300001;
  exception when integrity_constraint_violation then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'immutable producer identity update was allowed');
end;
$block$;

-- Actual role changes prove denial rather than relying only on catalog inspection.
set local role anon;
do $block$
declare v_denied boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
      935300003, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
      '3333333333333333333333333333333333333333', null, null);
  exception when insufficient_privilege then v_denied := true;
  end;
  if not v_denied then
    raise exception 'PHASE353_LIVE_VALIDATION_FAILED: anon executed a mutation RPC';
  end if;
end;
$block$;
reset role;

set local role authenticated;
do $block$
declare v_denied boolean := false;
begin
  begin
    perform public.claim_phase353_handoff(
      'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
      935300003, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
      '3333333333333333333333333333333333333333', null, null);
  exception when insufficient_privilege then v_denied := true;
  end;
  if not v_denied then
    raise exception 'PHASE353_LIVE_VALIDATION_FAILED: authenticated executed a mutation RPC';
  end if;
end;
$block$;
reset role;

-- A second receipt proves CLAIMED -> FAILED. The first proves DISPATCH_ACCEPTED -> FAILED.
set local role service_role;
select pg_temp.phase353_assert(
  (select claim_result = 'CLAIM_ACQUIRED'
   from public.claim_phase353_handoff(
     'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
     935300003, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
     '3333333333333333333333333333333333333333', null, null)),
  'service_role could not claim the CLAIMED-to-FAILED validation receipt'
);

select pg_temp.phase353_assert(
  (select transition_result = 'FAILED' and receipt_status = 'FAILED'
   from public.mark_phase353_handoff_failed(
     (select id from public.phase353_handoff_receipts
      where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY' and producer_run_id = 935300003),
     'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
     935300003, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
     '3333333333333333333333333333333333333333', 'CLAIMED',
     'VALIDATION_ONLY_PHASE353_CLAIM_FAILURE')),
  'CLAIMED to FAILED did not succeed'
);

select pg_temp.phase353_assert(
  (select transition_result = 'FAILED' and receipt_status = 'FAILED'
   from public.mark_phase353_handoff_failed(
     (select id from public.phase353_handoff_receipts
      where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY' and producer_run_id = 935300001),
     'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
     935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
     '1111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
     'VALIDATION_ONLY_PHASE353_DISPATCH_FAILURE')),
  'DISPATCH_ACCEPTED to FAILED did not succeed'
);

select pg_temp.phase353_assert(
  (select transition_result = 'ALREADY_FAILED' and receipt_status = 'FAILED'
   from public.mark_phase353_handoff_failed(
     (select id from public.phase353_handoff_receipts
      where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY' and producer_run_id = 935300001),
     'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
     935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
     '1111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
     'VALIDATION_ONLY_PHASE353_DISPATCH_FAILURE')),
  'identical FAILED replay was not idempotent'
);
reset role;

do $block$
declare v_rejected boolean := false;
begin
  begin
    perform public.mark_phase353_handoff_failed(
      (select id from public.phase353_handoff_receipts
       where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY' and producer_run_id = 935300001),
      'VALIDATION_ONLY_PHASE353_REPOSITORY', 'VALIDATION_ONLY_PHASE353_WORKFLOW',
      935300001, 1, 'VALIDATION_ONLY_PHASE353_CONSUMER',
      '1111111111111111111111111111111111111111', 'DISPATCH_ACCEPTED',
      'VALIDATION_ONLY_PHASE353_CONFLICTING_FAILURE');
  exception when integrity_constraint_violation then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'conflicting FAILED replay did not fail closed');

  v_rejected := false;
  begin
    update public.phase353_handoff_receipts set status = 'CLAIMED'
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY' and producer_run_id = 935300001;
  exception when invalid_transaction_state then v_rejected := true;
  end;
  perform pg_temp.phase353_assert(v_rejected, 'FAILED was not terminal');
end;
$block$;

delete from public.phase353_handoff_receipts
where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
  and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
  and producer_run_id in (935300001, 935300002, 935300003)
  and producer_run_attempt = 1
  and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER';

select pg_temp.phase353_assert(
  not exists (
    select 1 from public.phase353_handoff_receipts
    where repository = 'VALIDATION_ONLY_PHASE353_REPOSITORY'
      and producer_workflow = 'VALIDATION_ONLY_PHASE353_WORKFLOW'
      and producer_run_id in (935300001, 935300002, 935300003)
      and producer_run_attempt = 1
      and consumer = 'VALIDATION_ONLY_PHASE353_CONSUMER'
  ),
  'validation row cleanup did not remove every exact validation tuple'
);

commit;

select 'PHASE353_HANDOFF_RECEIPT_LIVE_VALIDATION_PASS' as validation_result;
