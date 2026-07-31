-- GPT Quant V20 Institutional Edition
-- Copy the entire file into Supabase SQL Editor and press Run.

create table if not exists public.performance_attribution_v20 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  attribution_date date not null,
  component text not null,
  contribution numeric not null default 0,
  exposure numeric not null default 0,
  detail text,
  created_at timestamptz not null default now()
);

create unique index if not exists performance_attribution_v20_uidx
on public.performance_attribution_v20(
  account_name,
  attribution_date,
  component
);

create table if not exists public.institutional_reports_v20 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  report_date date not null,
  system_health numeric not null default 0,
  data_status text not null,
  signal_status text not null,
  execution_status text not null,
  portfolio_status text not null,
  risk_status text not null,
  strategy_status text not null,
  headline text not null,
  executive_summary text not null,
  action_items text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists institutional_reports_v20_uidx
on public.institutional_reports_v20(account_name, report_date);

alter table public.performance_attribution_v20 enable row level security;
alter table public.institutional_reports_v20 enable row level security;

drop policy if exists "v20 read attribution"
on public.performance_attribution_v20;

drop policy if exists "v20 read reports"
on public.institutional_reports_v20;

create policy "v20 read attribution"
on public.performance_attribution_v20
for select to anon, authenticated
using (true);

create policy "v20 read reports"
on public.institutional_reports_v20
for select to anon, authenticated
using (true);

select 'V20 Institutional Edition setup complete' as result;
