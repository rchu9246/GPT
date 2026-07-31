# GPT Quant V11 Enterprise AI 覆蓋指南

1. GitHub Desktop → Repository → Show in Explorer。
2. 在 GPT 根目錄刪除舊的 `src` 資料夾。
3. 不要刪除 `.git`、`.github`、`automation`、`supabase`。
4. 解壓縮 V11 ZIP。
5. 將解壓後全部內容複製到 GPT 根目錄。
6. GitHub Desktop Summary：
   `Upgrade to GPT Quant V11 Enterprise AI`
7. Commit to main → Push origin。
8. GitHub Actions 成功後，網站按 `Ctrl + Shift + R`。

## 誠實資料原則

- AI 助理使用目前 Supabase 量化訊號，不宣稱連線到尚未配置的外部 LLM。
- 全球市場頁目前使用代理指標，不偽造即時指數報價。
- 事件情緒頁目前使用量化事件，不偽裝成即時新聞。
- 未來的秘密金鑰應放在 Supabase Edge Function 或 GitHub Secrets，不能放在 Vite 前端。
