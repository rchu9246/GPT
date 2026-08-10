# GPT Quant V9.2 Paper Trading Dashboard v1.0

## 你會看到什麼

- Shadow Production 執行狀態
- V9 / V9.1 切換
- Total Equity
- Cash
- Market Value
- Unrealized P&L
- Open Positions
- 最新模擬訂單
- Latest Run
- Equity Curve
- Current Positions
- Recent Paper Orders

## 安全設計

前端絕對不要使用 `SUPABASE_SERVICE_ROLE_KEY`。

Dashboard 只能使用：
- Supabase Project URL
- Publishable Key / anon key

## 安裝

1. 解壓覆蓋 GPT repository 根目錄。
2. 到 Supabase SQL Editor 決定是否執行：
   `supabase/GPT_QUANT_V92_PAPER_DASHBOARD_READONLY.sql`

   注意：這會允許 anon role READ 四張 Paper Trading 表。
   若 GitHub Pages 是公開網站，Paper Trading 資料也會可公開讀取。

3. GitHub Repository Variables 新增：
   - `DASHBOARD_SUPABASE_URL`
   - `DASHBOARD_SUPABASE_PUBLISHABLE_KEY`

4. Commit：
   `Add GPT Quant V9.2 Paper Trading Dashboard v1.0`

5. Push origin。

6. GitHub → Settings → Pages：
   Source 選 `GitHub Actions`。

7. GitHub → Actions：
   執行 `Deploy Paper Trading Dashboard`。

成功後 GitHub Pages 的首頁就是 Paper Trading Dashboard。

## 若不想公開 Paper Trading 資料

不要執行 Dashboard READONLY SQL。
下一版可以改成：
- Supabase Auth 登入
- authenticated-only RLS
- private dashboard
