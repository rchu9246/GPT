# Enterprise 5.7.3 Promotion Calibration Engine v1.1

## 目的

分析最近候選人的 Evolution、Confidence 與 Rule Pass Rate，
產生 Paper Pilot 專用的建議門檻。

不會修改 STRICT 門檻：

- Evolution >= 70
- Confidence >= 60
- Rule Pass Rate = 100%

Paper Pilot 安全下限：

- Evolution >= 60
- Confidence >= 30
- Rule Pass Rate >= 60%

## 模式

### ANALYZE_ONLY

只分析並寫入 Audit、Status 與 Diagnostics。
不會建立 Human Review Request。

第一次請先使用此模式。

### APPLY_PAPER_PILOT

僅當 Rank 1 Candidate 同時高於 Paper Safety Floors，
才會：

- 標記 Candidate 為 ELIGIBLE
- 建立 PENDING Human Review Request
- 建立 PENDING Human Review Decision

這不代表通過正式晉升，只代表允許進入 Paper-only 人工審核。

## 部署

1. 解壓 ZIP。
2. 覆蓋至 GPT 專案根目錄。
3. Commit：
   `Enterprise 5.7.3 Promotion Calibration Engine v1.0`
4. Push origin。
5. GitHub Actions 執行：
   `Enterprise 5.7.3 Promotion Calibration Engine`

第一次：

- mode = ANALYZE_ONLY
- limit = 100

確認 Diagnostics 後，再決定是否執行 APPLY_PAPER_PILOT。

## 安全限制

- Human Approval Required
- Paper Only
- Strict Thresholds 不變
- Automatic Baseline Activation = false
- Live Trading = false
- Broker Submission = false


## v1.1 修正

- 修正 `promotion_status_v57` HTTP 400。
- 不再寫入可能違反 CHECK constraint 的：
  - `CALIBRATION_READY`
  - `CALIBRATION_WARNING`
- 保留資料庫原本的 `overall_status`。
- Calibration 結果改存於 `diagnostics`、`summary`、`warnings` 與 `promotion_audit_v57`。
- 不需重新執行 Foundation Database SQL。
