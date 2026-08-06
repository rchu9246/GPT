# GPT Quant V9.2 Production Evidence Adapter v3.4.1

- Metrics 缺失時，會由 trades 與 equity 自動計算。
- 缺檔或命令失敗時，仍會上傳 JSON／Markdown 診斷 Artifact。
- 真實回測命令必須建立 `GPTQ_TRADES_OUTPUT` 與 `GPTQ_EQUITY_OUTPUT`。
- `GPTQ_METRICS_OUTPUT` 可省略。

Commit：`Upgrade Production Evidence Adapter to v3.4.1`
