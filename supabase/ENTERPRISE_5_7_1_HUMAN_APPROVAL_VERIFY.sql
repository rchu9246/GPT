select
  c.id as candidate_id,
  c.source_version_no,
  c.candidate_status,
  c.eligibility_status,
  r.id as review_request_id,
  r.request_status,
  d.decision,
  d.decided_by,
  d.decided_at,
  d.decision_comment,
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
order by c.created_at desc, r.requested_at desc;

select *
from public.promotion_status_v57
order by status_date desc
limit 5;

select *
from public.baseline_history_v57
order by event_time desc
limit 20;

select *
from public.promotion_audit_v57
order by audit_time desc
limit 20;
