# V9 覆蓋部署

1. GitHub Desktop → Repository → Show in Explorer。
2. 在 GPT 根目錄刪除舊的 `src` 資料夾。
3. 解壓 V9 ZIP，複製全部內容到 GPT 根目錄。
4. Windows 詢問時選擇取代。
5. GitHub Desktop Summary：`Upgrade to GPT Quant V9 Enterprise`
6. Commit to main → Push origin。
7. 等 GitHub Actions Success。
8. 網站按 Ctrl + Shift + R。

不要刪除 `.git`、`automation`、`supabase`。
