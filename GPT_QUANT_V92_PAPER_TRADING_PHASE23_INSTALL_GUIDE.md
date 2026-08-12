# GPT Quant V9.2 Paper Trading Phase 2.3 – Automatic Signal Execution

1. Supabase SQL Editor 執行：
   `supabase/GPT_QUANT_V92_PAPER_TRADING_PHASE23_UPGRADE.sql`

2. ZIP 解壓覆蓋 GPT repository。

3. Commit：
   `Add GPT Quant V9.2 Paper Trading Phase 2.3 Automatic Signal Execution`

4. Push origin。

5. GitHub Actions 執行：
   `GPT Quant V9.2 Paper Trading Phase 2.3 - Automatic Signal Execution`

6. strategy_version 選 `V9.1`。

目前 Phase 2.1 已有 2454 / 67.13 與 2330 / 67.03 兩個 eligible signals。
若資金與曝險風控通過，預期建立兩筆 Paper BUY 與兩個模擬持倉。

此版本仍為 SHADOW_ONLY_NO_BROKER，不會送真實券商訂單。
