begin;

create table if not exists public.paper_operational_readiness_v92 (
    readiness_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    readiness_date date not null,

    readiness_status text not null,
    readiness_score numeric not null,
    promotion_gate_open boolean not null default false,
    observation_required boolean not null default false,
    operator_action_required boolean not null default false,

    master_status text,
    master_final_state text,
    autonomous_operation_status text,
    recovery_state text,
    health_status text,
    health_score numeric,
    sla_status text,
    sla_score numeric,

    success_rate_7d numeric,
    recovery_rate_7d numeric,
    incident_count_7d integer,
    successful_streak_days integer,

    eligible_signals integer,
    sized_candidates integer,
    order_intents_created integer,
    simulated_fills_created integer,
    fills_settled integer,

    cash numeric,
    market_value numeric,
    nav numeric,
    open_positions integer,

    gate_checks jsonb not null default '{}'::jsonb,
    blocking_reasons jsonb not null default '[]'::jsonb,

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

create unique index if not exists uq_paper_operational_readiness_v92_portfolio_date
    on public.paper_operational_readiness_v92 (portfolio_id, readiness_date);

create table if not exists public.paper_promotion_gate_audit_v92 (
    gate_audit_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    audit_date date not null,

    readiness_id text not null,
    readiness_status text not null,
    promotion_gate_open boolean not null default false,
    observation_required boolean not null default false,
    operator_action_required boolean not null default false,

    approved_for_autonomous_paper_operations boolean not null default false,
    approved_for_broker_trading boolean not null default false,
    approved_for_real_money_trading boolean not null default false,
    approved_for_live_money_release boolean not null default false,

    blocking_reasons jsonb not null default '[]'::jsonb,
    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_promotion_gate_audit_v92_portfolio_date
    on public.paper_promotion_gate_audit_v92 (portfolio_id, audit_date);

alter table public.paper_operational_readiness_v92 enable row level security;
alter table public.paper_promotion_gate_audit_v92 enable row level security;

comment on table public.paper_operational_readiness_v92 is
'GPT Quant V9.2 operational-readiness gate for autonomous paper trading only.';

comment on table public.paper_promotion_gate_audit_v92 is
'GPT Quant V9.2 promotion-gate audit. Broker and real-money approvals are hard-disabled.';

commit;
