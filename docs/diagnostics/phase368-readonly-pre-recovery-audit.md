# Phase 3.6.8 — read-only pre-recovery evidence audit

Status as of 2026-11-13: **INSUFFICIENT_EVIDENCE** for current database state. Historical Phase 3.6.7 supervision was SUSPENDED and safety-revoked; Phase 3.6.8 returned PRECHECK_BLOCKED. Historical producer run 43272218054 / attempt 1 is **not eligible** because canonical sizing authority is absent. Do not use these historical rows to infer current database status.

## Grounded code and schema mapping

The repository's Phase 3.6.7 engine reads latest rows for the portfolio from:
- supervision: `paper_runtime_supervision_state_v92` (`supervision_date`, persisted by Phase 3.6.7)
- activation: `paper_autonomous_activation_state_v92` (`activation_date`)
- qualification: `paper_continuous_qualification_v92` (`qualification_date`)
- readiness: `paper_operational_readiness_v92` (`readiness_date`)
- health: `paper_system_health_v92` (`health_date`)
- SLA: `paper_observability_daily_v92` (`observation_date`)
- master: `paper_master_cycles_v92` (`cycle_date`)
- incident: `paper_incident_audit_v92` (`incident_date`)

Sources: `automation/v92/paper_trading_phase367_production_paper_autonomous_runtime_supervision_safety_revocation_engine.py` and `automation/v92/paper_trading_phase368_production_paper_daily_autonomous_operations_controller.py`. These are source-code contracts, not proof that current database schema or rows exist.

## Minimum operator export

Provide a **redacted, non-secret, read-only** JSON object with `portfolio_id=V92_PRODUCTION_PAPER_V91`, `strategy_version=V9.1`, `business_date=YYYY-MM-DD`, plus exactly one independently verified row under each of the eight source keys above. Each row needs `portfolio_id`, `strategy_version`, its source-specific date column, an ISO8601 timezone-aware `updated_at` or `created_at`, relevant state flags, `reason_codes` and an explicit `critical_failures` list for supervision (empty list if none), and evidence provenance/hashes where available. Any critical failure or `CRITICAL_` supervision reason blocks review, and an absent `critical_failures` list is insufficient evidence. Include producer `run_id`, `attempt`, business date, portfolio/strategy, artifact SHA256 and *independently validated* canonical sizing authority. Include a separately documented, scoped recovery approval if issued (operator, code SHA, date window and stop conditions). Do not include API tokens, credentials, account numbers or sensitive raw trading records.

**Important:** the JSON auditor only checks structural/state assertions; it does not independently prove hashes, producer authority, database authenticity or human approval. A field that says `canonical_sizing_authority: true` is not sufficient for real recovery without separate source validation. A result of READY means *eligible for human review only*, not authorization to execute.

Run locally without network, credentials or writes:

```sh
python automation/v92/phase368_readonly_snapshot_audit.py /path/to/redacted-snapshot.json --business-date YYYY-MM-DD
python -m unittest tests.v92.test_phase368_readonly_snapshot_audit
```

Outcomes: BLOCKED when explicit unsafe, stale, revoked or scope-inconsistent evidence exists; INSUFFICIENT_EVIDENCE when records, authority or approval are missing; READY only for a fully populated, apparently consistent export, still requiring independent authenticity verification and explicit human approval before any runtime action.

**Safety boundary:** This PR does not query Supabase, run Phase 3.6.8, dispatch producer, change schedules, modify any database row, clear revocation, or merge to main. Production remains STOPPED.
