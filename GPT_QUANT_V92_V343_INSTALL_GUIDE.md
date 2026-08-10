# GPT Quant V9.2 Evidence Adapter → V9 vs V9.1 Comparison v3.4.3

這版會讓 automation/run_backtest.py 原生輸出 metrics/trades/equity，再自動做 Evidence Adapter 與 V9 vs V9.1 Comparison。

重要：目前 V9/V9.1 仍共用同一套核心演算法；真正差異必須透過 V9_* 與 V91_* Repository Variables 設定不同參數。若兩邊都不設定，會使用相同預設值，結果只能驗證 Pipeline，不能證明 V9.1 策略優於 V9。

Commit: `Add v3.4.3 production export and V9 vs V9.1 comparison`

Actions: `GPT Quant V9.2 Evidence Adapter → V9 vs V9.1 Comparison v3.4.3`
