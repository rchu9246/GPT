# Enterprise 4.6.5 Market Regime AI Pack

## 新增

- `automation/enterprise465_market_regime.py`
- `.github/workflows/enterprise-4-6-5-market-regime-ai.yml`
- `supabase/ENTERPRISE_4_6_5_MARKET_REGIME_AI_VERIFY.sql`

## 資料來源

- `performance_daily_v46`
- `market_regime_v46`
- `risk_governor_status_v41`
- `portfolio_health_v46`
- 過去的 `market_regime_ai_v46`

## 輸出

寫入：

`market_regime_ai_v46`

可能狀態：

- TRENDING_UP
- TRENDING_DOWN
- SIDEWAYS
- BREAKOUT
- HIGH_VOLATILITY
- LOW_VOLATILITY
- CRASH
- RECOVERY
- CHOPPY

## 安裝

1. 解壓並覆蓋目前 GPT 專案。
2. Commit：
   `Enterprise 4.6.5 Market Regime AI`
3. Push origin。
4. 執行：
   `Enterprise 4.6 Validation`
5. 再執行：
   `Enterprise 4.6.5 Market Regime AI`
6. Workflow 最後會自動確認當日資料已寫入。
7. Supabase 可再執行：
   `supabase/ENTERPRISE_4_6_5_MARKET_REGIME_AI_VERIFY.sql`

不需要額外執行建表 SQL，前提是 Enterprise 4.6.5 Foundation Database Pack 已安裝。
