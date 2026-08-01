-- GPT Quant Enterprise 4.3 Stable
-- AI Investment Committee, multi-agent voting, investment thesis,
-- explainable decisions, committee audit and knowledge capture.
-- PAPER ONLY. Safe to execute repeatedly.

begin;

create table if not exists public.investment_committee_sessions_v43 (
  id uuid primary key default gen_random_uuid(),
  session_date date not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  session_type text not null default 'DAILY',
  session_status text not null default 'OPEN',
  market_regime text not null default 'UNKNOWN',
  quorum_required integer not null default 4,
  quorum_reached integer not null default 0,
  chairman_decision text,
  chairman_confidence numeric,
  final_risk_status text,
  final_action text,
  summary text,
  blockers jsonb not null default '[]'::jsonb,
  live_trading_enabled boolean not null default false,
  opened_at timestamptz not null default now(),
  closed_at timestamptz
);

create unique index if not exists investment_committee_sessions_v43_uidx
on public.investment_committee_sessions_v43(session_date, portfolio_id, session_type);

create table if not exists public.committee_agents_v43 (
  id bigserial primary key,
  agent_key text not null unique,
  agent_name text not null,
  role_name text not null,
  voting_weight numeric not null default 1,
  veto_power boolean not null default false,
  enabled boolean not null default true,
  prompt_profile jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.committee_opinions_v43 (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.investment_committee_sessions_v43(id) on delete cascade,
  agent_id bigint not null references public.committee_agents_v43(id) on delete cascade,
  symbol text not null default 'PORTFOLIO',
  recommendation text not null,
  confidence numeric not null default 0,
  expected_return_pct numeric,
  downside_risk_pct numeric,
  proposed_weight_pct numeric,
  thesis_summary text not null,
  bull_case text not null,
  bear_case text not null,
  catalysts jsonb not null default '[]'::jsonb,
  risks jsonb not null default '[]'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists committee_opinions_v43_uidx
on public.committee_opinions_v43(session_id, agent_id, symbol);

create table if not exists public.committee_votes_v43 (
  id bigserial primary key,
  session_id uuid not null references public.investment_committee_sessions_v43(id) on delete cascade,
  agent_id bigint not null references public.committee_agents_v43(id) on delete cascade,
  symbol text not null default 'PORTFOLIO',
  vote text not null,
  confidence numeric not null default 0,
  weighted_vote numeric not null default 0,
  veto_exercised boolean not null default false,
  rationale text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists committee_votes_v43_uidx
on public.committee_votes_v43(session_id, agent_id, symbol);

create table if not exists public.investment_theses_v43 (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.investment_committee_sessions_v43(id) on delete cascade,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  symbol text not null default 'PORTFOLIO',
  thesis_date date not null,
  thesis_status text not null default 'ACTIVE',
  final_recommendation text not null,
  confidence numeric not null default 0,
  recommended_weight_pct numeric,
  expected_return_pct numeric,
  downside_risk_pct numeric,
  bull_case text not null,
  base_case text not null,
  bear_case text not null,
  catalysts jsonb not null default '[]'::jsonb,
  risks jsonb not null default '[]'::jsonb,
  invalidation_conditions jsonb not null default '[]'::jsonb,
  explanation text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists investment_theses_v43_uidx
on public.investment_theses_v43(session_id, symbol);

create table if not exists public.explainable_decisions_v43 (
  id uuid primary key default gen_random_uuid(),
  decision_date date not null,
  session_id uuid references public.investment_committee_sessions_v43(id) on delete set null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete cascade,
  symbol text not null default 'PORTFOLIO',
  requested_action text not null,
  final_action text not null,
  confidence numeric not null default 0,
  score_breakdown jsonb not null default '{}'::jsonb,
  supporting_reasons jsonb not null default '[]'::jsonb,
  opposing_reasons jsonb not null default '[]'::jsonb,
  risk_overrides jsonb not null default '[]'::jsonb,
  explanation text not null,
  approved_for_paper boolean not null default false,
  approved_for_live boolean not null default false,
  created_at timestamptz not null default now()
);

create unique index if not exists explainable_decisions_v43_uidx
on public.explainable_decisions_v43(decision_date, portfolio_id, symbol);

create table if not exists public.committee_audit_v43 (
  id bigserial primary key,
  event_time timestamptz not null default now(),
  session_id uuid references public.investment_committee_sessions_v43(id) on delete cascade,
  event_type text not null,
  actor_key text not null,
  entity_key text not null,
  before_state jsonb,
  after_state jsonb,
  rationale text,
  severity text not null default 'INFO',
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists committee_audit_v43_latest_idx
on public.committee_audit_v43(event_time desc, severity);

create table if not exists public.knowledge_records_v43 (
  id uuid primary key default gen_random_uuid(),
  record_date date not null,
  record_type text not null,
  source_entity_type text not null,
  source_entity_key text not null,
  portfolio_id uuid references public.enterprise_portfolios_v40(id) on delete set null,
  strategy_id uuid references public.enterprise_strategies_v40(id) on delete set null,
  title text not null,
  summary text not null,
  tags jsonb not null default '[]'::jsonb,
  facts jsonb not null default '{}'::jsonb,
  confidence numeric not null default 0,
  retention_status text not null default 'ACTIVE',
  created_at timestamptz not null default now()
);

create unique index if not exists knowledge_records_v43_uidx
on public.knowledge_records_v43(record_date, record_type, source_entity_type, source_entity_key);

create table if not exists public.committee_status_v43 (
  id bigserial primary key,
  status_date date not null unique,
  overall_status text not null,
  sessions_completed integer not null default 0,
  opinions_generated integer not null default 0,
  votes_cast integer not null default 0,
  theses_generated integer not null default 0,
  decisions_generated integer not null default 0,
  risk_vetoes integer not null default 0,
  live_trading_enabled boolean not null default false,
  blockers jsonb not null default '[]'::jsonb,
  summary text not null,
  created_at timestamptz not null default now()
);

insert into public.committee_agents_v43
  (agent_key, agent_name, role_name, voting_weight, veto_power, enabled)
values
  ('macro', 'Macro Economist', 'MACRO', 1.0, false, true),
  ('technical', 'Technical Analyst', 'TECHNICAL', 1.0, false, true),
  ('quant', 'Quant Analyst', 'QUANT', 1.2, false, true),
  ('risk', 'Chief Risk Officer', 'RISK', 1.3, true, true),
  ('portfolio', 'Portfolio Manager', 'PORTFOLIO', 1.1, false, true),
  ('chairman', 'Investment Committee Chairman', 'CHAIRMAN', 1.5, false, true)
on conflict (agent_key) do update
set
  agent_name = excluded.agent_name,
  role_name = excluded.role_name,
  voting_weight = excluded.voting_weight,
  veto_power = excluded.veto_power,
  enabled = excluded.enabled,
  updated_at = now();

alter table public.investment_committee_sessions_v43 enable row level security;
alter table public.committee_agents_v43 enable row level security;
alter table public.committee_opinions_v43 enable row level security;
alter table public.committee_votes_v43 enable row level security;
alter table public.investment_theses_v43 enable row level security;
alter table public.explainable_decisions_v43 enable row level security;
alter table public.committee_audit_v43 enable row level security;
alter table public.knowledge_records_v43 enable row level security;
alter table public.committee_status_v43 enable row level security;

drop policy if exists "enterprise43 read sessions" on public.investment_committee_sessions_v43;
drop policy if exists "enterprise43 read agents" on public.committee_agents_v43;
drop policy if exists "enterprise43 read opinions" on public.committee_opinions_v43;
drop policy if exists "enterprise43 read votes" on public.committee_votes_v43;
drop policy if exists "enterprise43 read theses" on public.investment_theses_v43;
drop policy if exists "enterprise43 read decisions" on public.explainable_decisions_v43;
drop policy if exists "enterprise43 read audit" on public.committee_audit_v43;
drop policy if exists "enterprise43 read knowledge" on public.knowledge_records_v43;
drop policy if exists "enterprise43 read status" on public.committee_status_v43;

create policy "enterprise43 read sessions" on public.investment_committee_sessions_v43 for select to anon, authenticated using (true);
create policy "enterprise43 read agents" on public.committee_agents_v43 for select to anon, authenticated using (true);
create policy "enterprise43 read opinions" on public.committee_opinions_v43 for select to anon, authenticated using (true);
create policy "enterprise43 read votes" on public.committee_votes_v43 for select to anon, authenticated using (true);
create policy "enterprise43 read theses" on public.investment_theses_v43 for select to anon, authenticated using (true);
create policy "enterprise43 read decisions" on public.explainable_decisions_v43 for select to anon, authenticated using (true);
create policy "enterprise43 read audit" on public.committee_audit_v43 for select to authenticated using (true);
create policy "enterprise43 read knowledge" on public.knowledge_records_v43 for select to anon, authenticated using (true);
create policy "enterprise43 read status" on public.committee_status_v43 for select to anon, authenticated using (true);

notify pgrst, 'reload schema';
commit;

select 'GPT Quant Enterprise 4.3 Stable setup complete' as result;
