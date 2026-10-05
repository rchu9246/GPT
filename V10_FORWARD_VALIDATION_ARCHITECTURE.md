# V10 Forward Validation Architecture

## Status and safety

This subsystem accumulates forward-only evidence for fixed research configurations. It is labeled **FORWARD SHADOW PAPER** and **NOT LIVE TRADING**.

- `PAPER_ONLY=True`
- `BROKER_ORDER_SUBMISSION_ENABLED=False`
- `REAL_MONEY_TRADING_ENABLED=False`
- `PRODUCTION_EXECUTION_AVAILABLE=False`
- `HISTORICAL_REWRITE_ALLOWED=False`
- Long only; no margin, shorting, or leverage.

It neither imports nor reads V9 financial state. It does not use Supabase or any broker path.

## Data flow

`official TWSE daily table → complete-session check → point-in-time eligibility → six fixed factors → cross-sectional normalization → fixed registry ranking → risk decision → independent shadow target → next actual tradable open → append-only account ledger → daily manifest/report`

A run fails closed if the official daily table, benchmark, or minimum complete market population is unavailable. There are no synthetic prices, tradable forward fills, caller supplied prices, or same-close fills.

## Immutable forward boundary

The first successful run creates `forward_boundary.json` with `FORWARD_VALIDATION_START_DATE`. The file is write once. Runs earlier than the boundary are rejected. Historical Phase 2 research artifacts remain `HISTORICAL`; this store contains only `FORWARD_SHADOW` runs.

## Frozen strategy registry

The registry contains exactly the 18 Phase 2 configurations:

- `H1_EQUAL_FACTOR`, `H2_TREND_MOMENTUM`, `H3_RISK_ADJUSTED`
- Top 5, 10, and 20
- Weekly and monthly rebalance frequencies

Every immutable specification records strategy ID, factor version, weights, Top N, frequency, risk version, cost version, universe version, labels, and SHA-256 fingerprint. Registry fingerprint changes require a new strategy version and a new forward clock. All entries remain `RESEARCH_ONLY`, `UNPROMOTED`, and `SHADOW_PAPER`.

## Account isolation and execution

Each configuration maps to one deterministic account ID and one append-only hash-chained ledger, starting with NT$1,000,000. Cash, positions, fills, PnL, and costs are never shared.

A target generated from day D close is stored as a `TARGETS` event. It can execute only when a later session supplies an actual open for the symbol. A `TARGET_EXECUTED` event consumes the target. Missing bars remain pending. Same-day reruns return the immutable existing manifest and cannot duplicate fills or increment the forward-day counter.

## Benchmark alignment

Every run stores cash return and the official TWSE capitalization-weighted index from the same data date. The benchmark has its own append-only ledger and shares the exact forward boundary with all strategy accounts.

## Reporting contract

Each daily manifest records total, eligible, and excluded symbols; exclusion reasons; data freshness; all account IDs; candidates and factor scores; risk decisions; targets; execution state; positions; equity; cash; market value; daily and cumulative PnL; strategy and benchmark returns; excess return; realized and unrealized PnL; drawdown; exposure; turnover; and transaction costs.

## Evidence and qualification

- Days 1–19: `COLLECTING`
- Days 20–59: `INSUFFICIENT_EVIDENCE` and preliminary observation only
- Day 60 onward: eligibility may be evaluated against positive net and excess return, Sharpe above 0.5, fixed drawdown limit, acceptable cost stress, valid accounting and data, stability, concentration, and single-symbol dominance checks.
- A shadow status never changes the research promotion registry and never enables production.

## Operation

Manual command:

```powershell
python -m automation.v10.forward_daily_run --cache <external-cache> --store <forward-store>
```

The V10 workflow has only `workflow_dispatch`, defaults its explicit approval input to false, has read-only repository permissions, and has no cron. Enabling any schedule requires final user approval.

