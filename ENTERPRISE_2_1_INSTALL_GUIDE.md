# Enterprise 2.1 安裝

1. 覆蓋專案、Commit、Push。
2. 先確認 Enterprise 2.0 Foundation SQL 已完成。
3. 打開 `supabase/ENTERPRISE_2_1_COPY_PASTE_SETUP.sql`。
4. 全選貼到 Supabase SQL Editor 執行。
5. 成功訊息：
   `GPT Quant Enterprise 2.1 Operational Platform setup complete`
6. GitHub Actions → `Enterprise 2.1 Operational Daily Cycle`
7. Run workflow。
8. 網站按 `Ctrl + Shift + R`。
9. 進入 `Enterprise 2.1`。

注意：主流程仍依賴既有 V16-V22 Legacy Engines；
請先確認各版本必要資料表存在。
