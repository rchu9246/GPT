# GPTQ V9.2 forward-only accounting contract

This change is review-only. `GPTQ_P0_ACCOUNTING_ENABLED` defaults to `false`.
The SQL file is not applied by this branch, and no historical `gptq` row is
rewritten or backfilled. `paper_*_v92` remains outside this lineage.

## Identity and ownership

`strategy_version` is the only stable account identity in the existing `gptq`
schema. The foundation supports one shadow-paper account per strategy version.
`business_date` and `accounting_state_version` identify a forward state.
The SQL RPC is the sole financial-state publisher after activation. Trading
phases submit BUY and SELL events through the atomic order RPC. Phase 2.6
submits MARK_TO_MARKET, validates cash, market value, equity and unrealized
P&L, then finalizes. Its SQL finalizer alone writes the compatibility equity
snapshot. The daily snapshot trigger requires agreement with finalized state.

## Initialization and trust boundary

After migration review and application, an operator must call
`gptq_paper_accounting_initialize_v1` exactly once with the chosen first
business date, reconciled opening cash, market value, unrealized P&L, stable
initialization event key, canonical content hash, state hash, and optional run
identity. The contract does not infer opening cash from old snapshots or
assume that one million is still the correct balance. Activation without an
initialized lineage fails closed. Once initialized, the previous business
date must be finalized before another date can begin.

`UNTRUSTED_BEFORE_DATE` is deliberately unset. Set it only after the migration
is applied, the owner is enabled, and the first clean accounting cycle passes
validation. Earlier dashboard performance remains untrusted. There is no
historical repair in this change.

## Arithmetic and replay

Cash follows prior closing cash plus net SELL proceeds minus BUY notional and
commission plus explicit authorized adjustments. SELL trade P&L is net
proceeds minus persisted cost basis. Daily and cumulative realized P&L are
separate state fields. A no-exit mark never changes either. Equity equals
closing cash plus market value to a one-cent tolerance. Events retain BUY
commission, SELL commission, transaction tax, slippage and cost basis.
Existing fee-rate environment variables and their defaults remain in use.

The stable event key is strategy/date/side/stock for each order and
strategy/date/MARK_TO_MARKET for the daily mark. Same-key identical content
returns the committed event without another cash effect. Same-key different
content fails closed. This implies at most one same-side order per stock and
day; an attempted second order fails closed until an explicit identity
extension is reviewed. If an order commits but its position mutation fails,
the next Phase 2.3 run stops for reconciliation instead of treating the
position as recovered. This is a known operational limitation.

## Schedule review

Existing schedules overlap: Phase 2.3 runs at 06:20 UTC; Phase 2 and 2.4 at
06:25; Phase 2.5 at 06:30; Phase 2.6 at 06:35; and Phase 2.7 reruns Phase 2.6
at 06:40 on weekdays. Phase 2.5 reruns Phase 2.3 and 2.4; Phase 2.6 invokes
Phase 2.5. This PR makes duplicate accounting events idempotent and financial
publication single-owner, but it does not change cron schedules. Before
activation, review concurrent order decisions, position reconciliation, and
the exact run ordering in a nonproduction setting. Leave the flag disabled
until that review is complete.

No broker calls, real-money execution, qualification change, or Phase 3
accounting change is part of this foundation.
