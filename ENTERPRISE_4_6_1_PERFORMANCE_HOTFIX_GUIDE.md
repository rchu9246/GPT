# Enterprise 4.6.1 Performance Compatibility Hotfix

## 修正內容

`enterprise46_performance_analytics.py` 不再要求
`portfolio_snapshots_v40` 必須存在。

資料來源優先順序：

1. `portfolio_snapshots_v40`（若存在）
2. `compat_portfolios_v40.latest_equity`
3. `enterprise_portfolios_v40.starting_cash`

若沒有歷史快照，分析仍會寫入基礎績效紀錄，但：
- sample_count 可能為 1
- Sharpe / Sortino / Calmar 多半為 0
- 需要後續累積每日權益資料，指標才會逐步有意義

## 安裝

1. 解壓並覆蓋目前 GPT 專案。
2. Commit：
   `Enterprise 4.6.1 Performance Compatibility Hotfix`
3. Push origin。
4. 執行 `Enterprise 4.6 Validation`。
5. 再執行 `Enterprise 4.6 Analytics Cycle`。

不需要額外執行 SQL。
