begin;
do $$
declare src text;
begin
  select c.relname into src
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relkind in ('r','p','v','m')
    and (c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92'
      or c.relname like 'paper_post_recovery_activation_master_cycle_reconstruction_audi%')
  order by case when c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92' then 0 else 1 end,
           length(c.relname) desc
  limit 1;

  if src is null then
    raise exception 'PHASE37261_V63_FATAL: source audit relation not found';
  end if;

  if exists (
    select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relname='phase37261_reconstruction_audit_v92'
      and c.relkind <> 'v'
  ) then
    raise exception 'PHASE37261_V63_FATAL: short API relation exists and is not a view';
  end if;

  execute format(
    'create or replace view public.phase37261_reconstruction_audit_v92 as select * from public.%I',
    src
  );
  raise notice 'V6.3 physical source relation: %',src;
end $$;

grant usage on schema public to anon,authenticated,service_role;
grant select on public.phase37261_reconstruction_audit_v92 to anon,authenticated,service_role;
comment on view public.phase37261_reconstruction_audit_v92 is
'GPT Quant V9.2 Phase 3.7.2.6.1 V6.3 short PostgREST canonical relation; paper-only; source history preserved.';
notify pgrst,'reload schema';
commit;

select c.relname,c.relkind,octet_length(c.relname) identifier_bytes
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and
(c.relname like 'paper_post_recovery_activation_master_cycle_reconstruction_audi%'
 or c.relname='phase37261_reconstruction_audit_v92')
order by c.relname;
