create or replace view compat_risk_snapshot_v41 as
select
 portfolio_id,
 risk_date as snapshot_date,
 var_95_pct,
 expected_shortfall_pct,
 max_drawdown_pct,
 concentration_pct,
 gross_exposure_pct,
 liquidity_score
from portfolio_risk_v41;
