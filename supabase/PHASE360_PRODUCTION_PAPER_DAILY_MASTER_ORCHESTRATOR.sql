begin;

create table if not exists public.paper_master_cycles_v92 (
    master_cycle_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    cycle_date date not null,

    master_status text not null,
    final_state text not null,
    failed_stage text,

    phase350_status text,
    phase351_status text,
    phase352_status text,
    phase353_status text,
    phase354_status text,
    phase355_status text,
    phase356_status text,

    canonical_runtime_state text,
    analytics_state text,
    risk_state text,
    execution_state text,
    settlement_state text,

    eligible_signals integer,
    sized_candidates integer,
    order_intents_created integer,
    simulated_fills_created integer,
    fills_settled integer,

    cash numeric,
    market_value numeric,
    nav numeric,
    realized_pnl numeric,
    unrealized_pnl numeric,
    open_positions integer,

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
    started_at timestamptz not null,
    completed_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_master_cycles_v92_portfolio_date
    on public.paper_master_cycles_v92 (portfolio_id, cycle_date);

alter table public.paper_master_cycles_v92 enable row level security;

comment on table public.paper_master_cycles_v92 is
'GPT Quant V9.2 Production Paper Daily Master Orchestrator audit ledger. Paper-only, fail-closed, no broker or real-money authority.';

commit;
