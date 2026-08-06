# GPT Quant V9.2 Phase 3：Production Research Pipeline

## 功能

- 讀取 Phase 2 最新成功 Artifact
- Walk-Forward Analysis
- Monte Carlo Robustness
- Production Research Report
- Production Release Gate
- Markdown／HTML／JSON 報告
- Research Evidence Artifact

## 安裝

解壓並覆蓋到 GPT 專案根目錄。

Commit：

`Add GPT Quant V9.2 Phase 3 production research pipeline`

## 前置條件

Phase 2 Workflow 必須至少成功執行一次，並產生：

`v92-phase2-real-backtest-evidence`

正式研究前，Phase 2 應以 production 模式執行。Smoke 資料只適合驗證流程。

## 執行

GitHub Actions：

`GPT Quant V9.2 Production Research Pipeline`

預設：

- fail_on_gate = true
- wfa_windows = 5
- monte_carlo_iterations = 1000

## 輸出

Artifact：

`v92-production-research-evidence`

包含：

- Walk-Forward JSON／Markdown
- Monte Carlo JSON／Markdown
- Production Research Report JSON／Markdown／HTML
- Release Gate JSON

## Release Gate

只有以下三項全部通過才會 APPROVE：

- V9 vs V9.1 Regression Gate
- Walk-Forward Analysis
- Monte Carlo Robustness

此 Pipeline 不會連接券商，也不會送出真實訂單。
