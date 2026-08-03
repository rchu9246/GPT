select *
from public.promotion_status_v55
order by status_date desc
limit 5;

select *
from public.promotion_metrics_v55
order by metric_date desc
limit 5;

select count(*) as promotion_requests
from public.promotion_requests_v55;

select count(*) as promotion_approvals
from public.promotion_approvals_v55;

select count(*) as paper_canary_plans
from public.paper_canary_plans_v55;

select count(*) as paper_canary_cycles
from public.paper_canary_cycles_v55;

select count(*) as comparisons
from public.candidate_baseline_comparisons_v55;

select count(*) as monitoring_records
from public.promotion_monitoring_v55;

select count(*) as regression_events
from public.regression_events_v55;

select count(*) as rollback_recommendations
from public.rollback_recommendations_v55;

select *
from public.promotion_dashboard_v55
order by request_date desc
limit 100;
