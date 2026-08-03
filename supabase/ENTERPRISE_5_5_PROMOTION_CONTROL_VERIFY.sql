select *
from public.promotion_status_v55
order by status_date desc
limit 5;

select *
from public.promotion_metrics_v55
order by metric_date desc
limit 5;

select *
from public.promotion_requests_v55
order by created_at desc
limit 100;

select *
from public.promotion_approvals_v55
order by created_at desc
limit 100;

select *
from public.paper_canary_plans_v55
order by created_at desc
limit 100;

select *
from public.paper_canary_cycles_v55
order by created_at desc
limit 100;

select *
from public.candidate_baseline_comparisons_v55
order by created_at desc
limit 100;

select *
from public.promotion_monitoring_v55
order by created_at desc
limit 100;

select *
from public.regression_events_v55
order by event_time desc
limit 100;

select *
from public.rollback_recommendations_v55
order by created_at desc
limit 100;

select *
from public.promotion_dashboard_v55
order by request_date desc
limit 100;
