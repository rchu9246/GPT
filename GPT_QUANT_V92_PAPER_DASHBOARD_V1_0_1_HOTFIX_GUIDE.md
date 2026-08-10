# GPT Quant V9.2 Paper Trading Dashboard v1.0.1 – Supabase REST Fix

## 覆蓋
把 ZIP 解壓到 GPT repository 根目錄並覆蓋。

## Commit
`Fix Paper Trading Dashboard Supabase REST URL`

## Push
Push origin 後執行：
`Deploy Paper Trading Dashboard`

## GitHub Variables
保留：
- `DASHBOARD_SUPABASE_URL`
- `DASHBOARD_SUPABASE_PUBLISHABLE_KEY`

`DASHBOARD_SUPABASE_URL` 建議填：
`https://<project-ref>.supabase.co`

不要填 Service Role Key 到前端。

## 成功後
Dashboard 頂部會顯示：
`REST: https://<project-ref>.supabase.co/rest/v1`

如果仍失敗，錯誤訊息會直接顯示 REST base 與 Supabase response。
