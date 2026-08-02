# GPT Quant Enterprise 4.4.2 Compatibility Pack

## Purpose
Resolves runtime 404 errors caused by missing Enterprise 3.2 compatibility tables used by Enterprise 4.x workflows.

## Included fixes
- risk_snapshots_v32 compatibility
- portfolio_target_weights_v32 compatibility
- factor_rankings_v32 compatibility
- factor_library_v32 and factor_observations_v32 compatibility
- portfolio_optimization_runs_v32 compatibility
- compat_risk_snapshot_v41 view
- safe fallback logic in Risk Governor, Adaptive Allocation, and Investment Committee

## Installation
1. Extract and overwrite the repository.
2. Run `supabase/ENTERPRISE_4_4_2_COMPATIBILITY_PACK.sql` in Supabase SQL Editor.
3. Commit and push.
4. Run `Enterprise 4.4 Validation`.
5. Run `Enterprise 4.4 Portfolio Brain`.

## Safety
- PAPER ONLY
- Live trading remains disabled
- Missing legacy analytical data returns an empty dataset rather than stopping the pipeline
