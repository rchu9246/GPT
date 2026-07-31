# Enterprise 3.0 Stable 安裝

1. 覆蓋專案、Commit、Push。
2. 確認 Enterprise 3.0 RC SQL 已完成。
3. 開啟 `supabase/ENTERPRISE_3_0_STABLE_COPY_PASTE_SETUP.sql`。
4. 完整貼入 Supabase SQL Editor 執行。
5. 成功訊息：
   `GPT Quant Enterprise 3.0 Stable setup complete`
6. `all_required_objects_ready` 必須為 `true`。
7. GitHub Actions → `Enterprise 3.0 Stable Daily Cycle`
8. Run workflow。
9. 執行 GitHub Pages 部署。
10. 網站按 `Ctrl + Shift + R`。
11. 首頁進入 `3.0 Stable`。

正式版只保留 `Enterprise 3.0 Stable Daily Cycle` 排程。
舊 RC Cycle 已改為 Manual Only。
