# GPT Quant Enterprise 3.0.3 Stable

## 新增

- Stable Smoke Test Workflow
- Python compile validation
- Frontend TypeScript type check
- Frontend production build validation
- Supabase stable-readiness diagnostics
- Diagnostics JSON artifact
- GitHub Actions job summary
- `3.0 Status` 狀態頁
- Node.js 22 明確版本鎖定

## 部署順序

1. 覆蓋並 Push。
2. 執行 `Enterprise 3.0 Stable Validation`。
3. 執行 `Enterprise 3.0 Stable Smoke Test`。
4. 兩者成功後，再執行 `Enterprise 3.0 Stable Daily Cycle`。
5. 最後執行 GitHub Pages 部署。
