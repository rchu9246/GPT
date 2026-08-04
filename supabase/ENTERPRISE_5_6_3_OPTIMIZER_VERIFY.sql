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

select
  round(max(evolution_score) - min(evolution_score), 4)
    as evolution_score_range,
  round(max(confidence_score) - min(confidence_score), 4)
    as confidence_score_range,
  round(avg(evolution_score), 4)
    as average_evolution_score,
  round(avg(confidence_score), 4)
    as average_confidence_score,
  count(*) filter (
    where recommendation = 'PROMOTE_FOR_HUMAN_REVIEW'
      and selected_for_review = true
  ) as ready_for_human_review,
  count(*) filter (
    where recommendation = 'REVIEW_REQUIRED'
  ) as review_required,
  count(*) filter (
    where recommendation = 'REJECT'
  ) as rejected
from public.portfolio_rankings_v56;

select
  overall_status,
  diagnostics
from public.evolution_status_v56
order by status_date desc
limit 1;
