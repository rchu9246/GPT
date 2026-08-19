begin;

create table if not exists public.paper_performance_ledger_v92 (
    ledger_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    ledger_date date not null,

    cycle_status text not null,
    canonical_runtime_state text not null,
    market_data_source text,
    latest_market_date date,

    cash numeric not null,
    market_value numeric not null,
    nav numeric not null,
    realized_pnl numeric not null,
    unrealized_pnl numeric not null,

    previous_nav numeric,
    initial_nav numeric not null,
    daily_return numeric not null,
    cumulative_return numeric not null,
    high_water_mark numeric not null,
    drawdown numeric not null,

    open_positions integer not null,
    eligible_signals integer not null,
    fills_applied integer not null,

    synthetic_market_data boolean not null default false,
    synthetic_signals boolean not null default false,
    fake_prices_allowed boolean not null default false,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_performance_ledger_v92_portfolio_date
    on public.paper_performance_ledger_v92 (portfolio_id, ledger_date);

alter table public.paper_performance_ledger_v92 enable row level security;

comment on table public.paper_performance_ledger_v92 is
'GPT Quant V9.2 persistent daily paper performance ledger. Simulation only; broker and real-money trading hard-disabled.';

commit;
