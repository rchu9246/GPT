-- GPT Quant V16 explainable trading engine
create extension if not exists pgcrypto;

create table if not exists public.order_evaluations_v16 (
  id uuid primary key default gen_random_uuid(),
  account_name text not null default 'paper-main',
  evaluation_date date not null,
  stock_id bigint,
  symbol text,
  name text,
  score numeric not null default 0,
  risk_score numeric not null default 0,
  confidence numeric not null default 0,
  reference_price numeric,
  decision text not null check (decision in ('ACCEPTED','REJECTED','SKIPPED')),
  reason_code text not null,
  reason_message text,
  proposed_quantity integer not null default 0,
  proposed_notional numeric not null default 0,
  order_id uuid references public.trade_orders_v13(id) on delete set null,
  created_at timestamptz not null default now()
);
create unique index if not exists order_evaluations_v16_uidx
  on public.order_evaluations_v16(account_name,evaluation_date,symbol,reason_code);
alter table public.order_evaluations_v16 enable row level security;
drop policy if exists "v16 read order evaluations" on public.order_evaluations_v16;
create policy "v16 read order evaluations" on public.order_evaluations_v16
  for select to anon, authenticated using (true);

alter table public.autotrader_configs_v13
  add column if not exists selection_mode text not null default 'STRICT',
  add column if not exists fallback_top_n integer not null default 1,
  add column if not exists fallback_max_risk_score numeric not null default 70;
