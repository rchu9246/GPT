# GPT Quant V4 部署指南

V4 新增：

- 真正的歷史回測 Python 引擎
- T+1 開盤進場
- 停利、停損、時間出場
- 手續費、證交稅、滑價
- 勝率、總報酬、年化報酬
- Profit Factor
- 最大回撤
- Sharpe / Sortino
- 資金曲線
- 交易明細
- 策略排行榜
- 每個交易日自動回測

## 1. Supabase

在 SQL Editor 執行：

```text
supabase/migrations/006_v4_backtest.sql
```

## 2. GitHub 上傳／覆蓋

新增：

```text
automation/run_backtest.py
.github/workflows/run-backtest.yml
src/pages/StrategyLeaderboard.tsx
```

覆蓋：

```text
src/pages/Backtest.tsx
src/app/App.tsx
src/types/quant.ts
```

## 3. CSS

把 `V4_CSS_APPEND.css` 的內容貼到：

```text
src/styles/dashboard.css
```

最下方。

## 4. 執行首次回測

GitHub：

```text
Actions
→ Run Quant Backtest
→ Run workflow
```

第一次建議：

```text
strategy: V3.1-MULTI
score_threshold: 65
take_profit: 0.10
stop_loss: 0.05
max_holding_days: 10
```

## 5. 驗收

Supabase：

```text
backtest_runs
backtest_trades
```

應新增資料。

網站新增：

```text
回測
策略排行
```

## 重要限制

目前只有 3 檔、約 220 日行情，因此回測樣本仍小。
應先擴大股票池與歷史資料，再用 Walk-forward 判定策略是否穩定。

排程使用 UTC cron `11:05`，約等於台北時間 19:05。
GitHub Actions 排程可能因平台負載延遲。
