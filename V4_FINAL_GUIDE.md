# GPT Quant V4 Final 完整修正版

這個版本已補上缺少的：

```text
src/pages/DataPipeline.tsx
```

並包含完整 V4 升級檔案：

```text
automation/run_backtest.py
.github/workflows/run-backtest.yml
supabase/migrations/006_v4_backtest.sql
src/pages/Backtest.tsx
src/pages/StrategyLeaderboard.tsx
src/pages/DataPipeline.tsx
src/app/App.tsx
src/types/quant.ts
V4_CSS_APPEND.css
```

## 最快修復目前編譯錯誤

只要先上傳：

```text
src/pages/DataPipeline.tsx
```

GitHub Actions 就能通過目前的：

```text
Cannot find module '../pages/DataPipeline'
```

## 完整 V4 部署

1. 在 Supabase SQL Editor 執行 `006_v4_backtest.sql`
2. 上傳／覆蓋所有檔案
3. 將 `V4_CSS_APPEND.css` 貼到 `src/styles/dashboard.css` 最下方
4. 等 GitHub Pages 部署成功
5. 執行 GitHub Actions → Run Quant Backtest
