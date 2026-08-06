# GPT Quant V9.2 Enterprise Production Research Pipeline v3.1

## v3.1 修正重點

- 自動檢查 Phase 2 equity／trades 是否足夠
- `auto` 模式下，若資料不足且已設定真實回測命令，會自動重跑 V9／V9.1 production backtest
- 尚未設定 production 命令時，會建立擴充 Smoke 資料來驗證 Pipeline
- Smoke 結果會標記 `VALIDATION ONLY`，永遠不能批准 Production Release
- Release Gate 只有真實 Production Evidence 且所有 Gate 通過才會 `APPROVE`
- 不再因 2 筆 equity curve 直接中斷且沒有報告

## 安裝

解壓覆蓋到 GPT 專案根目錄。

Commit：

`Upgrade GPT Quant V9.2 Production Research Pipeline to v3.1`

## 第一次執行

GitHub Actions：

`GPT Quant V9.2 Enterprise Production Research Pipeline v3.1`

建議：

- research_mode = auto
- fail_on_gate = false
- wfa_windows = 5
- monte_carlo_iterations = 1000

若尚未設定真實回測命令，執行結果應為：

`VALIDATION ONLY`

這代表技術流程成功，但不代表策略通過正式研究。

## 啟用真正 Production Research

Repository Settings → Secrets and variables → Actions → Variables：

- `V9_REAL_BACKTEST_COMMAND`
- `V91_REAL_BACKTEST_COMMAND`

兩個命令必須讀取：

- `GPTQ_METRICS_OUTPUT`
- `GPTQ_TRADES_OUTPUT`
- `GPTQ_EQUITY_OUTPUT`

並輸出完整 metrics、至少 20 筆 trades、至少 30 筆 equity points。

完成後以：

- research_mode = production
- fail_on_gate = true

執行。

## Artifact

`v92-production-research-v31-evidence`

包含輸入來源 manifest、比較報告、WFA、Monte Carlo、Research Report 與 Release Gate。
