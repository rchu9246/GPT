-- GPT Quant V18 AI Fund Manager
-- Copy this entire file into Supabase SQL Editor and press Run.

alter table public.autotrader_configs_v13
  add column if not exists target_cash_pct numeric not null default 30,
  add column if not exists min_position_pct numeric not null default 3,
  add column if not exists conviction_position_pct numeric not null default 12,
  add column if not exists max_sector_pct numeric not null default 35,
  add column if not exists ai_committee_enabled boolean not null default true;

create table if not exists public.ai_committee_decisions_v18 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  decision_date date not null,
  stock_id bigint,
  symbol text not null,
  name text,
  trend_vote numeric not null default 0,
  momentum_vote numeric not null default 0,
  quality_vote numeric not null default 0,
  risk_vote numeric not null default 0,
  liquidity_vote numeric not null default 0,
  committee_score numeric not null default 0,
  conviction text not null,
  target_weight numeric not null default 0,
  cash_regime text not null,
  decision text not null,
  memo text,
  order_id uuid references public.trade_orders_v13(id) on delete set null,
  created_at timestamptz not null default now()
);

create unique index if not exists ai_committee_decisions_v18_uidx
on public.ai_committee_decisions_v18(
  account_name,
  decision_date,
  symbol
);

create table if not exists public.cio_reports_v18 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_date date not null,
  market_regime text not null,
  target_cash_pct numeric not null,
  portfolio_equity numeric not null default 0,
  portfolio_exposure numeric not null default 0,
  proposed_orders integer not null default 0,
  approved_orders integer not null default 0,
  positions_count integer not null default 0,
  chief_message text not null,
  risk_message text not null,
  action_plan text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists cio_reports_v18_uidx
on public.cio_reports_v18(account_name, report_date);

alter table public.ai_committee_decisions_v18 enable row level security;
alter table public.cio_reports_v18 enable row level security;

drop policy if exists "v18 read committee" on public.ai_committee_decisions_v18;
drop policy if exists "v18 read cio reports" on public.cio_reports_v18;

create policy "v18 read committee"
on public.ai_committee_decisions_v18
for select to anon, authenticated
using (true);

create policy "v18 read cio reports"
on public.cio_reports_v18
for select to anon, authenticated
using (true);

select 'V18 AI Fund Manager setup complete' as result;
