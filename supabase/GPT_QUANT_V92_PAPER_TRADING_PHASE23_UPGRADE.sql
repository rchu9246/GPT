alter table if exists public.gptq_paper_orders
    add column if not exists execution_mode text not null default 'SHADOW_ONLY_NO_BROKER',
    add column if not exists source_signal_id bigint,
    add column if not exists risk_approved boolean not null default false,
    add column if not exists risk_reason text;

alter table if exists public.gptq_paper_positions
    add column if not exists source_signal_id bigint,
    add column if not exists execution_mode text not null default 'SHADOW_ONLY_NO_BROKER';

create table if not exists public.gptq_paper_execution_runs (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    status text not null,
    eligible_signals integer not null default 0,
    approved_signals integer not null default 0,
    rejected_signals integer not null default 0,
    orders_created integer not null default 0,
    positions_created integer not null default 0,
    starting_cash numeric not null default 0,
    ending_cash numeric not null default 0,
    starting_equity numeric not null default 0,
    ending_equity numeric not null default 0,
    gross_exposure numeric not null default 0,
    errors jsonb not null default '[]'::jsonb,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    unique(run_date, strategy_version)
);

create table if not exists public.gptq_paper_execution_decisions (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    signal_id bigint,
    stock_id bigint not null,
    symbol text,
    score numeric,
    decision text not null,
    reason text,
    reference_price numeric,
    simulated_fill_price numeric,
    shares integer not null default 0,
    notional numeric not null default 0,
    projected_exposure numeric,
    created_at timestamptz not null default now(),
    unique(run_date, strategy_version, stock_id)
);

alter table public.gptq_paper_execution_runs enable row level security;
alter table public.gptq_paper_execution_decisions enable row level security;

drop policy if exists "paper_dashboard_read_execution_runs"
on public.gptq_paper_execution_runs;
create policy "paper_dashboard_read_execution_runs"
on public.gptq_paper_execution_runs
for select to anon using (true);

drop policy if exists "paper_dashboard_read_execution_decisions"
on public.gptq_paper_execution_decisions;
create policy "paper_dashboard_read_execution_decisions"
on public.gptq_paper_execution_decisions
for select to anon using (true);
