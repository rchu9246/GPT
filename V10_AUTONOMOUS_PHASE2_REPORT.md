# V10 Autonomous Phase 2 Report

## Acceptance summary

Phase 2 architecture and research integrity pass. No configuration passed the pre-holdout development gate, so no strategy was selected, the final holdout remained untouched, and no paper strategy or daily pipeline was activated.

## Universe methodology

The research source is the official Taiwan Stock Exchange `MI_INDEX` daily complete security table:

- Endpoint: `https://www.twse.com.tw/exchangeReport/MI_INDEX`
- Requested span: 2023-10-04 through 2026-10-02
- Valid trading days: 727
- Valid four-digit TWSE listed-equity observations: 754900
- Distinct symbols observed: 1100
- Source fingerprint: `00db3524caadeebabd045ee15028225484ec5fff3bc7f4c3b7f2b836e068afbb`

Each research date starts from four-digit TWSE listed-equity observations with a valid actual TWSE observation on that date. Eligibility requires 60 historical observations, a valid price of at least NT$5, and trailing 20-observation median turnover of at least NT$50,000,000. Monthly research snapshots contained 327 to 498 eligible symbols, with median 397. The preceding 60 trading sessions are lookback warm-up and are excluded from every performance window.

Raw daily responses are cached outside the repository. Each parsed observation retains the response hash and official provider identity. The committed research artifact contains the aggregate source fingerprint and complete result matrix.

## Point-in-time and survivorship assessment

Membership is reconstructed independently from each historical day's complete TWSE table. Securities that later delisted remain present on dates when they actually traded. Current constituents are never projected backward. Missing, suspended, halted, invalid, or non-trading observations are excluded for that date and never forward-filled into a tradable bar.

`SURVIVORSHIP_BIAS_LIMITATION=NO` for the defined TWSE observed-tradable universe. The scope excludes TPEx and securities without an actual TWSE daily observation; this is a declared market-scope limitation.

## Factor definitions

Factor version: `V10_OHLCV_FACTORS_V1`.

- **TREND:** close relative to trailing 20-observation mean.
- **MOMENTUM:** trailing 60-observation return.
- **RELATIVE_STRENGTH:** trailing 20-observation return, ranked across that day's eligible universe.
- **VOLUME_LIQUIDITY:** trailing 20-observation median traded value.
- **VOLATILITY_RISK:** negative trailing 20-observation return volatility.
- **BREAKOUT:** close relative to the prior 59-observation maximum.

Each factor is ranked cross-sectionally to `[0, 1]`; ties resolve deterministically by symbol. Only observations at or before the signal date are used. No next open, future close, future volume, or future membership enters ranking.

## Pre-registered hypotheses and multiple-testing control

Three hypotheses were fixed before research:

1. `H1_EQUAL_FACTOR`: equal factor weights.
2. `H2_TREND_MOMENTUM`: trend and momentum weights doubled.
3. `H3_RISK_ADJUSTED`: low-volatility weight tripled.

Each was evaluated with Top 5, Top 10, and Top 20 equal-weight portfolios and weekly/monthly rebalancing: 3 hypotheses, 18 configurations total. No configurations were added after results were seen.

## Portfolio, execution, and risk

Portfolios are long-only with 90% target exposure, at least 10% cash, and maximum 20% per position. Ranking occurs on close D; target changes execute at the next actual tradable open. Missing observations remain pending until an actual bar. Sells execute before buys. The engine prohibits short positions, margin, leverage, same-close execution, synthetic fills, and zero-price execution.

Daily reconciliation proves `cash + market value = equity`. State is derived from fills without cash resets, duplicate fills, position double counting, or PnL overwrites.

## Cost model

Cost version: `TWSE_NET_V1`.

- Baseline buy commission: 0.001425.
- Baseline sell commission: 0.001425.
- Baseline sell transaction tax: 0.003.
- Baseline slippage: 0.
- Stress: doubled commissions and tax plus 0.001 adverse slippage per side.

Every development configuration was evaluated under baseline and stress costs.

## Temporal design and holdout policy

- Train: 2023-12-29 through 2025-08-26.
- Validation: 2025-08-27 through 2026-03-19.
- Untouched final holdout: 2026-03-20 through 2026-10-02.

Configuration selection required positive train and validation benchmark excess return, validation Sharpe above 0.5, maximum drawdown at or below 25%, and positive stressed validation return. No configuration passed because every configuration had negative train excess return. Therefore `selected_before_holdout=null`; the final holdout was not evaluated and could not influence selection.

## Benchmarks

The passive benchmark is the official TWSE capitalization-weighted index value contained in the same daily response. Cash is the second benchmark. No benchmark series was invented or substituted after results were observed.

## Complete development results

Percent values are net of the stated baseline costs unless marked stress.

| Configuration | Train return % | Train excess pp | Validation return % | Validation excess pp | Validation Sharpe | Validation max DD % | Stress validation return % | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| H1_EQUAL_FACTOR_TOP5_WEEKLY | -44.125794 | -79.675164 | 25.841813 | -11.555484 | 1.336664 | 15.815089 | 9.655308 | REJECTED |
| H1_EQUAL_FACTOR_TOP5_MONTHLY | 6.616036 | -28.933334 | 34.157129 | -3.240168 | 1.648029 | 14.328290 | 29.017885 | REJECTED |
| H1_EQUAL_FACTOR_TOP10_WEEKLY | -38.089451 | -73.638821 | 40.006936 | 2.609639 | 2.096943 | 10.783282 | 24.121473 | REJECTED |
| H1_EQUAL_FACTOR_TOP10_MONTHLY | -13.545815 | -49.095185 | 33.813243 | -3.584055 | 1.749917 | 15.472563 | 28.839561 | REJECTED |
| H1_EQUAL_FACTOR_TOP20_WEEKLY | -30.888194 | -66.437564 | 18.865494 | -18.531803 | 1.278966 | 11.676598 | 6.842809 | REJECTED |
| H1_EQUAL_FACTOR_TOP20_MONTHLY | -5.009293 | -40.558663 | 22.868931 | -14.528367 | 1.374539 | 11.067392 | 18.870059 | REJECTED |
| H2_TREND_MOMENTUM_TOP5_WEEKLY | -44.252328 | -79.801698 | 49.244462 | 11.847164 | 2.042692 | 18.459478 | 30.356496 | REJECTED |
| H2_TREND_MOMENTUM_TOP5_MONTHLY | -23.131789 | -58.681159 | 40.946371 | 3.549074 | 1.724928 | 18.532712 | 35.780812 | REJECTED |
| H2_TREND_MOMENTUM_TOP10_WEEKLY | -32.114570 | -67.663940 | 34.718466 | -2.678831 | 1.727124 | 13.660530 | 19.003224 | REJECTED |
| H2_TREND_MOMENTUM_TOP10_MONTHLY | -12.395993 | -47.945363 | 42.081306 | 4.684008 | 1.850994 | 15.551158 | 37.021694 | REJECTED |
| H2_TREND_MOMENTUM_TOP20_WEEKLY | -23.524732 | -59.074102 | 27.294078 | -10.103220 | 1.615580 | 13.057408 | 14.284061 | REJECTED |
| H2_TREND_MOMENTUM_TOP20_MONTHLY | 5.173019 | -30.376351 | 33.858540 | -3.538757 | 1.799426 | 13.132342 | 29.141243 | REJECTED |
| H3_RISK_ADJUSTED_TOP5_WEEKLY | -22.475755 | -58.025125 | 4.198907 | -33.198391 | 0.512675 | 9.403292 | -5.922328 | REJECTED |
| H3_RISK_ADJUSTED_TOP5_MONTHLY | -0.348479 | -35.897849 | -0.890274 | -38.287572 | -0.008134 | 9.978342 | -3.991522 | REJECTED |
| H3_RISK_ADJUSTED_TOP10_WEEKLY | -19.341186 | -54.890556 | -2.764798 | -40.162096 | -0.256550 | 7.445881 | -11.113762 | REJECTED |
| H3_RISK_ADJUSTED_TOP10_MONTHLY | -8.399107 | -43.948477 | -1.211602 | -38.608899 | -0.065009 | 7.184226 | -4.454385 | REJECTED |
| H3_RISK_ADJUSTED_TOP20_WEEKLY | -4.011409 | -39.560779 | -6.619079 | -44.016377 | -1.567512 | 8.917655 | -22.724433 | REJECTED |
| H3_RISK_ADJUSTED_TOP20_MONTHLY | 2.355342 | -33.194028 | -0.060699 | -37.457996 | 0.070968 | 8.032387 | -3.220296 | REJECTED |

## Walk-forward, robustness, and overfit assessment

The chronological train/validation comparison is materially unstable: trend/momentum configurations were strongly negative and far behind the benchmark in train, then strongly positive in validation. This regime dependence fails cross-period robustness and parameter stability. `OVERFIT_WARNING=YES`.

The prior sealed Step 8 moving-average family remains rejected for lacking benchmark-relative robust alpha. It was not modified or retested to obtain a different conclusion.

## Final holdout results

Not available by design. No configuration cleared the train/validation gate, so opening the final holdout would provide no legitimate promotion evidence.

- Final OOS net return: N/A.
- Final OOS excess return: N/A.
- Final OOS Sharpe: N/A.
- Final OOS maximum drawdown: N/A.

## Rejected strategies

- Sealed Step 8 MA crossover family: rejected, insufficient benchmark-relative robustness.
- All 18 Phase 2 multi-factor configurations: rejected, negative train benchmark excess return and cross-period instability.

## Promoted strategy

None. `PROMOTED_PAPER_STRATEGIES` remains empty. There is no `PromotedPaperStrategy`, promotion timestamp, or runtime-mutable parameter package.

## Paper pipeline architecture

The sealed manual composition root remains fail closed. With no promoted strategy it raises before universe selection or ledger mutation. No fill, broker order, schedule, production write, or V9 financial-state read occurs.

## Reporting and isolation

V10 reporting remains separate and is labeled `PAPER TRADING` and `NOT LIVE PERFORMANCE`. No V9 dashboard table, legacy workflow, Supabase production table, or existing schedule was modified.

## Tests

- Full V10 deterministic suite: 184/184 passed.
- Dedicated regression suite: 23/23 passed.
- Research artifact checks cover all 18 configurations, point-in-time membership, official lineage, cost stress, accounting reconciliation, untouched holdout, and fail-closed promotion.

## Manual operation instructions

There is no authorized manual paper run. The manual command intentionally fails closed because no strategy passed promotion. A future strategy may be added only by a new independently reviewed research artifact that passes the unchanged gate; this report must not be rewritten retroactively.

## Known limitations

- Research covers four-digit TWSE listed-equity observations, not TPEx or foreign markets.
- An absent daily row is treated as non-tradable and excluded; detailed historical halt reason classification is not provided by this table.
- Factor research is limited to OHLCV-derived signals and 18 pre-registered configurations.
- Market regimes differ sharply between train and validation.

## Final gate

Architecture and research integrity pass. Strategy promotion and daily pipeline readiness remain unavailable, which is a valid no-winner outcome.
