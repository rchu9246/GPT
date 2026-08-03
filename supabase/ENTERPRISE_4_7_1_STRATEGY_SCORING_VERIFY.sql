select
  score_date,
  portfolio_id,
  strategy_key,
  market_regime,
  performance_score,
  risk_score,
  regime_fit_score,
  learning_score,
  stability_score,
  liquidity_score,
  diversification_score,
  confidence_score,
  composite_score,
  rank,
  eligible,
  disqualification_reasons,
  diagnostics
from public.strategy_scores_v47
order by score_date desc, portfolio_id, rank
limit 100;

select *
from public.strategy_engine_status_v47
order by status_date desc
limit 5;
