# Phase 2.6 安裝
1. 解壓縮後把整包內容複製到 GPT repo 根目錄並覆蓋/合併。
2. Supabase SQL Editor 執行 `supabase/GPT_QUANT_V92_PHASE26_UPGRADE.sql`。
3. GitHub Desktop Commit + Push。
4. Actions → `GPT Quant V9.2 Paper Trading Phase 2.6 - Automatic Daily Trading Cycle` → Run workflow → V9.1。
5. 成功標準：Phase 2.2 / 2.1 / 2.3 / 2.4 全 PASS，status=COMPLETED，pipeline=COMPLETED。
6. Dashboard 使用 `dashboard/paper_trading_phase26.html`；只輸入 Project URL 與 Publishable/anon key，禁止使用 service_role key。
