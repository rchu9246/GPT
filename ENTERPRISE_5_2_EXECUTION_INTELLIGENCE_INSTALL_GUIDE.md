# Enterprise 5.2 Execution Intelligence Layer

## 安裝順序

1. 在 Supabase 執行：
   `supabase/ENTERPRISE_5_2_FOUNDATION_DATABASE_PACK_v1.0.sql`
2. 解壓並覆蓋 GPT 專案。
3. Commit：
   `Enterprise 5.2 Execution Intelligence Layer`
4. Push origin。
5. 依序執行：
   - Enterprise 5.0 Operating System
   - Enterprise 5.1 Multi-Agent Decision Council
   - Enterprise 5.2 Execution Intelligence
6. Supabase 驗證：
   `supabase/ENTERPRISE_5_2_EXECUTION_INTELLIGENCE_VERIFY.sql`

## 建立內容

- execution_constraints_v52
- execution_plans_v52
- execution_batches_v52
- execution_orders_v52
- execution_risk_checks_v52
- execution_metrics_v52
- execution_audit_v52
- execution_status_v52
- execution_dashboard_v52

## 主要規則

- Council BLOCK 或 Risk Veto 時停止建立可執行批次
- 檢查最大曝險、最低現金、最大每日週轉率
- 檢查單筆權重變化與最低信心
- 超過單筆權重上限時自動降額
- 所有訂單只建立 Paper Execution Plan

## 安全

- PAPER ONLY
- Live Trading disabled
- Broker Submission disabled
- 不呼叫任何券商 API
- 不會送出真實委託
