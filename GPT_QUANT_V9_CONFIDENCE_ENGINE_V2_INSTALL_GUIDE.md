# GPT Quant V9 Confidence Engine v2.2

## 功能

以多維證據重新計算每個 Portfolio Ranking 的 Confidence Score：

- Simulation Pass Rate
- Stress Test Pass Rate
- Walk-forward / OOS Consistency
- Regime Consistency
- Risk Stability
- Simulation Return Dispersion
- Evidence Density
- Data Completeness
- Uncertainty Penalty
- Previous Confidence

## 輸出

更新：

- portfolio_rankings_v56.confidence_score
- portfolio_rankings_v56.metadata.confidence_components
- portfolio_rankings_v56.metadata.confidence_blockers
- portfolio_rankings_v56.metadata.confidence_warnings
- portfolio_rankings_v56.metadata.confidence_recommendation
- evolution_status_v56.diagnostics

## Recommendation

- CONFIDENCE_READY
- CONFIDENCE_REVIEW_REQUIRED
- CONFIDENCE_REJECT

## 部署

1. 解壓 ZIP。
2. 覆蓋至 GPT 專案根目錄。
3. Commit：
   `GPT Quant V9 Confidence Engine v2.0`
4. Push origin。
5. 執行 GitHub Actions：
   `GPT Quant V9 Confidence Engine v2`

第一次：

- ranking_id 留空
- limit = 20

## 執行後順序

1. GPT Quant V9 Confidence Engine v2
2. Enterprise 5.6.3 Evolution Score Optimizer
3. Enterprise 5.7 Baseline Promotion
4. Enterprise 5.7.2 Promotion Eligibility Engine
5. Enterprise 5.7.3 Promotion Calibration
6. Enterprise 5.7.4 Promotion Decision

## 安全限制

- 不自動 Promotion
- 不自動啟用 Baseline
- Live Trading = false
- Broker Submission = false


## v2.1 修正

- 修正 `portfolio_rankings_v56.metadata` 不存在造成的 SQL 與 Supabase HTTP 400 問題。
- Ranking 僅更新既有的 `confidence_score` 欄位。
- Confidence components、blockers、warnings、recommendation 與 metrics 全部寫入：
  `evolution_status_v56.diagnostics.confidence_score_details`
- Workflow 驗證改讀取 `evolution_status_v56.diagnostics`。
- 驗證 SQL 不再查詢不存在的 `metadata` 欄位。
- 不需要重新執行 Foundation Database SQL。


## v2.2 修正

- 修正 Engine 只尋找「今天的」`evolution_status_v56` 狀態列。
- 改為讀取並更新 `evolution_status_v56` 最新一筆資料。
- 優先以 `id` 精確更新；若沒有 `id`，才使用 `status_date`。
- 若狀態表完全沒有資料，Engine 會明確失敗，不再假成功。
- Workflow 驗證版本更新為 `9.2.2`。
- 不需要重新執行 Foundation Database SQL。
