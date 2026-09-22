-- Forward-only provenance for completion-bound Phase 3.6.8 -> 3.6.9.
-- Legacy NULL provenance is deliberately retained and fails comparison in code.
-- Apply before enabling the workflows; never backfill or rewrite old evidence.
begin;

alter table public.paper_daily_autonomous_controller_v92
    add column if not exists producer_run_id text,
    add column if not exists producer_run_attempt integer,
    add column if not exists canonical_authority_hash text,
    add column if not exists controller_input_sha256 text,
    add column if not exists source_evidence_sha256 text,
    add column if not exists source_supervision_evidence_sha256 text,
    add column if not exists source_master_evidence_sha256 text;

alter table public.paper_daily_autonomous_controller_audit_v92
    add column if not exists producer_run_id text,
    add column if not exists producer_run_attempt integer,
    add column if not exists canonical_authority_hash text,
    add column if not exists controller_input_sha256 text,
    add column if not exists source_evidence_sha256 text,
    add column if not exists source_supervision_evidence_sha256 text,
    add column if not exists source_master_evidence_sha256 text;

alter table public.paper_daily_lifecycle_evidence_v92
    add column if not exists producer_run_id text,
    add column if not exists producer_run_attempt integer,
    add column if not exists canonical_authority_hash text,
    add column if not exists controller_run_id text,
    add column if not exists controller_run_attempt integer;

alter table public.paper_daily_lifecycle_evidence_audit_v92
    add column if not exists producer_run_id text,
    add column if not exists producer_run_attempt integer,
    add column if not exists canonical_authority_hash text,
    add column if not exists controller_run_id text,
    add column if not exists controller_run_attempt integer;

notify pgrst, 'reload schema';
commit;
