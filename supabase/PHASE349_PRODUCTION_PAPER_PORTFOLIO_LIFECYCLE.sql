begin;

create table if not exists public.paper_portfolios_v92 (
    portfolio_id text primary key,
    strategy_version text not null,
    trading_mode text not null,
    initial_cash numeric not null,
    cash numeric not null,
    realized_pnl numeric not null default 0,
    status text not null default 'ACTIVE',
    broker_trading_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.paper_positions_v92 (
    portfolio_id text not null,
    strategy_version text not null,
    symbol text not null,
    quantity numeric not null,
    avg_entry_price numeric not null,
    last_market_price numeric,
    market_value numeric not null default 0,
    unrealized_pnl numeric not null default 0,
    realized_pnl numeric not null default 0,
    opened_date date,
    last_mark_date date,
    status text not null default 'OPEN',
    synthetic_evidence boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    evidence_sha256 text,
    updated_at timestamptz not null default now(),
    primary key (portfolio_id, symbol)
);

create table if not exists public.paper_position_events_v92 (
    event_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    event_date date not null,
    event_type text not null,
    symbol text not null,
    quantity numeric not null,
    price numeric not null,
    cash_delta numeric not null,
    realized_pnl_delta numeric not null default 0,
    source_contract text not null,
    synthetic_evidence boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create table if not exists public.paper_portfolio_snapshots_v92 (
    snapshot_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    snapshot_date date not null,
    cash numeric not null,
    market_value numeric not null,
    nav numeric not null,
    realized_pnl numeric not null,
    unrealized_pnl numeric not null,
    open_positions integer not null,
    canonical_runtime_state text not null,
    daily_cycle_status text not null,
    market_data_source text,
    latest_market_date date,
    synthetic_evidence boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_portfolio_snapshots_v92_portfolio_date
    on public.paper_portfolio_snapshots_v92 (portfolio_id, snapshot_date);

alter table public.paper_portfolios_v92 enable row level security;
alter table public.paper_positions_v92 enable row level security;
alter table public.paper_position_events_v92 enable row level security;
alter table public.paper_portfolio_snapshots_v92 enable row level security;

comment on table public.paper_portfolios_v92 is
'GPT Quant V9.2 paper-only persistent portfolio ledger. Broker and real-money trading hard-disabled.';

comment on table public.paper_positions_v92 is
'GPT Quant V9.2 paper-only open-position ledger marked only from real canonical market evidence.';

comment on table public.paper_position_events_v92 is
'GPT Quant V9.2 paper position lifecycle audit log. Simulation only; no broker submission.';

comment on table public.paper_portfolio_snapshots_v92 is
'GPT Quant V9.2 daily paper portfolio NAV and mark-to-market snapshots.';

commit;
