begin;

create table if not exists public.paper_observability_daily_v92 (
    observability_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    observation_date date not null,

    health_status text not null,
    autonomous_operation_status text,
    recovery_state text,
    master_final_state text,

    end_to_end_duration_seconds numeric,
    stage_duration_seconds jsonb not null default '{}'::jsonb,

    success_rate_7d numeric,
    recovery_rate_7d numeric,
    incident_count_7d integer,
    successful_streak_days integer,

    sla_status text not null,
    sla_score numeric not null,
    sla_details jsonb not null default '{}'::jsonb,

    cash numeric,
    market_value numeric,
    nav numeric,
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
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_observability_daily_v92_portfolio_date
    on public.paper_observability_daily_v92 (portfolio_id, observation_date);

create table if not exists public.paper_sla_audit_v92 (
    sla_audit_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    audit_date date not null,

    sla_status text not null,
    overall_score numeric not null,

    max_cycle_seconds numeric not null,
    min_success_rate_7d numeric not null,
    max_recovery_rate_7d numeric not null,
    max_incidents_7d integer not null,

    measured_cycle_seconds numeric,
    measured_success_rate_7d numeric,
    measured_recovery_rate_7d numeric,
    measured_incidents_7d integer,

    breach_reasons jsonb not null default '[]'::jsonb,
    operator_action_required boolean not null default false,

    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_sla_audit_v92_portfolio_date
    on public.paper_sla_audit_v92 (portfolio_id, audit_date);

alter table public.paper_observability_daily_v92 enable row level security;
alter table public.paper_sla_audit_v92 enable row level security;

comment on table public.paper_observability_daily_v92 is
'GPT Quant V9.2 production-paper observability ledger with rolling health and duration metrics.';

comment on table public.paper_sla_audit_v92 is
'GPT Quant V9.2 production-paper SLA audit ledger. No broker or real-money authority.';

commit;
