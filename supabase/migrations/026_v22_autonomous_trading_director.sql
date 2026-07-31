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

select 'V22 Autonomous Trading Director setup complete' as result;
