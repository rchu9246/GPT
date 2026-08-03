select *
from public.adaptive_status_v54
order by status_date desc
limit 5;

select *
from public.adaptive_metrics_v54
order by metric_date desc
limit 5;

select *
from public.adaptive_proposals_v54
order by created_at desc
limit 100;

select *
from public.proposal_items_v54
order by created_at desc
limit 100;

select *
from public.safety_gate_results_v54
order by checked_at desc
limit 200;

select *
from public.shadow_simulations_v54
order by created_at desc
limit 100;

select *
from public.adaptive_reviews_v54
order by review_time desc
limit 100;

select *
from public.parameter_versions_v54
order by created_at desc
limit 20;

select *
from public.agent_weight_versions_v54
order by created_at desc
limit 100;

select *
from public.rollback_snapshots_v54
order by created_at desc
limit 20;

select *
from public.adaptive_dashboard_v54
order by proposal_date desc
limit 100;
