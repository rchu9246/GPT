# GPT Quant V3

台股量化研究平台：GitHub Pages 前端 + Supabase PostgreSQL / Edge Functions。

## V3 新增
- FinMind 行情匯入 Edge Function
- MA / RSI / MACD / ATR / 量價與突破特徵
- V3 加權評分與 S/A/B/C/D 訊號
- Outcome T+1/T+3/T+5/T+10/T+20
- Pipeline 執行紀錄與前端監控頁
- Market Regime 基礎廣度判斷

## 升級
1. 執行 `supabase/migrations/003_v3_pipeline.sql`
2. 部署三個 V3 Edge Functions
3. 網站重新部署
4. 在「資料管線」先匯入 3 檔示範資料，再產生訊號

完整步驟見 `V3_DEPLOYMENT.md`。
