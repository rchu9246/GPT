# Enterprise 5.1 Multi-Agent Decision Council

## 安裝順序

1. 先在 Supabase 執行：
   `supabase/ENTERPRISE_5_1_FOUNDATION_DATABASE_PACK_v1.0.sql`
2. 解壓本 Pack 並覆蓋 GPT 專案。
3. Commit：
   `Enterprise 5.1 Multi-Agent Decision Council`
4. Push origin。
5. 先執行：
   `Enterprise 5.0 Operating System`
6. 再執行：
   `Enterprise 5.1 Multi-Agent Decision Council`
7. Supabase 可執行：
   `supabase/ENTERPRISE_5_1_MULTI_AGENT_COUNCIL_VERIFY.sql`

## Agents

- MARKET_AGENT
- RISK_AGENT
- STRATEGY_AGENT
- OPTIMIZER_AGENT
- LEARNING_AGENT
- DECISION_COUNCIL

## 決策規則

- Risk 或 Market Agent 可行使 Veto
- Veto 優先於一般多數決
- 非 Veto 情況使用信心分數與 Voting Weight 加權
- 所有投票、理由、衝突與最終決策均寫入資料庫

## 安全

- PAPER ONLY
- Live Trading disabled
- Autonomous Execution disabled
- Council 只產生 Paper Decision
