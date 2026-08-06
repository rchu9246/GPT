# GPT Quant V9.2 Production Evidence Adapter v3.4

## 目的

v3.4 將現有 V9 與 V9.1 真實回測引擎的輸出，自動轉換成 v3.3 Enterprise Dashboard 所需的標準格式。

## 標準輸出

每個版本產生：

- `{version}_metrics.json`
- `{version}_trades.csv`
- `{version}_equity_curve.csv`
- `{version}_production_evidence_manifest.json`

合併後產生 Artifact：

`v92-production-evidence-v34`

## 自動欄位映射

Metrics 支援常見別名，例如：

- `return` → `total_return`
- `max_dd` → `max_drawdown`
- `sharpe_ratio` → `sharpe`
- `pf` → `profit_factor`
- `trade_count` → `total_trades`

Trades 支援：

- `time`／`datetime` → `timestamp`
- `direction` → `side`
- `entry` → `entry_price`
- `exit` → `exit_price`
- `profit` → `pnl`

Equity 支援：

- `time`／`date` → `timestamp`
- `balance`／`nav`／`account_value` → `equity`

## 安裝

解壓後覆蓋到 GPT 專案根目錄。

Commit：

`Add GPT Quant V9.2 Production Evidence Adapter v3.4`

## Repository Variables

前往：

Settings → Secrets and variables → Actions → Variables

設定：

- `V9_REAL_BACKTEST_COMMAND`
- `V91_REAL_BACKTEST_COMMAND`

範例：

```text
python automation/run_v9_backtest.py
python automation/run_v91_backtest.py
```

真實回測程式可寫入以下任一組環境變數：

```text
GPTQ_RAW_METRICS_OUTPUT
GPTQ_RAW_TRADES_OUTPUT
GPTQ_RAW_EQUITY_OUTPUT
```

或既有相容名稱：

```text
GPTQ_METRICS_OUTPUT
GPTQ_TRADES_OUTPUT
GPTQ_EQUITY_OUTPUT
```

## 執行

GitHub Actions：

`GPT Quant V9.2 Production Evidence Adapter v3.4`

預設：

- min_trades = 20
- min_equity_rows = 30

成功後下載 Artifact：

`v92-production-evidence-v34`

資料來源 manifest 會顯示：

```json
{
  "source_type": "production_backtest",
  "production_evidence": true
}
```

## 串接 Dashboard

v3.3 Dashboard 目前自行重跑 Production Command。

後續可將 Dashboard Workflow 改為下載：

`v92-production-evidence-v34`

並直接使用其中的標準化檔案，避免重複執行回測。

本 Adapter 只處理回測證據，不會連接券商或送出訂單。
