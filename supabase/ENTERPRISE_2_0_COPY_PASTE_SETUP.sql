-- GPT Quant Enterprise 2.0 Foundation
-- This creates the stable core model. Existing V13-V22 tables are preserved.

create table if not exists public.quant_modules (
  id bigserial primary key,
  module_key text not null unique,
  module_name text not null,
  module_type text not null,
  current_version text not null,
  enabled boolean not null default true,
  execution_order integer not null default 100,
  config jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.quant_runs (
  id uuid primary key default gen_random_uuid(),
  account_name text not null default 'paper-main',
  run_date date not null,
  run_type text not null,
  status text not null default 'RUNNING',
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  module_count integer not null default 0,
  success_count integer not null default 0,
  failure_count integer not null default 0,
  summary jsonb not null default '{}'::jsonb,
  error_message text
);

create index if not exists quant_runs_account_date_idx
on public.quant_runs(account_name, run_date desc);

create table if not exists public.quant_decisions (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  decision_date date not null,
  decision_scope text not null,
  entity_type text not null,
  entity_key text not null,
  module_key text not null,
  engine_version text not null,
  action text not null,
  score numeric,
  confidence numeric,
  risk_score numeric,
  target_weight numeric,
  target_cash_pct numeric,
  status text not null default 'ACTIVE',
  rationale text not null,
  evidence jsonb not null default '{}'::jsonb,
  parent_decision_id bigint references public.quant_decisions(id) on delete set null,
  source_record jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_decisions_dedup_idx
on public.quant_decisions(
  account_name,
  decision_date,
  decision_scope,
  entity_type,
  entity_key,
  module_key,
  engine_version
);

create index if not exists quant_decisions_latest_idx
on public.quant_decisions(account_name, decision_date desc, decision_scope);

create table if not exists public.quant_orders (
  id uuid primary key default gen_random_uuid(),
  account_name text not null default 'paper-main',
  decision_id bigint references public.quant_decisions(id) on delete set null,
  external_order_id text,
  symbol text not null,
  side text not null,
  order_type text not null default 'MARKET',
  quantity integer not null,
  reference_price numeric,
  notional numeric,
  mode text not null default 'PAPER',
  status text not null default 'PROPOSED',
  approval_status text not null default 'PENDING',
  risk_status text not null default 'PENDING',
  idempotency_key text not null unique,
  reason_code text,
  reason_message text,
  proposed_at timestamptz not null default now(),
  approved_at timestamptz,
  filled_at timestamptz,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists quant_orders_status_idx
on public.quant_orders(account_name, status, proposed_at desc);

create table if not exists public.quant_positions (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  symbol text not null,
  quantity integer not null default 0,
  average_price numeric not null default 0,
  cost_basis numeric not null default 0,
  last_price numeric not null default 0,
  market_value numeric not null default 0,
  unrealized_pnl numeric not null default 0,
  realized_pnl numeric not null default 0,
  high_watermark_price numeric,
  holding_days integer not null default 0,
  status text not null default 'OPEN',
  opened_at timestamptz,
  closed_at timestamptz,
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create unique index if not exists quant_positions_account_symbol_idx
on public.quant_positions(account_name, symbol);

create table if not exists public.quant_portfolio_snapshots (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  snapshot_date date not null,
  equity numeric not null default 0,
  cash numeric not null default 0,
  market_value numeric not null default 0,
  gross_exposure_pct numeric not null default 0,
  net_exposure_pct numeric not null default 0,
  realized_pnl numeric not null default 0,
  unrealized_pnl numeric not null default 0,
  daily_return numeric not null default 0,
  total_return numeric not null default 0,
  max_drawdown numeric not null default 0,
  var_95 numeric not null default 0,
  expected_shortfall_95 numeric not null default 0,
  sharpe numeric not null default 0,
  positions_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_portfolio_snapshots_uidx
on public.quant_portfolio_snapshots(account_name, snapshot_date);

create table if not exists public.quant_reports (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_date date not null,
  report_type text not null,
  report_version text not null,
  headline text not null,
  executive_summary text not null,
  action_items text not null,
  status text not null default 'PUBLISHED',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_reports_uidx
on public.quant_reports(account_name, report_date, report_type, report_version);

create table if not exists public.quant_audit_logs (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  run_id uuid references public.quant_runs(id) on delete set null,
  module_key text not null,
  event_type text not null,
  severity text not null default 'INFO',
  entity_type text,
  entity_key text,
  message text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists quant_audit_logs_latest_idx
on public.quant_audit_logs(account_name, created_at desc);

create table if not exists public.quant_system_health (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  health_date date not null,
  overall_score numeric not null default 0,
  data_score numeric not null default 0,
  signal_score numeric not null default 0,
  execution_score numeric not null default 0,
  portfolio_score numeric not null default 0,
  risk_score numeric not null default 0,
  automation_score numeric not null default 0,
  status text not null,
  issues jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_system_health_uidx
on public.quant_system_health(account_name, health_date);

insert into public.quant_modules
  (module_key, module_name, module_type, current_version, execution_order, config)
values
  ('market_data', 'Market Data Pipeline', 'DATA', '2.0.0', 10, '{}'::jsonb),
  ('features', 'Feature Engine', 'ANALYTICS', '2.0.0', 20, '{}'::jsonb),
  ('signals', 'Signal Engine', 'DECISION', '2.0.0', 30, '{}'::jsonb),
  ('risk', 'Risk Engine', 'RISK', '2.0.0', 40, '{}'::jsonb),
  ('council', 'Investment Council', 'DECISION', '2.0.0', 50, '{}'::jsonb),
  ('director', 'Trading Director', 'GOVERNANCE', '2.0.0', 60, '{}'::jsonb),
  ('orders', 'Order Proposal Engine', 'EXECUTION', '2.0.0', 70, '{}'::jsonb),
  ('portfolio', 'Portfolio Engine', 'PORTFOLIO', '2.0.0', 80, '{}'::jsonb),
  ('reporting', 'Institutional Reporting', 'REPORTING', '2.0.0', 90, '{}'::jsonb)
on conflict (module_key) do update
set
  module_name = excluded.module_name,
  module_type = excluded.module_type,
  current_version = excluded.current_version,
  execution_order = excluded.execution_order,
  updated_at = now();

alter table public.quant_modules enable row level security;
alter table public.quant_decisions enable row level security;
alter table public.quant_orders enable row level security;
alter table public.quant_positions enable row level security;
alter table public.quant_portfolio_snapshots enable row level security;
alter table public.quant_reports enable row level security;
alter table public.quant_system_health enable row level security;

drop policy if exists "enterprise2 read modules" on public.quant_modules;
drop policy if exists "enterprise2 read decisions" on public.quant_decisions;
drop policy if exists "enterprise2 read orders" on public.quant_orders;
drop policy if exists "enterprise2 read positions" on public.quant_positions;
drop policy if exists "enterprise2 read portfolio" on public.quant_portfolio_snapshots;
drop policy if exists "enterprise2 read reports" on public.quant_reports;
drop policy if exists "enterprise2 read health" on public.quant_system_health;

create policy "enterprise2 read modules"
on public.quant_modules for select to anon, authenticated using (true);
create policy "enterprise2 read decisions"
on public.quant_decisions for select to anon, authenticated using (true);
create policy "enterprise2 read orders"
on public.quant_orders for select to anon, authenticated using (true);
create policy "enterprise2 read positions"
on public.quant_positions for select to anon, authenticated using (true);
create policy "enterprise2 read portfolio"
on public.quant_portfolio_snapshots for select to anon, authenticated using (true);
create policy "enterprise2 read reports"
on public.quant_reports for select to anon, authenticated using (true);
create policy "enterprise2 read health"
on public.quant_system_health for select to anon, authenticated using (true);

select 'GPT Quant Enterprise 2.0 Foundation setup complete' as result;
