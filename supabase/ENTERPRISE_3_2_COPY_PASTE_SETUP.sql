begin;
create table if not exists public.factor_library_v32 (
 id bigserial primary key, factor_key text not null, factor_version text not null default '1.0',
 factor_name text not null, factor_category text not null, description text not null,
 enabled boolean not null default true, weight numeric not null default 0, ic numeric,
 rank_ic numeric, hit_rate numeric, decay_score numeric, stability_score numeric,
 quality_score numeric not null default 0, latest_evaluation_date date,
 config jsonb not null default '{}'::jsonb, updated_at timestamptz not null default now(),
 created_at timestamptz not null default now());
create unique index if not exists factor_library_v32_uidx on public.factor_library_v32(factor_key,factor_version);

create table if not exists public.factor_observations_v32 (
 id bigserial primary key, account_name text not null default 'paper-main',
 observation_date date not null, symbol text not null, stock_id bigint,
 factor_key text not null, raw_value numeric, normalized_score numeric not null default 0,
 percentile numeric, source_table text, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now());
create unique index if not exists factor_observations_v32_uidx on public.factor_observations_v32(account_name,observation_date,symbol,factor_key);

create table if not exists public.factor_rankings_v32 (
 id bigserial primary key, account_name text not null default 'paper-main',
 ranking_date date not null, factor_key text not null, rank_position integer not null,
 quality_score numeric not null default 0, ic numeric, rank_ic numeric, stability_score numeric,
 recommendation text not null, created_at timestamptz not null default now());
create unique index if not exists factor_rankings_v32_uidx on public.factor_rankings_v32(account_name,ranking_date,factor_key);

create table if not exists public.portfolio_optimization_runs_v32 (
 id uuid primary key default gen_random_uuid(), account_name text not null default 'paper-main',
 optimization_date date not null, method text not null, status text not null,
 target_volatility numeric, estimated_volatility numeric, expected_return_score numeric,
 estimated_var_95 numeric, estimated_expected_shortfall numeric, turnover_pct numeric,
 cash_weight numeric, constraints jsonb not null default '{}'::jsonb,
 diagnostics jsonb not null default '{}'::jsonb, created_at timestamptz not null default now());
create unique index if not exists portfolio_optimization_runs_v32_uidx on public.portfolio_optimization_runs_v32(account_name,optimization_date,method);

create table if not exists public.portfolio_target_weights_v32 (
 id bigserial primary key, run_id uuid references public.portfolio_optimization_runs_v32(id) on delete cascade,
 account_name text not null default 'paper-main', optimization_date date not null,
 symbol text not null, stock_id bigint, current_weight numeric not null default 0,
 target_weight numeric not null default 0, delta_weight numeric not null default 0,
 risk_contribution numeric not null default 0, expected_return_score numeric not null default 0,
 action text not null, rationale text not null, created_at timestamptz not null default now());
create unique index if not exists portfolio_target_weights_v32_uidx on public.portfolio_target_weights_v32(account_name,optimization_date,symbol);

create table if not exists public.risk_snapshots_v32 (
 id bigserial primary key, account_name text not null default 'paper-main',
 snapshot_date date not null, equity numeric not null default 0,
 gross_exposure_pct numeric not null default 0, net_exposure_pct numeric not null default 0,
 var_95_pct numeric not null default 0, expected_shortfall_pct numeric not null default 0,
 max_drawdown_pct numeric not null default 0, stress_loss_pct numeric not null default 0,
 concentration_pct numeric not null default 0, liquidity_score numeric not null default 0,
 risk_score numeric not null default 0, risk_status text not null,
 breaches jsonb not null default '[]'::jsonb, diagnostics jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now());
create unique index if not exists risk_snapshots_v32_uidx on public.risk_snapshots_v32(account_name,snapshot_date);

alter table public.factor_library_v32 enable row level security;
alter table public.factor_observations_v32 enable row level security;
alter table public.factor_rankings_v32 enable row level security;
alter table public.portfolio_optimization_runs_v32 enable row level security;
alter table public.portfolio_target_weights_v32 enable row level security;
alter table public.risk_snapshots_v32 enable row level security;

drop policy if exists "enterprise32 read factor library" on public.factor_library_v32;
drop policy if exists "enterprise32 read factor observations" on public.factor_observations_v32;
drop policy if exists "enterprise32 read factor rankings" on public.factor_rankings_v32;
drop policy if exists "enterprise32 read optimization runs" on public.portfolio_optimization_runs_v32;
drop policy if exists "enterprise32 read target weights" on public.portfolio_target_weights_v32;
drop policy if exists "enterprise32 read risk snapshots" on public.risk_snapshots_v32;

create policy "enterprise32 read factor library" on public.factor_library_v32 for select to anon,authenticated using(true);
create policy "enterprise32 read factor observations" on public.factor_observations_v32 for select to anon,authenticated using(true);
create policy "enterprise32 read factor rankings" on public.factor_rankings_v32 for select to anon,authenticated using(true);
create policy "enterprise32 read optimization runs" on public.portfolio_optimization_runs_v32 for select to anon,authenticated using(true);
create policy "enterprise32 read target weights" on public.portfolio_target_weights_v32 for select to anon,authenticated using(true);
create policy "enterprise32 read risk snapshots" on public.risk_snapshots_v32 for select to anon,authenticated using(true);

insert into public.factor_library_v32(factor_key,factor_version,factor_name,factor_category,description,enabled,weight)
values
 ('trend','1.0','Trend','TECHNICAL','Directional trend strength',true,0.25),
 ('momentum','1.0','Momentum','TECHNICAL','Recent return persistence',true,0.25),
 ('volume','1.0','Volume Confirmation','LIQUIDITY','Volume participation',true,0.15),
 ('quality','1.0','Quality Proxy','FUNDAMENTAL_PROXY','Internal quality proxy',true,0.15),
 ('risk_adjusted','1.0','Risk Adjusted Score','RISK','Reward adjusted by risk',true,0.20)
on conflict(factor_key,factor_version) do update set
 factor_name=excluded.factor_name,factor_category=excluded.factor_category,
 description=excluded.description,enabled=excluded.enabled,weight=excluded.weight,updated_at=now();

notify pgrst,'reload schema';
commit;
select 'GPT Quant Enterprise 3.2 Stable setup complete' as result;
