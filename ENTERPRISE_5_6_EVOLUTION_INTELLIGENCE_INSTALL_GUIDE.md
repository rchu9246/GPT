# Enterprise 5.6 Evolution Intelligence Suite v1.1

## 修正內容

GitHub Action v1.0 在寫入 `simulation_runs_v56.random_seed` 時可能產生超過
PostgreSQL signed BIGINT 上限的整數，造成 PostgREST HTTP 400。

v1.1 將 deterministic seed 限制為：

`0 <= random_seed < 2^63 - 1`

因此可安全寫入 PostgreSQL `bigint`。

## 覆蓋部署

1. 解壓 ZIP。
2. 將所有檔案覆蓋到 GPT 專案根目錄。
3. GitHub Desktop Commit：
   `Fix Enterprise 5.6 random seed bigint overflow`
4. Push origin。
5. GitHub Actions → Enterprise 5.6 Evolution Intelligence → Run workflow。

## 不需要重跑 Foundation SQL

資料表結構無須修改。

## 安全限制

- PAPER ONLY
- Human Approval Required
- No automatic baseline promotion
- No live trading
- No broker submission
