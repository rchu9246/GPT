# Enterprise 5.6 Evolution Intelligence Suite v1.0

## 前置條件

Supabase 已完整執行：

`ENTERPRISE_5_6_FOUNDATION_DATABASE_PACK_v1.0.sql`

Enterprise 5.5 Promotion Control v2.0 至少已執行一次。

GitHub Actions Secrets 已存在：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## 覆蓋部署

1. 解壓 ZIP。
2. 將所有檔案與資料夾複製到 GPT 專案根目錄。
3. Windows 詢問是否合併或覆蓋時，選擇取代目的地中的檔案。

## 新增檔案

- `automation/enterprise56_evolution_intelligence.py`
- `.github/workflows/enterprise-5-6-evolution-intelligence.yml`
- `supabase/ENTERPRISE_5_6_EVOLUTION_VERIFY.sql`

## Commit

GitHub Desktop Summary：

`Enterprise 5.6 Evolution Intelligence Suite v1.0`

完成：

- Commit to main
- Push origin

## 執行順序

1. Enterprise 5.5 Promotion Control
2. Enterprise 5.6 Evolution Intelligence

## GitHub Action

Actions → Enterprise 5.6 Evolution Intelligence → Run workflow

## 驗證

Workflow 成功後，在 Supabase 執行：

`supabase/ENTERPRISE_5_6_EVOLUTION_VERIFY.sql`

## 說明

目前 Historical Replay、Stress Test 與 Monte Carlo 採用可重現的
Paper-only proxy simulation。它不代表真實歷史績效，也不會觸發任何
實盤交易、Broker Order 或自動版本升級。

## 安全限制

- PAPER ONLY
- Human Approval Required = true
- Automatic Baseline Promotion = false
- Automatic Portfolio Application = false
- Automatic Live Deployment = false
- Automatic Rollback Execution = false
- Live Trading = false
- Broker Submission = false
