# PR #22 post-review evidence

Draft retained. Original 18 accounts, V10.1 V1 frozen registry, website and production schedules are unchanged. No forward run, broker order or promotion has been started.

## Corporate-action coverage

Official reference events: **1554**. Audited actual holding scenarios: **218**. Held-event intersections: **174** across **17** unique symbol/ex-date pairs. The complete per-holding audit remains private/local.
All scenarios remain **BLOCKED** for certified total-return/forward eligibility. The official reference table does not provide complete historical announcement availability, record/pay dates, stock entitlement delivery, split/rights elections or delisting cash settlement. Zero intersections cannot certify a no-event period. No reference adjustment was invented as a dividend or settlement.

Source: [TWSE TWT49U](https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json&startDate=20251001&endDate=20261102); retrieved 2026-11-03T04:43:40.753721+00:00; SHA-256 `2abb1e190f93f39f608d9948c0b2a76d60d165f0f8e34505ac82bba5002b09f7`.

The adapter verifies HTTPS official-source provenance, payload digest and schema, preserves signed reference adjustments, and audits holdings immediately BEFORE the ex-open. Entitlement primitives separate receivables from cash, pay only on settlement, deliver verified stock/split terms, block unsupported rights elections, fractional-share terms and missing delisting settlement. These tested primitives do not certify missing historical fields or unlock forward.

## Exposure and rising-market diagnostics

Fixed paired control: reuse each challenger's known T-close gross target, divide equally over its same ranked basket; preserve next-open, whole-lot, trailing-liquidity, commission/tax/slippage and band rules. No parameters were selected using returns. Post-trade exposure must remain within **1 percentage point on every date**, with **at least 10 active sessions**, to label a matched diagnostic. Otherwise report UNMATCHED or insufficient activity. Even a match remains unverified-price research, not alpha proof.

| Block | Challenger | Stress | Strategy net | Paired net | Max exposure gap | Pair status | TWSE gross | Cash opportunity gap* |
|---|---|---:|---:|---:|---:|---|---:|---:|
|WF_1|V101_VOL_MOMENTUM_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|18.5326%|18.5326 pp|
|WF_1|V101_VOL_MOMENTUM_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|18.5326%|18.5326 pp|
|WF_1|V101_REGIME_VOL_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|18.5326%|18.5326 pp|
|WF_1|V101_REGIME_VOL_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|18.5326%|18.5326 pp|
|WF_1|V101_REGIME_VOL_BAND_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|18.5326%|18.5326 pp|
|WF_1|V101_REGIME_VOL_BAND_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|18.5326%|18.5326 pp|
|WF_2|V101_VOL_MOMENTUM_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|9.4044%|9.4044 pp|
|WF_2|V101_VOL_MOMENTUM_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|9.4044%|9.4044 pp|
|WF_2|V101_REGIME_VOL_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|9.4044%|9.4044 pp|
|WF_2|V101_REGIME_VOL_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|9.4044%|9.4044 pp|
|WF_2|V101_REGIME_VOL_BAND_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|9.4044%|9.4044 pp|
|WF_2|V101_REGIME_VOL_BAND_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|9.4044%|9.4044 pp|
|WF_3|V101_VOL_MOMENTUM_V1|1.0|-0.2211%|0.0000%|2.520 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|-0.7759%|-0.8283 pp|
|WF_3|V101_VOL_MOMENTUM_V1|2.0|-0.2273%|0.0000%|2.521 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|-0.7759%|-0.8283 pp|
|WF_3|V101_REGIME_VOL_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|-0.7759%|-0.7759 pp|
|WF_3|V101_REGIME_VOL_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|-0.7759%|-0.7759 pp|
|WF_3|V101_REGIME_VOL_BAND_V1|1.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|-0.7759%|-0.7759 pp|
|WF_3|V101_REGIME_VOL_BAND_V1|2.0|0.0000%|0.0000%|0.000 pp|CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS|-0.7759%|-0.7759 pp|
|FINAL_HOLDOUT|V101_VOL_MOMENTUM_V1|1.0|-0.9896%|-3.2124%|7.539 pp|EXPOSURE_NOT_MATCHED|-1.2993%|-1.9450 pp|
|FINAL_HOLDOUT|V101_VOL_MOMENTUM_V1|2.0|-1.1603%|-3.4091%|7.551 pp|EXPOSURE_NOT_MATCHED|-1.2993%|-1.9444 pp|
|FINAL_HOLDOUT|V101_REGIME_VOL_V1|1.0|-0.9896%|-3.2124%|7.539 pp|EXPOSURE_NOT_MATCHED|-1.2993%|-1.9450 pp|
|FINAL_HOLDOUT|V101_REGIME_VOL_V1|2.0|-1.1603%|-3.4091%|7.551 pp|EXPOSURE_NOT_MATCHED|-1.2993%|-1.9444 pp|
|FINAL_HOLDOUT|V101_REGIME_VOL_BAND_V1|1.0|-0.8880%|-3.2124%|10.442 pp|EXPOSURE_NOT_MATCHED|-1.2993%|-1.7852 pp|
|FINAL_HOLDOUT|V101_REGIME_VOL_BAND_V1|2.0|-1.0454%|-3.4091%|10.458 pp|EXPOSURE_NOT_MATCHED|-1.2993%|-1.7845 pp|

*Cash opportunity gap is the compounded TWSE index path minus an index-return path scaled by PREVIOUS-close observed exposure. It is a non-tradable attribution control with no index fills or executable index costs, NOT an equal-cost traded comparison. Positive gap means foregone index upside; negative means avoided index downside. Cash control assumes zero interest. Stock net returns and executable paired controls include unchanged calibration-free 1x/2x commission/slippage stress and statutory tax.

## Archival and gate

The original artifact is now preserved locally in a content-addressed, digest-verified private archive. Replays verify SHA-256 continuity and reject changed bytes. No remote archival destination has been authorized and no raw file was published. Existing CI continues to require the original artifact; expiration fails closed rather than selecting a newer run.

Remaining blockers: verified point-in-time corporate-action/payment/delisting evidence; sufficiently active realized-exposure matches; genuine independent 60-session forward observation after data gates pass. Historical backfill never counts as forward.


## Reproduce and validate

The source body and capture receipt are private inputs, not checked into Git. The receipt contains the exact official URL, UTC retrieval timestamp and SHA-256; the parser does not treat retrieval as historical publication time. Preserve the original raw bytes for digest verification.

```powershell
python -m automation.v101.review_run --cache local-v101-cache --original-root v10-original-readonly --original-zip v10-forward.zip --previous-comparison v101_research_run_001/comparison.json --snapshot v101_review_inputs/TWT49U.json --snapshot-source v101_review_inputs/TWT49U.source.json --output v101_review_evidence_new --archive v101_private_archive
python scripts/check_v101.py
```

Local full regression: **413 tests passed** (267 main including 16 new review tests; 146 V92). Tests cover source/schema/digest rejection, publication/as-of timestamps including Taiwan time, signed rights-reference values, ex-date holding eligibility, receivable/payment separation, stock delivery, split fractions, rights elections, delisting retirement, action replay conflicts, private archive continuity, lagged attribution and exposure-match rejection. Existing CI discovers these tests and rechecks the immutable 18-account baseline. No website or production workflow source was changed in this follow-up.

The operational adapter is intentionally **partial**: official reference-event parsing and entitlement accounting primitives are implemented and tested, but missing primary announcement/payment/settlement evidence is not admitted or certified. The existing forward entry point remains blocked. This follow-up does not satisfy the full corporate-action/forward acceptance requirement or justify merging the Draft PR.
