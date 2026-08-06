create table if not exists public.gpt_quant_v91_confidence_calibration (
  ranking_id uuid primary key,
  raw_confidence numeric not null,
  historical_percentile numeric not null,
  z_score numeric not null,
  calibrated_confidence numeric not null,
  consistency_penalty numeric not null default 0,
  final_confidence numeric not null,
  governed_recommendation text not null,
  engine_version text not null,
  calculated_at timestamptz not null default now()
);

create table if not exists public.gpt_quant_v91_adaptive_risk_state (
  state_date date primary key,
  base_risk_budget numeric not null,
  adaptive_risk_budget numeric not null,
  pnl_multiplier numeric not null,
  drawdown_multiplier numeric not null,
  var_multiplier numeric not null,
  daily_pnl numeric not null default 0,
  portfolio_drawdown numeric not null default 0,
  estimated_total_var numeric not null default 0,
  risk_regime text not null,
  kill_switch_active boolean not null default false,
  paper_only boolean not null default true,
  live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false,
  engine_version text not null,
  calculated_at timestamptz not null default now()
);

create table if not exists public.gpt_quant_v91_portfolio_allocations (
  allocation_date date not null,
  ranking_id uuid not null,
  final_confidence numeric not null,
  governed_recommendation text not null,
  raw_weight numeric not null,
  optimized_weight numeric not null,
  risk_budget numeric not null,
  paper_only boolean not null default true,
  live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false,
  engine_version text not null,
  calculated_at timestamptz not null default now(),
  primary key (allocation_date, ranking_id)
);

create table if not exists public.gpt_quant_v91_paper_sessions (
  id uuid primary key,
  session_date date not null unique,
  starting_equity numeric not null,
  ending_equity numeric not null,
  realized_pnl numeric not null default 0,
  unrealized_pnl numeric not null default 0,
  gross_exposure numeric not null default 0,
  open_positions integer not null default 0,
  session_status text not null,
  paper_only boolean not null default true,
  live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false,
  engine_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gpt_quant_v91_paper_positions (
  id uuid primary key,
  session_id uuid not null references public.gpt_quant_v91_paper_sessions(id),
  position_date date not null,
  ranking_id uuid not null,
  target_weight numeric not null,
  filled_weight numeric not null,
  entry_price numeric,
  mark_price numeric,
  unrealized_pnl numeric not null default 0,
  position_status text not null,
  paper_only boolean not null default true,
  live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false,
  engine_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(position_date, ranking_id)
);

alter table public.gpt_quant_v91_confidence_calibration enable row level security;
alter table public.gpt_quant_v91_adaptive_risk_state enable row level security;
alter table public.gpt_quant_v91_portfolio_allocations enable row level security;
alter table public.gpt_quant_v91_paper_sessions enable row level security;
alter table public.gpt_quant_v91_paper_positions enable row level security;

drop policy if exists "service v91 confidence" on public.gpt_quant_v91_confidence_calibration;
create policy "service v91 confidence" on public.gpt_quant_v91_confidence_calibration for all to service_role using(true) with check(true);
drop policy if exists "service v91 risk" on public.gpt_quant_v91_adaptive_risk_state;
create policy "service v91 risk" on public.gpt_quant_v91_adaptive_risk_state for all to service_role using(true) with check(true);
drop policy if exists "service v91 allocations" on public.gpt_quant_v91_portfolio_allocations;
create policy "service v91 allocations" on public.gpt_quant_v91_portfolio_allocations for all to service_role using(true) with check(true);
drop policy if exists "service v91 sessions" on public.gpt_quant_v91_paper_sessions;
create policy "service v91 sessions" on public.gpt_quant_v91_paper_sessions for all to service_role using(true) with check(true);
drop policy if exists "service v91 positions" on public.gpt_quant_v91_paper_positions;
create policy "service v91 positions" on public.gpt_quant_v91_paper_positions for all to service_role using(true) with check(true);
