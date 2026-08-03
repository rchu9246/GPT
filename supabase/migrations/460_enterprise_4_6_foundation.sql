begin;
create extension if not exists pgcrypto;
create table if not exists public.performance_daily_v46 (
 id bigserial primary key, performance_date date not null,
 portfolio_id uuid not null references public.enterprise_portfolios_v40(id) on delete cascade,
 equity numeric not null default 0, daily_return_pct numeric not null default 0,
 cumulative_return_pct numeric not null default 0, rolling_volatility_pct numeric not null default 0,
 sharpe_ratio numeric not null default 0, sortino_ratio numeric not null default 0,
 calmar_ratio numeric not null default 0, max_drawdown_pct numeric not null default 0,
 win_rate numeric not null default 0, profit_factor numeric not null default 0,
 expectancy_pct numeric not null default 0, gross_exposure_pct numeric not null default 0,
 cash_ratio_pct numeric not null default 100, sample_count integer not null default 0,
 diagnostics jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create unique index if not exists performance_daily_v46_uidx on public.performance_daily_v46(performance_date,portfolio_id);

create table if not exists public.market_regime_v46 (
 id bigserial primary key, regime_date date not null unique,
 trend_regime text not null, volatility_regime text not null, risk_regime text not null,
 market_regime text not null, regime_confidence numeric not null default 0 check (regime_confidence between 0 and 100),
 benchmark_return_pct numeric not null default 0, realized_volatility_pct numeric not null default 0,
 drawdown_pct numeric not null default 0, breadth_score numeric not null default 50,
 liquidity_score numeric not null default 50, evidence jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.strategy_analytics_v46 (
 id bigserial primary key, analytics_date date not null,
 strategy_id uuid references public.enterprise_strategies_v40(id) on delete cascade,
 strategy_key text not null, sample_count integer not null default 0,
 alpha_pct numeric not null default 0, beta numeric not null default 0,
 volatility_pct numeric not null default 0, consistency_score numeric not null default 0,
 stability_score numeric not null default 0, learning_speed numeric not null default 0,
 confidence_drift numeric not null default 0, edge_score numeric not null default 0,
 regime_fit_score numeric not null default 0, analytics_status text not null,
 recommended_action text not null, diagnostics jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index if not exists strategy_analytics_v46_uidx on public.strategy_analytics_v46(analytics_date,strategy_key);

create table if not exists public.portfolio_health_v46 (
 id bigserial primary key, health_date date not null,
 portfolio_id uuid not null references public.enterprise_portfolios_v40(id) on delete cascade,
 health_score numeric not null default 0, risk_score numeric not null default 0,
 growth_score numeric not null default 0, liquidity_score numeric not null default 0,
 diversification_score numeric not null default 0, exposure_score numeric not null default 0,
 drawdown_score numeric not null default 0, learning_score numeric not null default 0,
 health_status text not null, blockers jsonb not null default '[]'::jsonb,
 recommendations jsonb not null default '[]'::jsonb, diagnostics jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create unique index if not exists portfolio_health_v46_uidx on public.portfolio_health_v46(health_date,portfolio_id);

create table if not exists public.market_replay_v46 (
 id uuid primary key default gen_random_uuid(), replay_date date not null,
 portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
 market_regime text not null, risk_status text not null, committee_status text not null,
 brain_status text not null, recommendation text not null, confidence numeric not null default 0,
 expected_return_pct numeric, realized_return_pct numeric, snapshot jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
create unique index if not exists market_replay_v46_uidx on public.market_replay_v46(replay_date,portfolio_id);

create table if not exists public.enterprise_dashboard_v46 (
 id bigserial primary key, dashboard_date date not null unique,
 overall_status text not null, market_regime text not null,
 portfolios_processed integer not null default 0, strategies_processed integer not null default 0,
 average_health_score numeric not null default 0, average_strategy_edge numeric not null default 0,
 open_decisions integer not null default 0, learning_feedback_records integer not null default 0,
 scheduler_status text not null, live_trading_enabled boolean not null default false,
 live_learning_enabled boolean not null default false, blockers jsonb not null default '[]'::jsonb,
 highlights jsonb not null default '[]'::jsonb, summary text not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 check (live_trading_enabled=false and live_learning_enabled=false)
);

create or replace function public.enterprise46_set_updated_at()
returns trigger language plpgsql security invoker set search_path=public as $$
begin new.updated_at=now(); return new; end; $$;

do $$
declare t text; p text;
begin
 foreach t in array array['performance_daily_v46','market_regime_v46','strategy_analytics_v46','portfolio_health_v46','enterprise_dashboard_v46']
 loop
  execute format('drop trigger if exists %I_set_updated_at on public.%I',t,t);
  execute format('create trigger %I_set_updated_at before update on public.%I for each row execute function public.enterprise46_set_updated_at()',t,t);
 end loop;
 foreach t in array array['performance_daily_v46','market_regime_v46','strategy_analytics_v46','portfolio_health_v46','market_replay_v46','enterprise_dashboard_v46']
 loop
  execute format('alter table public.%I enable row level security',t);
  p:='enterprise46 read '||t;
  execute format('drop policy if exists %I on public.%I',p,t);
  execute format('create policy %I on public.%I for select to anon,authenticated using (true)',p,t);
  execute format('grant select on public.%I to anon,authenticated',t);
 end loop;
end $$;
notify pgrst,'reload schema';
commit;
select 'GPT Quant Enterprise 4.6 Foundation setup complete' as result;
