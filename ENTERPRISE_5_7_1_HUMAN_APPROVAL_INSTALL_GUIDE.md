# Enterprise 5.7.1 Human Approval API v1.0

## 前置條件

- Enterprise 5.7 Foundation Database 已安裝
- Enterprise 5.7 Promotion Engine 已產生 Eligible Candidate
- Candidate 已存在 Human Review Request 與 Promotion Plan
- GitHub Secrets：
  - SUPABASE_URL
  - SUPABASE_SERVICE_ROLE_KEY

## 部署

1. 解壓 ZIP。
2. 將全部檔案覆蓋至 GPT 專案根目錄。
3. GitHub Desktop Commit：
   `Enterprise 5.7.1 Human Approval API`
4. Push origin。

## 操作

GitHub → Actions → Enterprise 5.7.1 Human Approval → Run workflow

輸入：

- candidate_id：`promotion_candidates_v57.id`
- decision：APPROVED / REJECTED / RETEST_REQUIRED
- reviewer：審核者名稱
- comment：必要審核說明

## APPROVED 的效果

- Human Review Request → APPROVED
- Human Review Decision → APPROVED
- Candidate → APPROVED
- Promotion Plan → READY_FOR_MANUAL_ACTIVATION
- Candidate Baseline → APPROVED_FOR_MANUAL_ACTIVATION
- 寫入 Baseline History 與 Audit

不會自動啟用 Baseline。

## 安全限制

- Approval Scope = PAPER_BASELINE_ONLY
- Automatic Activation = false
- Automatic Rollback = false
- Live Trading = false
- Broker Submission = false
