select * from public.gpt_quant_v91_confidence_calibration order by final_confidence desc limit 100;
select * from public.gpt_quant_v91_adaptive_risk_state order by state_date desc limit 20;
select *, round(optimized_weight*100,4) as optimized_weight_percent
from public.gpt_quant_v91_portfolio_allocations
order by allocation_date desc, optimized_weight desc limit 100;
select * from public.gpt_quant_v91_paper_sessions order by session_date desc limit 20;
select * from public.gpt_quant_v91_paper_positions order by position_date desc, target_weight desc limit 100;
