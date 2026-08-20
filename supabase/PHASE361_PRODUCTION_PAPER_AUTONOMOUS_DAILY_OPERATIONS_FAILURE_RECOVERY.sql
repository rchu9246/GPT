begin;

create table if not exists public.paper_autonomous_operations_v92 (
    operation_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    operation_date date not null,

    operation_status text not null,
    recovery_state text not null,
    attempt_count integer not null default 1,
    max_attempts integer not null default 2,

    master_cycle_id text,
    master_final_state text,
    failed_stage text,
    failure_message text,

    zero_signal_valid boolean not null default false,
    zero_order_valid boolean not null default false,
    zero_fill_valid boolean not null default false,

    first_attempt_started_at timestamptz not null,
    last_attempt_started_at timestamptz not null,
    completed_at timestamptz,

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

create unique index if not exists uq_paper_autonomous_operations_v92_portfolio_date
    on public.paper_autonomous_operations_v92 (portfolio_id, operation_date);

create table if not exists public.paper_operation_attempts_v92 (
    attempt_id text primary key,
    operation_id text not null,
    portfolio_id text not null,
    strategy_version text not null,
    operation_date date not null,

    attempt_number integer not null,
    attempt_status text not null,
    failed_stage text,
    failure_message text,

    master_cycle_id text,
    master_final_state text,

    started_at timestamptz not null,
    completed_at timestamptz not null,

    evidence_sha256 text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_paper_operation_attempts_v92_operation_attempt
    on public.paper_operation_attempts_v92 (operation_id, attempt_number);

alter table public.paper_autonomous_operations_v92 enable row level security;
alter table public.paper_operation_attempts_v92 enable row level security;

comment on table public.paper_autonomous_operations_v92 is
'GPT Quant V9.2 autonomous production-paper daily operations ledger with bounded recovery. No broker or real-money authority.';

comment on table public.paper_operation_attempts_v92 is
'GPT Quant V9.2 autonomous production-paper attempt/recovery audit trail.';

commit;
