-- GPT Quant V9.2 Paper Trading Phase 2.1
-- Live Market Data + Signal Generation
-- SHADOW ONLY / NO BROKER EXECUTION

alter table if exists public.gptq_paper_signals
    add column if not exists market_date date,
    add column if not exists rank_no integer,
    add column if not exists trend_score numeric,
    add column if not exists momentum_score numeric,
    add column if not exists volume_score numeric,
    add column if not exists breakout_score numeric,
    add column if not exists risk_score numeric,
    add column if not exists rsi14 numeric,
    add column if not exists roc20 numeric,
    add column if not exists volume_ratio numeric,
    add column if not exists atr_pct numeric,
    add column if not exists data_rows integer,
    add column if not exists data_fresh boolean not null default false;

create table if not exists public.gptq_market_data_health (
    id bigserial primary key,
    run_date date not null,
    source_table text not null,
    active_stocks integer not null default 0,
    stocks_with_history integer not null default 0,
    latest_market_date date,
    stale_days integer,
    rows_scanned integer not null default 0,
    status text not null,
    message text,
    created_at timestamptz not null default now(),
    unique(run_date, source_table)
);

create table if not exists public.gptq_signal_generation_summary (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    score_threshold numeric not null,
    stocks_scanned integer not null default 0,
    stocks_eligible integer not null default 0,
    top_score numeric,
    top_symbol text,
    latest_market_date date,
    data_status text not null,
    distribution jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique(run_date, strategy_version)
);

alter table public.gptq_market_data_health enable row level security;
alter table public.gptq_signal_generation_summary enable row level security;

drop policy if exists "paper_dashboard_read_market_health" on public.gptq_market_data_health;
create policy "paper_dashboard_read_market_health"
on public.gptq_market_data_health for select
to anon
using (true);

drop policy if exists "paper_dashboard_read_signal_summary" on public.gptq_signal_generation_summary;
create policy "paper_dashboard_read_signal_summary"
on public.gptq_signal_generation_summary for select
to anon
using (true);
