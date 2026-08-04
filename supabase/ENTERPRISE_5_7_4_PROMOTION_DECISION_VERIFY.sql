select
  audit_time,
  candidate_id,
  review_request_id,
  promotion_plan_id,
  event_status,
  message,
  previous_state,
  new_state,
  metadata
from public.promotion_audit_v57
where event_type = 'FINAL_PROMOTION_DECISION'
order by audit_time desc
limit 20;

select
  id as candidate_id,
  source_version_no,
  rank_no,
  eligibility_status,
  eligibility_score,
  candidate_status,
  metadata
from public.promotion_candidates_v57
order by candidate_date desc, rank_no asc;

select
  id as promotion_plan_id,
  candidate_id,
  plan_status,
  current_baseline_version,
  proposed_baseline_version,
  automatic_activation_enabled,
  automatic_rollback_enabled,
  live_trading_enabled,
  broker_submission_enabled
from public.baseline_promotion_plans_v57
order by created_at desc
limit 20;

select
  overall_status,
  current_top_candidate_version,
  current_review_request_id,
  current_promotion_plan_id,
  blockers,
  warnings,
  summary,
  diagnostics
from public.promotion_status_v57
order by status_date desc
limit 1;
