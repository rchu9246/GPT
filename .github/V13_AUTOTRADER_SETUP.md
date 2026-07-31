# GPT Quant V13 Enterprise AutoTrader

## What works immediately
- Browser-based Paper Trading account
- Signal-to-order proposal engine
- Approval/rejection queue
- Simulated fills and position ledger
- Kill Switch and risk gates

## Optional server-side automatic paper orders
1. Run `supabase/migrations/013_v13_autotrader.sql` in Supabase SQL Editor.
2. Insert one config row and keep `mode='PAPER'`.
3. Add GitHub Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.
4. Enable `autotrader_configs_v13.enabled=true` only after reviewing limits.
5. Workflow `V13 Paper AutoTrader` runs weekdays at 09:05 Taiwan time and can be run manually.

## Live trading
Live trading is intentionally locked. A broker adapter must run on a secure local machine/server with broker certificate and credentials. Never put broker secrets in Vite, GitHub Pages, localStorage, or the public repository.
