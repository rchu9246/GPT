select
  id as candidate_id,
  source_version_no,
  rank_no,
  evolution_score,
  confidence_score,
  source_recommendation,
  source_selected_for_review,
  candidate_status,
  eligibility_status,
  eligibility_score,
  rejection_reason
from public.promotion_candidates_v57
order by candidate_date desc, rank_no asc;

select
  c.id as candidate_id,
  c.source_version_no,
  r.id as review_request_id,
  r.request_status,
  d.decision,
  p.id as promotion_plan_id,
  p.plan_status,
  p.proposed_baseline_version,
  p.automatic_activation_enabled,
  p.live_trading_enabled,
  p.broker_submission_enabled
from public.promotion_candidates_v57 c
left join public.human_review_requests_v57 r
  on r.candidate_id = c.id
left join public.human_review_decisions_v57 d
  on d.review_request_id = r.id
left join public.baseline_promotion_plans_v57 p
  on p.candidate_id = c.id
order by c.candidate_date desc, c.rank_no asc;

select *
from public.promotion_status_v57
order by status_date desc
limit 5;

select *
from public.promotion_metrics_v57
order by metric_date desc
limit 5;

select *
from public.promotion_audit_v57
where event_type = 'ELIGIBILITY_REEVALUATED'
order by audit_time desc
limit 100;
