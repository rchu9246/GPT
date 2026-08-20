begin;

create table if not exists public.paper_performance_analytics_v92 (
    analytics_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    as_of_date date not null,
    analytics_state text not null,
    ledger_rows integer not null,
    first_ledger_date date not null,
    last_ledger_date date not null,
    initial_nav numeric not null,
    current_nav numeric not null,
    daily_return numeric not null,
    cumulative_return numeric not null,
    annualized_volatility numeric,
    sharpe_ratio numeric,
    current_drawdown numeric not null,
    max_drawdown numeric not null,
    positive_days integer not null,
    negative_days integer not null,
    flat_days integer not null,
    win_rate numeric,
    average_gain numeric,
    average_loss numeric,
    profit_factor numeric,
    return_observations integer not null,
    min_history_required integer not null,
    risk_free_rate_annual numeric not null default 0,
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

create unique index if not exists uq_paper_performance_analytics_v92_portfolio_date
    on public.paper_performance_analytics_v92 (portfolio_id, as_of_date);

alter table public.paper_performance_analytics_v92 enable row level security;

comment on table public.paper_performance_analytics_v92 is
'GPT Quant V9.2 production-paper performance analytics and risk metrics derived only from canonical paper_performance_ledger_v92. Simulation only; broker and real-money trading hard-disabled.';

commit;
