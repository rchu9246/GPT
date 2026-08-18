-- GPT Quant V9.1 Paper Trading 404 Fix v3
-- Positions Schema Fix
-- Target: public.gpt_quant_v91_paper_positions
-- Generated from CURRENT Paper Trading position upsert payload.
-- Safe to run repeatedly.
-- No synthetic position rows are inserted.

begin;

create table if not exists public.gpt_quant_v91_paper_positions (
  "broker_submission_enabled" boolean,
  "created_at" timestamptz,
  "engine_version" text,
  "filled_weight" numeric,
  "id" text,
  "live_trading_enabled" boolean,
  "paper_only" boolean,
  "position_date" date not null,
  "position_status" text,
  "ranking_id" text not null,
  "session_id" text,
  "target_weight" numeric,
  "unrealized_pnl" numeric,
  "updated_at" timestamptz
);

alter table public.gpt_quant_v91_paper_positions add column if not exists "broker_submission_enabled" boolean;
alter table public.gpt_quant_v91_paper_positions add column if not exists "created_at" timestamptz;
alter table public.gpt_quant_v91_paper_positions add column if not exists "engine_version" text;
alter table public.gpt_quant_v91_paper_positions add column if not exists "filled_weight" numeric;
alter table public.gpt_quant_v91_paper_positions add column if not exists "id" text;
alter table public.gpt_quant_v91_paper_positions add column if not exists "live_trading_enabled" boolean;
alter table public.gpt_quant_v91_paper_positions add column if not exists "paper_only" boolean;
alter table public.gpt_quant_v91_paper_positions add column if not exists "position_date" date;
alter table public.gpt_quant_v91_paper_positions add column if not exists "position_status" text;
alter table public.gpt_quant_v91_paper_positions add column if not exists "ranking_id" text;
alter table public.gpt_quant_v91_paper_positions add column if not exists "session_id" text;
alter table public.gpt_quant_v91_paper_positions add column if not exists "target_weight" numeric;
alter table public.gpt_quant_v91_paper_positions add column if not exists "unrealized_pnl" numeric;
alter table public.gpt_quant_v91_paper_positions add column if not exists "updated_at" timestamptz;

create unique index if not exists gpt_quant_v91_paper_positions_position_date_ranking_id_uidx
on public.gpt_quant_v91_paper_positions("position_date", "ranking_id");

alter table public.gpt_quant_v91_paper_positions enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 paper trading 404 fix v3 installed' as result,
  to_regclass('public.gpt_quant_v91_paper_positions') is not null as table_exists,
  'position_date,ranking_id' as conflict_key,
  true as payload_contains_id;
