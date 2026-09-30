begin;

create table if not exists public.phase353_handoff_receipts (
  id bigint generated always as identity primary key,
  repository text not null,
  producer_workflow text not null,
  producer_run_id bigint not null check (producer_run_id > 0),
  producer_run_attempt integer not null check (producer_run_attempt > 0),
  consumer text not null,
  producer_sha text not null check (producer_sha ~ '^[0-9a-fA-F]{40}$'),
  business_date date,
  authority_hash text,
  status text not null default 'CLAIMED'
    check (status in ('CLAIMED', 'DISPATCH_ACCEPTED', 'COMPLETED', 'FAILED')),
  claimed_at timestamptz not null default clock_timestamp(),
  dispatched_at timestamptz,
  consumer_run_id bigint check (consumer_run_id is null or consumer_run_id > 0),
  last_error text,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  constraint phase353_handoff_receipts_identity_key unique (
    repository,
    producer_workflow,
    producer_run_id,
    producer_run_attempt,
    consumer
  )
);

alter table public.phase353_handoff_receipts enable row level security;

create or replace function public.phase353_reject_handoff_identity_change()
returns trigger
language plpgsql
set search_path = pg_catalog
as $function$
begin
  if new.repository is distinct from old.repository
     or new.producer_workflow is distinct from old.producer_workflow
     or new.producer_run_id is distinct from old.producer_run_id
     or new.producer_run_attempt is distinct from old.producer_run_attempt
     or new.consumer is distinct from old.consumer
     or new.producer_sha is distinct from old.producer_sha
     or new.business_date is distinct from old.business_date
     or new.authority_hash is distinct from old.authority_hash then
    raise exception 'PHASE353_HANDOFF_IMMUTABLE_IDENTITY_CONFLICT'
      using errcode = 'integrity_constraint_violation';
  end if;
  new.updated_at := clock_timestamp();
  return new;
end;
$function$;

drop trigger if exists phase353_handoff_receipts_immutable_identity
  on public.phase353_handoff_receipts;
create trigger phase353_handoff_receipts_immutable_identity
before update on public.phase353_handoff_receipts
for each row execute function public.phase353_reject_handoff_identity_change();

create or replace function public.phase353_guard_handoff_state_change()
returns trigger
language plpgsql
set search_path = pg_catalog
as $function$
declare
  v_transition text := current_setting('app.phase353_handoff_transition', true);
begin
  if new.status is not distinct from old.status then
    if new.last_error is distinct from old.last_error then
      raise exception 'PHASE353_HANDOFF_LAST_ERROR_REQUIRES_FAILURE_TRANSITION'
        using errcode = 'invalid_transaction_state';
    end if;
    return new;
  end if;

  if old.status = 'CLAIMED'
     and new.status = 'DISPATCH_ACCEPTED'
     and v_transition = 'CLAIMED->DISPATCH_ACCEPTED' then
    if new.last_error is not null then
      raise exception 'PHASE353_HANDOFF_DISPATCH_ACCEPTED_CANNOT_HAVE_ERROR'
        using errcode = 'invalid_transaction_state';
    end if;
    return new;
  end if;

  if old.status in ('CLAIMED', 'DISPATCH_ACCEPTED')
     and new.status = 'FAILED'
     and v_transition = old.status || '->FAILED' then
    if nullif(btrim(new.last_error), '') is null then
      raise exception 'PHASE353_HANDOFF_FAILURE_REQUIRES_ERROR'
        using errcode = 'invalid_parameter_value';
    end if;
    return new;
  end if;

  raise exception 'PHASE353_HANDOFF_INVALID_STATUS_TRANSITION: % -> %', old.status, new.status
    using errcode = 'invalid_transaction_state';
end;
$function$;

drop trigger if exists phase353_handoff_receipts_status_guard
  on public.phase353_handoff_receipts;
create trigger phase353_handoff_receipts_status_guard
before update of status, last_error on public.phase353_handoff_receipts
for each row execute function public.phase353_guard_handoff_state_change();

create or replace function public.claim_phase353_handoff(
  p_repository text,
  p_producer_workflow text,
  p_producer_run_id bigint,
  p_producer_run_attempt integer,
  p_consumer text,
  p_producer_sha text,
  p_business_date date default null,
  p_authority_hash text default null
)
returns table (claim_result text, receipt_id bigint, receipt_status text)
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_receipt public.phase353_handoff_receipts%rowtype;
begin
  if nullif(btrim(p_repository), '') is null
     or nullif(btrim(p_producer_workflow), '') is null
     or p_producer_run_id is null or p_producer_run_id <= 0
     or p_producer_run_attempt is null or p_producer_run_attempt <= 0
     or nullif(btrim(p_consumer), '') is null
     or p_producer_sha is null or p_producer_sha !~ '^[0-9a-fA-F]{40}$' then
    raise exception 'PHASE353_HANDOFF_INVALID_CLAIM'
      using errcode = 'invalid_parameter_value';
  end if;

  insert into public.phase353_handoff_receipts (
    repository, producer_workflow, producer_run_id, producer_run_attempt,
    consumer, producer_sha, business_date, authority_hash, status
  ) values (
    p_repository, p_producer_workflow, p_producer_run_id, p_producer_run_attempt,
    p_consumer, lower(p_producer_sha), p_business_date, p_authority_hash, 'CLAIMED'
  )
  on conflict (repository, producer_workflow, producer_run_id, producer_run_attempt, consumer)
  do nothing
  returning * into v_receipt;

  if found then
    return query select 'CLAIM_ACQUIRED'::text, v_receipt.id, v_receipt.status;
    return;
  end if;

  select * into strict v_receipt
  from public.phase353_handoff_receipts
  where repository = p_repository
    and producer_workflow = p_producer_workflow
    and producer_run_id = p_producer_run_id
    and producer_run_attempt = p_producer_run_attempt
    and consumer = p_consumer
  for update;

  if v_receipt.producer_sha <> lower(p_producer_sha)
     or (p_business_date is not null and v_receipt.business_date is distinct from p_business_date)
     or (p_authority_hash is not null and v_receipt.authority_hash is distinct from p_authority_hash) then
    raise exception 'PHASE353_HANDOFF_IMMUTABLE_IDENTITY_CONFLICT'
      using errcode = 'integrity_constraint_violation';
  end if;

  return query select 'ALREADY_CLAIMED'::text, v_receipt.id, v_receipt.status;
end;
$function$;

create or replace function public.mark_phase353_handoff_dispatch_accepted(
  p_receipt_id bigint,
  p_repository text,
  p_producer_workflow text,
  p_producer_run_id bigint,
  p_producer_run_attempt integer,
  p_consumer text,
  p_producer_sha text
)
returns table (transition_result text, receipt_id bigint, receipt_status text)
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_receipt public.phase353_handoff_receipts%rowtype;
begin
  select * into strict v_receipt
  from public.phase353_handoff_receipts
  where id = p_receipt_id
  for update;

  if v_receipt.repository is distinct from p_repository
     or v_receipt.producer_workflow is distinct from p_producer_workflow
     or v_receipt.producer_run_id is distinct from p_producer_run_id
     or v_receipt.producer_run_attempt is distinct from p_producer_run_attempt
     or v_receipt.consumer is distinct from p_consumer
     or v_receipt.producer_sha is distinct from lower(p_producer_sha) then
    raise exception 'PHASE353_HANDOFF_IMMUTABLE_IDENTITY_CONFLICT'
      using errcode = 'integrity_constraint_violation';
  end if;

  if v_receipt.status = 'CLAIMED' then
    perform set_config('app.phase353_handoff_transition', 'CLAIMED->DISPATCH_ACCEPTED', true);
    update public.phase353_handoff_receipts
    set status = 'DISPATCH_ACCEPTED', dispatched_at = clock_timestamp(), last_error = null
    where id = v_receipt.id
    returning * into v_receipt;
    return query select 'DISPATCH_ACCEPTED'::text, v_receipt.id, v_receipt.status;
    return;
  end if;

  if v_receipt.status = 'DISPATCH_ACCEPTED' then
    return query select 'ALREADY_DISPATCH_ACCEPTED'::text, v_receipt.id, v_receipt.status;
    return;
  end if;

  raise exception 'PHASE353_HANDOFF_INVALID_STATUS_TRANSITION: %', v_receipt.status
    using errcode = 'invalid_transaction_state';
end;
$function$;

create or replace function public.mark_phase353_handoff_failed(
  p_receipt_id bigint,
  p_repository text,
  p_producer_workflow text,
  p_producer_run_id bigint,
  p_producer_run_attempt integer,
  p_consumer text,
  p_producer_sha text,
  p_expected_status text,
  p_last_error text
)
returns table (transition_result text, receipt_id bigint, receipt_status text)
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_receipt public.phase353_handoff_receipts%rowtype;
begin
  if p_expected_status not in ('CLAIMED', 'DISPATCH_ACCEPTED')
     or nullif(btrim(p_last_error), '') is null then
    raise exception 'PHASE353_HANDOFF_INVALID_FAILURE_REQUEST'
      using errcode = 'invalid_parameter_value';
  end if;

  select * into strict v_receipt
  from public.phase353_handoff_receipts
  where id = p_receipt_id
  for update;

  if v_receipt.repository is distinct from p_repository
     or v_receipt.producer_workflow is distinct from p_producer_workflow
     or v_receipt.producer_run_id is distinct from p_producer_run_id
     or v_receipt.producer_run_attempt is distinct from p_producer_run_attempt
     or v_receipt.consumer is distinct from p_consumer
     or v_receipt.producer_sha is distinct from lower(p_producer_sha) then
    raise exception 'PHASE353_HANDOFF_IMMUTABLE_IDENTITY_CONFLICT'
      using errcode = 'integrity_constraint_violation';
  end if;

  if v_receipt.status = 'FAILED' then
    if v_receipt.last_error = p_last_error then
      return query select 'ALREADY_FAILED'::text, v_receipt.id, v_receipt.status;
      return;
    end if;
    raise exception 'PHASE353_HANDOFF_CONFLICTING_FAILURE'
      using errcode = 'integrity_constraint_violation';
  end if;

  if v_receipt.status <> p_expected_status then
    raise exception 'PHASE353_HANDOFF_EXPECTED_STATUS_CONFLICT: expected %, found %',
      p_expected_status, v_receipt.status
      using errcode = 'invalid_transaction_state';
  end if;

  perform set_config(
    'app.phase353_handoff_transition', v_receipt.status || '->FAILED', true
  );
  update public.phase353_handoff_receipts
  set status = 'FAILED', last_error = p_last_error
  where id = v_receipt.id
  returning * into v_receipt;

  return query select 'FAILED'::text, v_receipt.id, v_receipt.status;
end;
$function$;

revoke all on table public.phase353_handoff_receipts from public, anon, authenticated;
revoke all on function public.phase353_reject_handoff_identity_change() from public, anon, authenticated;
revoke all on function public.phase353_guard_handoff_state_change() from public, anon, authenticated;
revoke all on function public.claim_phase353_handoff(text, text, bigint, integer, text, text, date, text) from public, anon, authenticated;
revoke all on function public.mark_phase353_handoff_dispatch_accepted(bigint, text, text, bigint, integer, text, text) from public, anon, authenticated;
revoke all on function public.mark_phase353_handoff_failed(bigint, text, text, bigint, integer, text, text, text, text) from public, anon, authenticated;

revoke all privileges on table public.phase353_handoff_receipts from service_role;
grant select on table public.phase353_handoff_receipts to service_role;
grant execute on function public.claim_phase353_handoff(text, text, bigint, integer, text, text, date, text) to service_role;
grant execute on function public.mark_phase353_handoff_dispatch_accepted(bigint, text, text, bigint, integer, text, text) to service_role;
grant execute on function public.mark_phase353_handoff_failed(bigint, text, text, bigint, integer, text, text, text, text) to service_role;

commit;
