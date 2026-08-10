# GPT Quant V9.2 Production Paper Trading / Shadow Production Phase 1

這是「實際市場環境 + 模擬資金」版本。

## 安全邊界

- 不連券商
- 不送真實訂單
- 不使用真實資金
- 只寫入 Supabase Shadow / Paper Trading tables

## 安裝順序

1. Supabase SQL Editor 執行：
   `supabase/GPT_QUANT_V92_PAPER_TRADING_PHASE1_FOUNDATION.sql`

2. 解壓套件覆蓋 GPT 專案根目錄。

3. Commit：
   `Add GPT Quant V9.2 Production Paper Trading Phase 1`

4. Push origin。

5. GitHub Actions 執行：
   `GPT Quant V9.2 Production Paper Trading Phase 1`

第一次建議手動選 `V9.1`。

## 預設風控

- Initial capital: 1,000,000
- Score threshold: 65
- Position size: 10%
- Max new orders/day: 5
- Max open positions: 10
- Slippage: 0.1%
- Commission: 0.1425%

## 自動排程

Workflow 會在台北時間週一至週五約 14:20 執行。
這是 Shadow Production，不代表交易所交易日判斷；假日若沒有新行情資料，仍可能產生當日 run 記錄。

## 成功後檢查 Supabase

- gptq_paper_runs
- gptq_paper_orders
- gptq_paper_positions
- gptq_paper_equity_snapshots

## 下一階段

Phase 2 才加入：
- position exit / take-profit / stop-loss lifecycle
- realized P&L
- daily mark-to-market
- V9 / V9.1 parallel shadow portfolios
- production dashboard
- alerting
