# Enterprise 4.9.1 Portfolio Optimizer Engine Pack

## 功能

整合：

- market_regime_ai_v46
- strategy_scores_v47
- strategy_catalog_v47
- portfolio_health_v46
- risk_governor_status_v41
- allocation_policies_v48
- allocation_constraints_v48

產生：

- allocation_candidates_v48
- portfolio_allocations_v48
- allocation_engine_status_v48
- portfolio_target_weights_v49
- rebalance_plans_v49
- allocation_decisions_v49
- trade_plans_v49
- execution_queue_v49
- portfolio_health_v49
- optimization_runs_v49

## 安裝條件

必須先完成：

1. Enterprise 4.7 Foundation Database Pack
2. Enterprise 4.7.1 Strategy Scoring
3. Enterprise 4.8 Foundation Database Pack
4. Enterprise 4.9 Foundation Database Pack

## 安裝步驟

1. 解壓並覆蓋目前 GPT 專案。
2. Commit：
   `Enterprise 4.9.1 Portfolio Optimizer Engine`
3. Push origin。
4. 先執行：
   `Enterprise 4.7.1 Strategy Scoring`
5. 再執行：
   `Enterprise 4.9.1 Portfolio Optimizer`
6. Workflow 會自動驗證主要資料寫入。
7. Supabase 可再執行：
   `supabase/ENTERPRISE_4_9_1_PORTFOLIO_OPTIMIZER_VERIFY.sql`

## 安全限制

- PAPER ONLY
- Live Trading disabled
- Autonomous Execution disabled
- Broker Submission disabled
- execution_queue_v49 只使用 PAPER broker
- Trade Plans 只是模擬執行計畫，不會送出真實訂單
