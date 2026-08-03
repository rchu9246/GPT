select
  regime_date,
  market_regime,
  trend_state,
  volatility_state,
  liquidity_state,
  breadth_state,
  risk_state,
  transition_state,
  regime_confidence,
  trend_score,
  volatility_score,
  stress_score,
  recovery_score,
  recommended_posture,
  preferred_strategy_styles,
  avoided_strategy_styles,
  rationale,
  features,
  evidence,
  created_at,
  updated_at
from public.market_regime_ai_v46
order by regime_date desc
limit 10;
