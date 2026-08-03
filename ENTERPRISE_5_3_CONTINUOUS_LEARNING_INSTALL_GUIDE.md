# Enterprise 5.3 Continuous Learning & Feedback Engine

## 安裝順序

1. 在 Supabase 執行：
   `supabase/ENTERPRISE_5_3_FOUNDATION_DATABASE_PACK_v1.0.sql`
2. 解壓並覆蓋 GPT 專案。
3. Commit：
   `Enterprise 5.3 Continuous Learning and Feedback`
4. Push origin。
5. 依序執行：
   - Enterprise 5.0 Operating System
   - Enterprise 5.1 Multi-Agent Decision Council
   - Enterprise 5.2 Execution Intelligence
   - Enterprise 5.3 Continuous Learning
6. Supabase 驗證：
   `supabase/ENTERPRISE_5_3_CONTINUOUS_LEARNING_VERIFY.sql`

## 建立內容

- learning_observations_v53
- decision_outcomes_v53
- agent_feedback_v53
- agent_weight_adjustments_v53
- strategy_outcomes_v53
- regime_outcomes_v53
- confidence_calibration_v53
- learning_cycles_v53
- learning_metrics_v53
- learning_status_v53
- learning_dashboard_v53

## 學習邏輯

- 評估 Council 決策是否產生有效 Paper Execution Plan
- 評估 Agent 投票正確性與信心校準
- 產生 Agent Voting Weight 調整提案
- 建立策略與市場狀態 Outcome 記錄
- 在缺乏真實績效或模擬成交資料時標記 INSUFFICIENT_DATA

## 安全限制

- PAPER ONLY
- 不自動套用 Agent 權重
- 不自動覆寫風控參數
- 不自動訓練模型
- 不連接券商
- 所有權重調整皆維持 PROPOSED
