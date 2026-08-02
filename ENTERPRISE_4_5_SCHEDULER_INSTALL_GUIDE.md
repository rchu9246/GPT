# GPT Quant Enterprise 4.5 Scheduler Pack

## 預設排程

- 台灣時區：Asia/Taipei
- 執行時間：週一至週五 16:10
- GitHub Actions cron：`10 8 * * 1-5`
- GitHub cron 固定採 UTC，因此 08:10 UTC = 16:10 台灣時間
- 同時保留 `workflow_dispatch` 手動執行

## 集中排程 Workflow

`.github/workflows/enterprise-4-5-operational-scheduler.yml`

此 Workflow 依序執行：

1. Enterprise 4.0 Foundation Gate
2. Enterprise 4.1 Central Risk Governor
3. Enterprise 4.2 Adaptive Allocation
4. Enterprise 4.3 Investment Committee
5. Enterprise 4.4 Portfolio Brain
6. Enterprise 4.5 Capture Decision Memory
7. Enterprise 4.5 Evaluate Learning Outcomes
8. Enterprise 4.5 Update Strategy Ratings
9. 驗證當日狀態資料

## 防止重複執行

原本 `enterprise-4-5-learning-cycle.yml` 的自動 schedule 已移除，只保留手動執行。
正式自動營運由單一 Operational Scheduler 管理。

## 安裝

1. 解壓並覆蓋目前 GPT 專案。
2. GitHub Desktop Commit：
   `Install Enterprise 4.5 Scheduler Pack`
3. Push origin。
4. 確認 GitHub Secrets 已存在：
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
5. 到 Actions 手動執行一次：
   `Enterprise 4.5 Operational Scheduler`
6. 手動測試成功後，後續會於平日 16:10 自動執行。

## 注意

- GitHub Actions 排程可能因平台負載延遲數分鐘。
- Cron 不會自動排除台灣國定假日或休市日。
- 目前維持 PAPER ONLY。
- Live trading 與 live learning 皆關閉。
