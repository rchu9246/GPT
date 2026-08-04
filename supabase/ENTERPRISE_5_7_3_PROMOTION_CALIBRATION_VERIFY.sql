select
  audit_time,
  event_status,
  message,
  metadata
from public.promotion_audit_v57
where event_type = 'PROMOTION_CALIBRATION'
order by audit_time desc
limit 20;

select
  overall_status,
  summary,
  warnings,
  diagnostics
from public.promotion_status_v57
order by status_date desc
limit 1;

select
  id as candidate_id,
  source_version_no,
  rank_no,
  evolution_score,
  confidence_score,
  eligibility_status,
  eligibility_score,
  candidate_status
from public.promotion_candidates_v57
order by candidate_date desc, rank_no asc;

select
  id as review_request_id,
  candidate_id,
  request_status,
  review_summary,
  requested_at
from public.human_review_requests_v57
order by requested_at desc
limit 20;
