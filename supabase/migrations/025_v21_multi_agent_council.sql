-- GPT Quant V21 Multi-Agent Investment Council
-- Copy the entire file into Supabase SQL Editor and press Run.

alter table public.autotrader_configs_v13
  add column if not exists council_buy_threshold numeric not null default 60,
  add column if not exists council_min_agreement_pct numeric not null default 66,
  add column if not exists council_risk_veto_score numeric not null default 65,
  add column if not exists council_auto_propose boolean not null default true;

create table if not exists public.agent_opinions_v21 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  council_date date not null,
  stock_id bigint,
  symbol text not null,
  name text,
  agent_name text not null,
  agent_role text not null,
  score numeric not null default 0,
  vote text not null,
  confidence numeric not null default 0,
  veto boolean not null default false,
  rationale text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists agent_opinions_v21_uidx
on public.agent_opinions_v21(
  account_name,
  council_date,
  symbol,
  agent_name
);

create table if not exists public.investment_council_decisions_v21 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  council_date date not null,
  stock_id bigint,
  symbol text not null,
  name text,
  consensus_score numeric not null default 0,
  agreement_pct numeric not null default 0,
  dispersion numeric not null default 0,
  bullish_votes integer not null default 0,
  neutral_votes integer not null default 0,
  bearish_votes integer not null default 0,
  veto_count integer not null default 0,
  final_decision text not null,
  conviction text not null,
  target_weight numeric not null default 0,
  cio_memo text not null,
  order_id uuid references public.trade_orders_v13(id) on delete set null,
  created_at timestamptz not null default now()
);

create unique index if not exists investment_council_decisions_v21_uidx
on public.investment_council_decisions_v21(
  account_name,
  council_date,
  symbol
);

create table if not exists public.council_reports_v21 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_date date not null,
  market_posture text not null,
  symbols_reviewed integer not null default 0,
  buy_decisions integer not null default 0,
  hold_decisions integer not null default 0,
  avoid_decisions integer not null default 0,
  vetoed_decisions integer not null default 0,
  average_consensus numeric not null default 0,
  chief_investment_officer_message text not null,
  dissent_summary text not null,
  execution_guidance text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists council_reports_v21_uidx
on public.council_reports_v21(account_name, report_date);

alter table public.agent_opinions_v21 enable row level security;
alter table public.investment_council_decisions_v21 enable row level security;
alter table public.council_reports_v21 enable row level security;

drop policy if exists "v21 read agent opinions"
on public.agent_opinions_v21;
drop policy if exists "v21 read council decisions"
on public.investment_council_decisions_v21;
drop policy if exists "v21 read council reports"
on public.council_reports_v21;

create policy "v21 read agent opinions"
on public.agent_opinions_v21
for select to anon, authenticated
using (true);

create policy "v21 read council decisions"
on public.investment_council_decisions_v21
for select to anon, authenticated
using (true);

create policy "v21 read council reports"
on public.council_reports_v21
for select to anon, authenticated
using (true);

select 'V21 Multi-Agent Investment Council setup complete' as result;
