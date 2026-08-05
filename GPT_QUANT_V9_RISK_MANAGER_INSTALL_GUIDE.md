# GPT Quant V9 Risk Manager v1.0

## 部署

1. 在 Supabase 執行 `supabase/GPT_QUANT_V9_RISK_MANAGER_FOUNDATION.sql`。
2. 將 ZIP 內容覆蓋到 GPT 專案根目錄。
3. Commit：`GPT Quant V9 Risk Manager v1.0`。
4. Push origin。
5. 執行 GitHub Actions：`GPT Quant V9 Risk Manager`。

第一次建議值：

- limit = 100
- max_single_position = 0.10
- max_total_exposure = 0.60
- max_open_positions = 10
- daily_loss_limit = 0.02
- portfolio_drawdown_limit = 0.10
- max_var_per_position = 0.02

## 決策

- APPROVE
- SCALE_DOWN
- BLOCK
- KILL_SWITCH

目前 Position Sizing 全部為 BLOCKED 時，Risk Manager 預期同樣輸出 approved_position_size = 0。

## 安全限制

Paper Only、Live Trading = false、Broker Submission = false，不修改原始 Position Sizing 結果。
