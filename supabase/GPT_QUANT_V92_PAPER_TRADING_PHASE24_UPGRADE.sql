-- GPT Quant V9.2 Paper Trading Phase 2.4
-- Automatic Position Management
-- SHADOW ONLY / NO BROKER EXECUTION

alter table if exists public.gptq_paper_positions
    add column if not exists highest_price numeric,
    add column if not exists holding_days integer not null default 0,
    add column if not exists stop_price numeric,
    add column if not exists take_profit_price numeric,
    add column if not exists last_mark_date date,
    add column if not exists exit_signal_score numeric;

alter table if exists public.gptq_paper_orders
    add column if not exists commission numeric not null default 0,
    add column if not exists slippage numeric not null default 0;

create table if not exists public.gptq_paper_position_management_runs (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    status text not null,
    positions_before integer not null default 0,
    positions_marked integer not null default 0,
    exits_triggered integer not null default 0,
    stop_loss_exits integer not null default 0,
    take_profit_exits integer not null default 0,
    trailing_stop_exits integer not null default 0,
    max_holding_exits integer not null default 0,
    signal_weakness_exits integer not null default 0,
    realized_pnl_today numeric not null default 0,
    ending_cash numeric not null default 0,
    ending_market_value numeric not null default 0,
    ending_equity numeric not null default 0,
    unrealized_pnl numeric not null default 0,
    errors jsonb not null default '[]'::jsonb,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    unique(run_date, strategy_version)
);

create table if not exists public.gptq_paper_position_management_decisions (
    id bigserial primary key,
    run_date date not null,
    strategy_version text not null,
    stock_id bigint not null,
    symbol text,
    decision text not null,
    reason text,
    entry_price numeric,
    last_price numeric,
    highest_price numeric,
    holding_days integer not null default 0,
    unrealized_pnl numeric not null default 0,
    realized_pnl numeric not null default 0,
    exit_fill_price numeric,
    created_at timestamptz not null default now(),
    unique(run_date, strategy_version, stock_id)
);

alter table public.gptq_paper_position_management_runs enable row level security;
alter table public.gptq_paper_position_management_decisions enable row level security;

drop policy if exists "paper_dashboard_read_position_management_runs"
on public.gptq_paper_position_management_runs;
create policy "paper_dashboard_read_position_management_runs"
on public.gptq_paper_position_management_runs
for select to anon using (true);

drop policy if exists "paper_dashboard_read_position_management_decisions"
on public.gptq_paper_position_management_decisions;
create policy "paper_dashboard_read_position_management_decisions"
on public.gptq_paper_position_management_decisions
for select to anon using (true);
