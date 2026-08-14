-- GPT Quant V9.1 Adaptive Risk 404 Fix v3
-- Target: public.gpt_quant_v91_adaptive_risk_state
-- Generated from CURRENT Adaptive Risk upsert payload.
-- Safe to run repeatedly.
-- No synthetic rows are inserted.

begin;

create table if not exists public.gpt_quant_v91_adaptive_risk_state (
  id bigserial primary key,
  "adaptive_risk_budget" numeric,
  "base_risk_budget" numeric,
  "broker_submission_enabled" boolean,
  "calculated_at" timestamptz,
  "daily_pnl" text,
  "drawdown_multiplier" numeric,
  "engine_version" text,
  "estimated_total_var" text,
  "kill_switch_active" text,
  "live_trading_enabled" boolean,
  "paper_only" text,
  "pnl_multiplier" numeric,
  "portfolio_drawdown" numeric,
  "risk_regime" numeric,
  "state_date" date not null,
  "var_multiplier" numeric
);

alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "adaptive_risk_budget" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "base_risk_budget" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "broker_submission_enabled" boolean;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "calculated_at" timestamptz;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "daily_pnl" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "drawdown_multiplier" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "engine_version" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "estimated_total_var" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "kill_switch_active" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "live_trading_enabled" boolean;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "paper_only" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "pnl_multiplier" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "portfolio_drawdown" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "risk_regime" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "state_date" date;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "var_multiplier" numeric;

create unique index if not exists gpt_quant_v91_adaptive_risk_state_state_date_uidx
on public.gpt_quant_v91_adaptive_risk_state("state_date");

alter table public.gpt_quant_v91_adaptive_risk_state enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 404 fix v3 installed' as result,
  to_regclass('public.gpt_quant_v91_adaptive_risk_state') is not null as table_exists,
  'state_date' as conflict_key;
