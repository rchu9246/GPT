# V16 Enterprise Trading Engine

1. 覆蓋專案並 Push。
2. 將 `supabase/V16_COPY_PASTE_SETUP.sql` 全部貼入 Supabase SQL Editor 執行。
3. GitHub Actions → `V16 Generate Explainable Orders` → Run workflow。
4. 網站「交易引擎」查看每一檔被接受或拒絕的原因。

目前你的 2330 訊號 Score 約 42、Risk 約 66，而設定 max_risk_score=60，因此 STRICT 模式會拒絕。

測試較寬鬆風控：
```sql
update public.autotrader_configs_v13 set max_risk_score=70 where account_name='paper-main';
```

或明確啟用 fallback：
```sql
update public.autotrader_configs_v13
set selection_mode='FALLBACK_TOP_N', fallback_top_n=1, fallback_max_risk_score=70
where account_name='paper-main';
```
