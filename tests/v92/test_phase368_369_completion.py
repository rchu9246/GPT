"""Offline controller/governance authority, artifact and replay boundaries."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "automation/v92"))
import paper_trading_phase368_production_paper_daily_autonomous_operations_controller as controller
import paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine as governance
import phase369_controller_completion as completion

DAY = "2026-09-21"
REPO = "rchu9246/GPT"
AUTH = dict(producer_run_id="123", producer_run_attempt=2, canonical_authority_hash="a" * 64,
            source_evidence_sha256="b" * 64, controller_input_sha256="c" * 64)


class Database:
    def __init__(self):
        self.rows = {}
        self.writes = []

    def get(self, table, query):
        if "=lt." in query:
            return []
        rows = copy.deepcopy(self.rows.get(table, []))
        for column in ("controller_date", "supervision_date", "cycle_date", "evidence_date"):
            marker = column + "=eq."
            if marker in query:
                value = query.split(marker, 1)[1].split("&", 1)[0]
                rows = [row for row in rows if row.get(column) == value]
        return rows

    def request(self, method, table, query="", payload=None, prefer=None):
        if method == "POST":
            self.writes.append(table)
            if table in ("paper_daily_autonomous_controller_v92", "paper_daily_lifecycle_evidence_v92"):
                if self.rows.get(table):
                    raise RuntimeError("unique constraint")
                self.rows[table] = [copy.deepcopy(payload)]
            elif table.endswith("_audit_v92"):
                self.rows.setdefault(table, []).append(copy.deepcopy(payload))
        return None


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.args = Mock(portfolio_id="V92_PRODUCTION_PAPER_V91", strategy_version="V9.1",
                         controller_date=DAY, approver="operator", provenance=copy.deepcopy(AUTH),
                         supervision_hash="d" * 64)
        self.pre = dict(authorized=True, activation_state="ACTIVE", qualification_state="QUALIFIED",
                        supervision_state="CONTINUE_ACTIVE", supervision_score=100, observation=False)
        self.master = dict(cycle_date=DAY, final_state="DAILY_MASTER_CYCLE_COMPLETED", evidence_sha256="e" * 64)

    def persist(self, state="COMPLETED", master=None):
        with patch.object(controller, "write_artifact") as artifact:
            sha = controller.persist(self.db, self.args, state, self.pre, self.master if master is None else master,
                                     True, 0, ["PASS"])
        artifact.assert_called_once_with(self.args, state, sha)
        return sha

    def test_insert_same_authority_replay_and_no_duplicate_audit(self):
        sha = self.persist()
        self.assertEqual(self.persist(), sha)
        self.assertEqual(self.db.writes, ["paper_daily_autonomous_controller_v92",
                                          "paper_daily_autonomous_controller_audit_v92"])
        self.assertEqual(len(self.db.rows["paper_daily_autonomous_controller_v92"]), 1)

    def test_conflicts_and_legacy_fail_before_write(self):
        self.persist()
        initial = list(self.db.writes)
        for key, value, error in (("producer_run_id", "124", "AUTHORITY_CONFLICT"),
                                  ("canonical_authority_hash", "z" * 64, "AUTHORITY_CONFLICT"),
                                  ("controller_input_sha256", "f" * 64, "AUTHORITY_CONFLICT")):
            with self.subTest(key=key):
                self.args.provenance[key] = value
                with self.assertRaisesRegex(RuntimeError, error):
                    self.persist()
                self.args.provenance[key] = AUTH[key]
        with self.assertRaisesRegex(RuntimeError, "CONTENT_CONFLICT"):
            self.persist(master={**self.master, "evidence_sha256": "f" * 64})
        self.db.rows["paper_daily_autonomous_controller_v92"][0]["producer_run_id"] = None
        with self.assertRaisesRegex(RuntimeError, "LEGACY_PROVENANCE"):
            self.persist()
        self.assertEqual(self.db.writes, initial)

    def test_incomplete_existing_fails_closed(self):
        self.persist()
        self.db.rows["paper_daily_autonomous_controller_v92"][0]["controller_state"] = "FAIL_CLOSED"
        with self.assertRaisesRegex(RuntimeError, "INCOMPLETE"):
            self.persist()

    def test_missing_audit_fails_closed_without_repair(self):
        self.persist()
        self.db.rows["paper_daily_autonomous_controller_audit_v92"] = []
        with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_CONTROLLER_AUDIT"):
            self.persist()

    def test_date_and_artifact_identity(self):
        result = {"evidence_sha256": "b" * 64, "canonical_authority": {
            "trade_date": DAY, "producer_run_id": "123", "producer_run_attempt": "2",
            "authority_hash": "a" * 64}}
        self.assertEqual(controller.provenance(result, DAY)["producer_run_attempt"], 2)
        with self.assertRaisesRegex(RuntimeError, "DATE_DOES_NOT_MATCH"):
            controller.provenance(result, "2026-09-22")
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(controller.os, "getcwd", return_value="/tmp"), \
                patch.object(controller.os, "makedirs"), patch("builtins.open", create=True) as out:
            controller.write_artifact(self.args, "COMPLETED", "f" * 64)
            text = "".join(call.args[0] for call in out.return_value.__enter__.return_value.write.call_args_list)
        artifact = json.loads(text)
        self.assertEqual(artifact["business_date"], DAY)
        self.assertEqual(artifact["controller_run_id"], "456")
        self.assertEqual(artifact["artifact_sha256"], controller.stable_hash({k: v for k, v in artifact.items() if k != "artifact_sha256"}))

    def test_missing_same_date_supervision_never_runs_master(self):
        producer = {"evidence_sha256": "b" * 64, "canonical_authority": {
            "trade_date": DAY, "producer_run_id": "123", "producer_run_attempt": "2", "authority_hash": "a" * 64}}
        with patch.object(sys, "argv", ["controller", "--controller-date", DAY]), \
                patch.dict(os.environ, {"GITHUB_SHA": "f" * 40, "SUPABASE_URL": "https://offline.invalid", "SUPABASE_SERVICE_ROLE_KEY": "offline"}), \
                patch.object(controller, "load_explicit_producer_result", return_value=producer), \
                patch.object(controller, "Supabase", return_value=self.db), \
                patch.object(controller, "run_master") as run_master:
            with self.assertRaisesRegex(RuntimeError, "SAME_DATE_RUNTIME_SUPERVISION_MISSING"):
                controller.main()
            run_master.assert_not_called()
        self.assertEqual(self.db.writes, [])

    def test_wrong_date_master_fails_closed_before_persist(self):
        producer = {"evidence_sha256": "b" * 64, "canonical_authority": {
            "trade_date": DAY, "producer_run_id": "123", "producer_run_attempt": "2", "authority_hash": "a" * 64}}
        self.db.rows["paper_runtime_supervision_state_v92"] = [{"supervision_date": DAY, "evidence_sha256": "d" * 64,
            "activation_state": "ACTIVE", "qualification_state": "QUALIFIED", "supervision_state": "CONTINUE_ACTIVE",
            "autonomous_paper_operations_continued": True, "safety_revocation_triggered": False}]
        self.db.rows["paper_master_cycles_v92"] = [{**self.master, "cycle_date": "2026-09-11"}]
        with patch.object(sys, "argv", ["controller", "--controller-date", DAY]), \
                patch.dict(os.environ, {"GITHUB_SHA": "f" * 40, "SUPABASE_URL": "https://offline.invalid", "SUPABASE_SERVICE_ROLE_KEY": "offline"}), \
                patch.object(controller, "load_explicit_producer_result", return_value=producer), \
                patch.object(controller, "Supabase", return_value=self.db), \
                patch.object(controller, "run_master", return_value=Mock(returncode=0, stdout="", stderr="")):
            with self.assertRaisesRegex(RuntimeError, "SAME_DATE_MASTER_CYCLE_MISSING"):
                controller.main()
        self.assertEqual(self.db.writes, [])


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.event = dict(action="completed", repository={"full_name": REPO}, workflow_run=dict(
            id=456, run_attempt=1, head_repository={"full_name": REPO}, head_branch="main",
            path=completion.WORKFLOW, event="workflow_dispatch", status="completed",
            conclusion="success", head_sha="f" * 40))
        self.artifact = dict(contract=completion.CONTRACT, portfolio_id="V92_PRODUCTION_PAPER_V91",
            business_date=DAY, strategy_version="V9.1", **AUTH, controller_state="COMPLETED", controller_evidence_sha256="e" * 64,
            controller_run_id="456", controller_run_attempt=1)
        self.artifact["artifact_sha256"] = governance.stable_hash(self.artifact)

    def responses(self, artifact_count=1, expired=False, altered_zip=False):
        content = json.dumps(self.artifact).encode()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("daily_autonomous_controller_evidence.json", content)
        data = stream.getvalue()
        run = {**self.event["workflow_run"], "repository": {"full_name": REPO}}
        entry = dict(id=789, name="phase368-controller-456-attempt-1", expired=expired,
                     workflow_run={"id": 456, "head_sha": "f" * 40},
                     digest="sha256:" + hashlib.sha256(data).hexdigest())
        def get(url, **kwargs):
            if url.endswith("/attempts/1"):
                return Mock(status_code=200, json=lambda: run)
            if url.endswith("/artifacts"):
                return Mock(status_code=200, json=lambda: {"total_count": artifact_count,
                    "artifacts": [copy.deepcopy(entry) for _ in range(artifact_count)]})
            return Mock(status_code=200, content=data + (b"bad" if altered_zip else b""))
        return get

    def test_exact_run_artifact_and_delayed_date(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run", "GH_TOKEN": "offline"}), \
                patch.object(completion.requests, "get", side_effect=self.responses()):
            self.assertEqual(completion.load_exact_artifact(self.event), self.artifact)
        self.assertEqual(self.artifact["business_date"], DAY)  # independent of today's runner date

    def test_wrong_event_identity_and_conclusion(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run"}):
            for key, value in (("head_branch", "other"), ("path", "other.yml"),
                               ("head_repository", {"full_name": "other/repo"}), ("id", 0),
                               ("run_attempt", 0), ("status", "queued")):
                event = copy.deepcopy(self.event)
                event["workflow_run"][key] = value
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    completion.completion_reference(event)
            event = copy.deepcopy(self.event)
            event["repository"]["full_name"] = "other/repo"
            with self.assertRaises(RuntimeError):
                completion.completion_reference(event)

    def test_missing_multiple_expired_and_bad_digest(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run", "GH_TOKEN": "offline"}):
            for count, expired, bad in ((0, False, False), (2, False, False),
                                        (1, True, False), (1, False, True)):
                with self.subTest(case=(count, expired, bad)), \
                        patch.object(completion.requests, "get", side_effect=self.responses(count, expired, bad)):
                    with self.assertRaises(RuntimeError):
                        completion.load_exact_artifact(self.event)

    def test_wrong_attempt_artifact_identity_and_hash(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_run", "GH_TOKEN": "offline"}):
            event = copy.deepcopy(self.event)
            event["workflow_run"]["run_attempt"] = 2
            with patch.object(completion.requests, "get", side_effect=self.responses()):
                with self.assertRaisesRegex(RuntimeError, "EVENT_RUN_MISMATCH"):
                    completion.load_exact_artifact(event)
            for field, value in (("controller_run_id", "999"), ("controller_run_attempt", 2),
                                 ("business_date", "2026-09-22")):
                with self.subTest(field=field):
                    old = self.artifact[field]
                    self.artifact[field] = value  # hash stays unchanged: tampering must fail
                    with patch.object(completion.requests, "get", side_effect=self.responses()):
                        with self.assertRaisesRegex(RuntimeError, "RESULT_HASH_MISMATCH"):
                            completion.load_exact_artifact(self.event)
                    self.artifact[field] = old


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.artifact = dict(portfolio_id="V92_PRODUCTION_PAPER_V91", business_date=DAY, strategy_version="V9.1", **AUTH,
                             controller_state="COMPLETED", controller_evidence_sha256="e" * 64,
                             controller_run_id="456", controller_run_attempt=1, artifact_sha256="f" * 64)
        self.db.rows["paper_daily_autonomous_controller_v92"] = [dict(controller_date=DAY, portfolio_id=self.artifact["portfolio_id"],
            **AUTH, strategy_version="V9.1", controller_state="COMPLETED", controller_passed=True, evidence_sha256="e" * 64,
            source_master_evidence_sha256="m" * 64, autonomous_daily_operations_authorized=True,
            daily_paper_cycle_executed=True, activation_state="ACTIVE", qualification_state="QUALIFIED",
            runtime_supervision_state="CONTINUE_ACTIVE", safety_revocation_triggered=False)]
        self.db.rows["paper_master_cycles_v92"] = [dict(cycle_date=DAY, evidence_sha256="m" * 64)]

    def govern(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://offline.invalid", "SUPABASE_SERVICE_ROLE_KEY": "offline"}), \
                patch.object(governance, "Supabase", return_value=self.db), patch.object(governance.os, "makedirs"), \
                patch("builtins.open", create=True), patch.object(governance.os, "getcwd", return_value="/tmp"), \
                redirect_stdout(io.StringIO()):
            return governance.main(self.artifact)

    def test_new_date_then_same_authority_replay_has_no_writes(self):
        self.assertEqual(self.govern(), 0)
        writes = list(self.db.writes)
        self.assertEqual(self.govern(), 0)
        self.assertEqual(self.db.writes, writes)
        self.assertEqual(writes, ["paper_daily_lifecycle_evidence_v92", "paper_daily_lifecycle_evidence_audit_v92"])

    def test_stale_controller_hash_and_different_authority_fail(self):
        self.db.rows["paper_daily_autonomous_controller_v92"] = []
        with self.assertRaisesRegex(RuntimeError, "controller evidence missing"):
            self.govern()
        self.db.rows["paper_daily_autonomous_controller_v92"] = [dict(**AUTH, controller_date=DAY, strategy_version="V9.1", evidence_sha256="bad", controller_state="COMPLETED")]
        with self.assertRaisesRegex(RuntimeError, "HASH_MISMATCH"):
            self.govern()
        self.db.rows["paper_daily_autonomous_controller_v92"][0].update(
            evidence_sha256="e" * 64, source_master_evidence_sha256="m" * 64, controller_passed=True)
        self.govern()
        self.artifact["producer_run_id"] = "124"
        self.db.rows["paper_daily_autonomous_controller_v92"][0]["producer_run_id"] = "124"
        with self.assertRaisesRegex(RuntimeError, "AUTHORITY_CONFLICT"):
            self.govern()

    def test_artifact_database_hash_mismatch_precedes_write(self):
        self.artifact["controller_evidence_sha256"] = "z" * 64
        with self.assertRaisesRegex(RuntimeError, "HASH_MISMATCH"):
            self.govern()
        self.assertEqual(self.db.writes, [])

    def test_missing_lifecycle_audit_fails_closed_without_repair(self):
        self.govern()
        self.db.rows["paper_daily_lifecycle_evidence_audit_v92"] = []
        with self.assertRaisesRegex(RuntimeError, "INCOMPLETE_LIFECYCLE_AUDIT"):
            self.govern()

    def test_same_authority_changed_content_and_legacy_row_fail_closed(self):
        self.govern()
        writes = list(self.db.writes)
        self.db.rows["paper_master_cycles_v92"][0]["nav"] = 42
        with self.assertRaisesRegex(RuntimeError, "CONTENT_CONFLICT"):
            self.govern()
        self.db.rows["paper_master_cycles_v92"][0].pop("nav")
        row = self.db.rows["paper_daily_lifecycle_evidence_v92"][0]
        row["canonical_authority_hash"] = None
        with self.assertRaisesRegex(RuntimeError, "LEGACY_PROVENANCE"):
            self.govern()
        self.assertEqual(self.db.writes, writes)

    def test_workflows_have_single_owner_and_no_cron_loop(self):
        root = Path(__file__).resolve().parents[2] / ".github/workflows"
        a = (root / "gpt-quant-v92-paper-trading-phase368-production-paper-daily-autonomous-operations-controller.yml").read_text(encoding="utf-8-sig")
        b = (root / "gpt-quant-v92-paper-trading-phase369-production-paper-autonomous-daily-evidence-lifecycle-governance-engine.yml").read_text()
        self.assertNotIn("  schedule:", a)
        self.assertNotIn("  schedule:", b)
        self.assertIn("workflow_run:", b)
        self.assertNotIn("workflow_run:", a)
        self.assertIn("phase368-controller-${{ github.run_id }}-attempt-${{ github.run_attempt }}", a)


if __name__ == "__main__":
    unittest.main()
