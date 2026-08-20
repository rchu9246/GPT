begin;

-- Canonical source created by Phase 3.6.2:
--   public.paper_system_health_v92
--
-- Compatibility alias expected by older qualification readers:
--   public.paper_health_monitoring_v92

do $$
begin
    if to_regclass('public.paper_health_monitoring_v92') is null then
        execute $v$
            create view public.paper_health_monitoring_v92 as
            select
                health_id,
                portfolio_id,
                strategy_version,
                health_date,
                health_status,
                health_score,
                incident_required,
                autonomous_operation_status,
                recovery_state,
                master_final_state,
                market_data_status,
                latest_market_date,
                eligible_signals,
                sized_candidates,
                order_intents_created,
                simulated_fills_created,
                fills_settled,
                cash,
                market_value,
                nav,
                realized_pnl,
                unrealized_pnl,
                open_positions,
                checks_passed,
                checks_failed,
                check_details,
                synthetic_market_data,
                synthetic_signals,
                fake_prices_allowed,
                broker_api_used,
                broker_credentials_used,
                broker_order_submission_enabled,
                real_money_trading_enabled,
                live_money_release_authorized,
                fail_closed_policy,
                evidence_sha256,
                created_at,
                updated_at
            from public.paper_system_health_v92
        $v$;
    end if;
end
$$;

-- Canonical source created by Phase 3.6.3:
--   public.paper_observability_daily_v92
--
-- Compatibility alias expected by older qualification readers:
--   public.paper_observability_sla_v92

do $$
begin
    if to_regclass('public.paper_observability_sla_v92') is null then
        execute $v$
            create view public.paper_observability_sla_v92 as
            select
                observability_id,
                portfolio_id,
                strategy_version,
                observation_date as sla_date,
                observation_date,
                health_status,
                autonomous_operation_status,
                recovery_state,
                master_final_state,
                end_to_end_duration_seconds,
                stage_duration_seconds,
                success_rate_7d,
                recovery_rate_7d,
                incident_count_7d,
                successful_streak_days,
                sla_status,
                sla_score,
                sla_details,
                cash,
                market_value,
                nav,
                open_positions,
                synthetic_market_data,
                synthetic_signals,
                fake_prices_allowed,
                broker_api_used,
                broker_credentials_used,
                broker_order_submission_enabled,
                real_money_trading_enabled,
                live_money_release_authorized,
                fail_closed_policy,
                evidence_sha256,
                created_at,
                updated_at
            from public.paper_observability_daily_v92
        $v$;
    end if;
end
$$;

comment on view public.paper_health_monitoring_v92 is
'Phase 3.6.5.2 compatibility bridge to canonical public.paper_system_health_v92.';

comment on view public.paper_observability_sla_v92 is
'Phase 3.6.5.2 compatibility bridge to canonical public.paper_observability_daily_v92.';

commit;