# GPT Quant V7 Professional 部署

## 更新內容

- 個股分析頁：價格趨勢、多因子雷達與交易計畫
- 回測中心：總報酬、最大回撤、Sharpe、勝率與資金曲線
- 每日研究報告：市場摘要、候選股與風險提醒
- 投資組合：依 Score / Risk 自動產生建議權重
- 選股中心：可調整最低 Score
- V7 深色專業介面
- 修正 TypeScript `allowImportingTsExtensions` 建置問題

## 覆蓋部署

1. 解壓縮本套件。
2. 將所有檔案複製到 GitHub Desktop 的 GPT Repository 根目錄。
3. 選擇「全部取代」。
4. GitHub Desktop Commit：
   `Upgrade to GPT Quant V7 Professional`
5. Push origin。
6. 到 GitHub Actions 等待部署變綠。

## 選用 Migration

在 Supabase SQL Editor 執行：

`supabase/migrations/008_v7_professional.sql`

目前前端不依賴這兩張新表，所以即使尚未執行 Migration，網站仍可正常運作。

## Secrets

保留：

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `FINMIND_TOKEN`
