begin;

create table if not exists public.paper_risk_governance_v92 (
    governance_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    governance_date date not null,

    analytics_state text not null,
    risk_state text not null,
    new_paper_entries_authorized boolean not null,
    paper_halt boolean not null,

    current_drawdown numeric,
    maximum_drawdown numeric,
    daily_return numeric,
    cumulative_return numeric,
    annualized_volatility numeric,
    sharpe_ratio numeric,

    portfolio_exposure numeric,
    max_position_concentration numeric,
    consecutive_loss_days integer not null default 0,

    drawdown_guard_triggered boolean not null default false,
    daily_loss_guard_triggered boolean not null default false,
    exposure_guard_triggered boolean not null default false,
    concentration_guard_triggered boolean not null default false,
    consecutive_loss_guard_triggered boolean not null default false,

    risk_reduction_factor numeric not null default 1.0,
    governance_reason text,

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

create unique index if not exists uq_paper_risk_governance_v92_portfolio_date
    on public.paper_risk_governance_v92 (portfolio_id, governance_date);

alter table public.paper_risk_governance_v92 enable row level security;

comment on table public.paper_risk_governance_v92 is
'GPT Quant V9.2 paper-only risk governance state. PAPER_HALT blocks new simulated entries only; broker and real-money trading remain disabled.';

commit;
