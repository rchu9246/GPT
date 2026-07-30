# 台股自動更新補丁

本補丁會透過 GitHub Actions：

1. 從 FinMind 取得指定股票的 `TaiwanStockPrice`
2. Upsert 至 Supabase `daily_prices`
3. 計算最新一日 MA、RSI、MACD、ATR、量價與突破特徵
4. Upsert 至 `features`
5. 產生 `V2.5-AUTO` 訊號並 Upsert 至 `signals`

## 上傳位置

將解壓縮後的內容放到 GPT Repository 根目錄：

```text
GPT/
├── .github/
│   └── workflows/
│       └── update-market.yml
├── automation/
│   └── update_market.py
└── requirements-automation.txt
```

## 手動測試

GitHub：

```text
Actions
→ Update Taiwan Market Data
→ Run workflow
```

第一次先使用：

```text
symbols: 2330,2454,2382
lookback_days: 220
```

## 自動排程

工作流程設定為台北時間週一至週五 18:37 執行。

GitHub 排程可能延遲，且公開 repository 若 60 天沒有活動，排程可能會被自動停用。

## 安全

只使用 GitHub Secrets：

```text
FINMIND_TOKEN
SUPABASE_SERVICE_ROLE_KEY
VITE_SUPABASE_URL
```

Service Role Key 不會傳到 GitHub Pages 前端。

## 目前限制

- 預設只更新 3 檔，先驗證流程。
- 此版尚未計算三大法人，因此 institutional score 暫時使用中性值 50。
- 此版只寫入最新一日 feature 與 signal，但會保存抓取期間全部日價格。
- FinMind 帳戶方案可能限制請求頻率或可查詢範圍。
