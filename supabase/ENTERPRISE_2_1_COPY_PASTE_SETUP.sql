-- GPT Quant Enterprise 2.1 Operational Platform

create table if not exists public.quant_operational_status (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  status_date date not null,
  pipeline_status text not null,
  data_freshness_status text not null,
  signals_status text not null,
  orders_status text not null,
  portfolio_status text not null,
  risk_status text not null,
  reports_status text not null,
  overall_score numeric not null default 0,
  latest_data_date date,
  latest_signal_date date,
  proposed_orders integer not null default 0,
  approved_orders integer not null default 0,
  filled_orders integer not null default 0,
  open_positions integer not null default 0,
  issues jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_operational_status_uidx
on public.quant_operational_status(account_name, status_date);

create table if not exists public.quant_risk_limits (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  limit_key text not null,
  limit_value numeric not null,
  warning_value numeric,
  enabled boolean not null default true,
  unit text not null default 'PCT',
  description text,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create unique index if not exists quant_risk_limits_uidx
on public.quant_risk_limits(account_name, limit_key);

create table if not exists public.quant_risk_events (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  event_date date not null,
  event_type text not null,
  severity text not null,
  metric_value numeric,
  limit_value numeric,
  entity_type text,
  entity_key text,
  message text not null,
  status text not null default 'OPEN',
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists quant_risk_events_latest_idx
on public.quant_risk_events(account_name, event_date desc, severity);

create table if not exists public.quant_daily_briefs (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  brief_date date not null,
  brief_type text not null,
  headline text not null,
  summary text not null,
  market_view text not null,
  portfolio_view text not null,
  risk_view text not null,
  action_plan text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists quant_daily_briefs_uidx
on public.quant_daily_briefs(account_name, brief_date, brief_type);

insert into public.quant_risk_limits
  (account_name, limit_key, limit_value, warning_value, unit, description)
values
  ('paper-main', 'MAX_DRAWDOWN_PCT', 12, 8, 'PCT', 'Maximum allowed portfolio drawdown'),
  ('paper-main', 'VAR_95_PCT', 3, 2, 'PCT', 'Maximum one-day 95% VaR as equity percentage'),
  ('paper-main', 'MAX_GROSS_EXPOSURE_PCT', 100, 85, 'PCT', 'Maximum gross exposure'),
  ('paper-main', 'MAX_SINGLE_POSITION_PCT', 15, 12, 'PCT', 'Maximum single position weight'),
  ('paper-main', 'MIN_CASH_PCT', 25, 30, 'PCT', 'Minimum preferred cash reserve')
on conflict (account_name, limit_key) do update
set
  limit_value = excluded.limit_value,
  warning_value = excluded.warning_value,
  unit = excluded.unit,
  description = excluded.description,
  updated_at = now();

alter table public.quant_operational_status enable row level security;
alter table public.quant_risk_limits enable row level security;
alter table public.quant_risk_events enable row level security;
alter table public.quant_daily_briefs enable row level security;

drop policy if exists "enterprise21 read operational status" on public.quant_operational_status;
drop policy if exists "enterprise21 read risk limits" on public.quant_risk_limits;
drop policy if exists "enterprise21 read risk events" on public.quant_risk_events;
drop policy if exists "enterprise21 read daily briefs" on public.quant_daily_briefs;

create policy "enterprise21 read operational status"
on public.quant_operational_status for select to anon, authenticated using (true);
create policy "enterprise21 read risk limits"
on public.quant_risk_limits for select to anon, authenticated using (true);
create policy "enterprise21 read risk events"
on public.quant_risk_events for select to anon, authenticated using (true);
create policy "enterprise21 read daily briefs"
on public.quant_daily_briefs for select to anon, authenticated using (true);

select 'GPT Quant Enterprise 2.1 Operational Platform setup complete' as result;
