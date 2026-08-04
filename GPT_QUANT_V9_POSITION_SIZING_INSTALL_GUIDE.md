# GPT Quant V9 Position Sizing Engine v1.0

## 功能

根據以下資訊計算 Paper-only 建議持倉：

- Evolution Score
- Confidence Score
- Rank
- Max Drawdown
- Volatility
- Risk Stability
- Data Completeness
- Recommendation
- Selected for Review

## Sizing Status

- NORMAL
- REDUCED
- MINIMAL
- BLOCKED

當 `recommendation = REJECT` 時：

- governance_multiplier = 0
- final_position_size = 0
- sizing_status = BLOCKED

這是刻意的安全設計，不會因為排名高就繞過治理結果。

## 部署順序

### 1. 先建立資料表

在 Supabase SQL Editor 執行：

`supabase/GPT_QUANT_V9_POSITION_SIZING_FOUNDATION.sql`

只需執行一次。

### 2. 覆蓋專案

解壓 ZIP 後覆蓋到 GPT 專案根目錄。

Commit：

`GPT Quant V9 Position Sizing Engine v1.0`

Push origin。

### 3. 執行 Workflow

GitHub Actions：

`GPT Quant V9 Position Sizing Engine`

第一次建議：

- ranking_id 留空
- limit = 20
- max_single_weight = 0.10
- total_risk_budget = 1.00

## 安全限制

- Position Size 最大 25%
- 預設單一部位最大 10%
- Paper Only
- 不自動下單
- Live Trading = false
- Broker Submission = false
- 不修改 promotion_candidates_v57
- 不覆寫 portfolio_rankings_v56
