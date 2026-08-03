begin;

create extension if not exists pgcrypto;

create or replace function public.enterprise52_set_updated_at()
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

create table if not exists public.execution_constraints_v52 (
  id uuid primary key default gen_random_uuid(),
  constraint_key text not null unique,
  constraint_name text not null,
  constraint_scope text not null,
  constraint_type text not null,
  numeric_value numeric,
  text_value text,
  severity text not null default 'WARNING',
  action_on_breach text not null default 'BLOCK',
  enabled boolean not null default true,
  paper_only boolean not null default true,
  live_enabled boolean not null default false,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint execution_constraints_v52_scope_chk
    check (constraint_scope in ('ORDER','BATCH','PORTFOLIO','SYSTEM')),
  constraint execution_constraints_v52_severity_chk
    check (severity in ('INFO','WARNING','CRITICAL')),
  constraint execution_constraints_v52_action_chk
    check (action_on_breach in ('WARN','REDUCE','BLOCK','CANCEL')),
  constraint execution_constraints_v52_safety_chk
    check (paper_only = true and live_enabled = false)
);

create table if not exists public.execution_plans_v52 (
  id uuid primary key default gen_random_uuid(),
  plan_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  council_decision_id uuid references public.decision_council_v51(id) on delete set null,
  session_id uuid references public.council_sessions_v51(id) on delete set null,
  cycle_id uuid,
  market_regime text not null default 'UNKNOWN',
  final_decision text not null,
  execution_mode text not null default 'PAPER',
  plan_status text not null default 'DRAFT',
  target_exposure_pct numeric not null default 0,
  target_cash_pct numeric not null default 100,
  expected_turnover_pct numeric not null default 0,
  expected_order_count integer not null default 0,
  approved_order_count integer not null default 0,
  rejected_order_count integer not null default 0,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  rationale text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  paper_approved boolean not null default true,
  live_approved boolean not null default false,
  broker_submission_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint execution_plans_v52_mode_chk
    check (execution_mode in ('PAPER','SIMULATION')),
  constraint execution_plans_v52_status_chk
    check (plan_status in ('DRAFT','VALIDATED','APPROVED_FOR_PAPER','BLOCKED','CANCELLED','COMPLETED')),
  constraint execution_plans_v52_safety_chk
    check (
      paper_approved = true and
      live_approved = false and
      broker_submission_enabled = false
    )
);

create unique index if not exists execution_plans_v52_uidx
on public.execution_plans_v52(plan_date, portfolio_id, council_decision_id);

create table if not exists public.execution_batches_v52 (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.execution_plans_v52(id) on delete cascade,
  batch_no integer not null,
  batch_status text not null default 'DRAFT',
  priority integer not null default 100,
  scheduled_at timestamptz,
  order_count integer not null default 0,
  approved_count integer not null default 0,
  rejected_count integer not null default 0,
  estimated_value numeric not null default 0,
  estimated_turnover_pct numeric not null default 0,
  paper_only boolean not null default true,
  live_submission_enabled boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint execution_batches_v52_status_chk
    check (batch_status in ('DRAFT','READY','VALIDATED','BLOCKED','COMPLETED','CANCELLED')),
  constraint execution_batches_v52_safety_chk
    check (paper_only = true and live_submission_enabled = false)
);

create unique index if not exists execution_batches_v52_uidx
on public.execution_batches_v52(plan_id, batch_no);

create table if not exists public.execution_orders_v52 (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.execution_plans_v52(id) on delete cascade,
  batch_id uuid references public.execution_batches_v52(id) on delete set null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  source_trade_plan_id uuid references public.trade_plans_v49(id) on delete set null,
  symbol text not null,
  asset_type text not null default 'STRATEGY',
  side text not null,
  order_type text not null default 'TARGET_WEIGHT',
  target_weight_pct numeric not null default 0,
  current_weight_pct numeric not null default 0,
  delta_weight_pct numeric not null default 0,
  quantity numeric,
  estimated_price numeric,
  estimated_value numeric not null default 0,
  priority integer not null default 100,
  confidence numeric not null default 0,
  risk_level text not null default 'MEDIUM',
  order_status text not null default 'DRAFT',
  validation_status text not null default 'PENDING',
  rejection_reason text,
  reason text not null,
  evidence jsonb not null default '{}'::jsonb,
  paper_only boolean not null default true,
  live_submission_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint execution_orders_v52_side_chk
    check (side in ('BUY','SELL','REDUCE','EXIT','HOLD')),
  constraint execution_orders_v52_status_chk
    check (order_status in ('DRAFT','READY','QUEUED','SIMULATED','REJECTED','CANCELLED')),
  constraint execution_orders_v52_validation_chk
    check (validation_status in ('PENDING','APPROVED','REDUCED','BLOCKED')),
  constraint execution_orders_v52_conf_chk
    check (confidence between 0 and 100),
  constraint execution_orders_v52_safety_chk
    check (paper_only = true and live_submission_enabled = false)
);

create unique index if not exists execution_orders_v52_uidx
on public.execution_orders_v52(plan_id, symbol, side);

create index if not exists execution_orders_v52_status_idx
on public.execution_orders_v52(order_status, validation_status, priority);

create table if not exists public.execution_risk_checks_v52 (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.execution_plans_v52(id) on delete cascade,
  order_id uuid references public.execution_orders_v52(id) on delete cascade,
  constraint_key text not null,
  check_scope text not null,
  observed_value numeric,
  limit_value numeric,
  check_status text not null,
  severity text not null,
  action_taken text not null,
  message text not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint execution_risk_checks_v52_scope_chk
    check (check_scope in ('ORDER','BATCH','PORTFOLIO','SYSTEM')),
  constraint execution_risk_checks_v52_status_chk
    check (check_status in ('PASS','WARNING','FAILED','BLOCKED')),
  constraint execution_risk_checks_v52_severity_chk
    check (severity in ('INFO','WARNING','CRITICAL'))
);

create index if not exists execution_risk_checks_v52_plan_idx
on public.execution_risk_checks_v52(plan_id, check_status, severity);

create table if not exists public.execution_metrics_v52 (
  id uuid primary key default gen_random_uuid(),
  metric_date date not null,
  plan_id uuid references public.execution_plans_v52(id) on delete cascade,
  plans_created integer not null default 0,
  batches_created integer not null default 0,
  orders_created integer not null default 0,
  approved_orders integer not null default 0,
  reduced_orders integer not null default 0,
  rejected_orders integer not null default 0,
  blocked_plans integer not null default 0,
  average_confidence numeric not null default 0,
  expected_turnover_pct numeric not null default 0,
  estimated_total_value numeric not null default 0,
  runtime_seconds numeric not null default 0,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists execution_metrics_v52_uidx
on public.execution_metrics_v52(metric_date, plan_id);

create table if not exists public.execution_audit_v52 (
  id uuid primary key default gen_random_uuid(),
  audit_time timestamptz not null default now(),
  audit_date date not null default current_date,
  plan_id uuid references public.execution_plans_v52(id) on delete cascade,
  order_id uuid references public.execution_orders_v52(id) on delete cascade,
  event_type text not null,
  event_status text not null,
  actor text not null default 'ENTERPRISE52_EXECUTION_LAYER',
  message text not null,
  previous_state jsonb not null default '{}'::jsonb,
  new_state jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists execution_audit_v52_date_idx
on public.execution_audit_v52(audit_time desc);

create table if not exists public.execution_status_v52 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  current_plan_id uuid,
  plans_created integer not null default 0,
  plans_approved integer not null default 0,
  plans_blocked integer not null default 0,
  batches_created integer not null default 0,
  orders_created integer not null default 0,
  orders_approved integer not null default 0,
  orders_reduced integer not null default 0,
  orders_rejected integer not null default 0,
  risk_checks_run integer not null default 0,
  risk_checks_failed integer not null default 0,
  average_confidence numeric not null default 0,
  expected_turnover_pct numeric not null default 0,
  paper_mode_enabled boolean not null default true,
  live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  summary text not null,
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint execution_status_v52_status_chk
    check (overall_status in ('PASS','WARNING','CRITICAL')),
  constraint execution_status_v52_safety_chk
    check (
      paper_mode_enabled = true and
      live_trading_enabled = false and
      broker_submission_enabled = false
    )
);

drop trigger if exists execution_constraints_v52_set_updated_at on public.execution_constraints_v52;
create trigger execution_constraints_v52_set_updated_at
before update on public.execution_constraints_v52
for each row execute function public.enterprise52_set_updated_at();

drop trigger if exists execution_plans_v52_set_updated_at on public.execution_plans_v52;
create trigger execution_plans_v52_set_updated_at
before update on public.execution_plans_v52
for each row execute function public.enterprise52_set_updated_at();

drop trigger if exists execution_batches_v52_set_updated_at on public.execution_batches_v52;
create trigger execution_batches_v52_set_updated_at
before update on public.execution_batches_v52
for each row execute function public.enterprise52_set_updated_at();

drop trigger if exists execution_orders_v52_set_updated_at on public.execution_orders_v52;
create trigger execution_orders_v52_set_updated_at
before update on public.execution_orders_v52
for each row execute function public.enterprise52_set_updated_at();

drop trigger if exists execution_metrics_v52_set_updated_at on public.execution_metrics_v52;
create trigger execution_metrics_v52_set_updated_at
before update on public.execution_metrics_v52
for each row execute function public.enterprise52_set_updated_at();

drop trigger if exists execution_status_v52_set_updated_at on public.execution_status_v52;
create trigger execution_status_v52_set_updated_at
before update on public.execution_status_v52
for each row execute function public.enterprise52_set_updated_at();

do $$
declare
  t text;
  p text;
begin
  foreach t in array array[
    'execution_constraints_v52',
    'execution_plans_v52',
    'execution_batches_v52',
    'execution_orders_v52',
    'execution_risk_checks_v52',
    'execution_metrics_v52',
    'execution_audit_v52',
    'execution_status_v52'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    p := 'enterprise52 read ' || t;
    execute format('drop policy if exists %I on public.%I', p, t);
    execute format(
      'create policy %I on public.%I for select to anon, authenticated using (true)',
      p, t
    );
    execute format('grant select on public.%I to anon, authenticated', t);
  end loop;
end $$;

insert into public.execution_constraints_v52 (
  constraint_key, constraint_name, constraint_scope, constraint_type,
  numeric_value, severity, action_on_breach, enabled,
  paper_only, live_enabled, description
)
values
('MAX_ORDER_WEIGHT_CHANGE_PCT','Maximum Order Weight Change','ORDER','MAX_VALUE',25,'CRITICAL','REDUCE',true,true,false,'Maximum absolute target-weight change per simulated order.'),
('MAX_DAILY_TURNOVER_PCT','Maximum Daily Turnover','PORTFOLIO','MAX_VALUE',60,'CRITICAL','BLOCK',true,true,false,'Maximum aggregate daily turnover for a portfolio.'),
('MIN_ORDER_CONFIDENCE','Minimum Order Confidence','ORDER','MIN_VALUE',40,'WARNING','BLOCK',true,true,false,'Minimum confidence required to approve a Paper order.'),
('MAX_GROSS_EXPOSURE_PCT','Maximum Gross Exposure','PORTFOLIO','MAX_VALUE',100,'CRITICAL','BLOCK',true,true,false,'Maximum gross exposure after execution.'),
('MIN_CASH_PCT','Minimum Cash Percentage','PORTFOLIO','MIN_VALUE',20,'CRITICAL','BLOCK',true,true,false,'Minimum cash allocation after execution.'),
('BLOCK_COUNCIL_DECISION','Block Council Decision','SYSTEM','TEXT_MATCH',null,'CRITICAL','BLOCK',true,true,false,'Blocks execution when Council final decision is BLOCK.')
on conflict (constraint_key) do update
set
  constraint_name = excluded.constraint_name,
  constraint_scope = excluded.constraint_scope,
  constraint_type = excluded.constraint_type,
  numeric_value = excluded.numeric_value,
  severity = excluded.severity,
  action_on_breach = excluded.action_on_breach,
  enabled = true,
  paper_only = true,
  live_enabled = false,
  description = excluded.description,
  updated_at = now();

insert into public.execution_status_v52 (
  status_date, overall_status, plans_created, plans_approved,
  plans_blocked, batches_created, orders_created,
  orders_approved, orders_reduced, orders_rejected,
  risk_checks_run, risk_checks_failed, average_confidence,
  expected_turnover_pct, paper_mode_enabled,
  live_trading_enabled, broker_submission_enabled,
  blockers, warnings, summary, diagnostics
)
values (
  current_date, 'WARNING', 0,0,0,0,0,0,0,0,0,0,0,0,
  true,false,false,
  '["EXECUTION_LAYER_NOT_RUN"]'::jsonb,
  '[]'::jsonb,
  'Enterprise 5.2 foundation installed; execution intelligence has not run yet.',
  '{"foundation_version":"5.2.0"}'::jsonb
)
on conflict (status_date) do nothing;

create or replace view public.execution_dashboard_v52 as
select
  p.plan_date,
  p.id as plan_id,
  p.plan_status,
  p.final_decision,
  p.market_regime,
  p.target_exposure_pct,
  p.target_cash_pct,
  p.expected_turnover_pct,
  p.expected_order_count,
  p.approved_order_count,
  p.rejected_order_count,
  count(distinct b.id) as batch_count,
  count(distinct o.id) as order_count,
  count(distinct r.id) as risk_check_count
from public.execution_plans_v52 p
left join public.execution_batches_v52 b on b.plan_id = p.id
left join public.execution_orders_v52 o on o.plan_id = p.id
left join public.execution_risk_checks_v52 r on r.plan_id = p.id
group by
  p.plan_date, p.id, p.plan_status, p.final_decision,
  p.market_regime, p.target_exposure_pct, p.target_cash_pct,
  p.expected_turnover_pct, p.expected_order_count,
  p.approved_order_count, p.rejected_order_count;

grant select on public.execution_dashboard_v52 to anon, authenticated;

notify pgrst, 'reload schema';

commit;

select 'Enterprise 5.2 Foundation Database Pack v1.0 setup complete' as result;
