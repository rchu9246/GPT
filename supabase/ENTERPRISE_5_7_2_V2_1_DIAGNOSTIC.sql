select
  c.id as candidate_id,
  c.source_version_no,
  c.rank_no,
  c.eligibility_status,
  c.eligibility_score,
  count(e.id) as evaluation_rows,
  count(*) filter (where e.passed = true) as passed_rows,
  count(*) filter (where e.passed = false) as failed_rows
from public.promotion_candidates_v57 c
left join public.candidate_evaluations_v57 e
  on e.candidate_id = c.id
group by
  c.id,
  c.source_version_no,
  c.rank_no,
  c.eligibility_status,
  c.eligibility_score
order by c.rank_no asc;

select
  candidate_id,
  rule_key,
  evaluation_status,
  passed,
  severity,
  observed_numeric_value,
  observed_text_value,
  threshold_numeric_value,
  threshold_text_value
from public.candidate_evaluations_v57
order by candidate_id, created_at;
