# GPT Quant V5 Professional 部署指南

## V5 新增功能

- 每日專業研究報告
- 市場狀態與策略健康度
- 風險警示清單
- Top Signals 解釋與交易價格區間
- 投資組合中心
- 現金、持倉、市值與未實現損益
- 最大回撤、波動率與 VaR 欄位
- V4 回測與策略排行完整保留

## 1. Supabase

在 SQL Editor 執行：

```text
supabase/migrations/007_v5_professional.sql
```

## 2. GitHub 新增

```text
automation/generate_daily_report.py
.github/workflows/generate-daily-report.yml
src/pages/DailyReportPage.tsx
src/pages/PortfolioPage.tsx
```

## 3. GitHub 覆蓋

```text
src/app/App.tsx
src/types/quant.ts
```

其餘 V4 檔案已包含在完整包中。

## 4. CSS

把：

```text
V5_CSS_APPEND.css
```

貼到：

```text
src/styles/dashboard.css
```

最下方。

## 5. 首次產生報告

GitHub Actions：

```text
Generate Professional Daily Report
→ Run workflow
```

策略：

```text
V3.1-MULTI
```

## 6. 驗收

Supabase 應新增：

```text
daily_reports
risk_snapshots
portfolios
portfolio_positions
portfolio_snapshots
```

網站導覽列新增：

```text
每日報告
投資組合
```

品牌顯示：

```text
GPT QUANT V5 PROFESSIONAL
```

## 注意

目前投資組合資料表已建立，但不會自動下單。
後續可將紙上交易結果同步到 portfolio_positions。
