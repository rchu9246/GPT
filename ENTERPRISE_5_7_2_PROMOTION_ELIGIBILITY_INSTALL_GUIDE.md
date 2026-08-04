# Enterprise 5.7.2 Promotion Eligibility Engine v2.0

## 目的

重新彙總 Enterprise 5.7 Candidate Evaluation，計算資格狀態，
並只對符合資格的候選建立 Human Review Request 與手動 Promotion Plan。

## 政策

### STRICT

- Rule Pass Rate = 100%
- Rank = 1
- selected_for_review = true
- recommendation = PROMOTE_FOR_HUMAN_REVIEW
- 不允許 Critical Rule Failure

### PAPER_PILOT

- Rule Pass Rate >= 60%
- Rank = 1
- 可容許 selected_for_review = false
- 可容許 recommendation 尚未為 PROMOTE_FOR_HUMAN_REVIEW
- Critical Failure 只作為警告
- 仍然只建立 Paper-only Human Review
- 不會自動核准或啟用 Baseline

## 部署

1. 解壓 ZIP。
2. 覆蓋到 GPT 專案根目錄。
3. Commit：
   `Enterprise 5.7.2 Promotion Eligibility Engine v2.0`
4. Push origin。

## 執行

GitHub → Actions → Enterprise 5.7.2 Promotion Eligibility Engine

第一次建議：

- policy：PAPER_PILOT
- candidate_id：留空

PAPER_PILOT 只是允許候選進入人工 Paper Baseline 審核，
不等於策略已通過實盤標準。

## 執行完成後

若有 Eligible Candidate：

- `human_review_requests_v57.request_status = PENDING`
- `human_review_decisions_v57.decision = PENDING`
- `baseline_promotion_plans_v57.plan_status = WAITING_FOR_APPROVAL`

接著才能執行 Enterprise 5.7.1 Human Approval。

## 安全限制

- Human Approval Required
- Paper Baseline Only
- Automatic Promotion = false
- Automatic Activation = false
- Automatic Rollback = false
- Live Trading = false
- Broker Submission = false
