create table if not exists public.gpt_quant_v9_risk_portfolio_state (
  id uuid primary key default gen_random_uuid(), state_date date not null unique,
  daily_pnl numeric not null default 0, portfolio_drawdown numeric not null default 0,
  gross_exposure numeric not null default 0, net_exposure numeric not null default 0,
  open_positions integer not null default 0, metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.gpt_quant_v9_risk_decisions (
  id uuid primary key, risk_date date not null, sizing_result_id uuid not null,
  ranking_id uuid, source_version_no text, rank_no integer,
  proposed_position_size numeric not null, approved_position_size numeric not null,
  position_var numeric not null default 0, risk_decision text not null,
  blockers jsonb not null default '[]'::jsonb, warnings jsonb not null default '[]'::jsonb,
  risk_metrics jsonb not null default '{}'::jsonb, kill_switch_active boolean not null default false,
  paper_only boolean not null default true, live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false, engine_version text not null,
  calculated_at timestamptz not null default now(), created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(), unique (risk_date, sizing_result_id),
  check (approved_position_size >= 0 and approved_position_size <= 0.25),
  check (paper_only = true and live_trading_enabled = false and broker_submission_enabled = false)
);

create table if not exists public.gpt_quant_v9_risk_summaries (
  id uuid primary key, risk_date date not null unique, daily_pnl numeric not null default 0,
  portfolio_drawdown numeric not null default 0, max_single_position numeric not null,
  max_total_exposure numeric not null, max_open_positions integer not null,
  daily_loss_limit numeric not null, portfolio_drawdown_limit numeric not null,
  max_var_per_position numeric not null, approved_total_exposure numeric not null default 0,
  estimated_total_var numeric not null default 0, approved_positions integer not null default 0,
  blocked_positions integer not null default 0, kill_switch_active boolean not null default false,
  kill_switch_reasons jsonb not null default '[]'::jsonb, exposure_scale numeric not null default 1,
  paper_only boolean not null default true, live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false, engine_version text not null,
  calculated_at timestamptz not null default now(), created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (paper_only = true and live_trading_enabled = false and broker_submission_enabled = false)
);

insert into public.gpt_quant_v9_risk_portfolio_state (state_date)
values (current_date) on conflict (state_date) do nothing;

alter table public.gpt_quant_v9_risk_portfolio_state enable row level security;
alter table public.gpt_quant_v9_risk_decisions enable row level security;
alter table public.gpt_quant_v9_risk_summaries enable row level security;

drop policy if exists "service role manages risk portfolio state" on public.gpt_quant_v9_risk_portfolio_state;
create policy "service role manages risk portfolio state" on public.gpt_quant_v9_risk_portfolio_state for all to service_role using (true) with check (true);
drop policy if exists "service role manages risk decisions" on public.gpt_quant_v9_risk_decisions;
create policy "service role manages risk decisions" on public.gpt_quant_v9_risk_decisions for all to service_role using (true) with check (true);
drop policy if exists "service role manages risk summaries" on public.gpt_quant_v9_risk_summaries;
create policy "service role manages risk summaries" on public.gpt_quant_v9_risk_summaries for all to service_role using (true) with check (true);
