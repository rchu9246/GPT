-- GPT Quant V9.2 Production Paper Trading / Shadow Production Phase 1
-- Safe foundation schema: simulation only, no broker execution.

create table if not exists public.gptq_paper_runs (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    status text not null default 'RUNNING',
    starting_cash numeric not null default 1000000,
    ending_cash numeric,
    ending_equity numeric,
    realized_pnl numeric not null default 0,
    unrealized_pnl numeric not null default 0,
    orders_created integer not null default 0,
    positions_open integer not null default 0,
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    unique(run_date, strategy_version)
);

create table if not exists public.gptq_paper_orders (
    id bigserial primary key,
    run_id bigint references public.gptq_paper_runs(id) on delete cascade,
    run_date date not null,
    strategy_version text not null,
    stock_id bigint not null,
    symbol text,
    side text not null check (side in ('BUY','SELL')),
    signal_score numeric,
    signal_label text,
    reference_price numeric,
    simulated_fill_price numeric,
    shares integer not null default 0,
    notional numeric not null default 0,
    status text not null default 'FILLED',
    reason text,
    created_at timestamptz not null default now()
);

create index if not exists idx_gptq_paper_orders_run_date
    on public.gptq_paper_orders(run_date, strategy_version);

create table if not exists public.gptq_paper_positions (
    id bigserial primary key,
    strategy_version text not null,
    stock_id bigint not null,
    symbol text,
    shares integer not null default 0,
    average_price numeric not null default 0,
    last_price numeric,
    market_value numeric,
    unrealized_pnl numeric not null default 0,
    opened_at date,
    updated_at timestamptz not null default now(),
    unique(strategy_version, stock_id)
);

create table if not exists public.gptq_paper_equity_snapshots (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    cash numeric not null,
    market_value numeric not null,
    total_equity numeric not null,
    realized_pnl numeric not null default 0,
    unrealized_pnl numeric not null default 0,
    open_positions integer not null default 0,
    created_at timestamptz not null default now(),
    unique(run_date, strategy_version)
);

alter table public.gptq_paper_runs enable row level security;
alter table public.gptq_paper_orders enable row level security;
alter table public.gptq_paper_positions enable row level security;
alter table public.gptq_paper_equity_snapshots enable row level security;
