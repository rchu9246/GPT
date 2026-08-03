select *
from public.execution_constraints_v52
order by constraint_scope, constraint_key;

select *
from public.execution_plans_v52
order by created_at desc
limit 20;

select *
from public.execution_batches_v52
order by created_at desc
limit 50;

select *
from public.execution_orders_v52
order by created_at desc
limit 100;

select *
from public.execution_risk_checks_v52
order by created_at desc
limit 200;

select *
from public.execution_metrics_v52
order by created_at desc
limit 20;

select *
from public.execution_audit_v52
order by audit_time desc
limit 200;

select *
from public.execution_status_v52
order by status_date desc
limit 10;

select *
from public.execution_dashboard_v52
order by plan_date desc
limit 20;
