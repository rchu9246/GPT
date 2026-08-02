-- GPT Quant Enterprise 4.4 Stable
-- Portfolio Brain, decision memory, trade replay, pattern learning,
-- confidence calibration, strategy evolution and self-learning.
-- PAPER ONLY. Safe to execute repeatedly.

begin;

create table if not exists public.portfolio_brain_snapshots_v44 (
  id bigserial primary key,
  snapshot_date date not null,
  portfolio_id uuid not null references public.enterprise_portfolios_v40(id) on delete cascade,
  market_regime text not null default 'UNKNOWN',
  brain_status text not null,
  memory_records integer not null default 0,
  replay_records integer not null default 0,
  win_patterns integer not null default 0,
  mistake_patterns integer not null default 0,
  calibrated_confidence numeric not null default 50,
  learning_score numeric not null default 0,
  recommended_action text not null default 'HOLD',
  risk_override boolean not null default false,
  summary text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists portfolio_brain_snapshots_v44_uidx
on public.portfolio_brain_snapshots_v44(snapshot_date, portfolio_id);

create table if not exists public.decision_memory_v44 (
  id uuid primary key default gen_random_uuid(),
  memory_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  source_decision_id uuid references public.explainable_decisions_v43(id) on delete set null,
  symbol text not null default 'PORTFOLIO',
  decision_action text not null,
  original_confidence numeric not null default 0,
  market_regime text not null default 'UNKNOWN',
  risk_status text not null default 'UNKNOWN',
  expected_return_pct numeric,
  downside_risk_pct numeric,
  realized_return_pct numeric,
  outcome_status text not null default 'PENDING',
  lesson_type text,
  lesson_summary text,
  feature_snapshot jsonb not null default '{}'::jsonb,
  retained_weight numeric not null default 1,
  created_at timestamptz not null default now(),
  evaluated_at timestamptz
);

create unique index if not exists decision_memory_v44_uidx
on public.decision_memory_v44(memory_date, portfolio_id, symbol, source_decision_id);

create table if not exists public.trade_replay_v44 (
  id uuid primary key default gen_random_uuid(),
  replay_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  source_memory_id uuid references public.decision_memory_v44(id) on delete cascade,
  symbol text not null,
  original_action text not null,
  original_confidence numeric not null default 0,
  original_target_weight numeric not null default 0,
  simulated_entry_price numeric,
  simulated_exit_price numeric,
  simulated_return_pct numeric,
  max_favorable_excursion_pct numeric,
  max_adverse_excursion_pct numeric,
  replay_status text not null,
  outcome_class text not null,
  replay_notes text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists trade_replay_v44_uidx
on public.trade_replay_v44(replay_date, source_memory_id, symbol);

create table if not exists public.learning_patterns_v44 (
  id uuid primary key default gen_random_uuid(),
  pattern_date date not null,
  pattern_key text not null,
  pattern_type text not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  market_regime text,
  sample_count integer not null default 0,
  success_rate numeric not null default 0,
  average_return_pct numeric not null default 0,
  average_drawdown_pct numeric not null default 0,
  confidence_score numeric not null default 0,
  pattern_status text not null default 'ACTIVE',
  conditions jsonb not null default '{}'::jsonb,
  lesson text not null,
  recommended_adjustment jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists learning_patterns_v44_uidx
on public.learning_patterns_v44(pattern_date, pattern_key, portfolio_id);

create table if not exists public.confidence_calibration_v44 (
  id bigserial primary key,
  calibration_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  original_confidence numeric not null default 0,
  calibrated_confidence numeric not null default 0,
  reliability_score numeric not null default 0,
  sample_count integer not null default 0,
  win_rate numeric not null default 0,
  average_error numeric not null default 0,
  calibration_status text not null,
  calibration_curve jsonb not null default '{}'::jsonb,
  rationale text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists confidence_calibration_v44_uidx
on public.confidence_calibration_v44(calibration_date, portfolio_id, strategy_id);

create table if not exists public.strategy_evolution_v44 (
  id uuid primary key default gen_random_uuid(),
  evolution_date date not null,
  strategy_id uuid not null references public.enterprise_strategies_v40(id) on delete cascade,
  current_version text,
  candidate_version text not null,
  current_score numeric not null default 0,
  candidate_score numeric not null default 0,
  learning_score numeric not null default 0,
  evolution_action text not null,
  paper_approved boolean not null default false,
  live_approved boolean not null default false,
  parameter_changes jsonb not null default '{}'::jsonb,
  supporting_patterns jsonb not null default '[]'::jsonb,
  risks jsonb not null default '[]'::jsonb,
  rationale text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists strategy_evolution_v44_uidx
on public.strategy_evolution_v44(evolution_date, strategy_id, candidate_version);

create table if not exists public.learning_feedback_v44 (
  id bigserial primary key,
  feedback_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  source_type text not null,
  source_key text not null,
  feedback_type text not null,
  signal_value numeric,
  reward_value numeric not null default 0,
  penalty_value numeric not null default 0,
  applied boolean not null default false,
  application_target text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists learning_feedback_v44_uidx
on public.learning_feedback_v44(feedback_date, source_type, source_key, feedback_type);

create table if not exists public.self_learning_status_v44 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  portfolios_processed integer not null default 0,
  memories_captured integer not null default 0,
  replays_completed integer not null default 0,
  win_patterns_found integer not null default 0,
  mistake_patterns_found integer not null default 0,
  calibrations_generated integer not null default 0,
  evolutions_proposed integer not null default 0,
  live_learning_enabled boolean not null default false,
  live_trading_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  summary text not null,
  created_at timestamptz not null default now()
);

alter table public.portfolio_brain_snapshots_v44 enable row level security;
alter table public.decision_memory_v44 enable row level security;
alter table public.trade_replay_v44 enable row level security;
alter table public.learning_patterns_v44 enable row level security;
alter table public.confidence_calibration_v44 enable row level security;
alter table public.strategy_evolution_v44 enable row level security;
alter table public.learning_feedback_v44 enable row level security;
alter table public.self_learning_status_v44 enable row level security;

drop policy if exists "enterprise44 read brain" on public.portfolio_brain_snapshots_v44;
drop policy if exists "enterprise44 read memory" on public.decision_memory_v44;
drop policy if exists "enterprise44 read replay" on public.trade_replay_v44;
drop policy if exists "enterprise44 read patterns" on public.learning_patterns_v44;
drop policy if exists "enterprise44 read calibration" on public.confidence_calibration_v44;
drop policy if exists "enterprise44 read evolution" on public.strategy_evolution_v44;
drop policy if exists "enterprise44 read feedback" on public.learning_feedback_v44;
drop policy if exists "enterprise44 read status" on public.self_learning_status_v44;

create policy "enterprise44 read brain" on public.portfolio_brain_snapshots_v44 for select to anon, authenticated using (true);
create policy "enterprise44 read memory" on public.decision_memory_v44 for select to anon, authenticated using (true);
create policy "enterprise44 read replay" on public.trade_replay_v44 for select to anon, authenticated using (true);
create policy "enterprise44 read patterns" on public.learning_patterns_v44 for select to anon, authenticated using (true);
create policy "enterprise44 read calibration" on public.confidence_calibration_v44 for select to anon, authenticated using (true);
create policy "enterprise44 read evolution" on public.strategy_evolution_v44 for select to anon, authenticated using (true);
create policy "enterprise44 read feedback" on public.learning_feedback_v44 for select to authenticated using (true);
create policy "enterprise44 read status" on public.self_learning_status_v44 for select to anon, authenticated using (true);

notify pgrst, 'reload schema';
commit;

select 'GPT Quant Enterprise 4.4 Stable setup complete' as result;
