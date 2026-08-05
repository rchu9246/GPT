select risk_date, source_version_no, rank_no, proposed_position_size,
       approved_position_size, round(approved_position_size * 100, 4) as approved_position_percent,
       position_var, risk_decision, blockers, warnings, kill_switch_active,
       paper_only, live_trading_enabled, broker_submission_enabled, engine_version, calculated_at
from public.gpt_quant_v9_risk_decisions
order by risk_date desc, rank_no asc limit 100;

select risk_date, daily_pnl, portfolio_drawdown, max_single_position,
       max_total_exposure, max_open_positions, daily_loss_limit,
       portfolio_drawdown_limit, max_var_per_position, approved_total_exposure,
       round(approved_total_exposure * 100, 4) as approved_total_exposure_percent,
       estimated_total_var, approved_positions, blocked_positions,
       kill_switch_active, kill_switch_reasons, exposure_scale,
       paper_only, live_trading_enabled, broker_submission_enabled,
       engine_version, calculated_at
from public.gpt_quant_v9_risk_summaries
order by risk_date desc limit 20;

select * from public.gpt_quant_v9_risk_portfolio_state
order by state_date desc limit 20;
