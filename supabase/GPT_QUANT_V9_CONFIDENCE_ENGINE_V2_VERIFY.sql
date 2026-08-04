-- 1. Ranking confidence results
select
  ranking_date,
  id as ranking_id,
  rank_no,
  evolution_score,
  confidence_score,
  recommendation,
  selected_for_review
from public.portfolio_rankings_v56
order by ranking_date desc, rank_no asc
limit 100;

-- 2. Confidence score distribution
select
  round(max(confidence_score) - min(confidence_score), 4)
    as confidence_score_range,
  round(avg(confidence_score), 4)
    as average_confidence_score,
  round(max(confidence_score), 4)
    as maximum_confidence_score,
  round(min(confidence_score), 4)
    as minimum_confidence_score
from public.portfolio_rankings_v56;

-- 3. Full v2.1 diagnostics
select
  overall_status,
  diagnostics ->> 'gpt_quant_v9_confidence_engine_version'
    as confidence_engine_version,
  diagnostics ->> 'confidence_rankings_updated'
    as confidence_rankings_updated,
  diagnostics ->> 'average_confidence_score'
    as average_confidence_score,
  diagnostics -> 'confidence_score_details'
    as confidence_score_details,
  diagnostics ->> 'confidence_updated_at'
    as confidence_updated_at
from public.evolution_status_v56
order by status_date desc
limit 1;

-- 4. Expand each candidate's confidence diagnostics
select
  detail ->> 'source_version_no' as source_version_no,
  (detail ->> 'rank_no')::integer as rank_no,
  (detail ->> 'confidence_score')::numeric
    as confidence_score,
  detail ->> 'confidence_recommendation'
    as confidence_recommendation,
  detail -> 'blockers' as blockers,
  detail -> 'warnings' as warnings,
  detail -> 'missing_flags' as missing_flags
from public.evolution_status_v56 s
cross join lateral jsonb_array_elements(
  coalesce(
    s.diagnostics -> 'confidence_score_details',
    '[]'::jsonb
  )
) as detail
order by s.status_date desc, rank_no asc;
