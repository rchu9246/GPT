select *
from public.operating_state_v50
order by state_date desc
limit 5;

select *
from public.orchestrator_status_v50
order by status_date desc
limit 5;

select *
from public.workflow_history_v50
order by started_at desc
limit 10;

select *
from public.execution_context_v50
order by started_at desc
limit 10;

select *
from public.decision_timeline_v50
order by event_time desc
limit 100;

select *
from public.event_bus_v50
order by event_time desc
limit 100;

select *
from public.system_health_v50
order by health_time desc
limit 10;

select *
from public.operating_dashboard_v50
order by state_date desc
limit 5;
