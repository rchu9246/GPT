-- GPT Quant Enterprise 2.1 verification
select * from public.quant_enterprise_2_1_readiness;

select
  tablename
from pg_tables
where schemaname = 'public'
  and tablename in (
    'market_state_v22',
    'trading_directives_v22',
    'director_reasoning_v22',
    'quant_modules',
    'quant_runs',
    'quant_decisions',
    'quant_orders',
    'quant_positions',
    'quant_portfolio_snapshots',
    'quant_reports',
    'quant_audit_logs',
    'quant_system_health',
    'quant_operational_status',
    'quant_risk_limits',
    'quant_risk_events',
    'quant_daily_briefs'
  )
order by tablename;

select
  module_key,
  module_name,
  current_version,
  enabled,
  execution_order
from public.quant_modules
order by execution_order;

select
  account_name,
  limit_key,
  warning_value,
  limit_value,
  enabled,
  unit
from public.quant_risk_limits
order by limit_key;
