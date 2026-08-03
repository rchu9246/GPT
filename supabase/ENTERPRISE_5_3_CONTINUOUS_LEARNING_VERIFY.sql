select *
from public.learning_cycles_v53
order by cycle_date desc
limit 10;

select *
from public.learning_status_v53
order by status_date desc
limit 10;

select *
from public.learning_metrics_v53
order by metric_date desc
limit 10;

select *
from public.decision_outcomes_v53
order by created_at desc
limit 100;

select *
from public.agent_feedback_v53
order by created_at desc
limit 200;

select *
from public.agent_weight_adjustments_v53
order by proposal_date desc, agent_key
limit 100;

select *
from public.strategy_outcomes_v53
order by outcome_date desc
limit 100;

select *
from public.regime_outcomes_v53
order by outcome_date desc
limit 100;

select *
from public.confidence_calibration_v53
order by calibration_date desc, subject_key
limit 100;

select *
from public.learning_dashboard_v53
order by cycle_date desc
limit 10;
