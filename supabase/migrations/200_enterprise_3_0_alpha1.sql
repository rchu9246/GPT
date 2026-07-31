-- GPT Quant Enterprise 3.0 Alpha 1
-- Research Intelligence + Strategy Marketplace + CEO Dashboard foundation.
-- Safe to execute repeatedly. Existing Enterprise 2.1 data is preserved.

create table if not exists public.quant_research_sources (
  id bigserial primary key,
  source_key text not null unique,
  source_name text not null,
  source_type text not null,
  enabled boolean not null default true,
  reliability_score numeric not null default 50,
  source_url text,
  config jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.quant_research_items (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  research_date date not null,
  symbol text not null,
  stock_id bigint,
  item_type text not null,
  title text not null,
  summary text not null,
  sentiment text not null default 'NEUTRAL',
  impact_score numeric not null default 0,
  confidence numeric not null default 0,
  source_key text,
  source_reference text,
  evidence jsonb not null default '{}'::jsonb,
  status text not null default 'PUBLISHED',
  created_at timestamptz not null default now()
);

create unique index if not exists quant_research_items_uidx
on public.quant_research_items(
  account_name,
  research_date,
  symbol,
  item_type,
  title
);

create index if not exists quant_research_items_latest_idx
on public.quant_research_items(account_name, research_date desc, symbol);

create table if not exists public.quant_research_reports (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_date date not null,
  symbol text not null,
  stock_id bigint,
  report_version text not null default '3.0-alpha1',
  rating text not null,
  research_score numeric not null default 0,
  confidence numeric not null default 0,
  trend_view text not null,
  momentum_view text not null,
  risk_view text not null,
  catalyst_view text not null,
  thesis text not null,
  invalidation_conditions text not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_research_reports_uidx
on public.quant_research_reports(
  account_name,
  report_date,
  symbol,
  report_version
);

create index if not exists quant_research_reports_latest_idx
on public.quant_research_reports(account_name, report_date desc, research_score desc);

create table if not exists public.quant_events (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  event_date date not null,
  symbol text,
  stock_id bigint,
  event_type text not null,
  event_severity text not null default 'INFO',
  title text not null,
  description text not null,
  expected_direction text not null default 'NEUTRAL',
  impact_score numeric not null default 0,
  confidence numeric not null default 0,
  source_key text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_events_uidx
on public.quant_events(
  account_name,
  event_date,
  coalesce(symbol, ''),
  event_type,
  title
);

create index if not exists quant_events_latest_idx
on public.quant_events(account_name, event_date desc, event_severity);

create table if not exists public.quant_strategy_marketplace (
  id bigserial primary key,
  strategy_key text not null,
  strategy_version text not null,
  strategy_name text not null,
  strategy_type text not null,
  lifecycle_status text not null default 'RESEARCH',
  enabled boolean not null default false,
  author text not null default 'GPT Quant',
  description text not null,
  signal_count integer not null default 0,
  latest_signal_date date,
  cagr numeric,
  sharpe numeric,
  sortino numeric,
  max_drawdown numeric,
  win_rate numeric,
  quality_score numeric not null default 0,
  validation_status text not null default 'UNVERIFIED',
  config jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create unique index if not exists quant_strategy_marketplace_uidx
on public.quant_strategy_marketplace(strategy_key, strategy_version);

create index if not exists quant_strategy_marketplace_rank_idx
on public.quant_strategy_marketplace(enabled desc, quality_score desc);

create table if not exists public.quant_ceo_snapshots (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  snapshot_date date not null,
  platform_status text not null,
  market_posture text not null,
  director_action text not null,
  research_confidence numeric not null default 0,
  system_health numeric not null default 0,
  operational_score numeric not null default 0,
  equity numeric not null default 0,
  cash numeric not null default 0,
  total_return numeric not null default 0,
  max_drawdown numeric not null default 0,
  risk_events integer not null default 0,
  proposed_orders integer not null default 0,
  approved_orders integer not null default 0,
  filled_orders integer not null default 0,
  top_ideas jsonb not null default '[]'::jsonb,
  latest_actions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_ceo_snapshots_uidx
on public.quant_ceo_snapshots(account_name, snapshot_date);

insert into public.quant_research_sources
  (source_key, source_name, source_type, enabled, reliability_score)
values
  ('QUANT_SIGNAL', 'Enterprise Quant Signal Engine', 'INTERNAL', true, 90),
  ('PRICE_ACTION', 'Daily Price Action', 'INTERNAL', true, 85),
  ('RISK_ENGINE', 'Central Risk Engine', 'INTERNAL', true, 95),
  ('MANUAL_RESEARCH', 'Manual Research Input', 'MANUAL', true, 70)
on conflict (source_key) do update
set
  source_name = excluded.source_name,
  source_type = excluded.source_type,
  enabled = excluded.enabled,
  reliability_score = excluded.reliability_score,
  updated_at = now();

alter table public.quant_research_sources enable row level security;
alter table public.quant_research_items enable row level security;
alter table public.quant_research_reports enable row level security;
alter table public.quant_events enable row level security;
alter table public.quant_strategy_marketplace enable row level security;
alter table public.quant_ceo_snapshots enable row level security;

drop policy if exists "enterprise30 read research sources" on public.quant_research_sources;
drop policy if exists "enterprise30 read research items" on public.quant_research_items;
drop policy if exists "enterprise30 read research reports" on public.quant_research_reports;
drop policy if exists "enterprise30 read events" on public.quant_events;
drop policy if exists "enterprise30 read strategies" on public.quant_strategy_marketplace;
drop policy if exists "enterprise30 read ceo snapshots" on public.quant_ceo_snapshots;

create policy "enterprise30 read research sources"
on public.quant_research_sources for select to anon, authenticated using (true);
create policy "enterprise30 read research items"
on public.quant_research_items for select to anon, authenticated using (true);
create policy "enterprise30 read research reports"
on public.quant_research_reports for select to anon, authenticated using (true);
create policy "enterprise30 read events"
on public.quant_events for select to anon, authenticated using (true);
create policy "enterprise30 read strategies"
on public.quant_strategy_marketplace for select to anon, authenticated using (true);
create policy "enterprise30 read ceo snapshots"
on public.quant_ceo_snapshots for select to anon, authenticated using (true);

notify pgrst, 'reload schema';

select 'GPT Quant Enterprise 3.0 Alpha 1 setup complete' as result;
