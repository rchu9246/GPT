-- GPT Quant V9.2 Paper Trading Phase 2
-- Live Signal Pipeline / Position Lifecycle / P&L Engine
-- SHADOW ONLY - NO BROKER EXECUTION

alter table if exists public.gptq_paper_positions
    add column if not exists entry_score numeric,
    add column if not exists entry_signal text,
    add column if not exists highest_price numeric,
    add column if not exists holding_days integer not null default 0,
    add column if not exists stop_price numeric,
    add column if not exists take_profit_price numeric;

alter table if exists public.gptq_paper_orders
    add column if not exists realized_pnl numeric not null default 0,
    add column if not exists holding_days integer,
    add column if not exists exit_reason text;

create table if not exists public.gptq_paper_signals (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    stock_id bigint not null,
    symbol text,
    score numeric not null,
    signal_label text,
    reference_price numeric,
    eligible boolean not null default false,
    selected boolean not null default false,
    reject_reason text,
    created_at timestamptz not null default now(),
    unique(run_date, strategy_version, stock_id)
);

create index if not exists idx_gptq_paper_signals_date
    on public.gptq_paper_signals(run_date, strategy_version, score desc);

create table if not exists public.gptq_paper_risk_events (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    event_type text not null,
    severity text not null default 'INFO',
    symbol text,
    message text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.gptq_paper_signals enable row level security;
alter table public.gptq_paper_risk_events enable row level security;

drop policy if exists "paper_dashboard_read_signals" on public.gptq_paper_signals;
create policy "paper_dashboard_read_signals"
on public.gptq_paper_signals for select
to anon
using (true);

drop policy if exists "paper_dashboard_read_risk_events" on public.gptq_paper_risk_events;
create policy "paper_dashboard_read_risk_events"
on public.gptq_paper_risk_events for select
to anon
using (true);
