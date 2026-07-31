# GPT Quant V13.1 Operational Paper Trading Engine

## 這一版真的會做什麼

每日台灣時間約 14:10，GitHub Actions 會：

1. 讀取最新 `signals`。
2. 讀取 `daily_prices.close`，不再用合成價格。
3. 更新持倉最新價與未實現損益。
4. 先檢查賣出規則：
   - 停損
   - 停利
   - Score 轉弱
   - 最大持有天數
5. 再依 Score、Risk、現金保留和單股上限建立買單。
6. 在自動模式下模擬成交。
7. 更新：
   - 現金
   - 持倉成本
   - 已實現損益
   - 未實現損益
   - 手續費與交易稅
   - 每日淨值快照
   - 引擎執行紀錄
8. 使用 idempotency key，重跑同一日不會重複下同一張單。

## 啟用步驟

### 1. 覆蓋專案並 Push

GitHub Desktop Summary：

`Upgrade to V13.1 Operational Paper Engine`

### 2. Supabase SQL Editor

先確定已執行：

`supabase/migrations/013_v13_autotrader.sql`

再執行：

`supabase/migrations/014_v13_1_operational_paper_engine.sql`

### 3. GitHub Secrets

Repository → Settings → Secrets and variables → Actions，確認存在：

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

`SERVICE_ROLE_KEY` 只能放在 GitHub Secrets，不可放在前端、README 或公開 Repository。

### 4. 先用人工核准測試

```sql
update public.autotrader_configs_v13
set enabled = true,
    mode = 'PAPER',
    kill_switch = false,
    require_approval = true,
    auto_fill = false
where account_name = 'paper-main';
```

這會產生 `PROPOSED` 委託，但不自動成交。

### 5. 啟用全自動模擬成交

確認委託與風控設定合理後執行：

```sql
update public.autotrader_configs_v13
set enabled = true,
    mode = 'PAPER',
    kill_switch = false,
    require_approval = false,
    auto_fill = true
where account_name = 'paper-main';
```

### 6. 手動測試

GitHub → Actions → `V13.1 Operational Paper Trading` → Run workflow。

## 查詢結果

```sql
select * from paper_accounts_v13;
select * from trade_orders_v13 order by created_at desc limit 20;
select * from paper_fills_v13 order by filled_at desc limit 20;
select * from paper_positions_v13 order by symbol;
select * from paper_equity_snapshots_v13 order by snapshot_date desc limit 30;
select * from paper_engine_runs_v13 order by started_at desc limit 20;
```

## 緊急停止

```sql
update public.autotrader_configs_v13
set kill_switch = true
where account_name = 'paper-main';
```

## 重要限制

- 這是模擬交易，不會連接券商。
- 成交價使用資料庫最新收盤價。
- GitHub Actions 並非低延遲交易環境。
- 正式績效評估仍應納入滑價、除權息、漲跌停與流動性限制。
