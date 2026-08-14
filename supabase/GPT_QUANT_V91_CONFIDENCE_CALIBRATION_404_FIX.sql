-- GPT Quant V9.1 Confidence Calibration 404 Fix
-- Generated from the CURRENT Python upsert payload.
-- Safe to run repeatedly.

begin;

create table if not exists public.gpt_quant_v91_confidence_calibration (
  id bigserial primary key,
  "calculated_at" timestamptz,
  "calibrated_confidence" numeric,
  "consistency_penalty" text,
  "engine_version" text,
  "final_confidence" numeric,
  "governed_recommendation" text,
  "historical_percentile" text,
  "ranking_id" text not null,
  "raw_confidence" numeric,
  "z_score" numeric
);

-- Add any payload columns that may be absent on an older partial table.
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "calculated_at" timestamptz;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "calibrated_confidence" numeric;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "consistency_penalty" text;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "engine_version" text;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "final_confidence" numeric;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "governed_recommendation" text;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "historical_percentile" text;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "ranking_id" text;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "raw_confidence" numeric;
alter table public.gpt_quant_v91_confidence_calibration add column if not exists "z_score" numeric;

create unique index if not exists gpt_quant_v91_confidence_calibration_ranking_id_uidx
on public.gpt_quant_v91_confidence_calibration(ranking_id);

alter table public.gpt_quant_v91_confidence_calibration enable row level security;

-- Service-role GitHub Actions bypasses RLS.
-- Read-only dashboard access may be enabled separately if needed.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 confidence calibration 404 fix installed' as result,
  to_regclass('public.gpt_quant_v91_confidence_calibration') is not null as table_exists;
