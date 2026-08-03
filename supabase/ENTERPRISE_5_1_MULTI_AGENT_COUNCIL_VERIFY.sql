select *
from public.agent_registry_v51
order by execution_order, agent_key;

select *
from public.council_sessions_v51
order by started_at desc
limit 10;

select *
from public.agent_votes_v51
order by created_at desc
limit 100;

select *
from public.agent_explanations_v51
order by created_at desc
limit 100;

select *
from public.agent_conflicts_v51
order by created_at desc
limit 100;

select *
from public.decision_council_v51
order by decision_date desc
limit 10;

select *
from public.consensus_history_v51
order by created_at desc
limit 10;

select *
from public.council_status_v51
order by status_date desc
limit 10;

select *
from public.council_dashboard_v51
order by session_date desc
limit 10;
