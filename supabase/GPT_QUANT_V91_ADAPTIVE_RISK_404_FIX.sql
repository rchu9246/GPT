-- GPT Quant V9.1 Adaptive Risk 404 Fix
-- Generated from CURRENT adaptive-risk reader.
-- No synthetic/fake risk data is inserted.
-- Safe to run repeatedly.

begin;

create table if not exists public.gpt_quant_v9_risk_summaries (
  id bigserial primary key,
  "risk_date" date not null,
  "state_date" date
);

alter table public.gpt_quant_v9_risk_summaries add column if not exists "risk_date" date;
alter table public.gpt_quant_v9_risk_summaries add column if not exists "state_date" date;

create index if not exists gpt_quant_v9_risk_summaries_risk_date_idx
on public.gpt_quant_v9_risk_summaries(risk_date desc);

alter table public.gpt_quant_v9_risk_summaries enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anon write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 404 fix installed' as result,
  to_regclass('public.gpt_quant_v9_risk_summaries') is not null as table_exists;
