select *
from public.optimization_runs_v49
where run_key = 'PORTFOLIO_OPTIMIZER'
order by run_date desc
limit 5;

select *
from public.allocation_engine_status_v48
order by status_date desc
limit 5;

select *
from public.portfolio_allocations_v48
order by allocation_date desc, portfolio_id
limit 20;

select *
from public.portfolio_target_weights_v49
order by weight_date desc, portfolio_id, priority
limit 100;

select *
from public.rebalance_plans_v49
order by plan_date desc, portfolio_id
limit 20;

select *
from public.allocation_decisions_v49
order by decision_date desc, portfolio_id
limit 100;

select *
from public.trade_plans_v49
order by trade_date desc, portfolio_id, priority
limit 100;

select *
from public.execution_queue_v49
order by queue_time desc
limit 100;

select *
from public.portfolio_dashboard_v49
limit 20;
