create table if not exists public.paper_eod_ledger_v92(
    ledger_date date primary key,
    nav numeric default 1000000,
    cash numeric default 1000000,
    market_value numeric default 0,
    realized_pnl numeric default 0,
    unrealized_pnl numeric default 0,
    created_at timestamptz default now()
);
