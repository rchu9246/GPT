# Enterprise 4.7.1 Strategy Scoring Engine Pack

## 功能

整合：

- market_regime_ai_v46
- strategy_analytics_v46
- strategy_rating_v45
- portfolio_health_v46
- risk_governor_status_v41
- strategy_catalog_v47

輸出：

- strategy_scores_v47
- strategy_engine_status_v47

## 評分構成

- Performance Score
- Risk Score
- Regime Fit Score
- Learning Score
- Stability Score
- Liquidity Score
- Diversification Score
- Confidence Score
- Composite Score
- Eligibility / Disqualification

## 安裝

1. Enterprise 4.7 Foundation Database Pack 必須已安裝。
2. 解壓並覆蓋目前 GPT 專案。
3. Commit：
   `Enterprise 4.7.1 Strategy Scoring Engine`
4. Push origin。
5. 執行：
   `Enterprise 4.6 Validation`
6. 執行：
   `Enterprise 4.7.1 Strategy Scoring`
7. Workflow 會自動驗證 `strategy_scores_v47` 與
   `strategy_engine_status_v47` 的當日資料。
8. Supabase 可再執行：
   `supabase/ENTERPRISE_4_7_1_STRATEGY_SCORING_VERIFY.sql`

## 安全

- PAPER ONLY
- Live Trading disabled
- Autonomous Execution disabled
- 此階段只評分，不產生實際委託
