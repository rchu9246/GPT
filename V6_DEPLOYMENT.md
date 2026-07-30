# GPT Quant V6 Professional 整包覆蓋指南

這個壓縮包是完整 Repository，不是局部補丁。

## 最穩定上傳方式

1. 先備份目前 GitHub Repository。
2. 解壓縮 V6。
3. 使用 GitHub Desktop Clone `rchu9246/GPT`。
4. 將 V6 解壓縮內容全部複製到 Clone 的 GPT 資料夾。
5. 選擇覆蓋現有檔案。
6. Commit：
   `Upgrade to GPT Quant V6 Professional`
7. Push origin。

## 使用 GitHub 網頁版

可上傳：

- `src`
- `automation`
- `supabase`
- `.github`
- `package.json`
- `index.html`
- `vite.config.ts`
- `tsconfig.json`
- `tsconfig.app.json`
- `tsconfig.node.json`

注意：`.github` 是隱藏資料夾，若瀏覽器無法拖曳，請用 Create new file 建立 workflow。

## Supabase

依序執行尚未執行的 migration：

- `006_v4_backtest.sql`
- `007_v5_professional.sql`

## GitHub Secrets

保留：

- `FINMIND_TOKEN`
- `SUPABASE_SERVICE_ROLE_KEY`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`

## 驗收

GitHub Actions 部署成功後，網站應為深色專業主題，標題：

`GPT QUANT V5 PROFESSIONAL`

導覽列包含：

- 總覽
- 選股
- 每日報告
- 投資組合
- 回測
- 策略排行
- 資料管線
- Walk-forward
- 紙上交易

這個版本已確保 `src/main.tsx` 正確載入 `src/styles/dashboard.css`。
