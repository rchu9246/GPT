-- GPT Quant V9.1 Adaptive Risk 400 Fix v4
-- Exact payload/schema alignment generated from CURRENT Python.
-- No synthetic rows inserted.
-- Safe to run repeatedly.

begin;

create table if not exists public.gpt_quant_v91_adaptive_risk_state (
  id bigserial primary key,
  "adaptive_risk_budget" numeric,
  "base_risk_budget" numeric,
  "broker_submission_enabled" boolean,
  "calculated_at" timestamptz,
  "daily_pnl" numeric,
  "drawdown_multiplier" numeric,
  "engine_version" text,
  "estimated_total_var" numeric,
  "kill_switch_active" text,
  "live_trading_enabled" boolean,
  "paper_only" boolean,
  "pnl_multiplier" numeric,
  "portfolio_drawdown" numeric,
  "risk_regime" text,
  "state_date" date not null,
  "var_multiplier" numeric
);

alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "adaptive_risk_budget" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "base_risk_budget" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "broker_submission_enabled" boolean;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "calculated_at" timestamptz;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "daily_pnl" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "drawdown_multiplier" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "engine_version" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "estimated_total_var" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "kill_switch_active" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "live_trading_enabled" boolean;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "paper_only" boolean;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "pnl_multiplier" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "portfolio_drawdown" numeric;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "risk_regime" text;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "state_date" date;
alter table public.gpt_quant_v91_adaptive_risk_state add column if not exists "var_multiplier" numeric;

-- Align existing column types with the actual Python payload.
alter table public.gpt_quant_v91_adaptive_risk_state alter column "adaptive_risk_budget" type numeric using nullif("adaptive_risk_budget"::text, '')::numeric;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "base_risk_budget" type numeric using nullif("base_risk_budget"::text, '')::numeric;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "broker_submission_enabled" type boolean using case when lower("broker_submission_enabled"::text) in ('true','t','1','yes') then true when lower("broker_submission_enabled"::text) in ('false','f','0','no') then false else null end;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "calculated_at" type timestamptz using nullif("calculated_at"::text, '')::timestamptz;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "daily_pnl" type numeric using nullif("daily_pnl"::text, '')::numeric;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "drawdown_multiplier" type numeric using nullif("drawdown_multiplier"::text, '')::numeric;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "engine_version" type text using "engine_version"::text;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "estimated_total_var" type numeric using nullif("estimated_total_var"::text, '')::numeric;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "kill_switch_active" type text using "kill_switch_active"::text;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "live_trading_enabled" type boolean using case when lower("live_trading_enabled"::text) in ('true','t','1','yes') then true when lower("live_trading_enabled"::text) in ('false','f','0','no') then false else null end;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "paper_only" type boolean using case when lower("paper_only"::text) in ('true','t','1','yes') then true when lower("paper_only"::text) in ('false','f','0','no') then false else null end;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "pnl_multiplier" type numeric using nullif("pnl_multiplier"::text, '')::numeric;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "portfolio_drawdown" type numeric using nullif("portfolio_drawdown"::text, '')::numeric;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "risk_regime" type text using "risk_regime"::text;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "state_date" type date using nullif("state_date"::text, '')::date;
alter table public.gpt_quant_v91_adaptive_risk_state alter column "var_multiplier" type numeric using nullif("var_multiplier"::text, '')::numeric;

drop index if exists public.gpt_quant_v91_adaptive_risk_state_state_date_uidx;

create unique index gpt_quant_v91_adaptive_risk_state_state_date_uidx
on public.gpt_quant_v91_adaptive_risk_state("state_date");

alter table public.gpt_quant_v91_adaptive_risk_state enable row level security;

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 adaptive risk 400 fix v4 installed' as result,
  to_regclass('public.gpt_quant_v91_adaptive_risk_state') is not null as table_exists,
  'state_date' as conflict_key;
