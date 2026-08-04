create table if not exists public.gpt_quant_v9_position_sizing_results (
  id uuid primary key,
  sizing_date date not null,
  ranking_id uuid not null,
  source_version_no text not null,
  rank_no integer not null,
  evolution_score numeric,
  confidence_score numeric,
  recommendation text,
  selected_for_review boolean not null default false,
  max_single_weight numeric not null,
  total_risk_budget numeric not null,
  raw_score numeric not null,
  base_weight numeric not null,
  final_position_size numeric not null,
  sizing_status text not null,
  blockers jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  components jsonb not null default '{}'::jsonb,
  risk_metrics jsonb not null default '{}'::jsonb,
  paper_only boolean not null default true,
  live_trading_enabled boolean not null default false,
  broker_submission_enabled boolean not null default false,
  engine_version text not null,
  calculated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (sizing_date, ranking_id),
  constraint gpt_quant_v9_position_size_range_chk
    check (final_position_size >= 0 and final_position_size <= 0.25),
  constraint gpt_quant_v9_position_safety_chk
    check (
      paper_only = true
      and live_trading_enabled = false
      and broker_submission_enabled = false
    )
);

create index if not exists
  gpt_quant_v9_position_sizing_date_rank_idx
on public.gpt_quant_v9_position_sizing_results (
  sizing_date desc,
  rank_no asc
);

create index if not exists
  gpt_quant_v9_position_sizing_ranking_idx
on public.gpt_quant_v9_position_sizing_results (ranking_id);

alter table public.gpt_quant_v9_position_sizing_results
  enable row level security;

drop policy if exists
  "service role manages position sizing"
on public.gpt_quant_v9_position_sizing_results;

create policy
  "service role manages position sizing"
on public.gpt_quant_v9_position_sizing_results
for all
to service_role
using (true)
with check (true);
