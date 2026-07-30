create extension if not exists pgcrypto;

create table if not exists public.stocks (
  id bigint generated always as identity primary key,
  symbol varchar(10) not null unique,
  name varchar(100) not null,
  market varchar(20) not null default 'TWSE',
  industry varchar(100),
  listed_date date,
  delisted_date date,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.daily_prices (
  id bigint generated always as identity primary key,
  stock_id bigint not null references public.stocks(id) on delete cascade,
  trade_date date not null,
  open numeric(12,4), high numeric(12,4), low numeric(12,4), close numeric(12,4),
  volume bigint, turnover numeric(20,2), adj_close numeric(12,4),
  created_at timestamptz not null default now(),
  unique(stock_id, trade_date)
);
create index if not exists idx_daily_prices_stock_date on public.daily_prices(stock_id, trade_date desc);

create table if not exists public.institutional_flows (
  id bigint generated always as identity primary key,
  stock_id bigint not null references public.stocks(id) on delete cascade,
  trade_date date not null,
  foreign_buy bigint default 0, foreign_sell bigint default 0, foreign_net bigint default 0,
  trust_buy bigint default 0, trust_sell bigint default 0, trust_net bigint default 0,
  dealer_buy bigint default 0, dealer_sell bigint default 0, dealer_net bigint default 0,
  total_net bigint default 0,
  unique(stock_id, trade_date)
);

create table if not exists public.features (
  id bigint generated always as identity primary key,
  stock_id bigint not null references public.stocks(id) on delete cascade,
  trade_date date not null,
  close numeric(12,4),
  return_1d numeric, return_5d numeric, return_20d numeric,
  ma5 numeric, ma20 numeric, ma60 numeric, ma120 numeric,
  ma20_slope numeric, ma60_slope numeric,
  rsi14 numeric, macd numeric, macd_signal numeric, macd_hist numeric,
  atr14 numeric, volume_ratio_5d numeric, volume_ratio_20d numeric,
  volatility_20d numeric, high_20d numeric, high_60d numeric,
  distance_high_20d numeric, distance_high_60d numeric,
  foreign_net_5d numeric, foreign_net_20d numeric,
  trust_net_5d numeric, trust_net_20d numeric,
  unique(stock_id, trade_date)
);

create table if not exists public.strategy_configs (
  id uuid primary key default gen_random_uuid(),
  version varchar(50) unique not null,
  trend_weight numeric not null default .20,
  momentum_weight numeric not null default .15,
  volume_weight numeric not null default .15,
  institutional_weight numeric not null default .15,
  breakout_weight numeric not null default .10,
  relative_strength_weight numeric not null default .10,
  market_weight numeric not null default .10,
  risk_weight numeric not null default .05,
  score_threshold numeric not null default 80,
  take_profit numeric not null default .07,
  stop_loss numeric not null default .03,
  max_holding_days integer not null default 5,
  max_positions integer not null default 10,
  position_size numeric not null default .10,
  created_at timestamptz not null default now()
);

create table if not exists public.signals (
  id bigint generated always as identity primary key,
  stock_id bigint not null references public.stocks(id) on delete cascade,
  trade_date date not null,
  strategy_version varchar(50) not null,
  total_score numeric(6,2) not null,
  trend_score numeric(6,2),
  momentum_score numeric(6,2),
  volume_score numeric(6,2),
  institutional_score numeric(6,2),
  breakout_score numeric(6,2),
  relative_strength_score numeric(6,2),
  market_score numeric(6,2),
  risk_score numeric(6,2),
  signal varchar(30) not null,
  confidence numeric(6,2),
  created_at timestamptz not null default now(),
  unique(stock_id, trade_date, strategy_version)
);
create index if not exists idx_signals_date_score on public.signals(trade_date, total_score desc);

create table if not exists public.signal_outcomes (
  id bigint generated always as identity primary key,
  signal_id bigint not null references public.signals(id) on delete cascade,
  t1_return numeric, t3_return numeric, t5_return numeric, t10_return numeric, t20_return numeric,
  t1_max_gain numeric, t1_max_loss numeric, t5_max_gain numeric, t5_max_loss numeric,
  hit_take_profit boolean, hit_stop_loss boolean,
  calculated_at timestamptz not null default now(),
  unique(signal_id)
);

create table if not exists public.backtest_runs (
  id uuid primary key default gen_random_uuid(),
  strategy_version varchar(50) not null,
  start_date date not null, end_date date not null,
  initial_capital numeric(20,2) not null,
  score_threshold numeric(6,2),
  take_profit numeric(8,4), stop_loss numeric(8,4),
  max_positions integer, position_size numeric(8,4),
  commission_rate numeric(8,6), tax_rate numeric(8,6), slippage_rate numeric(8,6),
  total_return numeric, annual_return numeric, win_rate numeric, profit_factor numeric,
  max_drawdown numeric, sharpe_ratio numeric, sortino_ratio numeric,
  total_trades integer,
  created_at timestamptz default now()
);

create table if not exists public.backtest_trades (
  id bigint generated always as identity primary key,
  run_id uuid not null references public.backtest_runs(id) on delete cascade,
  stock_id bigint not null references public.stocks(id),
  signal_date date not null, entry_date date not null, exit_date date,
  entry_price numeric, exit_price numeric, shares integer,
  gross_return numeric, net_return numeric, pnl numeric,
  exit_reason varchar(30),
  max_favorable_excursion numeric, max_adverse_excursion numeric
);

create table if not exists public.walk_forward_runs (
  id uuid primary key default gen_random_uuid(),
  strategy_version varchar(50),
  training_start date, training_end date,
  testing_start date, testing_end date,
  best_threshold numeric, best_take_profit numeric, best_stop_loss numeric,
  train_return numeric, test_return numeric,
  train_win_rate numeric, test_win_rate numeric,
  train_drawdown numeric, test_drawdown numeric,
  profit_factor numeric,
  stability_score numeric,
  created_at timestamptz default now()
);

create table if not exists public.market_regimes (
  id bigint generated always as identity primary key,
  trade_date date not null unique,
  taiex_score numeric,
  sox_score numeric,
  nasdaq_score numeric,
  fx_score numeric,
  breadth_score numeric,
  total_score numeric,
  regime varchar(30),
  created_at timestamptz default now()
);

create table if not exists public.paper_positions (
  id uuid primary key default gen_random_uuid(),
  stock_id bigint not null references public.stocks(id),
  entry_date date not null,
  entry_price numeric not null,
  shares integer not null,
  status varchar(20) not null default 'OPEN',
  exit_date date,
  exit_price numeric,
  pnl numeric,
  strategy_version varchar(50),
  created_at timestamptz default now()
);

alter table public.stocks enable row level security;
alter table public.daily_prices enable row level security;
alter table public.institutional_flows enable row level security;
alter table public.features enable row level security;
alter table public.signals enable row level security;
alter table public.signal_outcomes enable row level security;
alter table public.market_regimes enable row level security;

create policy "public read stocks" on public.stocks for select to anon, authenticated using (true);
create policy "public read daily prices" on public.daily_prices for select to anon, authenticated using (true);
create policy "public read institutional flows" on public.institutional_flows for select to anon, authenticated using (true);
create policy "public read features" on public.features for select to anon, authenticated using (true);
create policy "public read signals" on public.signals for select to anon, authenticated using (true);
create policy "public read signal outcomes" on public.signal_outcomes for select to anon, authenticated using (true);
create policy "public read market regimes" on public.market_regimes for select to anon, authenticated using (true);
