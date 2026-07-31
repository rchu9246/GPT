# GPT Quant V13.1 Operational Paper Engine

A Taiwan-equity quantitative platform with an operational, server-side paper
trading engine.

The engine uses Supabase signals and actual latest daily closing prices to:
- generate entries and exits,
- apply risk and cash limits,
- simulate fills,
- update cash and positions,
- calculate realized/unrealized P&L,
- write daily equity snapshots,
- preserve an auditable run and fill history.

It is PAPER trading only. Broker credentials and live orders are not supported
by the public GitHub Pages frontend.
