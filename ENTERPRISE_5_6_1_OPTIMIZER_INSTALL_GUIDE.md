# Enterprise 5.6.1 Evolution Score Optimizer v1.0

## 功能

- 讀取 portfolio_rankings_v56
- 嘗試讀取 portfolio_versions_v56
- 嘗試讀取 simulation_runs_v56 或 simulation_results_v56
- 嘗試讀取 stress_tests_v56
- 計算 Return、Risk、Stability、Robustness 與 Complexity Penalty
- 更新 evolution_score、confidence_score、recommendation、selected_for_review
- 不會直接修改 Enterprise 5.7 Candidate 或 Human Review 資料

## 晉升條件

必須同時符合：

- Rank = 1
- Evolution Score >= 70
- Confidence Score >= 60
- Max Drawdown <= 20
- Simulation Pass
- Stress Test Pass

符合時：

- recommendation = PROMOTE_FOR_HUMAN_REVIEW
- selected_for_review = true

資料不足或未達條件時，不會強制灌高分。

## 部署

1. 解壓 ZIP。
2. 覆蓋到 GPT 專案根目錄。
3. Commit：
   `Enterprise 5.6.1 Evolution Score Optimizer v1.0`
4. Push origin。

## 執行順序

1. Enterprise 5.6 Evolution Intelligence
2. Enterprise 5.6.1 Evolution Score Optimizer
3. Enterprise 5.7 Baseline Promotion
4. Enterprise 5.7.2 Promotion Eligibility Engine
5. Enterprise 5.7.1 Human Approval

## 驗證

執行：

`supabase/ENTERPRISE_5_6_1_OPTIMIZER_VERIFY.sql`
