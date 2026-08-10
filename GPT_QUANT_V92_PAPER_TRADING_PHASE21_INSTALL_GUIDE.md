# GPT Quant V9.2 Paper Trading Phase 2.1
## Live Market Data + Signal Generation

這版專門解決：
`signals_found = 0`

不是把 threshold 降低，而是先回答：

1. daily_prices 是否真的有最新資料？
2. 最新 market date 是哪一天？
3. 有多少 active stocks？
4. 有多少股票具有 >= 122 筆歷史資料？
5. 每檔股票實際 score 是多少？
6. 最接近 65 分門檻的是哪些股票？
7. 是資料過舊，還是策略真的沒有訊號？

## 安裝順序

1. Supabase SQL Editor 執行：
   `supabase/GPT_QUANT_V92_PAPER_TRADING_PHASE21_UPGRADE.sql`

2. 解壓 ZIP 覆蓋 GPT repository 根目錄。

3. Commit：
   `Add GPT Quant V9.2 Paper Trading Phase 2.1 Signal Engine`

4. Push origin。

5. GitHub Actions 執行：
   `GPT Quant V9.2 Paper Trading Phase 2.1 - Live Market Data + Signal Generation`

6. strategy_version 選：
   `V9.1`

## 成功後 GitHub Summary 會顯示

- Market data status
- Latest market date
- Stocks scanned
- Signals eligible
- Top candidate
- Top 15 candidates + score

## Supabase 新增

`gptq_market_data_health`
- 檢查 daily_prices 新鮮度

`gptq_signal_generation_summary`
- 每日訊號生成摘要

`gptq_paper_signals`
新增欄位：
- rank_no
- market_date
- trend_score
- momentum_score
- volume_score
- breakout_score
- risk_score
- rsi14
- roc20
- volume_ratio
- atr_pct
- data_rows
- data_fresh

## 執行順序

14:15 Phase 2.1 Signal Generation
↓
14:25 Phase 2 Paper Trading

如果 Phase 2.1 顯示 0 eligible signals，
下一步應先看 Top Candidates 與 Market Data Health，
不要直接降低 threshold。
