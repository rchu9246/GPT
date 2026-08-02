-- GPT Quant Enterprise 4.5 Foundation
-- Decision Memory + Learning Engine + Strategy Rating
-- PAPER ONLY. Safe to execute repeatedly.

begin;

create table if not exists public.decision_memory_v45 (
  id uuid primary key default gen_random_uuid(),
  decision_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  source_decision_id uuid references public.explainable_decisions_v43(id) on delete set null,
  source_thesis_id uuid references public.investment_theses_v43(id) on delete set null,
  symbol text not null default 'PORTFOLIO',
  recommendation text not null,
  confidence numeric not null default 0,
  rationale text not null,
  market_regime text not null default 'UNKNOWN',
  risk_status text not null default 'UNKNOWN',
  expected_return_pct numeric,
  downside_risk_pct numeric,
  baseline_equity numeric,
  baseline_date date,
  evaluation_due_date date,
  realized_return_pct numeric,
  outcome_status text not null default 'OPEN',
  learning_score numeric not null default 0,
  lesson_summary text,
  feature_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  evaluated_at timestamptz
);

create unique index if not exists decision_memory_v45_uidx
on public.decision_memory_v45(decision_date, portfolio_id, symbol, source_decision_id);

create table if not exists public.learning_feedback_v45 (
  id uuid primary key default gen_random_uuid(),
  feedback_date date not null,
  decision_memory_id uuid not null references public.decision_memory_v45(id) on delete cascade,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  prediction text not null,
  expected_return_pct numeric,
  actual_return_pct numeric,
  prediction_error_pct numeric,
  outcome_status text not null,
  reward_value numeric not null default 0,
  penalty_value numeric not null default 0,
  confidence_before numeric not null default 0,
  confidence_after numeric not null default 0,
  confidence_delta numeric not null default 0,
  strategy_score_delta numeric not null default 0,
  lesson text not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists learning_feedback_v45_uidx
on public.learning_feedback_v45(feedback_date, decision_memory_id);

create table if not exists public.strategy_rating_v45 (
  id bigserial primary key,
  rating_date date not null,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete cascade,
  strategy_key text not null,
  sample_count integer not null default 0,
  wins integer not null default 0,
  losses integer not null default 0,
  neutrals integer not null default 0,
  win_rate numeric not null default 0,
  prediction_accuracy numeric not null default 0,
  average_return_pct numeric not null default 0,
  average_confidence numeric not null default 0,
  calibration_score numeric not null default 0,
  risk_adjusted_score numeric not null default 0,
  overall_score numeric not null default 0,
  rating_status text not null,
  recommended_action text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists strategy_rating_v45_uidx
on public.strategy_rating_v45(rating_date, strategy_key);

create table if not exists public.learning_cycle_status_v45 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  decisions_captured integer not null default 0,
  decisions_evaluated integer not null default 0,
  open_decisions integer not null default 0,
  wins integer not null default 0,
  losses integer not null default 0,
  neutrals integer not null default 0,
  feedback_records integer not null default 0,
  strategy_ratings integer not null default 0,
  live_learning_enabled boolean not null default false,
  live_trading_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  summary text not null,
  created_at timestamptz not null default now()
);

alter table public.decision_memory_v45 enable row level security;
alter table public.learning_feedback_v45 enable row level security;
alter table public.strategy_rating_v45 enable row level security;
alter table public.learning_cycle_status_v45 enable row level security;

drop policy if exists "enterprise45 read decision memory" on public.decision_memory_v45;
drop policy if exists "enterprise45 read feedback" on public.learning_feedback_v45;
drop policy if exists "enterprise45 read ratings" on public.strategy_rating_v45;
drop policy if exists "enterprise45 read cycle status" on public.learning_cycle_status_v45;

create policy "enterprise45 read decision memory"
on public.decision_memory_v45 for select to anon, authenticated using (true);

create policy "enterprise45 read feedback"
on public.learning_feedback_v45 for select to anon, authenticated using (true);

create policy "enterprise45 read ratings"
on public.strategy_rating_v45 for select to anon, authenticated using (true);

create policy "enterprise45 read cycle status"
on public.learning_cycle_status_v45 for select to anon, authenticated using (true);

notify pgrst, 'reload schema';
commit;

select 'GPT Quant Enterprise 4.5 Foundation setup complete' as result;
