from __future__ import annotations
import ast, inspect, json, shutil, unittest, uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from automation.v10.forward_validation import (
    LABELS, MINIMUM_QUALIFICATION_DAYS, REGISTRY_FINGERPRINT, SHADOW_STRATEGY_REGISTRY,
    ForwardMarketData, ForwardStore, ForwardValidationStatus, account_id,
    latest_complete_session, run_forward_day, validation_status,
)
from automation.v10.research import PROMOTED_PAPER_STRATEGIES

def fixture_days(count=62, symbols=520):
    days=[]
    start=date(2026,1,1)
    for offset in range(count):
        session=start+timedelta(days=offset)
        rows=[]
        for number in range(1000,1000+symbols):
            price=Decimal("50")+Decimal(number%50)+Decimal(offset)/Decimal("10")
            rows.append({"symbol":str(number),"open":str(price),"high":str(price+1),
                "low":str(price-1),"close":str(price+Decimal("0.5")),"volume":2000000,
                "observation_id":f"fixture:{session}:{number}"})
        days.append({"date":session.isoformat(),"bars":rows,
                     "benchmark":str(20000+offset),"source_sha256":f"{offset:064x}"})
    return days

class ForwardValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=Path(".tmp_forward_tests")/uuid.uuid4().hex
        self.store=ForwardStore(self.tmp/"forward")
        self.data=ForwardMarketData(fixture_days())
        self.first=date(2026,3,2)
        self.second=date(2026,3,3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_registry_contains_only_fixed_phase2_grid(self):
        self.assertEqual(18,len(SHADOW_STRATEGY_REGISTRY))
        self.assertEqual({"H1_EQUAL_FACTOR","H2_TREND_MOMENTUM","H3_RISK_ADJUSTED"},
                         {s.hypothesis for s in SHADOW_STRATEGY_REGISTRY})
        self.assertEqual({5,10,20},{s.top_n for s in SHADOW_STRATEGY_REGISTRY})
        self.assertEqual({"WEEKLY","MONTHLY"},{s.rebalance_frequency for s in SHADOW_STRATEGY_REGISTRY})

    def test_specs_are_frozen_and_labeled(self):
        self.assertEqual(64,len(REGISTRY_FINGERPRINT))
        self.assertTrue(all(len(s.spec_fingerprint)==64 and s.labels==LABELS for s in SHADOW_STRATEGY_REGISTRY))
        self.assertNotIn("PROMOTED",LABELS)
        self.assertEqual((),PROMOTED_PAPER_STRATEGIES)

    def test_all_market_scan_and_candidate_output(self):
        result=run_forward_day(self.data,self.first,self.store)
        self.assertEqual(520,result["total_symbols"])
        self.assertEqual(520,result["eligible_symbols"])
        self.assertEqual(18,len(result["strategies"]))
        self.assertEqual(20,len(result["top_candidates"]))

    def test_first_day_waits_for_next_open(self):
        result=run_forward_day(self.data,self.first,self.store)
        self.assertEqual("PENDING_NEXT_TRADABLE_OPEN",result["execution_status"])
        self.assertEqual(0,result["fill_count"])

    def test_second_day_uses_actual_next_open(self):
        run_forward_day(self.data,self.first,self.store)
        result=run_forward_day(self.data,self.second,self.store)
        self.assertEqual("FILLED_NEXT_TRADABLE_OPEN",result["execution_status"])
        self.assertGreater(result["fill_count"],0)

    def test_duplicate_run_is_idempotent(self):
        one=run_forward_day(self.data,self.first,self.store)
        two=run_forward_day(self.data,self.first,self.store)
        self.assertEqual(one,two)
        self.assertEqual(1,len(self.store.completed_dates()))

    def test_restart_recovery(self):
        first=run_forward_day(self.data,self.first,self.store)
        restarted=ForwardStore(self.store.root)
        self.assertEqual(first,run_forward_day(self.data,self.first,restarted))
        for spec in SHADOW_STRATEGY_REGISTRY:
            ledger,_=restarted.ledger(spec)
            self.assertEqual(1,len(ledger.events))

    def test_shadow_accounts_are_isolated(self):
        result=run_forward_day(self.data,self.first,self.store)
        ids=result["account_ids"]
        self.assertEqual(18,len(ids))
        self.assertEqual(18,len(set(ids)))
        self.assertEqual(ids,[account_id(s) for s in SHADOW_STRATEGY_REGISTRY])

    def test_forward_boundary_rejects_backfill(self):
        run_forward_day(self.data,self.first,self.store)
        with self.assertRaises(RuntimeError):
            run_forward_day(self.data,self.first-timedelta(days=1),self.store)

    def test_strategy_registry_mutation_fails_closed(self):
        run_forward_day(self.data,self.first,self.store)
        registry=json.loads(self.store.registry_path.read_text())
        registry["strategies"][0]["top_n"]=7
        self.store.registry_path.write_text(json.dumps(registry))
        with self.assertRaises(RuntimeError):
            run_forward_day(self.data,self.second,self.store)

    def test_benchmark_is_aligned(self):
        result=run_forward_day(self.data,self.first,self.store)
        self.assertEqual(result["business_date"],result["data_date"])
        self.assertEqual("0",result["benchmark"]["twse_return"])

    def test_forward_day_counter_does_not_inflate_on_replay(self):
        self.assertEqual(1,run_forward_day(self.data,self.first,self.store)["forward_trading_days"])
        self.assertEqual(1,run_forward_day(self.data,self.first,self.store)["forward_trading_days"])
        self.assertEqual(2,run_forward_day(self.data,self.second,self.store)["forward_trading_days"])

    def test_qualification_requires_sixty_days(self):
        good={"net_return":"0.1","excess_return":"0.05","sharpe":"1",
              "max_drawdown":"0.1","accounting_valid":True,
              "data_integrity_valid":True,"concentration_valid":True,"cost_stress_acceptable":True,
              "strategy_stable":True,"single_symbol_dominance":False}
        self.assertEqual(ForwardValidationStatus.COLLECTING,validation_status(1,good))
        self.assertEqual(ForwardValidationStatus.INSUFFICIENT_EVIDENCE,validation_status(20,good))
        self.assertEqual(ForwardValidationStatus.QUALIFIED,validation_status(MINIMUM_QUALIFICATION_DAYS,good))


    def test_daily_performance_contract_and_benchmark_ledger(self):
        result=run_forward_day(self.data,self.first,self.store)
        account=result["strategies"][0]
        required={"equity","cash","market_value","daily_pnl","cumulative_pnl","return",
                  "benchmark_return","excess_return","realized_pnl","unrealized_pnl","drawdown",
                  "exposure","turnover","transaction_cost","positions"}
        self.assertTrue(required <= set(account))
        self.assertTrue((self.store.root/"benchmark.jsonl").exists())

    def test_target_is_consumed_only_on_later_actual_session(self):
        run_forward_day(self.data,self.first,self.store)
        run_forward_day(self.data,self.second,self.store)
        for spec in SHADOW_STRATEGY_REGISTRY:
            ledger,_=self.store.ledger(spec)
            self.assertEqual(1,sum(e.event_type=="TARGET_EXECUTED" for e in ledger.events))
            self.assertTrue(all(e.event_date>self.first for e in ledger.events if e.event_type=="PAPER_FILL"))
    def test_non_trading_day_resolves_without_new_forward_day(self):
        complete=fixture_days(1)[0]
        complete["date"]="2026-10-02"
        class Provider:
            def day(self, session):
                return complete if session==date(2026,10,2) else {"date":session.isoformat(),"bars":[],"benchmark":None}
        self.assertEqual(date(2026,10,2),latest_complete_session(Provider(),date(2026,10,4)))

    def test_automation_schedule_and_seed_are_fail_closed(self):
        workflow=(Path(__file__).resolve().parents[2]/".github/workflows/v10-forward-shadow-paper.yml").read_text()
        self.assertIn('cron: "0 8 * * 1-5"',workflow)
        self.assertIn("automation.v10.restore_forward_store --seed artifacts/v10_forward_store",workflow)
        self.assertIn("github.event_name == 'schedule'",workflow)
        self.assertIn("if: always()",workflow)
        self.assertNotIn("automation.v9",workflow.lower())
        self.assertNotIn("broker",workflow.lower())

    def test_committed_boundary_and_registry_are_preserved(self):
        root=Path(__file__).resolve().parents[2]/"artifacts/v10_forward_store"
        boundary=json.loads((root/"forward_boundary.json").read_text())
        registry=json.loads((root/"strategy_registry.json").read_text())
        self.assertEqual("2026-10-05",boundary["forward_validation_start_date"])
        self.assertFalse(boundary["historical_backfill_allowed"])
        self.assertEqual(REGISTRY_FINGERPRINT,registry["registry_fingerprint"])
        self.assertEqual(18,len(registry["strategies"]))
    def test_no_v9_or_broker_dependency(self):
        source=inspect.getsource(__import__("automation.v10.forward_validation",fromlist=["run_forward_day"]))
        imports={node.module for node in ast.walk(ast.parse(source)) if isinstance(node,ast.ImportFrom)}
        self.assertFalse(any(name and ("v9" in name or "supabase" in name or "broker" in name) for name in imports))
        result=run_forward_day(self.data,self.first,self.store)
        self.assertEqual(0,result["broker_orders_created"])

if __name__=="__main__":
    unittest.main()

