# Enterprise 2.0 安裝

1. 覆蓋專案、Commit、Push。
2. 打開 `supabase/ENTERPRISE_2_0_COPY_PASTE_SETUP.sql`。
3. 全選貼入 Supabase SQL Editor 執行。
4. 成功訊息：
   `GPT Quant Enterprise 2.0 Foundation setup complete`
5. GitHub Actions → `Enterprise 2.0 Daily Master Cycle`
6. Run workflow。
7. 網站按 `Ctrl + Shift + R`。
8. 進入 `Enterprise 2.0`。

注意：
- V22 SQL 若尚未執行，先建立 V22 表，因為目前 Director 仍屬 Legacy Engine。
- Enterprise 2.0 Foundation 不刪除任何舊資料表。
- 不要在驗證完成前停用舊 Workflow。
