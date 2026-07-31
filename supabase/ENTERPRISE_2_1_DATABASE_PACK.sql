-- ============================================================================
-- GPT Quant Enterprise 2.1 Database Pack
-- Pack version: 2.1.1
--
-- Purpose:
--   1. Install missing V22 Autonomous Trading Director schema.
--   2. Install or repair Enterprise 2.0 unified core schema.
--   3. Install or repair Enterprise 2.1 operational schema.
--   4. Add compatibility indexes, update triggers, RLS policies and readiness
--      views.
--
-- Safety:
--   - Idempotent: may be executed repeatedly.
--   - Does not DROP existing tables or user data.
--   - Does not delete V13-V21 legacy tables.
--
-- Requirement:
--   public.autotrader_configs_v13 must already exist.
-- ============================================================================

begin;

create extension if not exists pgcrypto;

do $$
begin
  if to_regclass('public.autotrader_configs_v13') is null then
    raise exception
      'Missing public.autotrader_configs_v13. Install the V13 AutoTrader schema before running this pack.';
  end if;
end
$$;


-- ========================= V22 SCHEMA =========================
-- GPT Quant V22 Autonomous Trading Director
-- Copy this entire file into Supabase SQL Editor and press Run.

alter table public.autotrader_configs_v13
  add column if not exists director_enabled boolean not null default true,
  add column if not exists director_buy_threshold numeric not null default 65,
  add column if not exists director_reduce_threshold numeric not null default 35,
  add column if not exists director_max_deploy_pct numeric not null default 20,
  add column if not exists director_min_cash_pct numeric not null default 25,
  add column if not exists director_drawdown_stop_pct numeric not null default 12;

create table if not exists public.market_state_v22 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  state_date date not null,
  market_state text not null,
  opportunity_score numeric not null default 0,
  risk_score numeric not null default 0,
  liquidity_score numeric not null default 0,
  breadth_score numeric not null default 0,
  confidence numeric not null default 0,
  rationale text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists market_state_v22_uidx
on public.market_state_v22(account_name, state_date);

create table if not exists public.trading_directives_v22 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  directive_date date not null,
  directive text not null,
  confidence numeric not null default 0,
  target_cash_pct numeric not null default 0,
  deploy_capital_pct numeric not null default 0,
  reduce_exposure_pct numeric not null default 0,
  market_state text not null,
  risk_gate text not null,
  council_alignment text not null,
  portfolio_action text not null,
  rationale text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists trading_directives_v22_uidx
on public.trading_directives_v22(account_name, directive_date);

create table if not exists public.director_reasoning_v22 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  directive_date date not null,
  component text not null,
  component_status text not null,
  score numeric not null default 0,
  weight numeric not null default 0,
  contribution numeric not null default 0,
  explanation text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists director_reasoning_v22_uidx
on public.director_reasoning_v22(
  account_name,
  directive_date,
  component
);

alter table public.market_state_v22 enable row level security;
alter table public.trading_directives_v22 enable row level security;
alter table public.director_reasoning_v22 enable row level security;

drop policy if exists "v22 read market state" on public.market_state_v22;
drop policy if exists "v22 read directives" on public.trading_directives_v22;
drop policy if exists "v22 read reasoning" on public.director_reasoning_v22;

create policy "v22 read market state"
on public.market_state_v22
for select to anon, authenticated
using (true);

create policy "v22 read directives"
on public.trading_directives_v22
for select to anon, authenticated
using (true);

create policy "v22 read reasoning"
on public.director_reasoning_v22
for select to anon, authenticated
using (true);



-- ================= ENTERPRISE 2.0 CORE =================
-- GPT Quant Enterprise 2.0 Foundation
-- This creates the stable core model. Existing V13-V22 tables are preserved.

create table if not exists public.quant_modules (
  id bigserial primary key,
  module_key text not null unique,
  module_name text not null,
  module_type text not null,
  current_version text not null,
  enabled boolean not null default true,
  execution_order integer not null default 100,
  config jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.quant_runs (
  id uuid primary key default gen_random_uuid(),
  account_name text not null default 'paper-main',
  run_date date not null,
  run_type text not null,
  status text not null default 'RUNNING',
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  module_count integer not null default 0,
  success_count integer not null default 0,
  failure_count integer not null default 0,
  summary jsonb not null default '{}'::jsonb,
  error_message text
);

create index if not exists quant_runs_account_date_idx
on public.quant_runs(account_name, run_date desc);

create table if not exists public.quant_decisions (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  decision_date date not null,
  decision_scope text not null,
  entity_type text not null,
  entity_key text not null,
  module_key text not null,
  engine_version text not null,
  action text not null,
  score numeric,
  confidence numeric,
  risk_score numeric,
  target_weight numeric,
  target_cash_pct numeric,
  status text not null default 'ACTIVE',
  rationale text not null,
  evidence jsonb not null default '{}'::jsonb,
  parent_decision_id bigint references public.quant_decisions(id) on delete set null,
  source_record jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_decisions_dedup_idx
on public.quant_decisions(
  account_name,
  decision_date,
  decision_scope,
  entity_type,
  entity_key,
  module_key,
  engine_version
);

create index if not exists quant_decisions_latest_idx
on public.quant_decisions(account_name, decision_date desc, decision_scope);

create table if not exists public.quant_orders (
  id uuid primary key default gen_random_uuid(),
  account_name text not null default 'paper-main',
  decision_id bigint references public.quant_decisions(id) on delete set null,
  external_order_id text,
  symbol text not null,
  side text not null,
  order_type text not null default 'MARKET',
  quantity integer not null,
  reference_price numeric,
  notional numeric,
  mode text not null default 'PAPER',
  status text not null default 'PROPOSED',
  approval_status text not null default 'PENDING',
  risk_status text not null default 'PENDING',
  idempotency_key text not null unique,
  reason_code text,
  reason_message text,
  proposed_at timestamptz not null default now(),
  approved_at timestamptz,
  filled_at timestamptz,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists quant_orders_status_idx
on public.quant_orders(account_name, status, proposed_at desc);

create table if not exists public.quant_positions (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  symbol text not null,
  quantity integer not null default 0,
  average_price numeric not null default 0,
  cost_basis numeric not null default 0,
  last_price numeric not null default 0,
  market_value numeric not null default 0,
  unrealized_pnl numeric not null default 0,
  realized_pnl numeric not null default 0,
  high_watermark_price numeric,
  holding_days integer not null default 0,
  status text not null default 'OPEN',
  opened_at timestamptz,
  closed_at timestamptz,
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create unique index if not exists quant_positions_account_symbol_idx
on public.quant_positions(account_name, symbol);

create table if not exists public.quant_portfolio_snapshots (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  snapshot_date date not null,
  equity numeric not null default 0,
  cash numeric not null default 0,
  market_value numeric not null default 0,
  gross_exposure_pct numeric not null default 0,
  net_exposure_pct numeric not null default 0,
  realized_pnl numeric not null default 0,
  unrealized_pnl numeric not null default 0,
  daily_return numeric not null default 0,
  total_return numeric not null default 0,
  max_drawdown numeric not null default 0,
  var_95 numeric not null default 0,
  expected_shortfall_95 numeric not null default 0,
  sharpe numeric not null default 0,
  positions_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_portfolio_snapshots_uidx
on public.quant_portfolio_snapshots(account_name, snapshot_date);

create table if not exists public.quant_reports (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_date date not null,
  report_type text not null,
  report_version text not null,
  headline text not null,
  executive_summary text not null,
  action_items text not null,
  status text not null default 'PUBLISHED',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_reports_uidx
on public.quant_reports(account_name, report_date, report_type, report_version);

create table if not exists public.quant_audit_logs (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  run_id uuid references public.quant_runs(id) on delete set null,
  module_key text not null,
  event_type text not null,
  severity text not null default 'INFO',
  entity_type text,
  entity_key text,
  message text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists quant_audit_logs_latest_idx
on public.quant_audit_logs(account_name, created_at desc);

create table if not exists public.quant_system_health (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  health_date date not null,
  overall_score numeric not null default 0,
  data_score numeric not null default 0,
  signal_score numeric not null default 0,
  execution_score numeric not null default 0,
  portfolio_score numeric not null default 0,
  risk_score numeric not null default 0,
  automation_score numeric not null default 0,
  status text not null,
  issues jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_system_health_uidx
on public.quant_system_health(account_name, health_date);

insert into public.quant_modules
  (module_key, module_name, module_type, current_version, execution_order, config)
values
  ('market_data', 'Market Data Pipeline', 'DATA', '2.0.0', 10, '{}'::jsonb),
  ('features', 'Feature Engine', 'ANALYTICS', '2.0.0', 20, '{}'::jsonb),
  ('signals', 'Signal Engine', 'DECISION', '2.0.0', 30, '{}'::jsonb),
  ('risk', 'Risk Engine', 'RISK', '2.0.0', 40, '{}'::jsonb),
  ('council', 'Investment Council', 'DECISION', '2.0.0', 50, '{}'::jsonb),
  ('director', 'Trading Director', 'GOVERNANCE', '2.0.0', 60, '{}'::jsonb),
  ('orders', 'Order Proposal Engine', 'EXECUTION', '2.0.0', 70, '{}'::jsonb),
  ('portfolio', 'Portfolio Engine', 'PORTFOLIO', '2.0.0', 80, '{}'::jsonb),
  ('reporting', 'Institutional Reporting', 'REPORTING', '2.0.0', 90, '{}'::jsonb)
on conflict (module_key) do update
set
  module_name = excluded.module_name,
  module_type = excluded.module_type,
  current_version = excluded.current_version,
  execution_order = excluded.execution_order,
  updated_at = now();

alter table public.quant_modules enable row level security;
alter table public.quant_decisions enable row level security;
alter table public.quant_orders enable row level security;
alter table public.quant_positions enable row level security;
alter table public.quant_portfolio_snapshots enable row level security;
alter table public.quant_reports enable row level security;
alter table public.quant_system_health enable row level security;

drop policy if exists "enterprise2 read modules" on public.quant_modules;
drop policy if exists "enterprise2 read decisions" on public.quant_decisions;
drop policy if exists "enterprise2 read orders" on public.quant_orders;
drop policy if exists "enterprise2 read positions" on public.quant_positions;
drop policy if exists "enterprise2 read portfolio" on public.quant_portfolio_snapshots;
drop policy if exists "enterprise2 read reports" on public.quant_reports;
drop policy if exists "enterprise2 read health" on public.quant_system_health;

create policy "enterprise2 read modules"
on public.quant_modules for select to anon, authenticated using (true);
create policy "enterprise2 read decisions"
on public.quant_decisions for select to anon, authenticated using (true);
create policy "enterprise2 read orders"
on public.quant_orders for select to anon, authenticated using (true);
create policy "enterprise2 read positions"
on public.quant_positions for select to anon, authenticated using (true);
create policy "enterprise2 read portfolio"
on public.quant_portfolio_snapshots for select to anon, authenticated using (true);
create policy "enterprise2 read reports"
on public.quant_reports for select to anon, authenticated using (true);
create policy "enterprise2 read health"
on public.quant_system_health for select to anon, authenticated using (true);



-- ============== ENTERPRISE 2.1 OPERATIONS ==============
-- GPT Quant Enterprise 2.1 Operational Platform

create table if not exists public.quant_operational_status (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  status_date date not null,
  pipeline_status text not null,
  data_freshness_status text not null,
  signals_status text not null,
  orders_status text not null,
  portfolio_status text not null,
  risk_status text not null,
  reports_status text not null,
  overall_score numeric not null default 0,
  latest_data_date date,
  latest_signal_date date,
  proposed_orders integer not null default 0,
  approved_orders integer not null default 0,
  filled_orders integer not null default 0,
  open_positions integer not null default 0,
  issues jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_operational_status_uidx
on public.quant_operational_status(account_name, status_date);

create table if not exists public.quant_risk_limits (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  limit_key text not null,
  limit_value numeric not null,
  warning_value numeric,
  enabled boolean not null default true,
  unit text not null default 'PCT',
  description text,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create unique index if not exists quant_risk_limits_uidx
on public.quant_risk_limits(account_name, limit_key);

create table if not exists public.quant_risk_events (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  event_date date not null,
  event_type text not null,
  severity text not null,
  metric_value numeric,
  limit_value numeric,
  entity_type text,
  entity_key text,
  message text not null,
  status text not null default 'OPEN',
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists quant_risk_events_latest_idx
on public.quant_risk_events(account_name, event_date desc, severity);

create table if not exists public.quant_daily_briefs (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  brief_date date not null,
  brief_type text not null,
  headline text not null,
  summary text not null,
  market_view text not null,
  portfolio_view text not null,
  risk_view text not null,
  action_plan text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_daily_briefs_uidx
on public.quant_daily_briefs(account_name, brief_date, brief_type);

insert into public.quant_risk_limits
  (account_name, limit_key, limit_value, warning_value, unit, description)
values
  ('paper-main', 'MAX_DRAWDOWN_PCT', 12, 8, 'PCT', 'Maximum allowed portfolio drawdown'),
  ('paper-main', 'VAR_95_PCT', 3, 2, 'PCT', 'Maximum one-day 95% VaR as equity percentage'),
  ('paper-main', 'MAX_GROSS_EXPOSURE_PCT', 100, 85, 'PCT', 'Maximum gross exposure'),
  ('paper-main', 'MAX_SINGLE_POSITION_PCT', 15, 12, 'PCT', 'Maximum single position weight'),
  ('paper-main', 'MIN_CASH_PCT', 25, 30, 'PCT', 'Minimum preferred cash reserve')
on conflict (account_name, limit_key) do update
set
  limit_value = excluded.limit_value,
  warning_value = excluded.warning_value,
  unit = excluded.unit,
  description = excluded.description,
  updated_at = now();

alter table public.quant_operational_status enable row level security;
alter table public.quant_risk_limits enable row level security;
alter table public.quant_risk_events enable row level security;
alter table public.quant_daily_briefs enable row level security;

drop policy if exists "enterprise21 read operational status" on public.quant_operational_status;
drop policy if exists "enterprise21 read risk limits" on public.quant_risk_limits;
drop policy if exists "enterprise21 read risk events" on public.quant_risk_events;
drop policy if exists "enterprise21 read daily briefs" on public.quant_daily_briefs;

create policy "enterprise21 read operational status"
on public.quant_operational_status for select to anon, authenticated using (true);
create policy "enterprise21 read risk limits"
on public.quant_risk_limits for select to anon, authenticated using (true);
create policy "enterprise21 read risk events"
on public.quant_risk_events for select to anon, authenticated using (true);
create policy "enterprise21 read daily briefs"
on public.quant_daily_briefs for select to anon, authenticated using (true);


-- ============================================================================
-- Enterprise 2.1 compatibility and governance repairs
-- ============================================================================

-- Ensure the Enterprise module registry reflects the current operational layer.
insert into public.quant_modules
  (module_key, module_name, module_type, current_version, enabled, execution_order, config)
values
  ('operations', 'Operational Status Engine', 'OPERATIONS', '2.1.0', true, 100, '{}'::jsonb),
  ('risk_governance', 'Central Risk Governance', 'RISK', '2.1.0', true, 110, '{}'::jsonb),
  ('daily_brief', 'CEO Daily Brief', 'REPORTING', '2.1.0', true, 120, '{}'::jsonb)
on conflict (module_key) do update
set
  module_name = excluded.module_name,
  module_type = excluded.module_type,
  current_version = excluded.current_version,
  enabled = excluded.enabled,
  execution_order = excluded.execution_order,
  updated_at = now();

-- Shared updated_at trigger.
create or replace function public.quant_set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists quant_modules_set_updated_at on public.quant_modules;
create trigger quant_modules_set_updated_at
before update on public.quant_modules
for each row execute function public.quant_set_updated_at();

drop trigger if exists quant_positions_set_updated_at on public.quant_positions;
create trigger quant_positions_set_updated_at
before update on public.quant_positions
for each row execute function public.quant_set_updated_at();

drop trigger if exists quant_risk_limits_set_updated_at on public.quant_risk_limits;
create trigger quant_risk_limits_set_updated_at
before update on public.quant_risk_limits
for each row execute function public.quant_set_updated_at();

-- Additional operational indexes.
create index if not exists market_state_v22_latest_idx
on public.market_state_v22(account_name, state_date desc);

create index if not exists trading_directives_v22_latest_idx
on public.trading_directives_v22(account_name, directive_date desc);

create index if not exists director_reasoning_v22_latest_idx
on public.director_reasoning_v22(account_name, directive_date desc, contribution desc);

create index if not exists quant_reports_latest_idx
on public.quant_reports(account_name, report_date desc, report_type);

create index if not exists quant_risk_events_status_idx
on public.quant_risk_events(account_name, status, event_date desc);

create index if not exists quant_daily_briefs_latest_idx
on public.quant_daily_briefs(account_name, brief_date desc, brief_type);

create index if not exists quant_operational_status_latest_idx
on public.quant_operational_status(account_name, status_date desc);

-- Apply RLS to administrative tables too. Service-role workflows bypass RLS.
alter table public.quant_runs enable row level security;
alter table public.quant_audit_logs enable row level security;

drop policy if exists "enterprise2 read runs" on public.quant_runs;
drop policy if exists "enterprise2 read audit logs" on public.quant_audit_logs;

create policy "enterprise2 read runs"
on public.quant_runs
for select to anon, authenticated
using (true);

create policy "enterprise2 read audit logs"
on public.quant_audit_logs
for select to authenticated
using (true);

-- Readiness view for fast troubleshooting.
create or replace view public.quant_enterprise_2_1_readiness
with (security_invoker = true)
as
select
  current_date as checked_on,
  to_regclass('public.market_state_v22') is not null as v22_market_state_ready,
  to_regclass('public.trading_directives_v22') is not null as v22_directives_ready,
  to_regclass('public.director_reasoning_v22') is not null as v22_reasoning_ready,
  to_regclass('public.quant_modules') is not null as enterprise_core_ready,
  to_regclass('public.quant_decisions') is not null as unified_decisions_ready,
  to_regclass('public.quant_portfolio_snapshots') is not null as portfolio_snapshots_ready,
  to_regclass('public.quant_system_health') is not null as system_health_ready,
  to_regclass('public.quant_operational_status') is not null as operational_status_ready,
  to_regclass('public.quant_risk_limits') is not null as risk_limits_ready,
  to_regclass('public.quant_risk_events') is not null as risk_events_ready,
  to_regclass('public.quant_daily_briefs') is not null as daily_briefs_ready,
  (
    to_regclass('public.market_state_v22') is not null
    and to_regclass('public.trading_directives_v22') is not null
    and to_regclass('public.director_reasoning_v22') is not null
    and to_regclass('public.quant_modules') is not null
    and to_regclass('public.quant_decisions') is not null
    and to_regclass('public.quant_portfolio_snapshots') is not null
    and to_regclass('public.quant_system_health') is not null
    and to_regclass('public.quant_operational_status') is not null
    and to_regclass('public.quant_risk_limits') is not null
    and to_regclass('public.quant_risk_events') is not null
    and to_regclass('public.quant_daily_briefs') is not null
  ) as all_required_objects_ready;

grant select on public.quant_enterprise_2_1_readiness to anon, authenticated;

-- Ask PostgREST to refresh its schema cache immediately.
notify pgrst, 'reload schema';

commit;

select
  'GPT Quant Enterprise 2.1 Database Pack setup complete' as result,
  all_required_objects_ready,
  v22_market_state_ready,
  v22_directives_ready,
  enterprise_core_ready,
  operational_status_ready,
  risk_limits_ready,
  daily_briefs_ready
from public.quant_enterprise_2_1_readiness;
