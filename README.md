# 台股 QUANT Dashboard V2

可直接部署至：

```text
GitHub Pages + Supabase
```

## 快速開始

```bash
npm install
cp .env.example .env.local
npm run check
npm run dev
```

完整部署步驟請看：

```text
DEPLOYMENT.md
```

## 已整理內容

- React + TypeScript + Vite 前端
- GitHub Pages Actions workflow
- Supabase PostgreSQL schema
- V2.0 策略預設參數
- 0～100 評分引擎
- T+1 開盤回測核心
- Dashboard / Screener / Stock Detail
- Backtest / Walk-forward / Paper Trading
- Supabase Edge Function 安全骨架
- Secrets 與 RLS 部署規則

## 主要網址

部署完成後：

```text
https://rchu9246.github.io/GPT/
```

## 目前狀態

目前已完成部署骨架與 MVP。

尚待串接：

- 實際台股 OHLCV
- 三大法人資料
- Feature Engine 完整批次計算
- Signal Outcome
- 歷史回測資料庫寫入
- Walk-forward 參數搜尋
- 每日自動排程

> 僅供量化研究與紙上交易，不構成投資建議。
