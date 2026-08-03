select *
from public.evolution_status_v56
order by status_date desc
limit 5;

select *
from public.evolution_metrics_v56
order by metric_date desc
limit 5;

select count(*) as portfolio_versions
from public.portfolio_versions_v56;

select count(*) as simulation_runs
from public.simulation_runs_v56;

select count(*) as simulation_results
from public.simulation_results_v56;

select count(*) as stress_tests
from public.stress_tests_v56;

select count(*) as monte_carlo_results
from public.monte_carlo_results_v56;

select count(*) as evolution_scores
from public.evolution_scores_v56;

select count(*) as portfolio_rankings
from public.portfolio_rankings_v56;

select *
from public.evolution_dashboard_v56
order by version_date desc
limit 100;
