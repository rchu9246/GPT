-- Enterprise 4.0 Foundation verification

select
  to_regclass('public.enterprise_portfolios_v40') is not null as portfolios_ready,
  to_regclass('public.enterprise_strategies_v40') is not null as strategies_ready,
  to_regclass('public.enterprise_runs_v40') is not null as runs_ready,
  to_regclass('public.enterprise_run_stages_v40') is not null as stages_ready,
  to_regclass('public.audit_logs_v40') is not null as audit_ready,
  to_regclass('public.market_regimes_v40') is not null as regime_ready,
  to_regclass('public.compat_portfolios_v40') is not null as portfolio_compat_ready,
  to_regclass('public.compat_strategies_v40') is not null as strategy_compat_ready;

select portfolio_key, portfolio_name, lifecycle_status
from public.enterprise_portfolios_v40
order by portfolio_key;

select strategy_key, strategy_name, lifecycle_status, paper_approved, live_approved
from public.enterprise_strategies_v40
order by strategy_key;
