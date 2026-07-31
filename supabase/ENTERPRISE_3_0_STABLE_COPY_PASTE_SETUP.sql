-- GPT Quant Enterprise 3.0 Stable
-- Safe, repeatable stable-release upgrade.
-- Requires Enterprise 2.1 Database Pack + Enterprise 3.0 Alpha 1 + RC schema.

begin;

create table if not exists public.quant_release_runs (
  id uuid primary key default gen_random_uuid(),
  account_name text not null default 'paper-main',
  release_version text not null,
  run_date date not null,
  run_status text not null default 'RUNNING',
  current_stage text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  stage_results jsonb not null default '[]'::jsonb,
  blockers jsonb not null default '[]'::jsonb,
  error_message text
);

create index if not exists quant_release_runs_latest_idx
on public.quant_release_runs(account_name, run_date desc, started_at desc);

create table if not exists public.quant_data_quality_checks (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  check_date date not null,
  check_key text not null,
  check_status text not null,
  observed_value text,
  expected_value text,
  severity text not null default 'INFO',
  message text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_data_quality_checks_uidx
on public.quant_data_quality_checks(account_name, check_date, check_key);

create table if not exists public.quant_stable_config (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  config_key text not null,
  config_value jsonb not null,
  description text,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create unique index if not exists quant_stable_config_uidx
on public.quant_stable_config(account_name, config_key);

insert into public.quant_stable_config
  (account_name, config_key, config_value, description)
values
  ('paper-main', 'release_mode', '"PAPER_ONLY"'::jsonb, 'Stable release execution mode'),
  ('paper-main', 'minimum_readiness_score', '85'::jsonb, 'Minimum score required for healthy stable status'),
  ('paper-main', 'fail_closed_on_schema_error', 'true'::jsonb, 'Stop the cycle if required schema is missing'),
  ('paper-main', 'allow_partial_noncritical_stages', 'true'::jsonb, 'Permit reporting-only stage failures'),
  ('paper-main', 'live_trading_enabled', 'false'::jsonb, 'Stable release remains paper-only')
on conflict (account_name, config_key) do update
set
  config_value = excluded.config_value,
  description = excluded.description,
  updated_at = now();

alter table public.quant_release_runs enable row level security;
alter table public.quant_data_quality_checks enable row level security;
alter table public.quant_stable_config enable row level security;

drop policy if exists "enterprise30 stable read release runs" on public.quant_release_runs;
drop policy if exists "enterprise30 stable read data quality" on public.quant_data_quality_checks;
drop policy if exists "enterprise30 stable read config" on public.quant_stable_config;

create policy "enterprise30 stable read release runs"
on public.quant_release_runs for select to authenticated using (true);

create policy "enterprise30 stable read data quality"
on public.quant_data_quality_checks for select to anon, authenticated using (true);

create policy "enterprise30 stable read config"
on public.quant_stable_config for select to authenticated using (true);

create or replace view public.quant_stable_readiness
with (security_invoker = true)
as
select
  current_date as checked_on,
  to_regclass('public.quant_runs') is not null as enterprise_core_ready,
  to_regclass('public.quant_operational_status') is not null as operations_ready,
  to_regclass('public.quant_research_reports') is not null as research_ready,
  to_regclass('public.quant_portfolio_recommendations') is not null as portfolio_ready,
  to_regclass('public.quant_risk_events') is not null as risk_ready,
  to_regclass('public.trade_orders_v13') is not null as paper_execution_ready,
  to_regclass('public.quant_reports') is not null as reporting_ready,
  to_regclass('public.quant_ceo_snapshots') is not null as dashboard_ready,
  to_regclass('public.quant_release_status') is not null as release_status_ready,
  (
    to_regclass('public.quant_runs') is not null
    and to_regclass('public.quant_operational_status') is not null
    and to_regclass('public.quant_research_reports') is not null
    and to_regclass('public.quant_portfolio_recommendations') is not null
    and to_regclass('public.quant_risk_events') is not null
    and to_regclass('public.trade_orders_v13') is not null
    and to_regclass('public.quant_reports') is not null
    and to_regclass('public.quant_ceo_snapshots') is not null
    and to_regclass('public.quant_release_status') is not null
  ) as all_required_objects_ready;

grant select on public.quant_stable_readiness to anon, authenticated;

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant Enterprise 3.0 Stable setup complete' as result,
  all_required_objects_ready,
  enterprise_core_ready,
  operations_ready,
  research_ready,
  portfolio_ready,
  risk_ready,
  paper_execution_ready,
  reporting_ready,
  dashboard_ready
from public.quant_stable_readiness;
