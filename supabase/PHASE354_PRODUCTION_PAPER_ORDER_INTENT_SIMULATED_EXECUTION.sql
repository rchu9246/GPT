begin;

create table if not exists public.paper_order_intents_v92 (
    order_intent_id text primary key,
    plan_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    intent_date date not null,

    symbol text not null,
    side text not null,
    quantity numeric not null,
    reference_price numeric not null,
    estimated_notional numeric not null,

    risk_state text not null,
    allocation_state text not null,
    intent_state text not null,

    synthetic_market_data boolean not null default false,
    synthetic_signal boolean not null default false,
    fake_price boolean not null default false,
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

create unique index if not exists uq_paper_order_intents_v92_plan_symbol
    on public.paper_order_intents_v92 (plan_id, symbol);

create table if not exists public.paper_simulated_fills_v92 (
    fill_id text primary key,
    order_intent_id text not null,
    plan_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    fill_date date not null,

    symbol text not null,
    side text not null,
    quantity numeric not null,
    fill_price numeric not null,
    fill_notional numeric not null,

    execution_state text not null,
    price_source text not null,

    synthetic_market_data boolean not null default false,
    synthetic_signal boolean not null default false,
    fake_price boolean not null default false,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_simulated_fills_v92_order_intent
    on public.paper_simulated_fills_v92 (order_intent_id);

create table if not exists public.paper_execution_cycles_v92 (
    cycle_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    cycle_date date not null,

    plan_id text,
    risk_state text not null,
    new_paper_entries_authorized boolean not null,
    paper_halt boolean not null,

    sized_candidates integer not null,
    order_intents_created integer not null,
    simulated_fills_created integer not null,
    total_fill_notional numeric not null,

    execution_state text not null,

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

create unique index if not exists uq_paper_execution_cycles_v92_portfolio_date
    on public.paper_execution_cycles_v92 (portfolio_id, cycle_date);

alter table public.paper_order_intents_v92 enable row level security;
alter table public.paper_simulated_fills_v92 enable row level security;
alter table public.paper_execution_cycles_v92 enable row level security;

comment on table public.paper_order_intents_v92 is
'GPT Quant V9.2 paper-only order intents derived from Phase 3.5.3 sizing. No broker submission authority.';

comment on table public.paper_simulated_fills_v92 is
'GPT Quant V9.2 simulated fills only. Prices must come from real canonical market evidence.';

comment on table public.paper_execution_cycles_v92 is
'GPT Quant V9.2 daily paper execution lifecycle summary. Zero-order days are valid when no sized candidate exists.';

commit;
