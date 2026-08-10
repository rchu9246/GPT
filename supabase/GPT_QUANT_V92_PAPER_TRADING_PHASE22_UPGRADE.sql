-- GPT Quant V9.2 Paper Trading Phase 2.2
-- Automatic Market Data Ingestion
-- Data ingestion only. NO BROKER EXECUTION.

create table if not exists public.gptq_market_ingestion_runs (
    id bigserial primary key,
    run_date date not null,
    provider text not null,
    status text not null,
    active_stocks integer not null default 0,
    stocks_attempted integer not null default 0,
    stocks_updated integer not null default 0,
    rows_received integer not null default 0,
    rows_inserted integer not null default 0,
    rows_updated integer not null default 0,
    rows_skipped integer not null default 0,
    latest_market_date_before date,
    latest_market_date_after date,
    stale_days_before integer,
    stale_days_after integer,
    error_count integer not null default 0,
    errors jsonb not null default '[]'::jsonb,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    unique(run_date, provider)
);

create table if not exists public.gptq_market_ingestion_stock_status (
    id bigserial primary key,
    run_date date not null,
    provider text not null,
    stock_id bigint not null,
    symbol text not null,
    start_date date,
    end_date date,
    rows_received integer not null default 0,
    rows_inserted integer not null default 0,
    rows_updated integer not null default 0,
    latest_market_date date,
    status text not null,
    message text,
    created_at timestamptz not null default now(),
    unique(run_date, provider, stock_id)
);

create index if not exists idx_gptq_market_ingestion_runs_created
    on public.gptq_market_ingestion_runs(created_at desc);

create index if not exists idx_gptq_market_ingestion_stock_status_run
    on public.gptq_market_ingestion_stock_status(run_date, provider, symbol);

alter table public.gptq_market_ingestion_runs enable row level security;
alter table public.gptq_market_ingestion_stock_status enable row level security;

drop policy if exists "paper_dashboard_read_market_ingestion_runs"
on public.gptq_market_ingestion_runs;
create policy "paper_dashboard_read_market_ingestion_runs"
on public.gptq_market_ingestion_runs
for select to anon using (true);

drop policy if exists "paper_dashboard_read_market_ingestion_stock_status"
on public.gptq_market_ingestion_stock_status;
create policy "paper_dashboard_read_market_ingestion_stock_status"
on public.gptq_market_ingestion_stock_status
for select to anon using (true);
