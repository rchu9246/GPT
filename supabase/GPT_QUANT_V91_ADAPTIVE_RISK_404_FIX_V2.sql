-- GPT Quant V9.1 Adaptive Risk 404 Fix v2
-- Target: public.gpt_quant_v9_risk_portfolio_state
-- Generated from CURRENT adaptive-risk reader.
-- No synthetic portfolio-state rows are inserted.
-- Safe to run repeatedly.

begin;

create table if not exists public.gpt_quant_v9_risk_portfolio_state (
  id bigserial primary key,
  "risk_date" date,
  "state_date" date not null
);

alter table public.gpt_quant_v9_risk_portfolio_state add column if not exists "risk_date" date;
alter table public.gpt_quant_v9_risk_portfolio_state add column if not exists "state_date" date;

create index if not exists gpt_quant_v9_risk_portfolio_state_state_date_idx
on public.gpt_quant_v9_risk_portfolio_state(state_date desc);

alter table public.gpt_quant_v9_risk_portfolio_state enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 404 fix v2 installed' as result,
  to_regclass('public.gpt_quant_v9_risk_portfolio_state') is not null as table_exists;
