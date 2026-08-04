# Enterprise 5.7.4 Promotion Decision Engine v1.0

## 功能

彙整：

- promotion_candidates_v57
- human_review_requests_v57
- human_review_decisions_v57
- baseline_promotion_plans_v57
- promotion_audit_v57 的 Calibration 紀錄
- promotion_status_v57

最後輸出：

- PROMOTE
- HOLD
- REJECT

## PROMOTE 條件

必須同時符合：

- Candidate eligibility_status = ELIGIBLE
- Human Review Request = APPROVED
- Human Review Decision = APPROVED
- Promotion Plan = READY_FOR_MANUAL_ACTIVATION
- Automatic Activation = false
- Live Trading = false
- Broker Submission = false

PROMOTE 只代表：

`APPROVED_FOR_MANUAL_ACTIVATION`

不會自動啟用 Baseline。

## HOLD

常見原因：

- Human Review 尚未完成
- Human Decision 仍為 PENDING
- Promotion Plan 尚在等待批准
- Calibration 尚未完整

## REJECT

常見原因：

- Candidate 不符合資格
- Human Review 拒絕
- Retest Required
- Promotion Plan 缺失或狀態不合法
- 安全設定未關閉

## 部署

1. 解壓 ZIP。
2. 覆蓋到 GPT 專案根目錄。
3. Commit：
   `Enterprise 5.7.4 Promotion Decision Engine v1.0`
4. Push origin。
5. GitHub Actions 執行：
   `Enterprise 5.7.4 Promotion Decision Engine`
6. 輸入 `promotion_candidates_v57.id`。

## 安全限制

- Human Approval Required
- Paper Only
- Automatic Baseline Activation = false
- Automatic Rollback = false
- Live Trading = false
- Broker Submission = false
