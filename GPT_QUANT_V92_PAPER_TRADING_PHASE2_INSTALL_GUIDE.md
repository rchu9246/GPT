# GPT Quant V9.2 Paper Trading Phase 2 – Live Signal Pipeline v1.0

## 這一版做什麼

Phase 1 已完成：
- Shadow Production
- Paper Trading tables
- Dashboard
- Supabase REST

Phase 2 新增：
- 每日 Live Signal Scan
- 模擬 BUY
- Position Lifecycle
- 每日 Mark-to-Market
- Stop Loss
- Take Profit
- Trailing Stop
- Max Holding Days Exit
- Realized P&L
- Unrealized P&L
- Gross Exposure Risk Gate
- Single Position Cap
- Risk Event Log

仍然是：
`SHADOW_ONLY_NO_BROKER`

不連券商、不送真實訂單、不使用真實資金。

## 安裝順序

### 1. Supabase
先執行：
`supabase/GPT_QUANT_V92_PAPER_TRADING_PHASE2_UPGRADE.sql`

成功應顯示：
`Success. No rows returned`

### 2. 覆蓋 Repository
解壓 ZIP 到 GPT repository 根目錄。

### 3. Commit
`Add GPT Quant V9.2 Paper Trading Phase 2 Live Signal Pipeline`

### 4. Push origin

### 5. GitHub Actions
執行：
`GPT Quant V9.2 Paper Trading Phase 2 - Live Signal Pipeline`

第一次選：
`V9.1`

## 新增資料表
- `gptq_paper_signals`
- `gptq_paper_risk_events`

## 延伸欄位
`gptq_paper_positions`
- entry_score
- entry_signal
- highest_price
- holding_days
- stop_price
- take_profit_price

`gptq_paper_orders`
- realized_pnl
- holding_days
- exit_reason

## 預設風控
- Score Threshold: 65
- Position Size: 10%
- Max Single Position: 15%
- Max Gross Exposure: 80%
- Max Open Positions: 10
- Stop Loss: 5%
- Take Profit: 10%
- Trailing Stop: 6%
- Max Holding Days: 10

## Dashboard
現有 Dashboard 會繼續讀：
- gptq_paper_runs
- gptq_paper_orders
- gptq_paper_positions
- gptq_paper_equity_snapshots

所以 Phase 2 一旦產生交易，
Current Positions / Recent Paper Orders / Equity Curve 會開始有實際 Shadow 資料。

## 注意
如果 `signals_found = 0`，代表當天沒有符合 score threshold 的訊號，
不是系統故障。不要為了讓畫面出現訂單而隨意降低風控門檻。
