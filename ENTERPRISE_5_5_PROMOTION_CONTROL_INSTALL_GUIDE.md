# Enterprise 5.5 Promotion Control Suite v1.0

## 前置條件

Supabase 已完整執行：

`ENTERPRISE_5_5_FOUNDATION_DATABASE_PACK_v1.0.sql`

GitHub Actions Secrets 已存在：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Enterprise 5.4 至少已執行一次。

## 覆蓋部署

1. 解壓本 ZIP。
2. 將所有檔案與資料夾複製到 GPT 專案根目錄。
3. Windows 詢問是否合併或覆蓋時，選擇取代目的地中的檔案。

## 新增檔案

- `automation/enterprise55_promotion_control.py`
- `.github/workflows/enterprise-5-5-promotion-control.yml`
- `supabase/ENTERPRISE_5_5_PROMOTION_CONTROL_VERIFY.sql`

## Commit

GitHub Desktop Summary：

`Enterprise 5.5 Promotion Control Suite v1.0`

完成：

- Commit to main
- Push origin

## 執行順序

建議依序執行：

1. Enterprise 5.3 Continuous Learning
2. Enterprise 5.4 Adaptive Governance
3. Enterprise 5.5 Promotion Control

## GitHub Action

Actions → Enterprise 5.5 Promotion Control → Run workflow

## 驗證

Workflow 成功後，在 Supabase 執行：

`supabase/ENTERPRISE_5_5_PROMOTION_CONTROL_VERIFY.sql`

## 安全限制

- PAPER ONLY
- Human Approval Required = true
- Automatic Production Promotion = false
- Automatic Agent Weight Application = false
- Automatic Risk Parameter Application = false
- Automatic Rollback Execution = false
- Live Trading = false
- Broker Submission = false
