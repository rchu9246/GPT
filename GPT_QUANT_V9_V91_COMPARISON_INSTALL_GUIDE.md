# GPT Quant V9 vs V9.1 Automated Comparison v1.0

套件會比較 V9 與 V9.1 的 JSON／CSV 回測指標，自動產生 Markdown、HTML、JSON 報告，並依 Policy 決定 GitHub Actions 是否通過。

## 安裝
解壓並覆蓋到 GPT 專案根目錄。本套件不包含 `manifest.json`，可避免再次產生主 manifest 衝突。

Commit：
`Add V9 vs V9.1 automated comparison report`

## 預設輸入
- `artifacts/backtest/v9_metrics.json`
- `artifacts/backtest/v91_metrics.json`

可在 Run workflow 時改路徑。

## 輸出
- `artifacts/comparison/v9-vs-v91-report.md`
- `artifacts/comparison/v9-vs-v91-report.html`
- `artifacts/comparison/v9-vs-v91-report.json`

報告也會顯示在 GitHub Actions Job Summary，並上傳為 Artifact。

## Policy
`config/gpt_quant_v9_v91_comparison_policy.json`

可設定必填指標、允許退步幅度、V9.1 最低 Sharpe 與 Profit Factor。

百分比可使用 24.0 或 0.24，工具會自動正規化。比較流程不會連接券商或送出訂單。
