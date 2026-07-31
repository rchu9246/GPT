-- GPT Quant Enterprise 3.0 Release Candidate
-- Safe, repeatable upgrade for Alpha 1 installations.

create table if not exists public.quant_research_outcomes (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_id bigint references public.quant_research_reports(id) on delete cascade,
  report_date date not null,
  evaluation_date date not null,
  symbol text not null,
  original_rating text not null,
  original_score numeric not null default 0,
  reference_price numeric,
  evaluation_price numeric,
  return_pct numeric,
  benchmark_return_pct numeric,
  excess_return_pct numeric,
  hit boolean,
  holding_days integer not null default 0,
  outcome_status text not null default 'PENDING',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_research_outcomes_uidx
on public.quant_research_outcomes(report_id, evaluation_date);

create index if not exists quant_research_outcomes_latest_idx
on public.quant_research_outcomes(account_name, evaluation_date desc, symbol);

create table if not exists public.quant_portfolio_recommendations (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  recommendation_date date not null,
  symbol text not null,
  stock_id bigint,
  action text not null,
  target_weight numeric not null default 0,
  max_weight numeric not null default 0,
  expected_return_score numeric not null default 0,
  risk_score numeric not null default 0,
  conviction numeric not null default 0,
  sizing_method text not null,
  stop_loss_pct numeric,
  take_profit_pct numeric,
  suggested_holding_days integer,
  rationale text not null,
  constraints jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_portfolio_recommendations_uidx
on public.quant_portfolio_recommendations(
  account_name,
  recommendation_date,
  symbol
);

create table if not exists public.quant_explainability_records (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  explanation_date date not null,
  entity_type text not null,
  entity_key text not null,
  action text not null,
  positive_factors jsonb not null default '[]'::jsonb,
  negative_factors jsonb not null default '[]'::jsonb,
  risk_factors jsonb not null default '[]'::jsonb,
  thresholds jsonb not null default '{}'::jsonb,
  decision_path jsonb not null default '[]'::jsonb,
  natural_language_summary text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_explainability_records_uidx
on public.quant_explainability_records(
  account_name,
  explanation_date,
  entity_type,
  entity_key,
  action
);

create table if not exists public.quant_release_status (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  release_date date not null,
  release_version text not null,
  readiness_score numeric not null default 0,
  data_ready boolean not null default false,
  research_ready boolean not null default false,
  portfolio_ready boolean not null default false,
  risk_ready boolean not null default false,
  execution_ready boolean not null default false,
  reporting_ready boolean not null default false,
  dashboard_ready boolean not null default false,
  live_trading_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_release_status_uidx
on public.quant_release_status(account_name, release_date, release_version);

alter table public.quant_research_outcomes enable row level security;
alter table public.quant_portfolio_recommendations enable row level security;
alter table public.quant_explainability_records enable row level security;
alter table public.quant_release_status enable row level security;

drop policy if exists "enterprise30 read research outcomes" on public.quant_research_outcomes;
drop policy if exists "enterprise30 read portfolio recommendations" on public.quant_portfolio_recommendations;
drop policy if exists "enterprise30 read explainability" on public.quant_explainability_records;
drop policy if exists "enterprise30 read release status" on public.quant_release_status;

create policy "enterprise30 read research outcomes"
on public.quant_research_outcomes for select to anon, authenticated using (true);

create policy "enterprise30 read portfolio recommendations"
on public.quant_portfolio_recommendations for select to anon, authenticated using (true);

create policy "enterprise30 read explainability"
on public.quant_explainability_records for select to anon, authenticated using (true);

create policy "enterprise30 read release status"
on public.quant_release_status for select to anon, authenticated using (true);

notify pgrst, 'reload schema';

select 'GPT Quant Enterprise 3.0 Release Candidate setup complete' as result;
