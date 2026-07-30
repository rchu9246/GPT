# GPT Quant V3 升級步驟

## 1. 上傳檔案
將本 ZIP 解壓後的所有內容覆蓋至 GitHub `rchu9246/GPT` 根目錄。保留既有 GitHub Secrets。

## 2. 資料庫升級
Supabase → SQL Editor，執行：
```text
supabase/migrations/003_v3_pipeline.sql
```

## 3. 部署 Functions
本機安裝 Supabase CLI，登入並 link：
```bash
npx supabase login
npx supabase link --project-ref zgpdgyeyllwtxbruvxfs
npx supabase functions deploy ingest-finmind
npx supabase functions deploy build-quant-signals
npx supabase functions deploy calculate-outcomes
```
先設定資料管線管理 Token（請自行建立至少 24 字元亂碼）：
```bash
npx supabase secrets set PIPELINE_ADMIN_TOKEN=你的長亂碼
```

若有 FinMind Token：
```bash
npx supabase secrets set FINMIND_TOKEN=你的Token
```

## 4. 重新部署網站
Push 到 main，等待 GitHub Actions 綠色完成。

## 5. 第一次資料執行
網站 → 資料管線：
1. 匯入示範股票
2. 計算 Features + Signals
3. 更新 Outcomes（需有未來交易日才會完整）

## 6. 自動排程
Supabase Dashboard → Integrations / Cron 建立每日工作。建議台灣交易日收盤後：
- 18:10 ingest-finmind
- 18:25 build-quant-signals
- 18:40 calculate-outcomes

免費或公開資料服務可能有速率限制；先小批次驗證，再逐步擴大股票清單。正式大量歷史資料應評估授權、配額與資料品質。
