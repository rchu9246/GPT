# GPT Quant V9.2 Paper Trading Phase 2.2
## Automatic Market Data Ingestion

這一版解決目前 Phase 2.1 顯示：

`Market data status: STALE`

以及：

`Latest market date: 2026-07-30`

Phase 2.2 會在每天 Phase 2.1 之前，自動讀取 `stocks` 中的 active stocks，
查詢缺少的日行情，再寫入既有 `daily_prices`。

## 資料來源

FinMind API v4
Dataset:
`TaiwanStockPrice`

GitHub Secret:
`FINMIND_TOKEN`

如果 FINMIND_TOKEN 未設定，程式會嘗試匿名存取，但建議使用 token。

## 安裝順序

### 1. Supabase

執行：

`supabase/GPT_QUANT_V92_PAPER_TRADING_PHASE22_UPGRADE.sql`

成功應看到：

`Success. No rows returned`

### 2. 覆蓋 Repository

解壓 ZIP 到 GPT repository 根目錄。

### 3. Commit

`Add GPT Quant V9.2 Paper Trading Phase 2.2 Market Data Ingestion`

### 4. Push origin

### 5. GitHub Secret

確認存在：

`FINMIND_TOKEN`

你原本若已經有，不需要重建。

### 6. 執行 GitHub Action

`GPT Quant V9.2 Paper Trading Phase 2.2 - Automatic Market Data Ingestion`

## 成功後 Summary 會顯示

- Provider
- Status
- Latest market date before
- Latest market date after
- Stale days before
- Stale days after
- Stocks attempted
- Stocks updated
- Rows received
- Rows inserted
- Errors

以及每檔股票：

- symbol
- status
- rows received
- rows inserted
- rows updated
- latest market date

## 自動排程

14:05 Phase 2.2 Market Data Ingestion
↓
14:15 Phase 2.1 Signal Generation
↓
14:25 Phase 2 Paper Trading
↓
Dashboard

## 資料寫入策略

Phase 2.2 不會盲目重灌歷史資料。

對每一檔 active stock：

1. 查 Supabase 最新 `trade_date`
2. 從下一天開始向 FinMind 補資料
3. 已存在且值相同 → skipped
4. 已存在但 OHLCV 不同 → update
5. 不存在 → insert

所以 workflow 可以重複執行。

## 安全模式

`MARKET_DATA_ONLY_NO_BROKER`

此版本：
- 不連券商
- 不送真實訂單
- 不改真實資金
- 只更新行情資料與 ingestion audit

## 執行後下一步

先確認 Phase 2.2：

`Latest market date after`

已更新到合理的最新交易日。

接著重新執行 Phase 2.1。

理想結果：

`Market data status: FRESH`

之後才重新執行 Phase 2 Paper Trading。
