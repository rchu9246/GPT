# GPT Quant V9.2 Paper Trading Phase 2.4 – Automatic Position Management

Phase 2.4 接手 Phase 2.3 已建立的 Paper Positions。

每天會：
1. 從 daily_prices 取得最新收盤價
2. 更新 Market Value / Unrealized P&L
3. 更新 Highest Price
4. 增加 Holding Days
5. 檢查 Exit Rules
6. 若觸發，建立 Paper SELL
7. 刪除已平倉 Paper Position
8. 更新 Cash / Realized P&L / Equity Snapshot

## Exit Rules

優先順序：
1. STOP_LOSS：預設 -5%
2. TAKE_PROFIT：預設 +10%
3. TRAILING_STOP：距最高價回落 6%
4. MAX_HOLDING_DAYS：預設 10 天
5. SIGNAL_WEAKNESS：今日 Score < 50

## 安裝順序

1. Supabase SQL Editor 執行：
   `supabase/GPT_QUANT_V92_PAPER_TRADING_PHASE24_UPGRADE.sql`

2. ZIP 解壓覆蓋 GPT repository。

3. Commit：
   `Add GPT Quant V9.2 Paper Trading Phase 2.4 Automatic Position Management`

4. Push origin。

5. GitHub Actions 執行：
   `GPT Quant V9.2 Paper Trading Phase 2.4 - Automatic Position Management`

6. strategy_version 選：
   `V9.1`

## 預期目前狀態

Phase 2.3 已有 2 個 open positions。
第一次 Phase 2.4 執行通常可能是：
- positions_before: 2
- positions_marked: 2
- exits_triggered: 0

如果沒有任何退出條件被觸發，持倉會維持 HOLD；
Dashboard 的 Market Value 與 Unrealized P&L 會被更新。

## 完整自動流程

14:05 Phase 2.2 Market Data
↓
14:15 Phase 2.1 Signal Generation
↓
14:20 Phase 2.3 Automatic Signal Execution
↓
14:25 Phase 2.4 Automatic Position Management
↓
Paper Trading Dashboard

此版本仍為 SHADOW_ONLY_NO_BROKER，不會送真實券商訂單。
