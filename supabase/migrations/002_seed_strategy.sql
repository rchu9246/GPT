insert into public.strategy_configs (
  version,
  trend_weight,
  momentum_weight,
  volume_weight,
  institutional_weight,
  breakout_weight,
  relative_strength_weight,
  market_weight,
  risk_weight,
  score_threshold,
  take_profit,
  stop_loss,
  max_holding_days,
  max_positions,
  position_size
)
values (
  'V2.0',
  0.20,
  0.15,
  0.15,
  0.15,
  0.10,
  0.10,
  0.10,
  0.05,
  80,
  0.07,
  0.03,
  5,
  10,
  0.10
)
on conflict (version) do nothing;
