# GPT Quant V9.2 Enterprise Dashboard v3.3

## v3.3 核心修正

v3.2 的 Comparison Step 會先寫入舊版 Phase 1 Summary，因此 Actions 頁面頂端仍顯示：

`GPT Quant V9.2 Phase 1 — V9 vs V9.1 Comparison`

v3.3 在執行比較器時暫時移除 `GITHUB_STEP_SUMMARY`，最後只由 Dashboard Builder 寫入正式 Summary。

Actions Summary 將改為：

`GPT Quant V9.2 Enterprise Dashboard v3.3`

## Dashboard 內容

- Research Score
- Grade
- Production Readiness
- Recommendation
- Evidence Source
- Regression Gate
- Walk-Forward Gate
- Monte Carlo Gate
- Production Evidence Gate
- V9.1 Performance
- V9 → V9.1 Delta
- Risk & Robustness
- Score Components
- Equity Curve
- Drawdown Curve

## HTML Dashboard

Artifact 內含：

- `enterprise_dashboard_v33.html`
- `enterprise_dashboard_v33.md`
- `enterprise_dashboard_v33.json`
- `research_score_v33.json`

HTML 不依賴外部 JavaScript 套件，可直接下載並在瀏覽器開啟。

## 安裝

解壓並覆蓋到 GPT 專案根目錄。

Commit：

`Add GPT Quant V9.2 Enterprise Dashboard v3.3`

## 執行

GitHub Actions：

`GPT Quant V9.2 Enterprise Dashboard v3.3`

第一次建議：

- research_mode = auto
- wfa_windows = 5
- monte_carlo_iterations = 1000

沒有 Production Evidence 時，Readiness 會維持：

`VALIDATION_ONLY`

不會因為 Smoke 分數高而允許部署。
