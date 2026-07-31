# GPT Quant V14 Enterprise AI Trading Platform

## A. 覆蓋 GitHub 專案

1. GitHub Desktop → Repository → Show in Explorer。
2. 刪除舊的 `src` 資料夾。
3. 解壓縮 V14 ZIP。
4. 複製解壓資料夾內全部內容到 GPT 根目錄。
5. Summary：`Upgrade to GPT Quant V14 Enterprise AI Trading Platform`
6. Commit to main → Push origin。

請確認 GPT 根目錄直接存在：

- `src/main.tsx`
- `package.json`
- `.github/workflows`
- `supabase/V14_COPY_PASTE_SETUP.sql`

## B. Supabase：不要輸入檔案路徑

請用記事本或 VS Code 打開：

`supabase/V14_COPY_PASTE_SETUP.sql`

按 `Ctrl + A`、`Ctrl + C`，將完整 SQL 貼入 Supabase SQL Editor，再按 Run。

不能只輸入：

`supabase/V14_COPY_PASTE_SETUP.sql`

因為 SQL Editor 不會讀取本機或 GitHub 檔案路徑。

## C. GitHub Secrets

Repository → Settings → Secrets and variables → Actions：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Service Role Key 不能放在前端或公開程式碼。

## D. 第一次測試：只產生委託、不成交

```sql
update public.autotrader_configs_v13
set enabled = true,
    mode = 'PAPER',
    kill_switch = false,
    require_approval = true,
    auto_fill = false
where account_name = 'paper-main';
```

GitHub Actions → `V14 Operational Paper Trading` → Run workflow。

## E. 啟用全自動 Paper Trading

測試正常後：

```sql
update public.autotrader_configs_v13
set enabled = true,
    mode = 'PAPER',
    kill_switch = false,
    require_approval = false,
    auto_fill = true
where account_name = 'paper-main';
```

## F. 緊急停止

```sql
update public.autotrader_configs_v13
set kill_switch = true
where account_name = 'paper-main';
```

## G. 網站

GitHub Actions 部署成功後，網站按 `Ctrl + Shift + R`。

進入「交易營運」可查看：

- 帳戶淨值與現金
- 持倉與損益
- 最新委託與成交
- 每日淨值曲線
- 引擎執行狀態
