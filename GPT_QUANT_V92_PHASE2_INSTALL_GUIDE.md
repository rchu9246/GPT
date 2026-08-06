# GPT Quant V9.2 Phase 2：真實回測整合

安裝後執行 Workflow：`GPT Quant V9.2 Enterprise CI/CD Phase 2`

第一次：
- mode = smoke
- fail_on_regression = true

Production 前到 Repository Settings → Secrets and variables → Actions → Variables 新增：
- `V9_REAL_BACKTEST_COMMAND`
- `V91_REAL_BACKTEST_COMMAND`

真實回測程式必須讀取：
- `GPTQ_METRICS_OUTPUT`
- `GPTQ_TRADES_OUTPUT`
- `GPTQ_EQUITY_OUTPUT`

並輸出：
- metrics JSON（必要：total_return、max_drawdown、sharpe、profit_factor、total_trades）
- trades CSV（timestamp,side,entry_price,exit_price,pnl）
- equity CSV（timestamp,equity）

本套件依賴 Phase 1 的：
- `automation/v92/compare_backtests.py`
- `config/gpt_quant_v92_phase1_policy.json`

Commit：
`Add GPT Quant V9.2 Phase 2 real backtest integration`
