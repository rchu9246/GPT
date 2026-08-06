# GPT Quant V9.2 Enterprise Research Dashboard v3.2

## 主要功能

- Research Score 0–100
- Grade A+／A／B／C／D
- Production Readiness
- Release Recommendation
- Regression Gate
- Walk-Forward Gate
- Monte Carlo Gate
- Production Evidence Gate
- Performance KPI
- Risk & Robustness KPI
- Markdown／HTML／JSON Dashboard
- GitHub Actions Summary 直接顯示完整儀表板

## 安裝

解壓並覆蓋到 GPT 專案根目錄。

本套件依賴 v3.1 與 Phase 1 的既有檔案：

- `automation/v92/research_input_resolver_v31.py`
- `automation/v92/walk_forward_analysis_v31.py`
- `automation/v92/monte_carlo_analysis_v31.py`
- `automation/v92/compare_backtests.py`
- `config/gpt_quant_v92_phase1_policy.json`

Commit：

`Add GPT Quant V9.2 Enterprise Research Dashboard v3.2`

## 執行

GitHub Actions：

`GPT Quant V9.2 Enterprise Research Dashboard v3.2`

第一次建議：

- research_mode = auto
- wfa_windows = 5
- monte_carlo_iterations = 1000

若沒有 Production Evidence，Dashboard 會顯示：

`VALIDATION_ONLY`

即使分數很高，也不會顯示可正式發布。

## Artifact

`v92-enterprise-research-dashboard-v32`

內含：

- `enterprise_research_dashboard.md`
- `enterprise_research_dashboard.html`
- `enterprise_research_dashboard.json`
- `research_score.json`
