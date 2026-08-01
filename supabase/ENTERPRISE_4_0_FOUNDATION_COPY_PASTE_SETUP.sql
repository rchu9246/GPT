-- GPT Quant Enterprise 4.0 Foundation Pack
-- Portfolio / Strategy Registry, Run Tracking, Audit, Regime Foundation,
-- compatibility views and stable release foundation.
-- Safe to execute repeatedly. Existing 3.x data is preserved.

begin;

create table if not exists public.enterprise_portfolios_v40 (
  id uuid primary key default gen_random_uuid(),
  portfolio_key text not null unique,
  portfolio_name text not null,
  account_name text not null default 'paper-main',
  portfolio_type text not null default 'PAPER',
  lifecycle_status text not null default 'ACTIVE',
  base_currency text not null default 'TWD',
  starting_cash numeric not null default 1000000,
  target_volatility_pct numeric,
  reserve_cash_pct numeric not null default 30,
  max_positions integer not null default 5,
  max_position_pct numeric not null default 15,
  max_drawdown_pct numeric not null default 12,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.enterprise_strategies_v40 (
  id uuid primary key default gen_random_uuid(),
  strategy_key text not null unique,
  strategy_name text not null,
  strategy_family text not null,
  lifecycle_status text not null default 'RESEARCH',
  enabled boolean not null default false,
  paper_approved boolean not null default false,
  live_approved boolean not null default false,
  description text not null,
  owner text not null default 'GPT Quant',
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.enterprise_strategy_versions_v40 (
  id uuid primary key default gen_random_uuid(),
  strategy_id uuid not null references public.enterprise_strategies_v40(id) on delete cascade,
  version text not null,
  code_reference text,
  parameter_schema jsonb not null default '{}'::jsonb,
  parameters jsonb not null default '{}'::jsonb,
  validation_status text not null default 'UNVERIFIED',
  backtest_status text not null default 'NOT_RUN',
  walk_forward_status text not null default 'NOT_RUN',
  paper_status text not null default 'NOT_RUN',
  active boolean not null default false,
  created_at timestamptz not null default now()
);

create unique index if not exists enterprise_strategy_versions_v40_uidx
on public.enterprise_strategy_versions_v40(strategy_id, version);

create table if not exists public.enterprise_portfolio_strategies_v40 (
  id bigserial primary key,
  portfolio_id uuid not null references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid not null references public.enterprise_strategies_v40(id) on delete cascade,
  enabled boolean not null default true,
  allocation_weight numeric not null default 0,
  min_allocation_weight numeric not null default 0,
  max_allocation_weight numeric not null default 100,
  regime_overrides jsonb not null default '{}'::jsonb,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists enterprise_portfolio_strategies_v40_uidx
on public.enterprise_portfolio_strategies_v40(portfolio_id, strategy_id);

create table if not exists public.enterprise_runs_v40 (
  id uuid primary key default gen_random_uuid(),
  run_key text not null unique,
  run_date date not null,
  run_type text not null,
  release_version text not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id),
  status text not null default 'RUNNING',
  current_stage text,
  idempotency_key text not null unique,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  blockers jsonb not null default '[]'::jsonb,
  error_message text
);

create index if not exists enterprise_runs_v40_latest_idx
on public.enterprise_runs_v40(run_date desc, started_at desc);

create table if not exists public.enterprise_run_stages_v40 (
  id bigserial primary key,
  run_id uuid not null references public.enterprise_runs_v40(id) on delete cascade,
  stage_key text not null,
  stage_order integer not null,
  status text not null default 'PENDING',
  critical boolean not null default true,
  started_at timestamptz,
  completed_at timestamptz,
  input_summary jsonb not null default '{}'::jsonb,
  output_summary jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now()
);

create unique index if not exists enterprise_run_stages_v40_uidx
on public.enterprise_run_stages_v40(run_id, stage_key);

create table if not exists public.audit_logs_v40 (
  id bigserial primary key,
  event_time timestamptz not null default now(),
  actor_type text not null default 'SYSTEM',
  actor_key text not null default 'enterprise-v40',
  action text not null,
  entity_type text not null,
  entity_key text not null,
  run_id uuid references public.enterprise_runs_v40(id) on delete set null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete set null,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  severity text not null default 'INFO',
  before_state jsonb,
  after_state jsonb,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists audit_logs_v40_latest_idx
on public.audit_logs_v40(event_time desc, severity);

create table if not exists public.market_regimes_v40 (
  id bigserial primary key,
  regime_date date not null,
  market_key text not null default 'TWSE',
  regime text not null,
  confidence numeric not null default 0,
  trend_score numeric not null default 0,
  breadth_score numeric not null default 0,
  volatility_score numeric not null default 0,
  momentum_score numeric not null default 0,
  drawdown_score numeric not null default 0,
  rationale text not null,
  features jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists market_regimes_v40_uidx
on public.market_regimes_v40(regime_date, market_key);

create table if not exists public.market_regime_features_v40 (
  id bigserial primary key,
  regime_date date not null,
  market_key text not null default 'TWSE',
  feature_key text not null,
  raw_value numeric,
  normalized_score numeric not null default 0,
  source_reference text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists market_regime_features_v40_uidx
on public.market_regime_features_v40(regime_date, market_key, feature_key);

create table if not exists public.strategy_regime_allocations_v40 (
  id bigserial primary key,
  strategy_id uuid not null references public.enterprise_strategies_v40(id) on delete cascade,
  regime text not null,
  target_weight numeric not null default 0,
  enabled boolean not null default true,
  rationale text not null,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists strategy_regime_allocations_v40_uidx
on public.strategy_regime_allocations_v40(strategy_id, regime);

create table if not exists public.release_status_v40 (
  id bigserial primary key,
  release_date date not null,
  release_version text not null,
  foundation_ready boolean not null default false,
  registry_ready boolean not null default false,
  run_tracking_ready boolean not null default false,
  audit_ready boolean not null default false,
  regime_ready boolean not null default false,
  compatibility_ready boolean not null default false,
  live_trading_enabled boolean not null default false,
  readiness_score numeric not null default 0,
  blockers jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists release_status_v40_uidx
on public.release_status_v40(release_date, release_version);

insert into public.enterprise_portfolios_v40 (
  portfolio_key, portfolio_name, account_name, portfolio_type,
  lifecycle_status, starting_cash, reserve_cash_pct, max_positions,
  max_position_pct, max_drawdown_pct, config
)
values
  (
    'paper-balanced',
    'Paper Balanced Portfolio',
    'paper-main',
    'PAPER',
    'ACTIVE',
    1000000,
    30,
    5,
    15,
    12,
    '{"source":"enterprise-3.x","migration_mode":"parallel"}'::jsonb
  ),
  (
    'paper-research',
    'Paper Research Portfolio',
    'paper-research',
    'PAPER',
    'ACTIVE',
    1000000,
    50,
    10,
    10,
    15,
    '{"purpose":"strategy validation"}'::jsonb
  )
on conflict (portfolio_key) do update
set
  portfolio_name = excluded.portfolio_name,
  lifecycle_status = excluded.lifecycle_status,
  updated_at = now();

insert into public.enterprise_strategies_v40 (
  strategy_key, strategy_name, strategy_family, lifecycle_status,
  enabled, paper_approved, live_approved, description, config
)
values
  ('momentum', 'Momentum', 'MOMENTUM', 'PAPER', true, true, false, 'Momentum strategy adapter foundation', '{}'::jsonb),
  ('trend-following', 'Trend Following', 'TREND', 'PAPER', true, true, false, 'Trend following strategy adapter foundation', '{}'::jsonb),
  ('mean-reversion', 'Mean Reversion', 'MEAN_REVERSION', 'RESEARCH', false, false, false, 'Mean reversion research strategy', '{}'::jsonb),
  ('low-volatility', 'Low Volatility', 'DEFENSIVE', 'RESEARCH', false, false, false, 'Low volatility defensive strategy', '{}'::jsonb),
  ('risk-adjusted-composite', 'Risk Adjusted Composite', 'COMPOSITE', 'PAPER', true, true, false, 'Enterprise 3.x compatibility composite', '{"source":"signals"}'::jsonb)
on conflict (strategy_key) do update
set
  strategy_name = excluded.strategy_name,
  strategy_family = excluded.strategy_family,
  lifecycle_status = excluded.lifecycle_status,
  enabled = excluded.enabled,
  paper_approved = excluded.paper_approved,
  live_approved = false,
  updated_at = now();

insert into public.enterprise_strategy_versions_v40 (
  strategy_id, version, code_reference, validation_status,
  backtest_status, walk_forward_status, paper_status, active
)
select id, '1.0.0', 'foundation-adapter', 'FOUNDATION',
       'LEGACY_DATA_AVAILABLE', 'LEGACY_DATA_AVAILABLE',
       case when paper_approved then 'APPROVED' else 'NOT_RUN' end,
       enabled
from public.enterprise_strategies_v40
on conflict (strategy_id, version) do update
set active = excluded.active,
    paper_status = excluded.paper_status;

insert into public.strategy_regime_allocations_v40 (
  strategy_id, regime, target_weight, enabled, rationale
)
select s.id, x.regime, x.target_weight, true, x.rationale
from public.enterprise_strategies_v40 s
cross join (
  values
    ('BULL', 1.00::numeric, 'Full allocation in bullish regime'),
    ('SIDEWAYS', 0.60::numeric, 'Reduced allocation in sideways regime'),
    ('BEAR', 0.20::numeric, 'Defensive allocation in bearish regime'),
    ('HIGH_VOLATILITY', 0.25::numeric, 'Reduced allocation during high volatility'),
    ('RISK_OFF', 0.00::numeric, 'Disabled in risk-off regime'),
    ('UNKNOWN', 0.25::numeric, 'Conservative allocation while regime is unknown')
) as x(regime, target_weight, rationale)
where s.strategy_key in ('momentum', 'trend-following', 'risk-adjusted-composite')
on conflict (strategy_id, regime) do update
set target_weight = excluded.target_weight,
    rationale = excluded.rationale,
    updated_at = now();

create or replace view public.compat_portfolios_v40
with (security_invoker = true)
as
select
  p.id as portfolio_id,
  p.portfolio_key,
  p.portfolio_name,
  p.account_name,
  p.starting_cash,
  coalesce(ps.equity, p.starting_cash) as latest_equity,
  coalesce(ps.cash, p.starting_cash) as latest_cash,
  ps.snapshot_date as latest_snapshot_date
from public.enterprise_portfolios_v40 p
left join lateral (
  select snapshot_date, equity, cash
  from public.quant_portfolio_snapshots q
  where q.account_name = p.account_name
  order by snapshot_date desc
  limit 1
) ps on true;

create or replace view public.compat_strategies_v40
with (security_invoker = true)
as
select
  s.id as strategy_id,
  s.strategy_key,
  s.strategy_name,
  s.lifecycle_status,
  s.enabled,
  s.paper_approved,
  sm.strategy_version as legacy_strategy_version,
  sm.quality_score as legacy_quality_score,
  sm.signal_count as legacy_signal_count,
  sm.latest_signal_date as legacy_latest_signal_date
from public.enterprise_strategies_v40 s
left join lateral (
  select strategy_version, quality_score, signal_count, latest_signal_date
  from public.quant_strategy_marketplace
  where lower(strategy_key) = lower(s.strategy_key)
     or lower(strategy_version) = lower(s.strategy_key)
  order by updated_at desc
  limit 1
) sm on true;

alter table public.enterprise_portfolios_v40 enable row level security;
alter table public.enterprise_strategies_v40 enable row level security;
alter table public.enterprise_strategy_versions_v40 enable row level security;
alter table public.enterprise_portfolio_strategies_v40 enable row level security;
alter table public.enterprise_runs_v40 enable row level security;
alter table public.enterprise_run_stages_v40 enable row level security;
alter table public.audit_logs_v40 enable row level security;
alter table public.market_regimes_v40 enable row level security;
alter table public.market_regime_features_v40 enable row level security;
alter table public.strategy_regime_allocations_v40 enable row level security;
alter table public.release_status_v40 enable row level security;

drop policy if exists "enterprise40 read portfolios" on public.enterprise_portfolios_v40;
drop policy if exists "enterprise40 read strategies" on public.enterprise_strategies_v40;
drop policy if exists "enterprise40 read strategy versions" on public.enterprise_strategy_versions_v40;
drop policy if exists "enterprise40 read portfolio strategies" on public.enterprise_portfolio_strategies_v40;
drop policy if exists "enterprise40 read runs" on public.enterprise_runs_v40;
drop policy if exists "enterprise40 read run stages" on public.enterprise_run_stages_v40;
drop policy if exists "enterprise40 read audit" on public.audit_logs_v40;
drop policy if exists "enterprise40 read regimes" on public.market_regimes_v40;
drop policy if exists "enterprise40 read regime features" on public.market_regime_features_v40;
drop policy if exists "enterprise40 read regime allocations" on public.strategy_regime_allocations_v40;
drop policy if exists "enterprise40 read release status" on public.release_status_v40;

create policy "enterprise40 read portfolios" on public.enterprise_portfolios_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read strategies" on public.enterprise_strategies_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read strategy versions" on public.enterprise_strategy_versions_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read portfolio strategies" on public.enterprise_portfolio_strategies_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read runs" on public.enterprise_runs_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read run stages" on public.enterprise_run_stages_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read audit" on public.audit_logs_v40 for select to authenticated using (true);
create policy "enterprise40 read regimes" on public.market_regimes_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read regime features" on public.market_regime_features_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read regime allocations" on public.strategy_regime_allocations_v40 for select to anon, authenticated using (true);
create policy "enterprise40 read release status" on public.release_status_v40 for select to anon, authenticated using (true);

grant select on public.compat_portfolios_v40 to anon, authenticated;
grant select on public.compat_strategies_v40 to anon, authenticated;

notify pgrst, 'reload schema';

commit;

select 'GPT Quant Enterprise 4.0 Foundation Pack setup complete' as result;
