begin;

create table if not exists public.paper_position_sizing_plans_v92 (
    plan_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    plan_date date not null,

    governance_date date not null,
    risk_state text not null,
    new_paper_entries_authorized boolean not null,
    paper_halt boolean not null,
    risk_reduction_factor numeric not null,

    nav numeric not null,
    cash numeric not null,
    current_market_value numeric not null,
    current_portfolio_exposure numeric not null,

    base_risk_budget_pct numeric not null,
    effective_risk_budget_pct numeric not null,
    max_position_pct numeric not null,
    max_new_capital numeric not null,
    total_allocated_capital numeric not null,
    remaining_risk_budget numeric not null,

    eligible_signals integer not null,
    sized_candidates integer not null,

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

create unique index if not exists uq_paper_position_sizing_plans_v92_portfolio_date
    on public.paper_position_sizing_plans_v92 (portfolio_id, plan_date);

create table if not exists public.paper_position_sizing_items_v92 (
    item_id text primary key,
    plan_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    plan_date date not null,

    symbol text not null,
    rank integer,
    score numeric,
    signal text,

    real_market_price numeric not null,
    existing_position_market_value numeric not null default 0,

    raw_target_capital numeric not null,
    concentration_capital_limit numeric not null,
    risk_budget_capital_limit numeric not null,
    final_target_capital numeric not null,

    round_lot integer not null,
    paper_quantity numeric not null,
    estimated_notional numeric not null,

    allocation_state text not null,
    allocation_reason text,

    synthetic_market_data boolean not null default false,
    synthetic_signal boolean not null default false,
    fake_price boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_position_sizing_items_v92_plan_symbol
    on public.paper_position_sizing_items_v92 (plan_id, symbol);

alter table public.paper_position_sizing_plans_v92 enable row level security;
alter table public.paper_position_sizing_items_v92 enable row level security;

comment on table public.paper_position_sizing_plans_v92 is
'GPT Quant V9.2 paper-only portfolio risk-budget allocation plan. No broker execution authority.';

comment on table public.paper_position_sizing_items_v92 is
'GPT Quant V9.2 per-symbol paper position sizing output based on real canonical signals/prices and Phase 3.5.2 risk governance.';

commit;
