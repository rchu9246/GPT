# Enterprise 5.7 Promotion Engine v2.1

## 前置條件

- 已執行 Enterprise 5.7 Foundation Database Pack v1.0
- Enterprise 5.6 Evolution Intelligence 已成功產生 portfolio_rankings_v56
- GitHub Secrets 已設定：
  - SUPABASE_URL
  - SUPABASE_SERVICE_ROLE_KEY

## 覆蓋部署

1. 解壓 ZIP。
2. 將全部檔案複製到 GPT 專案根目錄。
3. 選擇覆蓋同名檔案。

## Commit

`Implement Enterprise 5.7 Promotion Engine`

完成 Commit to main 與 Push origin。

## 執行

GitHub → Actions → Enterprise 5.7 Baseline Promotion → Run workflow

## 執行結果

Engine 會：

- 讀取 portfolio_rankings_v56
- 建立 promotion_candidates_v57
- 套用 promotion_rules_v57
- 建立 candidate_evaluations_v57
- 對 Eligible Candidate 建立 human_review_requests_v57
- 建立 PENDING human_review_decisions_v57
- 建立 baseline_versions_v57 Candidate Baseline
- 建立 baseline_promotion_plans_v57
- 更新 promotion_metrics_v57
- 更新 promotion_status_v57

## 注意

Engine 不會自動核准、不會自動啟用 Baseline，也不會進行任何實盤交易。

## 驗證

執行：

`supabase/ENTERPRISE_5_7_PROMOTION_ENGINE_VERIFY.sql`


## v2.1 修正

修正 `promotion_audit_v57` 寫入時傳入 `on_conflict=None`，
導致 `TypeError: quote_from_bytes() expected bytes` 的問題。

新版使用 deterministic UUID 作為 Audit 主鍵，並以 `id` 執行 upsert。
不需要重新執行 Foundation Database SQL。
