select *
from public.promotion_status_v57
order by status_date desc
limit 5;

select *
from public.promotion_metrics_v57
order by metric_date desc
limit 5;

select count(*) as promotion_candidates
from public.promotion_candidates_v57;

select count(*) as candidate_evaluations
from public.candidate_evaluations_v57;

select count(*) as human_review_requests
from public.human_review_requests_v57;

select count(*) as human_review_decisions
from public.human_review_decisions_v57;

select count(*) as baseline_promotion_plans
from public.baseline_promotion_plans_v57;

select count(*) as baseline_versions
from public.baseline_versions_v57;

select count(*) as baseline_history
from public.baseline_history_v57;

select *
from public.promotion_dashboard_v57
order by candidate_date desc, rank_no asc
limit 100;
