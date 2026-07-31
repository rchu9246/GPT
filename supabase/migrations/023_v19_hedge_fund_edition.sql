-- GPT Quant V19 Hedge Fund Edition
-- Copy this entire file into Supabase SQL Editor and press Run.

alter table public.autotrader_configs_v13
  add column if not exists var_limit_pct numeric not null default 3,
  add column if not exists max_gross_exposure_pct numeric not null default 100,
  add column if not exists max_net_exposure_pct numeric not null default 85,
  add column if not exists kelly_fraction_cap numeric not null default 0.25,
  add column if not exists risk_parity_enabled boolean not null default true,
  add column if not exists regime_switch_enabled boolean not null default true;

create table if not exists public.hedge_fund_allocations_v19 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  allocation_date date not null,
  strategy_name text not null,
  strategy_weight numeric not null default 0,
  expected_return numeric not null default 0,
  expected_volatility numeric not null default 0,
  risk_contribution numeric not null default 0,
  regime text not null,
  allocation_reason text,
  created_at timestamptz not null default now()
);

create unique index if not exists hedge_fund_allocations_v19_uidx
on public.hedge_fund_allocations_v19(
  account_name,
  allocation_date,
  strategy_name
);

create table if not exists public.risk_snapshots_v19 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  snapshot_date date not null,
  equity numeric not null default 0,
  cash numeric not null default 0,
  gross_exposure numeric not null default 0,
  net_exposure numeric not null default 0,
  daily_var_95 numeric not null default 0,
  daily_var_99 numeric not null default 0,
  expected_shortfall_95 numeric not null default 0,
  max_drawdown numeric not null default 0,
  volatility_20d numeric not null default 0,
  sharpe_20d numeric not null default 0,
  risk_status text not null,
  risk_message text,
  created_at timestamptz not null default now()
);

create unique index if not exists risk_snapshots_v19_uidx
on public.risk_snapshots_v19(account_name, snapshot_date);

create table if not exists public.hedge_fund_reports_v19 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_date date not null,
  market_regime text not null,
  portfolio_style text not null,
  target_cash_pct numeric not null default 0,
  recommended_gross_exposure numeric not null default 0,
  recommended_net_exposure numeric not null default 0,
  chief_risk_officer_message text not null,
  portfolio_manager_message text not null,
  execution_plan text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists hedge_fund_reports_v19_uidx
on public.hedge_fund_reports_v19(account_name, report_date);

alter table public.hedge_fund_allocations_v19 enable row level security;
alter table public.risk_snapshots_v19 enable row level security;
alter table public.hedge_fund_reports_v19 enable row level security;

drop policy if exists "v19 read allocations" on public.hedge_fund_allocations_v19;
drop policy if exists "v19 read risk snapshots" on public.risk_snapshots_v19;
drop policy if exists "v19 read hedge reports" on public.hedge_fund_reports_v19;

create policy "v19 read allocations"
on public.hedge_fund_allocations_v19
for select to anon, authenticated
using (true);

create policy "v19 read risk snapshots"
on public.risk_snapshots_v19
for select to anon, authenticated
using (true);

create policy "v19 read hedge reports"
on public.hedge_fund_reports_v19
for select to anon, authenticated
using (true);

select 'V19 Hedge Fund Edition setup complete' as result;
