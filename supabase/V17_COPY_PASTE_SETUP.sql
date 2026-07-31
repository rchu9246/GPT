-- GPT Quant V17 Portfolio OS setup

alter table public.autotrader_configs_v13
  add column if not exists trailing_stop_pct numeric not null default 7;

alter table public.paper_positions_v13
  add column if not exists high_watermark_price numeric;

create table if not exists public.portfolio_decisions_v17 (
  id bigserial primary key,
  account_name text not null default 'paper-main',
  decision_date date not null,
  symbol text not null,
  quantity integer,
  average_price numeric,
  current_price numeric,
  market_value numeric,
  unrealized_pnl numeric,
  score numeric,
  risk_score numeric,
  decision text not null,
  reason_code text not null,
  reason_message text,
  created_at timestamptz not null default now()
);

create unique index if not exists portfolio_decisions_v17_uidx
on public.portfolio_decisions_v17(
  account_name,
  decision_date,
  symbol,
  reason_code
);

alter table public.portfolio_decisions_v17 enable row level security;

drop policy if exists "v17 read portfolio decisions"
on public.portfolio_decisions_v17;

create policy "v17 read portfolio decisions"
on public.portfolio_decisions_v17
for select
to anon, authenticated
using (true);

select 'V17 Portfolio OS setup complete' as result;
