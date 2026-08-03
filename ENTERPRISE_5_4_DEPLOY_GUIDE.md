# Enterprise 5.4 Adaptive Governance Deploy Pack

## 覆蓋方式

1. 解壓縮本 ZIP。
2. 將解壓後所有資料夾與檔案複製到 GPT 專案根目錄。
3. Windows 詢問是否合併或覆蓋時，選擇「取代目的地中的檔案」。

## 本包內容

- `automation/enterprise54_adaptive_governance.py`
- `.github/workflows/enterprise-5-4-adaptive-governance.yml`
- `supabase/ENTERPRISE_5_4_ADAPTIVE_GOVERNANCE_VERIFY.sql`

## 前置條件

Supabase 已執行：

`ENTERPRISE_5_4_FOUNDATION_DATABASE_PACK_v1.0.sql`

GitHub Actions Secrets 已存在：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Commit

Summary：

`Enterprise 5.4 Adaptive Governance`

Commit 後執行 Push origin。

## 執行

GitHub：

Actions → Enterprise 5.4 Adaptive Governance → Run workflow

## 驗證

Workflow 成功後，在 Supabase 執行：

`supabase/ENTERPRISE_5_4_ADAPTIVE_GOVERNANCE_VERIFY.sql`

## 安全限制

- Automatic Proposal Application = false
- Automatic Agent Weight Update = false
- Automatic Risk Parameter Update = false
- Automatic Rollback = false
- Live Trading = false
