select
  sizing_date,
  source_version_no,
  rank_no,
  evolution_score,
  confidence_score,
  recommendation,
  final_position_size,
  round(final_position_size * 100, 4)
    as final_position_percent,
  sizing_status,
  blockers,
  warnings,
  components,
  risk_metrics,
  paper_only,
  live_trading_enabled,
  broker_submission_enabled,
  engine_version,
  calculated_at
from public.gpt_quant_v9_position_sizing_results
order by sizing_date desc, rank_no asc
limit 100;

select
  sizing_date,
  round(sum(final_position_size) * 100, 4)
    as total_allocated_percent,
  round(max(final_position_size) * 100, 4)
    as largest_position_percent,
  count(*) filter (
    where sizing_status = 'NORMAL'
  ) as normal_positions,
  count(*) filter (
    where sizing_status = 'REDUCED'
  ) as reduced_positions,
  count(*) filter (
    where sizing_status = 'MINIMAL'
  ) as minimal_positions,
  count(*) filter (
    where sizing_status = 'BLOCKED'
  ) as blocked_positions
from public.gpt_quant_v9_position_sizing_results
group by sizing_date
order by sizing_date desc
limit 20;

select
  diagnostics ->> 'gpt_quant_v9_position_sizing_engine_version'
    as position_sizing_engine_version,
  diagnostics ->> 'position_sizing_max_single_weight'
    as max_single_weight,
  diagnostics ->> 'position_sizing_total_risk_budget'
    as total_risk_budget,
  diagnostics ->> 'position_sizing_updated_at'
    as position_sizing_updated_at,
  diagnostics -> 'position_sizing_results'
    as position_sizing_results
from public.evolution_status_v56
order by status_date desc
limit 1;
