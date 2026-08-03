# Enterprise 5.0 Orchestrator Pack

## 功能

Enterprise 5.0 Orchestrator 依照 Engine Registry 執行：

1. Central Risk Governor
2. Market Regime AI
3. Strategy Scoring Engine
4. Portfolio Optimizer
5. Decision Learning Engine（Optional）

並更新：

- operating_state_v50
- execution_context_v50
- workflow_history_v50
- decision_timeline_v50
- event_bus_v50
- system_health_v50
- engine_registry_v50
- orchestrator_status_v50

## 安裝條件

必須先完成：

- Enterprise 5.0 Foundation Database Pack
- Enterprise 4.9.1 Portfolio Optimizer Engine
- Enterprise 4.7.1 Strategy Scoring
- Enterprise 4.6.5 Market Regime AI
- Enterprise 4.1 Risk Governor

## 安裝步驟

1. 解壓並覆蓋目前 GPT 專案。
2. Commit：
   `Enterprise 5.0 Orchestrator`
3. Push origin。
4. 執行：
   `Enterprise 5.0 Operating System`
5. Workflow 會自動驗證 Cycle、Context、Timeline、Event Bus、
   Workflow History、System Health 與 Orchestrator Status。
6. Supabase 可再執行：
   `supabase/ENTERPRISE_5_0_ORCHESTRATOR_VERIFY.sql`

## Required / Optional

Required Engine 失敗：

- 後續引擎停止
- Workflow 標記 BLOCKED
- GitHub Action 失敗

Optional Engine 失敗：

- Workflow 標記 WARNING
- 其他成果保留

## 安全限制

- PAPER ONLY
- Live Trading disabled
- Autonomous Execution disabled
- Broker Submission disabled
- Orchestrator 只執行資料分析及 Paper 計畫
