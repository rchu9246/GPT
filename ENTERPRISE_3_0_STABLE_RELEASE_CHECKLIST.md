# Enterprise 3.0 Stable Release Checklist

## Database
- Stable SQL executed successfully
- `quant_stable_readiness.all_required_objects_ready = true`
- PostgREST schema cache reloaded

## Secrets
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `FINMIND_TOKEN`

## Workflow
- Stable Daily Cycle succeeds
- Release run status is SUCCESS
- No critical stage failure
- Old RC workflow remains manual-only

## Dashboard
- 3.0 Stable page loads
- Data quality table is visible
- Stage results are visible
- No Supabase permission errors

## Safety
- `live_trading_enabled = false`
- AutoTrader mode remains PAPER
- Kill switch is available
- No broker credential is present in frontend code
