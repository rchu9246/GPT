# GPT Quant V9.2 Enterprise CI/CD Phase 1

解壓後覆蓋到 GPT 專案根目錄。本套件不含 manifest.json。

Commit：`Add GPT Quant V9.2 Enterprise CI/CD Phase 1`

第一次在 Actions 執行：
- mode = smoke
- fail_on_regression = true

Production 模式需在 Repository Variables 設定：
- V9_BACKTEST_COMMAND
- V91_BACKTEST_COMMAND

兩個回測命令必須分別寫入環境變數指定的輸出：
- V92_V9_METRICS_OUTPUT
- V92_V91_METRICS_OUTPUT

輸出 Artifacts：
- v92-backtest-results
- v92-comparison-report
