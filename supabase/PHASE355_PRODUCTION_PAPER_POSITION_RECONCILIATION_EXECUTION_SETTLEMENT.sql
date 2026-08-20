begin;

create table if not exists public.paper_settlement_cycles_v92 (
    settlement_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    settlement_date date not null,

    execution_cycle_id text,
    execution_state text not null,
    settlement_state text not null,

    fills_discovered integer not null,
    fills_settled integer not null,
    fills_already_settled integer not null,

    cash_before numeric not null,
    cash_after numeric not null,
    market_value_after numeric not null,
    nav_after numeric not null,
    realized_pnl_after numeric not null,
    unrealized_pnl_after numeric not null,
    open_positions_after integer not null,

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

create unique index if not exists uq_paper_settlement_cycles_v92_portfolio_date
    on public.paper_settlement_cycles_v92 (portfolio_id, settlement_date);

create table if not exists public.paper_fill_settlements_v92 (
    fill_settlement_id text primary key,
    settlement_id text not null,
    fill_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    settlement_date date not null,

    symbol text not null,
    side text not null,
    quantity numeric not null,
    fill_price numeric not null,
    fill_notional numeric not null,

    cash_delta numeric not null,
    realized_pnl_delta numeric not null default 0,
    position_quantity_after numeric not null,
    position_avg_entry_price_after numeric not null,
    settlement_state text not null,

    synthetic_market_data boolean not null default false,
    synthetic_signal boolean not null default false,
    fake_price boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,

    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_fill_settlements_v92_fill
    on public.paper_fill_settlements_v92 (fill_id);

alter table public.paper_settlement_cycles_v92 enable row level security;
alter table public.paper_fill_settlements_v92 enable row level security;

comment on table public.paper_settlement_cycles_v92 is
'GPT Quant V9.2 paper-only settlement-cycle ledger. Reconciles simulated fills into persistent paper cash/positions/NAV.';

comment on table public.paper_fill_settlements_v92 is
'GPT Quant V9.2 idempotent per-fill paper settlement audit log. No broker or real-money settlement.';

commit;
