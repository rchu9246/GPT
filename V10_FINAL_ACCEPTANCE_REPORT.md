# V10 Final Acceptance Report

## Scope and safety

V10 is an isolated standard-library Python package under `automation/v10`. It does not import or modify V9, Supabase production code, Phase 3.x workflows, broker adapters, or existing schedules.

The immutable safety constitution requires paper-only, long-only operation with broker submission, real-money trading, production execution, margin, shorting, and historical rewrites disabled.

## Architecture

The dependency flow is:

`provider observations -> trusted market data -> point-in-time universe -> factors -> cross-sectional ranking -> strategy intent -> risk decision -> controlled paper execution -> append-only ledger -> replayed accounting -> analytics/reporting`

Each module has one owner:

- `halt_authority.py`: repository-controlled halt evidence.
- `market_data.py`: OHLCV validation, lineage, and actual tradable bars.
- `universe.py`: date-aware eligibility and survivorship limitation.
- `factors.py`: trend, momentum, relative strength, liquidity, low volatility, and breakout.
- `portfolio.py`: fixed Top 5/10/20 equal-weight research portfolios.
- `risk.py`: approve, reduce, or reject only.
- `execution.py`: next actual tradable open paper fills and versioned costs.
- `ledger.py`: hash-chained canonical events, idempotency, append-only persistence, and restart replay.
- `backtest.py`: portfolio equity, exposure, turnover, and performance metrics.
- `reporting.py`: explicitly paper-labeled reporting contract.
- `pipeline.py`: manual composition root that fails closed while no strategy is promoted.

## Halt trust boundary

`RepositoryHaltAuthority` reads one repository path whose complete bytes are pinned by SHA-256. Its constructor accepts no data, path, confirmation, token, evidence object, or callback. `TrustedMarketData` constructs the authority internally. Strategy callers can query only symbol and date and cannot provide trusted halt state.

Result: `V10_HALT_POLICY=PASS`, `V10_TRUST_BOUNDARIES=PASS`.

## Data lineage and point-in-time safety

Every tradable bar requires provider and provider observation identity. Synthetic bars, non-trading observations, invalid OHLCV, duplicates, and confirmed halted observations fail closed. History queries truncate at the requested date. Factors and cross-sectional normalization use only the snapshot universe and observations available at the research date. Execution occurs at the next actual tradable bar open.

Historical point-in-time constituent membership is not available in this repository. The universe engine therefore selects only from symbols with trusted observations already available at each research date and reports this survivorship-bias limitation. It does not claim that the limitation is absent.

## Research results

### Rejected strategies

The sealed Step 8 moving-average hypothesis remains rejected and unpromoted:

- OOS windows: 15
- Positive return windows: 80.0000%
- Benchmark-beating windows: 20.0000%
- Median return: 38.604329%
- Median excess return: -20.945139%
- Median Sharpe: 1.512317
- Median maximum drawdown: 19.121100%
- Profitable symbols: 100.0000%
- Benchmark-beating symbols: 0.0000%
- Robustness gate: FAIL

The deterministic multi-factor baseline is implemented as research infrastructure but is not promoted because the repository has no trustworthy historical point-in-time constituent dataset or corresponding OOS research artifact. Missing evidence fails closed.

### Promoted paper strategies

None. `PROMOTED_PAPER_STRATEGIES` is intentionally empty. The manual daily pipeline refuses to run, creates no fill, and has no broker adapter. Therefore `PAPER_STRATEGY_AVAILABLE=NO` and daily pipeline operation is N/A.

## Risk controls

- Long only, no margin, no shorting, no leverage.
- Maximum position weight, maximum portfolio exposure, cash reserve, liquidity, volatility, and drawdown guards.
- Risk can approve, reduce, or reject; it cannot originate signals or increase requested weight.
- Unpromoted strategies cannot reach controlled paper execution.

## Accounting guarantees

- Canonical append-only hash-chained events.
- Exact idempotent replay and conflicting replay rejection.
- Duplicate fill rejection.
- No snapshot-as-truth accounting.
- Deterministic restart replay and verified append-only suffix persistence.
- No cash reset or realized-PnL overwrite.
- Daily `cash + market value = equity` assertion.
- Tampering, sequence gaps, short positions, and missing marks fail closed.

## Benchmarks and analytics

The engine computes total return, CAGR, Sharpe, maximum drawdown, profit factor, turnover, and exposure. Buy-and-hold uses trusted market closes only; cash is the second benchmark. No index or ETF series is invented.

## Reporting contract

The paper report includes equity, cash, positions, daily PnL, realized and unrealized PnL, drawdown, orders, fills, signals, universe, ranked candidates, and risk decisions. Its label is always `PAPER TRADING`.

## Tests

- Full V10 suite: 161 deterministic tests passing.
- Required regression suite: 23 tests passing.
- Python compilation: passing.
- Git whitespace validation: passing.
- Legacy production files changed: none.

The test matrix covers caller trust bypass, invalid and synthetic observations, point-in-time truncation, factor determinism, risk boundaries, next-bar execution, accounting replay, persistence restart, tamper rejection, benchmark sourcing, reporting, and promotion fail-closed behavior.

## Manual paper operation

No manual paper strategy is currently authorized. `python -m automation.v10.manual_daily_run ...` intentionally fails closed until an independently reviewed future commit adds a strategy identifier to the repository-controlled promotion registry after complete OOS evidence passes.

## Remaining production blockers

- No strategy has passed promotion evidence.
- Historical point-in-time universe membership data is unavailable.
- No V10-specific schedule is enabled or included.
- No production broker authorization or adapter exists.
- Production execution remains unavailable by constitution.

## Final gate

| Gate | Result |
|---|---|
| V10 accounting | PASS |
| V10 market data | PASS |
| V10 halt policy | PASS |
| V10 trust boundaries | PASS |
| V10 persistence | PASS |
| V10 restart recovery | PASS |
| Universe engine | PASS |
| Multi-factor engine | PASS |
| Ranking engine | PASS |
| Risk engine | PASS |
| Portfolio engine | PASS |
| No lookahead | PASS |
| Point-in-time computation safety | PASS |
| Backtest engine | PASS |
| Walk-forward engine | PASS (sealed evidence retained) |
| Strategy research complete | PASS (no promotion) |
| Paper strategy available | NO |
| Daily paper pipeline | N/A, fail closed |
| Manual daily run | N/A, fail closed |
| Broker order created | NO |
| Real money trading | NO |
| Critical findings | NONE |
