begin;

create table if not exists public.paper_system_health_v92 (
    health_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    health_date date not null,

    health_status text not null,
    health_score numeric not null,
    incident_required boolean not null default false,

    autonomous_operation_status text,
    recovery_state text,
    master_final_state text,
    market_data_status text,
    latest_market_date date,

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

    checks_passed integer not null,
    checks_failed integer not null,
    check_details jsonb not null default '{}'::jsonb,

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

create unique index if not exists uq_paper_system_health_v92_portfolio_date
    on public.paper_system_health_v92 (portfolio_id, health_date);

create table if not exists public.paper_incident_audit_v92 (
    incident_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    incident_date date not null,

    severity text not null,
    incident_type text not null,
    incident_state text not null,
    source_phase text,
    source_health_id text,

    summary text not null,
    details jsonb not null default '{}'::jsonb,

    autonomous_recovery_attempted boolean not null default false,
    autonomous_recovery_succeeded boolean not null default false,
    operator_action_required boolean not null default false,

    synthetic_market_data boolean not null default false,
    synthetic_signals boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    fail_closed_policy boolean not null default true,

    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_paper_incident_audit_v92_date
    on public.paper_incident_audit_v92 (portfolio_id, incident_date desc);

alter table public.paper_system_health_v92 enable row level security;
alter table public.paper_incident_audit_v92 enable row level security;

comment on table public.paper_system_health_v92 is
'GPT Quant V9.2 autonomous production-paper health snapshots. Paper-only, no broker authority.';

comment on table public.paper_incident_audit_v92 is
'GPT Quant V9.2 autonomous production-paper incident audit ledger.';

commit;
