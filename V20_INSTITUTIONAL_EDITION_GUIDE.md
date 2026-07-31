# V20 Institutional Edition 安裝

1. 覆蓋專案並 Push。
2. 打開 `supabase/V20_COPY_PASTE_SETUP.sql`。
3. 全選貼到 Supabase SQL Editor 執行。
4. GitHub Actions → `V20 Institutional Daily Cycle`。
5. Run workflow。
6. 網站按 `Ctrl + Shift + R`。
7. 進入「機構總控」。

V20 Daily Cycle 會依序執行：
- V16 Explainable Orders
- V17 Portfolio OS
- V18 AI Fund Manager
- V19 Hedge Fund Manager
- V20 Institutional Report

注意：V20 不會自動核准或成交候選委託。
Approve / Reject / Fill 仍保留人工安全控制。
