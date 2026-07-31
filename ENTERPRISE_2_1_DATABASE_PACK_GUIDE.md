# GPT Quant Enterprise 2.1 Database Pack

這份 Database Pack 一次整合：

- V22 Autonomous Trading Director
- Enterprise 2.0 Foundation
- Enterprise 2.1 Operational Platform
- 相容性索引
- `updated_at` Trigger
- RLS 與讀取 Policy
- PostgREST Schema Cache Reload
- Enterprise 2.1 Readiness View
- 驗證查詢

## 執行方式

1. 開啟 `ENTERPRISE_2_1_DATABASE_PACK.sql`。
2. `Ctrl + A` 全選檔案內容。
3. 複製到 Supabase SQL Editor。
4. 按 `Run`。
5. 成功後應看到：
   `GPT Quant Enterprise 2.1 Database Pack setup complete`
6. `all_required_objects_ready` 應為 `true`。
7. 回 GitHub Actions 重新執行：
   `Enterprise 2.1 Operational Daily Cycle`

## 安全性

- 可重複執行。
- 不刪除既有資料。
- 不移除 V13–V21 Legacy Tables。
- Service Role Workflow 仍可正常寫入。
