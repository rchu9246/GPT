# GitHub Pages + Supabase 部署指南

## 架構

- 前端：GitHub Pages
- 建置：GitHub Actions
- 資料庫：Supabase PostgreSQL
- 後端運算：Supabase Edge Functions
- 前端公開金鑰：Supabase Publishable Key
- 後端機密金鑰：只存 Supabase Edge Function Secrets

---

## 一、先備份目前正式版

建議在 GitHub 建立：

```text
backup-v1
```

或標籤：

```text
v1-dashboard-live
```

不要先刪除舊的 `dashboard_live.html`。

---

## 二、上傳專案

將本資料夾內容放在 repository 根目錄：

```text
GPT/
├── .github/
├── src/
├── supabase/
├── index.html
├── package.json
└── vite.config.ts
```

不要多包一層 `rchu9246-quant-v2/`。

---

## 三、建立 Supabase Project

在 Supabase 建立新 Project，接著依序執行：

```text
supabase/migrations/001_schema.sql
supabase/migrations/002_seed_strategy.sql
```

執行位置：

```text
Supabase Dashboard
→ SQL Editor
→ New query
```

---

## 四、設定 GitHub Secrets

GitHub repository：

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

新增：

```text
VITE_SUPABASE_URL
```

內容為 Supabase Project URL。

再新增：

```text
VITE_SUPABASE_PUBLISHABLE_KEY
```

內容為 Supabase Publishable Key。

禁止放入：

```text
SUPABASE_SERVICE_ROLE_KEY
```

因為 GitHub Pages 是公開前端。

---

## 五、設定 GitHub Pages

GitHub repository：

```text
Settings
→ Pages
→ Build and deployment
→ Source
→ GitHub Actions
```

---

## 六、部署前端

將程式 push 到 `main`。

GitHub Actions 會執行：

```text
.github/workflows/deploy-pages.yml
```

成功後網址：

```text
https://rchu9246.github.io/GPT/
```

---

## 七、本機測試

需要 Node.js 22。

```bash
npm install
cp .env.example .env.local
npm run dev
```

`.env.local`：

```env
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
```

Build 驗證：

```bash
npm run build
npm run preview
```

---

## 八、部署 Supabase Edge Functions

需要安裝 Supabase CLI 並登入。

```bash
supabase login
supabase link --project-ref YOUR_PROJECT_REF
```

部署健康檢查：

```bash
supabase functions deploy health-check
```

再依序部署：

```bash
supabase functions deploy ingest-market-data
supabase functions deploy calculate-features
supabase functions deploy generate-signals
supabase functions deploy calculate-outcomes
supabase functions deploy run-backtest
supabase functions deploy run-walk-forward
```

目前 Edge Functions 是安全骨架，會驗證 Supabase 連線，但尚未綁定實際台股資料來源。

---

## 九、Edge Function Secrets

Supabase 內建環境通常會提供：

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

外部市場資料 API 金鑰請使用：

```bash
supabase secrets set MARKET_DATA_API_KEY=YOUR_KEY
```

不要寫在：

```text
src/
.env.example
GitHub repository
```

---

## 十、驗收清單

### GitHub

- Actions 顯示綠色
- Pages Source 是 GitHub Actions
- 網址能開啟
- CSS、JS 沒有 404
- 瀏覽器 Console 沒有 Supabase URL/key 缺失錯誤

### Supabase

- 兩個 migration 都執行成功
- `strategy_configs` 有 `V2.0`
- RLS 已啟用
- anon 可以讀公開表
- anon 無法寫入資料
- `health-check` 回傳 `ok: true`

### 前端

- 沒有資料時顯示 Demo
- `signals` 有資料時切換為真實資料
- 個股頁、回測頁、Walk-forward 頁可正常開啟

---

## 十一、建議上線順序

1. GitHub Pages 顯示 V2 Demo
2. Supabase schema 建立完成
3. 插入少量測試股票與訊號
4. 驗證前端能讀 Supabase
5. 部署 health-check
6. 串接市場資料來源
7. 完成 Feature Engine
8. 完成 Signal Engine
9. 完成 Outcome Engine
10. 完成真實 Backtest
11. 完成 Walk-forward
12. 驗證後再移除舊版入口
