-- =====================================================================
-- GPT Quant Enterprise 5.4 Foundation Database Pack v1.0
-- Adaptive Governance & Controlled Evolution Foundation
--
-- Compatible with:
--   automation/enterprise54_adaptive_governance.py
--
-- Safety:
--   PAPER ONLY
--   Automatic Proposal Application = false
--   Automatic Agent Weight Update = false
--   Automatic Risk Parameter Update = false
--   Automatic Rollback = false
--   Live Trading = false
-- =====================================================================

begin;

create extension if not exists pgcrypto;

create or replace function public.enterprise54_set_updated_at()
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

-- =====================================================================
-- 1. Adaptive proposals
-- =====================================================================
create table if not exists public.adaptive_proposals_v54 (
  id uuid primary key default gen_random_uuid(),
  proposal_date date not null default current_date,
  proposal_key text not null,
  proposal_type text not null,
  proposal_title text not null,
  proposal_description text not null,
  proposal_source text not null,
  source_record_id uuid,
  status text not null default 'PROPOSED',
  priority text not null default 'MEDIUM',
  risk_level text not null default 'MEDIUM',
  evidence_count integer not null default 0,
  expected_benefit text,
  safety_gate_passed boolean,
  shadow_test_passed boolean,
  paper_only boolean not null default true,
  automatic_application_enabled boolean not null default false,
  live_trading_impact boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint adaptive_proposals_v54_type_chk
    check (
      proposal_type in (
        'AGENT_WEIGHT',
        'STRATEGY_PARAMETER',
        'RISK_PARAMETER',
        'EXECUTION_RULE',
        'REGIME_RULE',
        'CONFIDENCE_CALIBRATION'
      )
    ),

  constraint adaptive_proposals_v54_status_chk
    check (
      status in (
        'PROPOSED',
        'VALIDATING',
        'VALIDATION_FAILED',
        'SHADOW_TESTED',
        'READY_FOR_REVIEW',
        'APPROVED',
        'REJECTED',
        'MANUALLY_APPLIED',
        'MONITORING',
        'CONFIRMED',
        'ROLLED_BACK',
        'ARCHIVED'
      )
    ),

  constraint adaptive_proposals_v54_priority_chk
    check (priority in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),

  constraint adaptive_proposals_v54_risk_chk
    check (risk_level in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),

  constraint adaptive_proposals_v54_evidence_chk
    check (evidence_count >= 0),

  constraint adaptive_proposals_v54_safety_chk
    check (
      paper_only = true
      and automatic_application_enabled = false
      and live_trading_impact = false
    )
);

alter table public.adaptive_proposals_v54
drop constraint if exists adaptive_proposals_v54_unique;

alter table public.adaptive_proposals_v54
add constraint adaptive_proposals_v54_unique
unique (proposal_date, proposal_key);

create index if not exists adaptive_proposals_v54_status_idx
on public.adaptive_proposals_v54 (
  status,
  priority,
  proposal_date desc
);

-- =====================================================================
-- 2. Proposal items
-- =====================================================================
create table if not exists public.proposal_items_v54 (
  id uuid primary key default gen_random_uuid(),
  proposal_id uuid not null references public.adaptive_proposals_v54(id)
    on delete cascade,
  item_key text not null,
  item_type text not null,
  target_name text not null,
  current_value numeric,
  proposed_value numeric,
  change_pct numeric not null default 0,
  expected_benefit text,
  risk_level text not null default 'MEDIUM',
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint proposal_items_v54_type_chk
    check (
      item_type in (
        'AGENT_WEIGHT',
        'STRATEGY_PARAMETER',
        'RISK_PARAMETER',
        'EXECUTION_RULE',
        'REGIME_RULE',
        'CONFIDENCE_CALIBRATION'
      )
    ),

  constraint proposal_items_v54_risk_chk
    check (risk_level in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
);

alter table public.proposal_items_v54
drop constraint if exists proposal_items_v54_unique;

alter table public.proposal_items_v54
add constraint proposal_items_v54_unique
unique (proposal_id, item_key);

create index if not exists proposal_items_v54_proposal_idx
on public.proposal_items_v54 (proposal_id, item_type);

-- =====================================================================
-- 3. Safety gate results
-- =====================================================================
create table if not exists public.safety_gate_results_v54 (
  id uuid primary key default gen_random_uuid(),
  proposal_id uuid not null references public.adaptive_proposals_v54(id)
    on delete cascade,
  gate_key text not null,
  gate_status text not null,
  passed boolean not null,
  observed_value numeric,
  threshold_value numeric,
  severity text not null default 'INFO',
  message text not null,
  evidence jsonb not null default '{}'::jsonb,
  checked_at timestamptz not null default now(),
  created_at timestamptz not null default now(),

  constraint safety_gate_results_v54_status_chk
    check (gate_status in ('PASS', 'FAIL', 'WARNING', 'NOT_APPLICABLE')),

  constraint safety_gate_results_v54_severity_chk
    check (severity in ('INFO', 'WARNING', 'CRITICAL'))
);

alter table public.safety_gate_results_v54
drop constraint if exists safety_gate_results_v54_unique;

alter table public.safety_gate_results_v54
add constraint safety_gate_results_v54_unique
unique (proposal_id, gate_key);

create index if not exists safety_gate_results_v54_proposal_idx
on public.safety_gate_results_v54 (
  proposal_id,
  gate_status,
  severity
);

-- =====================================================================
-- 4. Shadow simulations
-- =====================================================================
create table if not exists public.shadow_simulations_v54 (
  id uuid primary key default gen_random_uuid(),
  proposal_id uuid not null references public.adaptive_proposals_v54(id)
    on delete cascade,
  simulation_date date not null default current_date,
  simulation_type text not null,
  sample_size integer not null default 0,
  baseline_score numeric not null default 0,
  candidate_score numeric not null default 0,
  stability_score numeric not null default 0,
  risk_regression_score numeric not null default 0,
  return_delta_pct numeric,
  sharpe_delta numeric,
  drawdown_delta_pct numeric,
  turnover_delta_pct numeric,
  passed boolean not null default false,
  simulation_status text not null,
  summary text not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint shadow_simulations_v54_sample_chk
    check (sample_size >= 0),

  constraint shadow_simulations_v54_scores_chk
    check (
      stability_score between 0 and 100
      and risk_regression_score between 0 and 100
    ),

  constraint shadow_simulations_v54_status_chk
    check (
      simulation_status in (
        'PASS',
        'FAILED',
        'INSUFFICIENT_OR_FAILED',
        'INSUFFICIENT_DATA'
      )
    )
);

alter table public.shadow_simulations_v54
drop constraint if exists shadow_simulations_v54_unique;

alter table public.shadow_simulations_v54
add constraint shadow_simulations_v54_unique
unique (proposal_id, simulation_date, simulation_type);

create index if not exists shadow_simulations_v54_proposal_idx
on public.shadow_simulations_v54 (
  proposal_id,
  simulation_date desc,
  passed
);

-- =====================================================================
-- 5. Adaptive reviews
-- =====================================================================
create table if not exists public.adaptive_reviews_v54 (
  id uuid primary key default gen_random_uuid(),
  proposal_id uuid not null references public.adaptive_proposals_v54(id)
    on delete cascade,
  review_stage text not null,
  review_result text not null,
  review_comment text not null,
  reviewer text not null,
  review_time timestamptz not null default now(),
  manual_approval_required boolean not null default true,
  automatic_application_enabled boolean not null default false,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint adaptive_reviews_v54_stage_chk
    check (
      review_stage in (
        'AUTOMATED_GOVERNANCE',
        'RISK_REVIEW',
        'MODEL_REVIEW',
        'HUMAN_APPROVAL',
        'POST_APPLICATION_MONITORING'
      )
    ),

  constraint adaptive_reviews_v54_result_chk
    check (
      review_result in (
        'READY_FOR_HUMAN_REVIEW',
        'REJECTED_BY_SAFETY_GATE',
        'APPROVED',
        'REJECTED',
        'NEEDS_MORE_EVIDENCE',
        'MONITORING',
        'CONFIRMED',
        'ROLLBACK_REQUIRED'
      )
    ),

  constraint adaptive_reviews_v54_safety_chk
    check (
      manual_approval_required = true
      and automatic_application_enabled = false
    )
);

alter table public.adaptive_reviews_v54
drop constraint if exists adaptive_reviews_v54_unique;

alter table public.adaptive_reviews_v54
add constraint adaptive_reviews_v54_unique
unique (proposal_id, review_stage);

-- =====================================================================
-- 6. Parameter versions
-- =====================================================================
create table if not exists public.parameter_versions_v54 (
  id uuid primary key default gen_random_uuid(),
  version_no text not null unique,
  version_type text not null,
  parameter_group text not null,
  version_status text not null,
  description text not null,
  source_run_id uuid,
  source_proposals jsonb not null default '[]'::jsonb,
  active boolean not null default false,
  paper_only boolean not null default true,
  automatic_application_enabled boolean not null default false,
  rollback_ready boolean not null default false,
  configuration jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint parameter_versions_v54_type_chk
    check (
      version_type in (
        'AGENT_WEIGHT_SET',
        'STRATEGY_PARAMETER_SET',
        'RISK_PARAMETER_SET',
        'EXECUTION_RULE_SET',
        'REGIME_RULE_SET'
      )
    ),

  constraint parameter_versions_v54_status_chk
    check (
      version_status in (
        'ACTIVE',
        'CANDIDATE',
        'SHADOW',
        'REJECTED',
        'ROLLED_BACK',
        'ARCHIVED'
      )
    ),

  constraint parameter_versions_v54_safety_chk
    check (
      paper_only = true
      and automatic_application_enabled = false
    )
);

create index if not exists parameter_versions_v54_status_idx
on public.parameter_versions_v54 (
  version_status,
  created_at desc
);

-- =====================================================================
-- 7. Agent weight versions
-- =====================================================================
create table if not exists public.agent_weight_versions_v54 (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.parameter_versions_v54(id)
    on delete cascade,
  agent_key text not null,
  weight numeric not null,
  previous_weight numeric,
  effective_date date,
  version_status text not null default 'CANDIDATE',
  source_proposal_id uuid references public.adaptive_proposals_v54(id)
    on delete set null,
  reliability_score numeric not null default 0,
  calibration_score numeric not null default 0,
  active boolean not null default false,
  automatic_application_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint agent_weight_versions_v54_status_chk
    check (
      version_status in (
        'ACTIVE',
        'CANDIDATE',
        'SHADOW',
        'REJECTED',
        'ROLLED_BACK',
        'ARCHIVED'
      )
    ),

  constraint agent_weight_versions_v54_scores_chk
    check (
      reliability_score between 0 and 100
      and calibration_score between 0 and 100
    ),

  constraint agent_weight_versions_v54_safety_chk
    check (automatic_application_enabled = false)
);

alter table public.agent_weight_versions_v54
drop constraint if exists agent_weight_versions_v54_unique;

alter table public.agent_weight_versions_v54
add constraint agent_weight_versions_v54_unique
unique (version_id, agent_key);

-- =====================================================================
-- 8. Strategy versions
-- =====================================================================
create table if not exists public.strategy_versions_v54 (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.parameter_versions_v54(id)
    on delete cascade,
  strategy_key text not null,
  score_weight numeric,
  allocation_weight numeric,
  parameter_snapshot jsonb not null default '{}'::jsonb,
  version_status text not null default 'CANDIDATE',
  active boolean not null default false,
  automatic_application_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint strategy_versions_v54_status_chk
    check (
      version_status in (
        'ACTIVE',
        'CANDIDATE',
        'SHADOW',
        'REJECTED',
        'ROLLED_BACK',
        'ARCHIVED'
      )
    ),

  constraint strategy_versions_v54_safety_chk
    check (automatic_application_enabled = false)
);

alter table public.strategy_versions_v54
drop constraint if exists strategy_versions_v54_unique;

alter table public.strategy_versions_v54
add constraint strategy_versions_v54_unique
unique (version_id, strategy_key);

-- =====================================================================
-- 9. Rollback snapshots
-- =====================================================================
create table if not exists public.rollback_snapshots_v54 (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.parameter_versions_v54(id)
    on delete cascade,
  snapshot_date date not null default current_date,
  snapshot_type text not null,
  snapshot_status text not null,
  configuration_snapshot jsonb not null default '{}'::jsonb,
  rollback_instructions text not null,
  automatic_rollback_enabled boolean not null default false,
  paper_only boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint rollback_snapshots_v54_type_chk
    check (
      snapshot_type in (
        'PRE_APPLICATION',
        'POST_APPLICATION',
        'MANUAL_BACKUP'
      )
    ),

  constraint rollback_snapshots_v54_status_chk
    check (
      snapshot_status in (
        'READY',
        'USED',
        'EXPIRED',
        'INVALID'
      )
    ),

  constraint rollback_snapshots_v54_safety_chk
    check (
      automatic_rollback_enabled = false
      and paper_only = true
    )
);

alter table public.rollback_snapshots_v54
drop constraint if exists rollback_snapshots_v54_unique;

alter table public.rollback_snapshots_v54
add constraint rollback_snapshots_v54_unique
unique (version_id, snapshot_type);

-- =====================================================================
-- 10. Rollback history
-- =====================================================================
create table if not exists public.rollback_history_v54 (
  id uuid primary key default gen_random_uuid(),
  from_version_id uuid references public.parameter_versions_v54(id)
    on delete set null,
  to_version_id uuid references public.parameter_versions_v54(id)
    on delete set null,
  rollback_reason text not null,
  executed_by text,
  executed_at timestamptz,
  rollback_status text not null default 'NOT_EXECUTED',
  automatic_execution_enabled boolean not null default false,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint rollback_history_v54_status_chk
    check (
      rollback_status in (
        'NOT_EXECUTED',
        'APPROVED',
        'EXECUTED',
        'FAILED',
        'CANCELLED'
      )
    ),

  constraint rollback_history_v54_safety_chk
    check (automatic_execution_enabled = false)
);

-- =====================================================================
-- 11. Adaptive metrics
-- =====================================================================
create table if not exists public.adaptive_metrics_v54 (
  id uuid primary key default gen_random_uuid(),
  metric_date date not null unique,
  total_proposals integer not null default 0,
  proposal_items integer not null default 0,
  safety_checks integer not null default 0,
  shadow_tests integer not null default 0,
  ready_for_review integer not null default 0,
  candidate_versions integer not null default 0,
  approved_versions integer not null default 0,
  rejected_proposals integer not null default 0,
  rollback_snapshots integer not null default 0,
  average_reliability numeric not null default 0,
  automatic_applications integer not null default 0,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint adaptive_metrics_v54_counts_chk
    check (
      total_proposals >= 0
      and proposal_items >= 0
      and safety_checks >= 0
      and shadow_tests >= 0
      and ready_for_review >= 0
      and candidate_versions >= 0
      and approved_versions >= 0
      and rejected_proposals >= 0
      and rollback_snapshots >= 0
      and automatic_applications >= 0
    ),

  constraint adaptive_metrics_v54_score_chk
    check (average_reliability between 0 and 100)
);

-- =====================================================================
-- 12. Adaptive status
-- =====================================================================
create table if not exists public.adaptive_status_v54 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  current_candidate_version text,
  proposals_generated integer not null default 0,
  proposal_items_generated integer not null default 0,
  safety_checks_run integer not null default 0,
  shadow_tests_run integer not null default 0,
  ready_for_review integer not null default 0,
  candidate_versions integer not null default 0,
  approved_versions integer not null default 0,
  rejected_proposals integer not null default 0,
  rollback_ready boolean not null default false,
  automatic_proposal_application_enabled boolean not null default false,
  automatic_agent_weight_update_enabled boolean not null default false,
  automatic_risk_parameter_update_enabled boolean not null default false,
  automatic_rollback_enabled boolean not null default false,
  live_trading_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  summary text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint adaptive_status_v54_status_chk
    check (overall_status in ('PASS', 'WARNING', 'CRITICAL')),

  constraint adaptive_status_v54_counts_chk
    check (
      proposals_generated >= 0
      and proposal_items_generated >= 0
      and safety_checks_run >= 0
      and shadow_tests_run >= 0
      and ready_for_review >= 0
      and candidate_versions >= 0
      and approved_versions >= 0
      and rejected_proposals >= 0
    ),

  constraint adaptive_status_v54_safety_chk
    check (
      automatic_proposal_application_enabled = false
      and automatic_agent_weight_update_enabled = false
      and automatic_risk_parameter_update_enabled = false
      and automatic_rollback_enabled = false
      and live_trading_enabled = false
    )
);

-- =====================================================================
-- updated_at triggers
-- =====================================================================
do $$
declare
  t text;
  trigger_name text;
begin
  foreach t in array array[
    'adaptive_proposals_v54',
    'proposal_items_v54',
    'shadow_simulations_v54',
    'adaptive_reviews_v54',
    'parameter_versions_v54',
    'agent_weight_versions_v54',
    'strategy_versions_v54',
    'rollback_snapshots_v54',
    'rollback_history_v54',
    'adaptive_metrics_v54',
    'adaptive_status_v54'
  ]
  loop
    trigger_name := t || '_set_updated_at';
    execute format(
      'drop trigger if exists %I on public.%I',
      trigger_name,
      t
    );
    execute format(
      'create trigger %I before update on public.%I
       for each row execute function public.enterprise54_set_updated_at()',
      trigger_name,
      t
    );
  end loop;
end $$;

-- =====================================================================
-- RLS and read grants
-- =====================================================================
do $$
declare
  t text;
  p text;
begin
  foreach t in array array[
    'adaptive_proposals_v54',
    'proposal_items_v54',
    'safety_gate_results_v54',
    'shadow_simulations_v54',
    'adaptive_reviews_v54',
    'parameter_versions_v54',
    'agent_weight_versions_v54',
    'strategy_versions_v54',
    'rollback_snapshots_v54',
    'rollback_history_v54',
    'adaptive_metrics_v54',
    'adaptive_status_v54'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    p := 'enterprise54 read ' || t;
    execute format('drop policy if exists %I on public.%I', p, t);
    execute format(
      'create policy %I on public.%I
       for select to anon, authenticated using (true)',
      p,
      t
    );
    execute format(
      'grant select on public.%I to anon, authenticated',
      t
    );
  end loop;
end $$;

grant usage, select
on sequence public.adaptive_status_v54_id_seq
to authenticated;

-- =====================================================================
-- Initial candidate baseline version
-- =====================================================================
insert into public.parameter_versions_v54 (
  version_no,
  version_type,
  parameter_group,
  version_status,
  description,
  source_run_id,
  source_proposals,
  active,
  paper_only,
  automatic_application_enabled,
  rollback_ready,
  configuration
)
values (
  '5.4-baseline-0001',
  'AGENT_WEIGHT_SET',
  'MULTI_AGENT_COUNCIL',
  'ACTIVE',
  'Enterprise 5.4 initial baseline version.',
  null,
  '[]'::jsonb,
  true,
  true,
  false,
  true,
  '{"foundation_version":"5.4.0","baseline":true}'::jsonb
)
on conflict (version_no) do nothing;

-- =====================================================================
-- Initial status
-- =====================================================================
insert into public.adaptive_status_v54 (
  status_date,
  overall_status,
  current_candidate_version,
  proposals_generated,
  proposal_items_generated,
  safety_checks_run,
  shadow_tests_run,
  ready_for_review,
  candidate_versions,
  approved_versions,
  rejected_proposals,
  rollback_ready,
  automatic_proposal_application_enabled,
  automatic_agent_weight_update_enabled,
  automatic_risk_parameter_update_enabled,
  automatic_rollback_enabled,
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
  0,0,0,0,0,0,0,0,
  true,
  false,false,false,false,false,
  '["ADAPTIVE_GOVERNANCE_NOT_RUN"]'::jsonb,
  '[]'::jsonb,
  'Enterprise 5.4 foundation installed; Adaptive Governance has not run yet.',
  '{"foundation_version":"5.4.0","paper_only":true}'::jsonb
)
on conflict (status_date) do update
set
  automatic_proposal_application_enabled = false,
  automatic_agent_weight_update_enabled = false,
  automatic_risk_parameter_update_enabled = false,
  automatic_rollback_enabled = false,
  live_trading_enabled = false,
  updated_at = now();

insert into public.adaptive_metrics_v54 (
  metric_date,
  total_proposals,
  proposal_items,
  safety_checks,
  shadow_tests,
  ready_for_review,
  candidate_versions,
  approved_versions,
  rejected_proposals,
  rollback_snapshots,
  average_reliability,
  automatic_applications,
  diagnostics
)
values (
  current_date,
  0,0,0,0,0,0,0,0,0,0,0,
  '{"foundation_version":"5.4.0"}'::jsonb
)
on conflict (metric_date) do nothing;

-- =====================================================================
-- Dashboard view
-- =====================================================================
create or replace view public.adaptive_dashboard_v54 as
select
  p.proposal_date,
  p.id as proposal_id,
  p.proposal_key,
  p.proposal_type,
  p.proposal_title,
  p.status as proposal_status,
  p.priority,
  p.risk_level,
  p.evidence_count,
  p.safety_gate_passed,
  p.shadow_test_passed,
  r.review_result,
  r.review_time,
  s.simulation_status,
  s.stability_score,
  s.risk_regression_score,
  v.version_no as candidate_version,
  v.version_status,
  v.rollback_ready,
  st.overall_status,
  st.ready_for_review,
  st.candidate_versions,
  st.approved_versions,
  st.live_trading_enabled
from public.adaptive_proposals_v54 p
left join public.adaptive_reviews_v54 r
  on r.proposal_id = p.id
  and r.review_stage = 'AUTOMATED_GOVERNANCE'
left join lateral (
  select s1.*
  from public.shadow_simulations_v54 s1
  where s1.proposal_id = p.id
  order by s1.simulation_date desc, s1.created_at desc
  limit 1
) s on true
left join public.agent_weight_versions_v54 aw
  on aw.source_proposal_id = p.id
left join public.parameter_versions_v54 v
  on v.id = aw.version_id
left join public.adaptive_status_v54 st
  on st.status_date = p.proposal_date;

grant select on public.adaptive_dashboard_v54
to anon, authenticated;

notify pgrst, 'reload schema';

commit;

-- =====================================================================
-- Verification
-- =====================================================================
select
  'Enterprise 5.4 Foundation Database Pack v1.0 setup complete'
  as result;

select
  count(*) as v54_table_count
from information_schema.tables
where table_schema = 'public'
and table_name in (
  'adaptive_proposals_v54',
  'proposal_items_v54',
  'safety_gate_results_v54',
  'shadow_simulations_v54',
  'adaptive_reviews_v54',
  'parameter_versions_v54',
  'agent_weight_versions_v54',
  'strategy_versions_v54',
  'rollback_snapshots_v54',
  'rollback_history_v54',
  'adaptive_metrics_v54',
  'adaptive_status_v54'
);

select table_name
from information_schema.tables
where table_schema = 'public'
and table_name like '%v54'
order by table_name;

select table_name
from information_schema.views
where table_schema = 'public'
and table_name = 'adaptive_dashboard_v54';

select *
from public.adaptive_status_v54
order by status_date desc
limit 5;
