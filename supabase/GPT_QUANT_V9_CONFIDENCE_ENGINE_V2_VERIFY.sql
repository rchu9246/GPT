select
  ranking_date,
  id as ranking_id,
  rank_no,
  evolution_score,
  confidence_score,
  recommendation,
  selected_for_review,
  metadata ->> 'confidence_engine_version'
    as confidence_engine_version,
  metadata ->> 'confidence_recommendation'
    as confidence_recommendation,
  metadata -> 'confidence_blockers'
    as confidence_blockers,
  metadata -> 'confidence_warnings'
    as confidence_warnings,
  metadata -> 'confidence_components'
    as confidence_components
from public.portfolio_rankings_v56
order by ranking_date desc, rank_no asc
limit 100;

select
  round(max(confidence_score) - min(confidence_score), 4)
    as confidence_score_range,
  round(avg(confidence_score), 4)
    as average_confidence_score,
  count(*) filter (
    where metadata ->> 'confidence_recommendation'
      = 'CONFIDENCE_READY'
  ) as confidence_ready,
  count(*) filter (
    where metadata ->> 'confidence_recommendation'
      = 'CONFIDENCE_REVIEW_REQUIRED'
  ) as confidence_review_required,
  count(*) filter (
    where metadata ->> 'confidence_recommendation'
      = 'CONFIDENCE_REJECT'
  ) as confidence_rejected
from public.portfolio_rankings_v56;

select
  overall_status,
  diagnostics
from public.evolution_status_v56
order by status_date desc
limit 1;
