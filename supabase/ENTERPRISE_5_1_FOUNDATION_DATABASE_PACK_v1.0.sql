begin;

create extension if not exists pgcrypto;

create or replace function public.enterprise51_set_updated_at()
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

create table if not exists public.agent_registry_v51 (
  id uuid primary key default gen_random_uuid(),
  agent_key text not null unique,
  agent_name text not null,
  agent_type text not null,
  enabled boolean not null default true,
  required boolean not null default true,
  voting_weight numeric not null default 1,
  minimum_confidence numeric not null default 50,
  execution_order integer not null default 100,
  source_table text,
  capabilities jsonb not null default '[]'::jsonb,
  configuration jsonb not null default '{}'::jsonb,
  health_status text not null default 'UNKNOWN',
  paper_only boolean not null default true,
  live_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_registry_v51_type_chk
    check (agent_type in ('MARKET','RISK','STRATEGY','OPTIMIZER','LEARNING','COUNCIL')),
  constraint agent_registry_v51_conf_chk
    check (minimum_confidence between 0 and 100),
  constraint agent_registry_v51_weight_chk
    check (voting_weight >= 0),
  constraint agent_registry_v51_safety_chk
    check (paper_only = true and live_enabled = false)
);

create table if not exists public.council_sessions_v51 (
  id uuid primary key default gen_random_uuid(),
  session_date date not null,
  cycle_id uuid,
  session_key text not null,
  session_status text not null default 'RUNNING',
  market_regime text not null default 'UNKNOWN',
  portfolio_count integer not null default 0,
  agents_expected integer not null default 0,
  agents_completed integer not null default 0,
  consensus_score numeric not null default 0,
  conflict_count integer not null default 0,
  final_decision text,
  final_confidence numeric not null default 0,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  summary text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint council_sessions_v51_status_chk
    check (session_status in ('RUNNING','PASS','WARNING','CRITICAL','BLOCKED','FAILED')),
  constraint council_sessions_v51_consensus_chk
    check (consensus_score between 0 and 100),
  constraint council_sessions_v51_confidence_chk
    check (final_confidence between 0 and 100)
);

create unique index if not exists council_sessions_v51_uidx
on public.council_sessions_v51(session_date, session_key);

create table if not exists public.agent_votes_v51 (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.council_sessions_v51(id) on delete cascade,
  agent_key text not null references public.agent_registry_v51(agent_key) on delete cascade,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  vote text not null,
  vote_direction text not null,
  confidence numeric not null default 0,
  weighted_score numeric not null default 0,
  risk_level text not null default 'MEDIUM',
  veto boolean not null default false,
  supporting_factors jsonb not null default '[]'::jsonb,
  opposing_factors jsonb not null default '[]'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint agent_votes_v51_direction_chk
    check (vote_direction in ('STRONG_BUY','BUY','HOLD','REDUCE','AVOID','BLOCK')),
  constraint agent_votes_v51_conf_chk
    check (confidence between 0 and 100),
  constraint agent_votes_v51_risk_chk
    check (risk_level in ('LOW','MEDIUM','HIGH','CRITICAL'))
);

create unique index if not exists agent_votes_v51_uidx
on public.agent_votes_v51(session_id, agent_key, portfolio_id);

create table if not exists public.agent_explanations_v51 (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.council_sessions_v51(id) on delete cascade,
  agent_key text not null references public.agent_registry_v51(agent_key) on delete cascade,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  explanation text not null,
  rationale jsonb not null default '{}'::jsonb,
  source_records jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.agent_conflicts_v51 (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.council_sessions_v51(id) on delete cascade,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  conflict_type text not null,
  agents_involved jsonb not null default '[]'::jsonb,
  severity text not null default 'WARNING',
  conflict_summary text not null,
  resolution text,
  resolved boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_conflicts_v51_severity_chk
    check (severity in ('INFO','WARNING','CRITICAL'))
);

create table if not exists public.decision_council_v51 (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null unique references public.council_sessions_v51(id) on delete cascade,
  decision_date date not null,
  cycle_id uuid,
  market_regime text not null default 'UNKNOWN',
  final_decision text not null,
  final_confidence numeric not null default 0,
  consensus_score numeric not null default 0,
  approval_ratio numeric not null default 0,
  veto_count integer not null default 0,
  selected_strategy text,
  recommended_exposure_pct numeric not null default 0,
  recommended_cash_pct numeric not null default 100,
  decision_status text not null,
  rationale text not null,
  vote_summary jsonb not null default '{}'::jsonb,
  conflicts jsonb not null default '[]'::jsonb,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  paper_approved boolean not null default true,
  live_approved boolean not null default false,
  autonomous_execution_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint decision_council_v51_decision_chk
    check (final_decision in ('STRONG_BUY','BUY','HOLD','REDUCE','AVOID','BLOCK')),
  constraint decision_council_v51_status_chk
    check (decision_status in ('APPROVED_FOR_PAPER','REDUCED','WARNING','BLOCKED')),
  constraint decision_council_v51_score_chk
    check (
      final_confidence between 0 and 100 and
      consensus_score between 0 and 100 and
      approval_ratio between 0 and 100
    ),
  constraint decision_council_v51_safety_chk
    check (
      paper_approved = true and
      live_approved = false and
      autonomous_execution_enabled = false
    )
);

create table if not exists public.consensus_history_v51 (
  id uuid primary key default gen_random_uuid(),
  consensus_date date not null,
  session_id uuid not null references public.council_sessions_v51(id) on delete cascade,
  final_decision text not null,
  consensus_score numeric not null,
  final_confidence numeric not null,
  agent_count integer not null default 0,
  conflict_count integer not null default 0,
  vote_distribution jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.agent_performance_v51 (
  id uuid primary key default gen_random_uuid(),
  performance_date date not null,
  agent_key text not null references public.agent_registry_v51(agent_key) on delete cascade,
  votes_cast integer not null default 0,
  correct_votes integer not null default 0,
  incorrect_votes integer not null default 0,
  accuracy_score numeric not null default 0,
  calibration_score numeric not null default 0,
  average_confidence numeric not null default 0,
  reliability_score numeric not null default 0,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint agent_performance_v51_scores_chk
    check (
      accuracy_score between 0 and 100 and
      calibration_score between 0 and 100 and
      average_confidence between 0 and 100 and
      reliability_score between 0 and 100
    )
);

create unique index if not exists agent_performance_v51_uidx
on public.agent_performance_v51(performance_date, agent_key);

create table if not exists public.council_metrics_v51 (
  id uuid primary key default gen_random_uuid(),
  metric_date date not null unique,
  sessions_completed integer not null default 0,
  agents_active integer not null default 0,
  votes_cast integer not null default 0,
  conflicts_detected integer not null default 0,
  vetoes_cast integer not null default 0,
  average_consensus numeric not null default 0,
  average_confidence numeric not null default 0,
  blocked_decisions integer not null default 0,
  approved_decisions integer not null default 0,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.council_status_v51 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  current_session_id uuid,
  sessions_completed integer not null default 0,
  agents_registered integer not null default 0,
  agents_completed integer not null default 0,
  votes_cast integer not null default 0,
  conflicts_detected integer not null default 0,
  vetoes_cast integer not null default 0,
  consensus_score numeric not null default 0,
  final_confidence numeric not null default 0,
  final_decision text,
  live_trading_enabled boolean not null default false,
  autonomous_execution_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  summary text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint council_status_v51_status_chk
    check (overall_status in ('PASS','WARNING','CRITICAL')),
  constraint council_status_v51_safety_chk
    check (
      live_trading_enabled = false and
      autonomous_execution_enabled = false
    )
);

create index if not exists agent_votes_v51_session_idx
on public.agent_votes_v51(session_id, confidence desc);

create index if not exists agent_conflicts_v51_session_idx
on public.agent_conflicts_v51(session_id, severity);

create index if not exists decision_council_v51_date_idx
on public.decision_council_v51(decision_date desc);

drop trigger if exists agent_registry_v51_set_updated_at on public.agent_registry_v51;
create trigger agent_registry_v51_set_updated_at
before update on public.agent_registry_v51
for each row execute function public.enterprise51_set_updated_at();

drop trigger if exists council_sessions_v51_set_updated_at on public.council_sessions_v51;
create trigger council_sessions_v51_set_updated_at
before update on public.council_sessions_v51
for each row execute function public.enterprise51_set_updated_at();

drop trigger if exists decision_council_v51_set_updated_at on public.decision_council_v51;
create trigger decision_council_v51_set_updated_at
before update on public.decision_council_v51
for each row execute function public.enterprise51_set_updated_at();

drop trigger if exists council_status_v51_set_updated_at on public.council_status_v51;
create trigger council_status_v51_set_updated_at
before update on public.council_status_v51
for each row execute function public.enterprise51_set_updated_at();

do $$
declare
  t text;
  p text;
begin
  foreach t in array array[
    'agent_registry_v51',
    'council_sessions_v51',
    'agent_votes_v51',
    'agent_explanations_v51',
    'agent_conflicts_v51',
    'decision_council_v51',
    'consensus_history_v51',
    'agent_performance_v51',
    'council_metrics_v51',
    'council_status_v51'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    p := 'enterprise51 read ' || t;
    execute format('drop policy if exists %I on public.%I', p, t);
    execute format(
      'create policy %I on public.%I for select to anon, authenticated using (true)',
      p, t
    );
    execute format('grant select on public.%I to anon, authenticated', t);
  end loop;
end $$;

insert into public.agent_registry_v51 (
  agent_key, agent_name, agent_type, enabled, required,
  voting_weight, minimum_confidence, execution_order,
  source_table, capabilities, configuration,
  health_status, paper_only, live_enabled
)
values
('MARKET_AGENT','Market Regime Agent','MARKET',true,true,1.0,50,10,
 'market_regime_ai_v46','["REGIME","POSTURE","LIQUIDITY"]'::jsonb,'{}'::jsonb,'UNKNOWN',true,false),
('RISK_AGENT','Risk Governor Agent','RISK',true,true,1.5,50,20,
 'risk_governor_status_v41','["RISK_GATE","VETO","CIRCUIT_BREAKER"]'::jsonb,'{}'::jsonb,'UNKNOWN',true,false),
('STRATEGY_AGENT','Strategy Scoring Agent','STRATEGY',true,true,1.2,50,30,
 'strategy_scores_v47','["RANKING","SELECTION","CONFIDENCE"]'::jsonb,'{}'::jsonb,'UNKNOWN',true,false),
('OPTIMIZER_AGENT','Portfolio Optimizer Agent','OPTIMIZER',true,true,1.2,50,40,
 'portfolio_allocations_v48','["WEIGHTS","CASH","EXPOSURE"]'::jsonb,'{}'::jsonb,'UNKNOWN',true,false),
('LEARNING_AGENT','Learning and Memory Agent','LEARNING',true,false,0.8,40,50,
 'learning_cycle_status_v45','["MEMORY","OUTCOME","CALIBRATION"]'::jsonb,'{}'::jsonb,'UNKNOWN',true,false),
('DECISION_COUNCIL','Decision Council','COUNCIL',true,true,0,0,100,
 'decision_council_v51','["CONSENSUS","CONFLICT_RESOLUTION","FINAL_DECISION"]'::jsonb,'{}'::jsonb,'UNKNOWN',true,false)
on conflict (agent_key) do update
set
  agent_name = excluded.agent_name,
  agent_type = excluded.agent_type,
  enabled = excluded.enabled,
  required = excluded.required,
  voting_weight = excluded.voting_weight,
  minimum_confidence = excluded.minimum_confidence,
  execution_order = excluded.execution_order,
  source_table = excluded.source_table,
  capabilities = excluded.capabilities,
  configuration = excluded.configuration,
  paper_only = true,
  live_enabled = false,
  updated_at = now();

insert into public.council_status_v51 (
  status_date, overall_status, sessions_completed,
  agents_registered, agents_completed, votes_cast,
  conflicts_detected, vetoes_cast, consensus_score,
  final_confidence, final_decision,
  live_trading_enabled, autonomous_execution_enabled,
  blockers, warnings, summary, diagnostics
)
values (
  current_date, 'WARNING', 0,
  (select count(*) from public.agent_registry_v51 where enabled=true),
  0,0,0,0,0,0,null,false,false,
  '["COUNCIL_NOT_RUN"]'::jsonb,
  '[]'::jsonb,
  'Enterprise 5.1 foundation installed; council has not run yet.',
  '{"foundation_version":"5.1.0"}'::jsonb
)
on conflict (status_date) do nothing;

create or replace view public.council_dashboard_v51 as
select
  s.session_date,
  s.session_key,
  s.session_status,
  s.market_regime,
  s.agents_expected,
  s.agents_completed,
  s.consensus_score,
  s.conflict_count,
  s.final_decision,
  s.final_confidence,
  d.decision_status,
  d.selected_strategy,
  d.recommended_exposure_pct,
  d.recommended_cash_pct,
  d.rationale
from public.council_sessions_v51 s
left join public.decision_council_v51 d
  on d.session_id = s.id;

grant select on public.council_dashboard_v51 to anon, authenticated;

notify pgrst, 'reload schema';

commit;

select 'Enterprise 5.1 Foundation Database Pack v1.0 setup complete' as result;
