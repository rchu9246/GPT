-- GPT Quant V9.1 Paper Trading 404 Fix v2
-- Duplicate-ID Guard + Session Schema Fix
-- Generated from CURRENT Paper Trading upsert payload.
-- Safe to run repeatedly.
-- No synthetic session rows are inserted.

begin;

create table if not exists public.gpt_quant_v91_paper_sessions (
  "broker_submission_enabled" boolean,
  "created_at" timestamptz,
  "ending_equity" numeric,
  "engine_version" text,
  "gross_exposure" numeric,
  "id" text,
  "live_trading_enabled" boolean,
  "open_positions" integer,
  "paper_only" boolean,
  "realized_pnl" numeric,
  "session_date" date not null,
  "session_status" text,
  "starting_equity" numeric,
  "unrealized_pnl" numeric,
  "updated_at" timestamptz
);

alter table public.gpt_quant_v91_paper_sessions add column if not exists "broker_submission_enabled" boolean;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "created_at" timestamptz;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "ending_equity" numeric;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "engine_version" text;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "gross_exposure" numeric;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "id" text;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "live_trading_enabled" boolean;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "open_positions" integer;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "paper_only" boolean;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "realized_pnl" numeric;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "session_date" date;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "session_status" text;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "starting_equity" numeric;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "unrealized_pnl" numeric;
alter table public.gpt_quant_v91_paper_sessions add column if not exists "updated_at" timestamptz;

create unique index if not exists gpt_quant_v91_paper_sessions_session_date_uidx
on public.gpt_quant_v91_paper_sessions("session_date");

alter table public.gpt_quant_v91_paper_sessions enable row level security;

-- GitHub Actions uses service_role and bypasses RLS.
-- No anonymous write policy is created.

notify pgrst, 'reload schema';

commit;

select
  'GPT Quant V9.1 paper trading 404 fix v2 installed' as result,
  to_regclass('public.gpt_quant_v91_paper_sessions') is not null as table_exists,
  'session_date' as conflict_key,
  true as payload_contains_id;
