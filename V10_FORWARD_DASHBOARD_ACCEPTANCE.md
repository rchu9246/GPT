# V10 Phase 3.1: Forward Shadow Paper Dashboard

The primary Pages entry redirects to `v10-forward/`. The existing V9 dashboard remains at `legacy-v9/`, with an explicit LEGACY V9 label. V10 performance is generated exclusively from the sealed forward store; its browser has no Supabase financial dependency.

## Evidence and first fills

- Frozen start: 2026-10-05. Registry fingerprint: `ceb2654fe2a70c5233976ba03c6356984a0c4ece14f6e01932a7ac6fb9decddd`.
- 2026-10-05 manifests and target events remain unchanged. All 18 frozen strategy specifications remain unchanged.
- 2026-10-06: 1,087 scanned, 389 eligible, 698 excluded; 2 completed forward trading days.
- The initial 210 target rows produced 210 paper fills across 18 isolated accounts, using each symbol's actual TWSE 2026-10-06 OPEN. No first-day close or synthetic fill price was used.
- Independently refetched 2026-10-06 official response matches the preserved market evidence exactly. Independently refetched 2026-10-05 OHLC and benchmark also match. The later official response includes revised volumes; the original signal-time evidence remains sealed rather than rewritten.
- Each daily account reconciles opening cash minus purchases and costs plus sales to ending cash. Replayed positions and same-date close marks reconcile cash plus market value to equity.
- Signal scores omitted by the sealed first-day manifest are shown as unavailable when they cannot be recovered from its preserved factor scores and frozen weights. New target events retain their exact signal scores. No missing prices or quantities are fabricated.

## Automation

The existing `V10 Forward Shadow Paper Validation` schedule remains `0 8 * * 1-5` (16:00 Asia/Taipei). Daily runs append evidence and produce a validated dashboard report. Successful completion triggers the Pages workflow, which restores compatible evidence and regenerates the public report automatically. The browser refreshes every five minutes and separately reads the latest public GitHub automation status.

The previous run failed because insignificant trailing whitespace was treated as a changed registry. JSON comparison now checks content without rewriting the original file. Blank JSONL lines no longer invalidate intact event hash chains. Restoration accepts old nested and new flat artifact layouts, verifies hash-chain prefixes, and keeps the richer compatible committed seed rather than resetting cash from a stale artifact. Conflicting evidence fails closed.

First fills retain target lineage, signal dates, observation IDs, and actual-open references. Per-symbol target completion prevents repeated partial fills. Skipped complete sessions must be processed in sequence. Qualification is evaluated after benchmark excess return is aligned, without changing any strategy or evidence gate.

## Validation

223 Python V10 tests and 12 JavaScript report/rendering tests pass. The 23 existing regression tests pass. Tests cover V9/V10 isolation, forward boundary, all strategies, candidates, pending/fill distinction, next-open evidence, duplicate fills, cash resets, account contamination, benchmark alignment, equity reconciliation, day gates, immutable provider revisions, and compatible artifact restoration.

Adversarial review: V9 PnL and pre-boundary curves are rejected; pending orders cannot carry execution dates or fill prices; duplicate fills and mismatched dates fail; rankings use only completed manifests; qualification claims before the required gate fail. Current status is COLLECTING, with 2/20 preliminary and 2/60 qualification days. Current profitability remains insufficient evidence.

PAPER_ONLY remains true. Broker submission, real-money trading, and production execution remain false. There are no live trade controls. Phase 4 is outside this change.
