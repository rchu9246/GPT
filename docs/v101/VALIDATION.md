# V10.1 acceptance and validation record

Issue: https://github.com/rchu9246/GPT/issues/21
Branch: `codex/v101-paper-challenger`

## Completed

- Downloaded original artifact 13164239769 from Run 41494044022; ZIP SHA-256 matches GitHub's digest. Extracted files match every ZIP member byte-for-byte. All 18 account chains and benchmark chain verify. Every account's daily equity and final cash, fees, realized/unrealized PnL reconcile. Original evidence was not modified.
- Reproduced the original 18-day forward comparison and exported all 18 account results locally, with capture freshness, sample counts, fee and drawdown fields. Original-account results are excluded from the public PR.
- Researched five primary academic sources and official Taiwan lot/tax rules; fixed three hypotheses and independent V101 IDs/accounts. Specification and engine implementation digests are frozen in the registry. No hypothesis or execution parameter was retuned after seeing final-block results.
- Acquired 261 complete official daily security tables (2025-10-01–2026-11-02), preserving request-source SHA-256 lineage. Evaluated 176 fold/stress comparisons plus eight same-period replays = 184 metric rows. Three chronological test blocks, five-session embargoes and a final 30-session block. All 18 common-execution V10 controls are included.
- Added an isolated dashboard route. Existing V9/V10 page components, original account stores, strategy modules and production schedules remain unchanged.
- Local verification: **397 tests passed** (251 main discovery, including 22 new V101 regressions; 146 additional V92 tests). Existing legacy discovery import and Windows long-path issues are handled by `python scripts/check_v101.py`; no production code was modified for those environment issues. Frontend TypeScript/Vite production build passed. Git whitespace validation passed.
- Regression coverage: no future-price leakage, contemporaneous membership vs future survivors, actual subsequent-open timing, costs/tax/minimum/slippage, lot sizes, trailing-only liquidity sizing, cash/equity accounting, stale/future/missing data, duplicate sessions, immutable replay/fingerprint conflicts, source ZIP/tree mismatch, original account non-interference, concentration caps, embargo/final-block separation, and rejection of caller-asserted corporate-action certification.

## Acceptance not met / explicit blockers

- Historical corporate actions are **not completely validated**. The official TWT49U historical result endpoint returned 1,554 records over the requested range, but reference-price/rights results do not establish complete point-in-time announcement availability, dividend payment, share entitlement and delisting settlement. No missing entitlement or price was fabricated. Raw data is retained locally and excluded from the PR.
- Historical metrics are **retrospective unadjusted-price diagnostics**, not clean total returns or certified ex-ante OOS. Chronological fold separation reduces leakage but cannot undo the fact that V10.1 research was conceived after this historical period. No profitability/promotion claim is made.
- New paper-forward observations: **0 / 60**. The forward module freezes an independent registry/boundary but deliberately rejects execution until a provenance-verified corporate-action adapter exists. A caller-supplied boolean cannot bypass this. No new forward or broker order has been produced.
- Three challengers are entirely cash in the original 18-day interval; two or three earlier historical blocks also have zero trades. No-trade outcomes fail to establish strategy effectiveness and can miss strong rallies. Reduced loss is not evidence of alpha.
- The archived GitHub artifact has a retention window; the CI baseline audit will fail closed if it expires or becomes inaccessible. Original raw evidence should be preserved under an approved immutable retention policy, never silently replaced with a newer artifact.

## Review boundary

Draft PR only. No merge, production schedule update, promotion activation, real-money setting, broker adapter, account secret, or alteration to the 18 originals. Raw artifacts, original positions/fills, downloaded OHLCV and intermediate local results are excluded from the commit. Only code, fixed specs, research notes and a compact set of new V101 diagnostic metrics are proposed. Original-account and full comparison exports remain local after publication review rejected their public release.
