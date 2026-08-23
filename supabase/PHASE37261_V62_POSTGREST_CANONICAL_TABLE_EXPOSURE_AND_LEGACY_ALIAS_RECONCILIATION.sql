begin;

do $$
declare
  canonical_kind "char";
  legacy_kind "char";
begin
  select c.relkind into canonical_kind
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public'
    and c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92';

  select c.relkind into legacy_kind
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public'
    and c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit';

  if canonical_kind is null and legacy_kind is not null then
    execute 'create view public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92 as
             select * from public.paper_post_recovery_activation_master_cycle_reconstruction_audit';
  elsif canonical_kind is null and legacy_kind is null then
    raise exception 'Neither canonical nor legacy reconstruction audit object exists.';
  end if;
end
$$;

grant usage on schema public to anon, authenticated, service_role;
grant select on public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92
  to anon, authenticated, service_role;

do $$
declare
  canonical_kind "char";
  seq_name text;
begin
  select c.relkind into canonical_kind
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public'
    and c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92';

  if canonical_kind='r' then
    grant insert on public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92
      to service_role;

    seq_name := pg_get_serial_sequence(
      'public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92',
      'id'
    );

    if seq_name is not null then
      execute format('grant usage, select on sequence %s to service_role', seq_name);
    end if;
  end if;
end
$$;

notify pgrst, 'reload schema';

commit;