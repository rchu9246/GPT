-- GPT Quant V9.1 Portfolio Optimizer 404 Fix v1
-- Target: public.gpt_quant_v91_portfolio_allocations
-- Generated from CURRENT Portfolio Optimizer upsert payload.
-- Safe to run repeatedly.
-- No synthetic allocation rows are inserted.

begin;

create table if not exists public.gpt_quant_v91_portfolio_allocations (
  id bigserial primary key,
  "allocation_date" date not null,
  "broker_submission_enabled" boolean,
  "calculated_at" timestamptz,
  "engine_version" text,
  "final_confidence" numeric,
  "governed_recommendation" text,
  "live_trading_enabled" boolean,
  "optimized_weight" numeric,
  "paper_only" text,
  "ranking_id" text not null,
  "raw_weight" numeric,
  "risk_budget" numeric
);

alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "allocation_date" date;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "broker_submission_enabled" boolean;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "calculated_at" timestamptz;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "engine_version" text;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "final_confidence" numeric;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "governed_recommendation" text;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "live_trading_enabled" boolean;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "optimized_weight" numeric;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "paper_only" text;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "ranking_id" text;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "raw_weight" numeric;
alter table public.gpt_quant_v91_portfolio_allocations add column if not exists "risk_budget" numeric;

create unique index if not exists gpt_quant_v91_portfolio_allocations_allocation_date_ranking_id_uidx
on public.gpt_quant_v91_portfolio_allocations("allocation_date", "ranking_id");

alter table public.gpt_quant_v91_portfolio_allocations enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 portfolio optimizer 404 fix v1 installed' as result,
  to_regclass('public.gpt_quant_v91_portfolio_allocations') is not null as table_exists,
  'allocation_date,ranking_id' as conflict_key;
