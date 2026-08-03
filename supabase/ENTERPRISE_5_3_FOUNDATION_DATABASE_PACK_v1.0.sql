begin;

create extension if not exists pgcrypto;

create or replace function public.enterprise53_set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.learning_observations_v53 (
  id uuid primary key default gen_random_uuid(),
  observation_date date not null,
  observation_type text not null,
  source_module text not null,
  source_record_id uuid,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  agent_key text,
  strategy_key text,
  market_regime text,
  observed_value numeric,
  benchmark_value numeric,
  outcome_label text not null default 'INSUFFICIENT_DATA',
  confidence numeric not null default 0,
  evidence jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default now(),
  constraint learning_observations_v53_type_chk
    check (observation_type in ('DECISION','AGENT','STRATEGY','REGIME','EXECUTION')),
  constraint learning_observations_v53_label_chk
    check (outcome_label in ('CORRECT','PARTIALLY_CORRECT','INCORRECT','INSUFFICIENT_DATA')),
  constraint learning_observations_v53_conf_chk
    check (confidence between 0 and 100)
);

create table if not exists public.decision_outcomes_v53 (
  id uuid primary key default gen_random_uuid(),
  outcome_date date not null,
  council_decision_id uuid not null references public.decision_council_v51(id) on delete cascade,
  execution_plan_id uuid references public.execution_plans_v52(id) on delete set null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  original_decision text not null,
  realized_outcome text not null,
  outcome_label text not null,
  realized_return_pct numeric,
  realized_drawdown_pct numeric,
  realized_volatility_pct numeric,
  horizon_days integer not null default 0,
  decision_score numeric not null default 0,
  confidence_calibration_error numeric not null default 0,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint decision_outcomes_v53_label_chk
    check (outcome_label in ('CORRECT','PARTIALLY_CORRECT','INCORRECT','INSUFFICIENT_DATA')),
  constraint decision_outcomes_v53_score_chk
    check (decision_score between 0 and 100),
  constraint decision_outcomes_v53_horizon_chk
    check (horizon_days >= 0)
);

create unique index if not exists decision_outcomes_v53_uidx
on public.decision_outcomes_v53(outcome_date, council_decision_id, portfolio_id);

create table if not exists public.agent_feedback_v53 (
  id uuid primary key default gen_random_uuid(),
  feedback_date date not null,
  agent_key text not null references public.agent_registry_v51(agent_key) on delete cascade,
  session_id uuid references public.council_sessions_v51(id) on delete cascade,
  vote_id uuid references public.agent_votes_v51(id) on delete cascade,
  vote_direction text not null,
  vote_confidence numeric not null default 0,
  outcome_label text not null,
  correctness_score numeric not null default 0,
  calibration_error numeric not null default 0,
  veto_was_correct boolean,
  regime_context text,
  feedback_summary text not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint agent_feedback_v53_label_chk
    check (outcome_label in ('CORRECT','PARTIALLY_CORRECT','INCORRECT','INSUFFICIENT_DATA')),
  constraint agent_feedback_v53_scores_chk
    check (
      vote_confidence between 0 and 100 and
      correctness_score between 0 and 100 and
      calibration_error between 0 and 100
    )
);

create unique index if not exists agent_feedback_v53_uidx
on public.agent_feedback_v53(feedback_date, vote_id);

create table if not exists public.agent_weight_adjustments_v53 (
  id uuid primary key default gen_random_uuid(),
  proposal_date date not null,
  agent_key text not null references public.agent_registry_v51(agent_key) on delete cascade,
  current_weight numeric not null,
  proposed_weight numeric not null,
  adjustment_pct numeric not null default 0,
  evidence_count integer not null default 0,
  reliability_score numeric not null default 0,
  calibration_score numeric not null default 0,
  proposal_status text not null default 'PROPOSED',
  adjustment_reason text not null,
  evidence jsonb not null default '{}'::jsonb,
  auto_apply_enabled boolean not null default false,
  approved_by text,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_weight_adjustments_v53_status_chk
    check (proposal_status in ('PROPOSED','APPROVED','REJECTED','APPLIED','EXPIRED')),
  constraint agent_weight_adjustments_v53_scores_chk
    check (
      reliability_score between 0 and 100 and
      calibration_score between 0 and 100
    ),
  constraint agent_weight_adjustments_v53_evidence_chk
    check (evidence_count >= 0),
  constraint agent_weight_adjustments_v53_safety_chk
    check (auto_apply_enabled = false)
);

create unique index if not exists agent_weight_adjustments_v53_uidx
on public.agent_weight_adjustments_v53(proposal_date, agent_key);

create table if not exists public.strategy_outcomes_v53 (
  id uuid primary key default gen_random_uuid(),
  outcome_date date not null,
  strategy_key text not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  market_regime text not null default 'UNKNOWN',
  selections integer not null default 0,
  approvals integer not null default 0,
  rejections integer not null default 0,
  realized_return_pct numeric,
  max_drawdown_pct numeric,
  volatility_pct numeric,
  win_rate numeric not null default 0,
  quality_score numeric not null default 0,
  outcome_label text not null default 'INSUFFICIENT_DATA',
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint strategy_outcomes_v53_label_chk
    check (outcome_label in ('CORRECT','PARTIALLY_CORRECT','INCORRECT','INSUFFICIENT_DATA')),
  constraint strategy_outcomes_v53_scores_chk
    check (win_rate between 0 and 100 and quality_score between 0 and 100)
);

create unique index if not exists strategy_outcomes_v53_uidx
on public.strategy_outcomes_v53(outcome_date, strategy_key, portfolio_id, market_regime);

create table if not exists public.regime_outcomes_v53 (
  id uuid primary key default gen_random_uuid(),
  outcome_date date not null,
  regime_date date not null,
  predicted_regime text not null,
  predicted_confidence numeric not null default 0,
  observed_regime text not null default 'UNKNOWN',
  regime_match boolean,
  accuracy_score numeric not null default 0,
  realized_market_return_pct numeric,
  realized_market_volatility_pct numeric,
  outcome_label text not null default 'INSUFFICIENT_DATA',
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint regime_outcomes_v53_label_chk
    check (outcome_label in ('CORRECT','PARTIALLY_CORRECT','INCORRECT','INSUFFICIENT_DATA')),
  constraint regime_outcomes_v53_scores_chk
    check (predicted_confidence between 0 and 100 and accuracy_score between 0 and 100)
);

create unique index if not exists regime_outcomes_v53_uidx
on public.regime_outcomes_v53(outcome_date, regime_date, predicted_regime);

create table if not exists public.confidence_calibration_v53 (
  id uuid primary key default gen_random_uuid(),
  calibration_date date not null,
  subject_type text not null,
  subject_key text not null,
  observations integer not null default 0,
  average_confidence numeric not null default 0,
  observed_accuracy numeric not null default 0,
  calibration_error numeric not null default 0,
  calibration_status text not null default 'INSUFFICIENT_DATA',
  suggested_adjustment numeric not null default 0,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint confidence_calibration_v53_type_chk
    check (subject_type in ('AGENT','STRATEGY','COUNCIL','REGIME')),
  constraint confidence_calibration_v53_scores_chk
    check (
      average_confidence between 0 and 100 and
      observed_accuracy between 0 and 100 and
      calibration_error between 0 and 100
    ),
  constraint confidence_calibration_v53_status_chk
    check (calibration_status in ('WELL_CALIBRATED','OVERCONFIDENT','UNDERCONFIDENT','INSUFFICIENT_DATA'))
);

create unique index if not exists confidence_calibration_v53_uidx
on public.confidence_calibration_v53(calibration_date, subject_type, subject_key);

create table if not exists public.learning_cycles_v53 (
  id uuid primary key default gen_random_uuid(),
  cycle_date date not null unique,
  cycle_status text not null,
  decisions_evaluated integer not null default 0,
  agent_votes_evaluated integer not null default 0,
  strategies_evaluated integer not null default 0,
  regimes_evaluated integer not null default 0,
  proposals_generated integer not null default 0,
  insufficient_data_count integer not null default 0,
  average_decision_score numeric not null default 0,
  average_agent_reliability numeric not null default 0,
  average_calibration_score numeric not null default 0,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  summary text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint learning_cycles_v53_status_chk
    check (cycle_status in ('RUNNING','PASS','WARNING','CRITICAL','FAILED')),
  constraint learning_cycles_v53_scores_chk
    check (
      average_decision_score between 0 and 100 and
      average_agent_reliability between 0 and 100 and
      average_calibration_score between 0 and 100
    )
);

create table if not exists public.learning_metrics_v53 (
  id uuid primary key default gen_random_uuid(),
  metric_date date not null unique,
  total_observations integer not null default 0,
  correct_decisions integer not null default 0,
  partial_decisions integer not null default 0,
  incorrect_decisions integer not null default 0,
  insufficient_data integer not null default 0,
  agent_feedback_records integer not null default 0,
  weight_proposals integer not null default 0,
  strategy_outcomes integer not null default 0,
  regime_outcomes integer not null default 0,
  average_decision_score numeric not null default 0,
  average_agent_accuracy numeric not null default 0,
  average_calibration_error numeric not null default 0,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.learning_status_v53 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  current_cycle_id uuid,
  decisions_evaluated integer not null default 0,
  agent_votes_evaluated integer not null default 0,
  strategies_evaluated integer not null default 0,
  regimes_evaluated integer not null default 0,
  proposals_generated integer not null default 0,
  observations_created integer not null default 0,
  insufficient_data_count integer not null default 0,
  average_decision_score numeric not null default 0,
  average_agent_reliability numeric not null default 0,
  average_calibration_score numeric not null default 0,
  automatic_weight_updates_enabled boolean not null default false,
  automatic_model_retraining_enabled boolean not null default false,
  live_trading_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  summary text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint learning_status_v53_status_chk
    check (overall_status in ('PASS','WARNING','CRITICAL')),
  constraint learning_status_v53_safety_chk
    check (
      automatic_weight_updates_enabled = false and
      automatic_model_retraining_enabled = false and
      live_trading_enabled = false
    )
);

do $$
declare
  t text;
  p text;
begin
  foreach t in array array[
    'learning_observations_v53',
    'decision_outcomes_v53',
    'agent_feedback_v53',
    'agent_weight_adjustments_v53',
    'strategy_outcomes_v53',
    'regime_outcomes_v53',
    'confidence_calibration_v53',
    'learning_cycles_v53',
    'learning_metrics_v53',
    'learning_status_v53'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    p := 'enterprise53 read ' || t;
    execute format('drop policy if exists %I on public.%I', p, t);
    execute format(
      'create policy %I on public.%I for select to anon, authenticated using (true)',
      p, t
    );
    execute format('grant select on public.%I to anon, authenticated', t);
  end loop;
end $$;

drop trigger if exists decision_outcomes_v53_set_updated_at on public.decision_outcomes_v53;
create trigger decision_outcomes_v53_set_updated_at
before update on public.decision_outcomes_v53
for each row execute function public.enterprise53_set_updated_at();

drop trigger if exists agent_weight_adjustments_v53_set_updated_at on public.agent_weight_adjustments_v53;
create trigger agent_weight_adjustments_v53_set_updated_at
before update on public.agent_weight_adjustments_v53
for each row execute function public.enterprise53_set_updated_at();

drop trigger if exists learning_cycles_v53_set_updated_at on public.learning_cycles_v53;
create trigger learning_cycles_v53_set_updated_at
before update on public.learning_cycles_v53
for each row execute function public.enterprise53_set_updated_at();

drop trigger if exists learning_metrics_v53_set_updated_at on public.learning_metrics_v53;
create trigger learning_metrics_v53_set_updated_at
before update on public.learning_metrics_v53
for each row execute function public.enterprise53_set_updated_at();

drop trigger if exists learning_status_v53_set_updated_at on public.learning_status_v53;
create trigger learning_status_v53_set_updated_at
before update on public.learning_status_v53
for each row execute function public.enterprise53_set_updated_at();

insert into public.learning_status_v53 (
  status_date,
  overall_status,
  current_cycle_id,
  decisions_evaluated,
  agent_votes_evaluated,
  strategies_evaluated,
  regimes_evaluated,
  proposals_generated,
  observations_created,
  insufficient_data_count,
  average_decision_score,
  average_agent_reliability,
  average_calibration_score,
  automatic_weight_updates_enabled,
  automatic_model_retraining_enabled,
  live_trading_enabled,
  blockers,
  warnings,
  summary,
  diagnostics
)
values (
  current_date,
  'WARNING',
  null,
  0,0,0,0,0,0,0,0,0,0,
  false,false,false,
  '["LEARNING_ENGINE_NOT_RUN"]'::jsonb,
  '[]'::jsonb,
  'Enterprise 5.3 foundation installed; learning cycle has not run yet.',
  '{"foundation_version":"5.3.0"}'::jsonb
)
on conflict (status_date) do nothing;

create or replace view public.learning_dashboard_v53 as
select
  c.cycle_date,
  c.cycle_status,
  c.decisions_evaluated,
  c.agent_votes_evaluated,
  c.strategies_evaluated,
  c.regimes_evaluated,
  c.proposals_generated,
  c.insufficient_data_count,
  c.average_decision_score,
  c.average_agent_reliability,
  c.average_calibration_score,
  s.overall_status,
  s.automatic_weight_updates_enabled,
  s.automatic_model_retraining_enabled,
  s.summary
from public.learning_cycles_v53 c
left join public.learning_status_v53 s
  on s.status_date = c.cycle_date;

grant select on public.learning_dashboard_v53 to anon, authenticated;

notify pgrst, 'reload schema';

commit;

select 'Enterprise 5.3 Foundation Database Pack v1.0 setup complete' as result;
