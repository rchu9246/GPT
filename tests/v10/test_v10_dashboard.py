import json, shutil, tempfile, unittest
from datetime import date, timedelta
from pathlib import Path
from automation.v10.dashboard_report import build_report
from automation.v10.forward_validation import ForwardMarketData, ForwardStore, run_forward_day
from automation.v10.restore_forward_store import restore
from test_v10_phase3 import fixture_days

class DashboardEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path(".tmp_forward_tests").mkdir(exist_ok=True)
        cls.base_temp=tempfile.TemporaryDirectory(dir=".tmp_forward_tests");cls.base=Path(cls.base_temp.name)/"seed"
        days=fixture_days()
        for i,d in enumerate(days):d["date"]=str(date(2026,8,6)+timedelta(days=i))
        cls.market=ForwardMarketData(days);cls.store=ForwardStore(cls.base)
        run_forward_day(cls.market,date(2026,10,5),cls.store)
        run_forward_day(cls.market,date(2026,10,6),cls.store)
    @classmethod
    def tearDownClass(cls):cls.base_temp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=".tmp_forward_tests");self.root=Path(self.temp.name)/"forward";shutil.copytree(self.base,self.root)
        self.store=ForwardStore(self.root)
    def tearDown(self):self.temp.cleanup()
    def mutate(self,name,fn):
        p=self.root/name;v=json.loads(p.read_text());fn(v);p.write_text(json.dumps(v))
    def test_all_18_scoreboard_and_positions(self):
        r=build_report(self.store);self.assertEqual(18,len(r["strategies"]));self.assertEqual(210,len(r["fills"]));self.assertTrue(all(s["position_details"] for s in r["strategies"]))
    def test_candidate_scores_and_actual_strategy_labels(self):
        r=build_report(self.store);self.assertEqual(20,len(r["top_candidates"]));self.assertEqual(6,len(r["top_candidates"][0]["factor_scores"]));self.assertTrue(r["top_candidates"][0]["strategy_id"].startswith("V10_SHADOW"))
    def test_first_day_pending_has_no_fabricated_price(self):
        temp=Path(self.temp.name)/"first";s=ForwardStore(temp);run_forward_day(self.market,date(2026,10,5),s)
        r=build_report(s);self.assertEqual("PENDING",r["first_fill_validation"]);self.assertFalse(r["fills"]);self.assertTrue(all(o["fill_price"] is None and o["execution_date"] is None for o in r["orders"]))
    def test_first_fill_actual_next_open_and_reconciliation(self):
        r=build_report(self.store);self.assertEqual("2026-10-06",r["first_fill_date"]);self.assertEqual("PASS",r["first_fill_validation"])
        self.assertTrue(all(f["signal_date"]=="2026-10-05" and f["reference"]=="TWSE_ACTUAL_NEXT_TRADABLE_OPEN" for f in r["fills"]))
        self.assertTrue(all(x["status"]=="PASS" for x in r["reconciliations"]))
    def test_pre_forward_date_rejected(self):
        shutil.copyfile(self.root/"runs/2026-10-05.json",self.root/"runs/2026-10-04.json")
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_v9_pnl_contamination_rejected(self):
        self.mutate("runs/2026-10-06.json",lambda m:m["strategies"][0].update(cumulative_pnl="999999"))
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_v9_mode_rejected(self):
        self.mutate("runs/2026-10-06.json",lambda m:m.update(mode="LEGACY_V9"))
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_cash_reset_rejected(self):
        self.mutate("runs/2026-10-06.json",lambda m:m["strategies"][0].update(cash="1000000"))
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_cross_strategy_account_rejected(self):
        self.mutate("runs/2026-10-06.json",lambda m:m["strategies"][0].update(account_id=m["strategies"][1]["account_id"]))
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_changed_open_evidence_rejected(self):
        def change(m):
            for b in m["bars"]:b["open"]="999"
        self.mutate("market_evidence/2026-10-06.json",change)
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_benchmark_alignment_rejected(self):
        self.mutate("runs/2026-10-06.json",lambda m:m["strategies"][0].update(benchmark_return="0.1"))
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_premature_validation_rejected(self):
        self.mutate("runs/2026-10-06.json",lambda m:m["strategies"][0].update(validation_status="QUALIFIED"))
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_forward_day_progress_not_calendar_days(self):
        r=build_report(self.store);self.assertEqual(2,r["forward_trading_days"]);self.assertEqual({"days":2,"required":20},r["preliminary_gate"]);self.assertEqual({"days":2,"required":60},r["qualification_gate"])
    def test_duplicate_ledger_event_rejected(self):
        p=next((self.root/"accounts").glob("*.jsonl"));p.write_text(p.read_text()+p.read_text().splitlines()[0]+"\n")
        with self.assertRaises(RuntimeError):build_report(self.store)
    def test_frozen_registry_format_whitespace_is_compatible(self):
        p=self.root/"strategy_registry.json";p.write_text(p.read_text()+"\n\n")
        self.store.initialize(date(2026,10,6));self.assertEqual(18,len(build_report(self.store)["strategies"]))
    def test_blank_ledger_lines_preserve_hash_chain(self):
        p=next((self.root/"accounts").glob("*.jsonl"));p.write_text(p.read_text()+"\n\n")
        self.assertEqual(210,len(build_report(self.store)["fills"]))
    def test_restore_nested_artifact_does_not_reset_accounts(self):
        download=Path(self.temp.name)/"artifact";shutil.copytree(self.base,download/"v10_forward_store")
        out=Path(self.temp.name)/"restored";restore(self.base,download,out);self.assertEqual(210,len(build_report(ForwardStore(out))["fills"]))
    def test_completed_replay_preserves_fills_and_curve(self):
        before=build_report(self.store);run_forward_day(self.market,date(2026,10,6),self.store);after=build_report(self.store)
        self.assertEqual(before["fills"],after["fills"]);self.assertEqual(before["strategies"],after["strategies"])
    def test_later_provider_revision_does_not_rewrite_sealed_evidence(self):
        before=(self.root/"market_evidence/2026-10-05.json").read_bytes()
        days=fixture_days()
        for i,d in enumerate(days):
            d["date"]=str(date(2026,8,6)+timedelta(days=i))
            for b in d["bars"]:b["volume"]+=100
        run_forward_day(ForwardMarketData(days),date(2026,10,5),self.store)
        self.assertEqual(before,(self.root/"market_evidence/2026-10-05.json").read_bytes())
    def test_no_v9_dependency_in_report_or_browser(self):
        paths=[Path("automation/v10/dashboard_report.py"),Path("dashboard/v10-forward/dashboard.js")]
        for p in paths:
            text=p.read_text(encoding="utf-8");self.assertNotIn("supabase",text.lower());self.assertNotIn("v9Data",text)

if __name__=="__main__":unittest.main()
