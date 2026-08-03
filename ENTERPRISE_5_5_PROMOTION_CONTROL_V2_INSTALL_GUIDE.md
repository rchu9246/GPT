# Enterprise 5.5 Promotion Control Suite v2.0

## v2.0 關鍵修正

v1.0 只讀取 `parameter_versions_v54` 中的 CANDIDATE 版本。

當 Enterprise 5.4 已產生 Proposal、Safety Gate、Shadow Test，
但 `candidate_versions = 0` 時，v1.0 會正常結束卻建立 0 筆 v55 資料。

v2.0 新增雙來源模式：

1. 優先使用 `parameter_versions_v54` CANDIDATE。
2. 若沒有 Candidate Version，改由 `adaptive_proposals_v54`
   建立 Paper-only 評估候選批次。

因此，只要 v54 有 Proposal，v55 就會建立：

- Promotion Request
- Human Approval Gate
- Paper Canary Plan
- Paper Canary Cycle
- Candidate/Baseline Comparison
- Monitoring Record
- Rollback Recommendation

## 覆蓋部署

1. 解壓 ZIP。
2. 將所有檔案與資料夾複製到 GPT 專案根目錄。
3. 選擇取代目的地中的檔案。

## Commit

`Enterprise 5.5 Promotion Control Suite v2.0`

完成 Commit to main 與 Push origin。

## 執行

Actions → Enterprise 5.5 Promotion Control → Run workflow

## 驗證

執行：

`supabase/ENTERPRISE_5_5_PROMOTION_CONTROL_VERIFY_v2.0.sql`

## 安全限制

- PAPER ONLY
- Human Approval Required = true
- Automatic Production Promotion = false
- Automatic Agent Weight Application = false
- Automatic Risk Parameter Application = false
- Automatic Rollback Execution = false
- Live Trading = false
- Broker Submission = false
