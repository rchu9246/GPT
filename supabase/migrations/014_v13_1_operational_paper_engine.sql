-- GPT Quant V13.1 Operational Paper Trading Engine
-- Run this AFTER 013_v13_autotrader.sql.
-- All writes require SUPABASE_SERVICE_ROLE_KEY. No anonymous write policy is created.

create extension if not exists pgcrypto;

alter table public.autotrader_configs_v13
  add column if not exists auto_fill boolean not null default false,
  add column if not exists max_daily_orders integer not null default 5,
  add column if not exists lot_size integer not null default 1,
  add column if not exists commission_rate numeric not null default 0.001425,
  add column if not exists sell_tax_rate numeric not null default 0.003,
  add column if not exists stop_loss_pct numeric not null default 8,
  add column if not exists take_profit_pct numeric not null default 15,
  add column if not exists exit_score numeric not null default 25,
  add column if not exists max_holding_days integer not null default 20,
  add column if not exists price_source text not null default 'LATEST_CLOSE',
  add column if not exists last_run_at timestamptz,
  add column if not exists last_run_status text,
  add column if not exists last_run_message text;

create table if not exists public.paper_accounts_v13 (
  account_name text primary key,
  starting_cash numeric not null default 1000000,
  cash numeric not null default 1000000,
  equity numeric not null default 1000000,
  realized_pnl numeric not null default 0,
  unrealized_pnl numeric not null default 0,
  total_fees numeric not null default 0,
  total_tax numeric not null default 0,
  updated_at timestamptz not null default now()
);

alter table public.trade_orders_v13
  add column if not exists signal_date date,
  add column if not exists execution_date date,
  add column if not exists fill_price numeric,
  add column if not exists commission numeric not null default 0,
  add column if not exists transaction_tax numeric not null default 0,
  add column if not exists realized_pnl numeric not null default 0,
  add column if not exists idempotency_key text,
  add column if not exists exit_reason text;

create unique index if not exists trade_orders_v13_idempotency_uidx
  on public.trade_orders_v13(idempotency_key)
  where idempotency_key is not null;

alter table public.paper_positions_v13
  add column if not exists stock_id bigint,
  add column if not exists name text,
  add column if not exists cost_basis numeric not null default 0,
  add column if not exists realized_pnl numeric not null default 0,
  add column if not exists opened_at timestamptz not null default now(),
  add column if not exists last_trade_date date,
  add column if not exists holding_days integer not null default 0;

create table if not exists public.paper_fills_v13 (
  id uuid primary key default gen_random_uuid(),
  order_id uuid references public.trade_orders_v13(id) on delete set null,
  account_name text not null,
  symbol text not null,
  side text not null check (side in ('BUY','SELL')),
  quantity integer not null check (quantity > 0),
  fill_price numeric not null check (fill_price > 0),
  gross_amount numeric not null,
  commission numeric not null default 0,
  transaction_tax numeric not null default 0,
  net_cash_flow numeric not null,
  realized_pnl numeric not null default 0,
  trade_date date not null,
  filled_at timestamptz not null default now()
);

create table if not exists public.paper_equity_snapshots_v13 (
  account_name text not null,
  snapshot_date date not null,
  cash numeric not null,
  market_value numeric not null,
  equity numeric not null,
  realized_pnl numeric not null default 0,
  unrealized_pnl numeric not null default 0,
  total_return numeric not null default 0,
  positions_count integer not null default 0,
  created_at timestamptz not null default now(),
  primary key (account_name, snapshot_date)
);

create table if not exists public.paper_engine_runs_v13 (
  id uuid primary key default gen_random_uuid(),
  account_name text not null,
  run_date date not null,
  status text not null check (status in ('RUNNING','SUCCESS','SKIPPED','FAILED')),
  signals_date date,
  buy_orders integer not null default 0,
  sell_orders integer not null default 0,
  fills integer not null default 0,
  message text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

alter table public.paper_accounts_v13 enable row level security;
alter table public.paper_fills_v13 enable row level security;
alter table public.paper_equity_snapshots_v13 enable row level security;
alter table public.paper_engine_runs_v13 enable row level security;

-- Seed one safe, disabled account configuration.
insert into public.autotrader_configs_v13 (
  account_name, mode, enabled, kill_switch, starting_cash,
  reserve_cash_pct, max_positions, max_position_pct,
  min_score, max_risk_score, require_approval, auto_fill
)
values (
  'paper-main', 'PAPER', false, false, 1000000,
  30, 5, 15, 40, 60, true, false
)
on conflict do nothing;

insert into public.paper_accounts_v13 (
  account_name, starting_cash, cash, equity
)
values ('paper-main', 1000000, 1000000, 1000000)
on conflict (account_name) do nothing;

-- To enable FULLY AUTOMATIC paper trading after testing:
-- update public.autotrader_configs_v13
-- set enabled = true,
--     mode = 'PAPER',
--     kill_switch = false,
--     require_approval = false,
--     auto_fill = true
-- where account_name = 'paper-main';
