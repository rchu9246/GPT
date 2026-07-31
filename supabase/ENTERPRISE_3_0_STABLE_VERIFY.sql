-- Enterprise 3.0 Stable verification
select * from public.quant_stable_readiness;

select
  release_date,
  release_version,
  readiness_score,
  live_trading_enabled,
  blockers
from public.quant_release_status
order by release_date desc
limit 10;

select
  run_date,
  release_version,
  run_status,
  current_stage,
  started_at,
  completed_at,
  blockers,
  error_message
from public.quant_release_runs
order by started_at desc
limit 20;

select
  check_date,
  check_key,
  check_status,
  severity,
  message
from public.quant_data_quality_checks
order by check_date desc, check_key;
