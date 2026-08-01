
begin;

create table if not exists public.risk_limits_v41 (
  id bigserial primary key,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete cascade,
  limit_key text not null,
  limit_value numeric,
  severity text not null default 'CRITICAL',
  action_on_breach text not null default 'BLOCK',
  enabled boolean not null default true,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists risk_limits_v41_uidx
on public.risk_limits_v41(
  coalesce(portfolio_id, '00000000-0000-0000-0000-000000000000'::uuid),
  coalesce(strategy_id, '00000000-0000-0000-0000-000000000000'::uuid),
  limit_key
);

create table if not exists public.portfolio_risk_v41 (
  id bigserial primary key,
  portfolio_id uuid not null references public.enterprise_portfolios_v40(id) on delete cascade,
  risk_date date not null,
  equity numeric not null default 0,
  daily_loss_pct numeric not null default 0,
  gross_exposure_pct numeric not null default 0,
  var_95_pct numeric not null default 0,
  expected_shortfall_pct numeric not null default 0,
  max_drawdown_pct numeric not null default 0,
  concentration_pct numeric not null default 0,
  liquidity_score numeric not null default 0,
  risk_score numeric not null default 0,
  risk_status text not null,
  breaches jsonb not null default '[]'::jsonb,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists portfolio_risk_v41_uidx
on public.portfolio_risk_v41(portfolio_id, risk_date);

create table if not exists public.strategy_risk_v41 (
  id bigserial primary key,
  strategy_id uuid not null references public.enterprise_strategies_v40(id) on delete cascade,
  risk_date date not null,
  allocation_weight numeric not null default 0,
  health_score numeric not null default 0,
  risk_score numeric not null default 0,
  risk_status text not null,
  breaches jsonb not null default '[]'::jsonb,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists strategy_risk_v41_uidx
on public.strategy_risk_v41(strategy_id, risk_date);

create table if not exists public.risk_events_v41 (
  id uuid primary key default gen_random_uuid(),
  event_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete cascade,
  event_type text not null,
  severity text not null,
  event_status text not null default 'OPEN',
  limit_key text,
  observed_value numeric,
  limit_value numeric,
  decision text not null,
  message text not null,
  metadata jsonb not null default '{}'::jsonb,
  opened_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table if not exists public.circuit_breakers_v41 (
  id bigserial primary key,
  breaker_key text not null unique,
  scope_type text not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete cascade,
  enabled boolean not null default true,
  breaker_status text not null default 'ARMED',
  trigger_action text not null default 'BLOCK_NEW_ORDERS',
  last_triggered_at timestamptz,
  trigger_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.risk_governor_decisions_v41 (
  id uuid primary key default gen_random_uuid(),
  decision_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete cascade,
  decision_scope text not null,
  requested_action text not null,
  decision text not null,
  rationale text not null,
  breaches jsonb not null default '[]'::jsonb,
  policy_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.risk_governor_status_v41 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  overall_risk_score numeric not null default 0,
  active_breakers integer not null default 0,
  open_critical_events integer not null default 0,
  open_warning_events integer not null default 0,
  portfolios_checked integer not null default 0,
  strategies_checked integer not null default 0,
  live_trading_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  summary text not null,
  created_at timestamptz not null default now()
);

insert into public.risk_limits_v41
  (portfolio_id, limit_key, limit_value, severity, action_on_breach)
select id, 'MAX_VAR_95_PCT', 3, 'CRITICAL', 'BLOCK'
from public.enterprise_portfolios_v40
on conflict do nothing;

insert into public.risk_limits_v41
  (portfolio_id, limit_key, limit_value, severity, action_on_breach)
select id, 'MAX_EXPECTED_SHORTFALL_PCT', 4, 'CRITICAL', 'BLOCK'
from public.enterprise_portfolios_v40
on conflict do nothing;

insert into public.risk_limits_v41
  (portfolio_id, limit_key, limit_value, severity, action_on_breach)
select id, 'MAX_DRAWDOWN_PCT', max_drawdown_pct, 'CRITICAL', 'TRIGGER_BREAKER'
from public.enterprise_portfolios_v40
on conflict do nothing;

insert into public.risk_limits_v41
  (portfolio_id, limit_key, limit_value, severity, action_on_breach)
select id, 'MAX_SINGLE_POSITION_PCT', max_position_pct, 'WARNING', 'REDUCE'
from public.enterprise_portfolios_v40
on conflict do nothing;

insert into public.circuit_breakers_v41
  (breaker_key, scope_type, portfolio_id, enabled, trigger_action)
select 'portfolio-' || portfolio_key || '-risk-breaker',
       'PORTFOLIO', id, true, 'BLOCK_NEW_ORDERS'
from public.enterprise_portfolios_v40
on conflict (breaker_key) do update
set enabled = true, updated_at = now();

insert into public.circuit_breakers_v41
  (breaker_key, scope_type, strategy_id, enabled, trigger_action)
select 'strategy-' || strategy_key || '-risk-breaker',
       'STRATEGY', id, true, 'PAUSE_STRATEGY'
from public.enterprise_strategies_v40
on conflict (breaker_key) do update
set enabled = true, updated_at = now();

alter table public.risk_limits_v41 enable row level security;
alter table public.portfolio_risk_v41 enable row level security;
alter table public.strategy_risk_v41 enable row level security;
alter table public.risk_events_v41 enable row level security;
alter table public.circuit_breakers_v41 enable row level security;
alter table public.risk_governor_decisions_v41 enable row level security;
alter table public.risk_governor_status_v41 enable row level security;

drop policy if exists "enterprise41 read risk limits" on public.risk_limits_v41;
drop policy if exists "enterprise41 read portfolio risk" on public.portfolio_risk_v41;
drop policy if exists "enterprise41 read strategy risk" on public.strategy_risk_v41;
drop policy if exists "enterprise41 read risk events" on public.risk_events_v41;
drop policy if exists "enterprise41 read circuit breakers" on public.circuit_breakers_v41;
drop policy if exists "enterprise41 read decisions" on public.risk_governor_decisions_v41;
drop policy if exists "enterprise41 read risk status" on public.risk_governor_status_v41;

create policy "enterprise41 read risk limits" on public.risk_limits_v41 for select to anon, authenticated using (true);
create policy "enterprise41 read portfolio risk" on public.portfolio_risk_v41 for select to anon, authenticated using (true);
create policy "enterprise41 read strategy risk" on public.strategy_risk_v41 for select to anon, authenticated using (true);
create policy "enterprise41 read risk events" on public.risk_events_v41 for select to anon, authenticated using (true);
create policy "enterprise41 read circuit breakers" on public.circuit_breakers_v41 for select to anon, authenticated using (true);
create policy "enterprise41 read decisions" on public.risk_governor_decisions_v41 for select to anon, authenticated using (true);
create policy "enterprise41 read risk status" on public.risk_governor_status_v41 for select to anon, authenticated using (true);

notify pgrst, 'reload schema';
commit;

select 'GPT Quant Enterprise 4.1 Stable setup complete' as result;
