
# GPT Quant V15 Enterprise Auto Portfolio

核心閉環：`signals → PROPOSED → APPROVED → FILLED → positions → P/L`

1. Actions → V15 Generate Proposed Orders → Run workflow。
2. 查詢 `trade_orders_v13` 的 PROPOSED 委託。
3. Actions → V14.5 Review Paper Order，貼完整 Order ID 並 APPROVE。
4. Actions → V14.5 Fill Approved Orders。
5. 網站「自動投組」查看持倉、淨值與損益。

V15 只建立 PAPER 委託，不會連接券商。
