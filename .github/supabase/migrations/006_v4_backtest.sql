alter table public.backtest_runs
  add column if not exists status varchar(20) not null default 'COMPLETED',
  add column if not exists average_return numeric,
  add column if not exists average_holding_days numeric,
  add column if not exists best_trade numeric,
  add column if not exists worst_trade numeric,
  add column if not exists final_capital numeric,
  add column if not exists parameters jsonb not null default '{}'::jsonb,
  add column if not exists equity_curve jsonb not null default '[]'::jsonb,
  add column if not exists completed_at timestamptz;

alter table public.backtest_trades
  add column if not exists score numeric,
  add column if not exists signal varchar(30),
  add column if not exists holding_days integer;

create index if not exists backtest_runs_strategy_created_idx
  on public.backtest_runs(strategy_version, created_at desc);

create index if not exists backtest_trades_run_entry_idx
  on public.backtest_trades(run_id, entry_date);

alter table public.backtest_runs enable row level security;
alter table public.backtest_trades enable row level security;

drop policy if exists "public read backtest runs" on public.backtest_runs;
create policy "public read backtest runs"
  on public.backtest_runs
  for select
  to anon, authenticated
  using (true);

drop policy if exists "public read backtest trades" on public.backtest_trades;
create policy "public read backtest trades"
  on public.backtest_trades
  for select
  to anon, authenticated
  using (true);

create or replace view public.strategy_leaderboard as
select
  strategy_version,
  count(*) as run_count,
  max(created_at) as latest_run_at,
  avg(total_return) as avg_total_return,
  avg(annual_return) as avg_annual_return,
  avg(win_rate) as avg_win_rate,
  avg(profit_factor) as avg_profit_factor,
  avg(max_drawdown) as avg_max_drawdown,
  avg(sharpe_ratio) as avg_sharpe_ratio,
  avg(total_trades) as avg_total_trades,
  max(total_return) as best_total_return
from public.backtest_runs
where status = 'COMPLETED'
group by strategy_version;

grant select on public.strategy_leaderboard to anon, authenticated;
