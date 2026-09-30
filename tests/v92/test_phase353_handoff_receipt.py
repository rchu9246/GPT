import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / ".github/supabase/migrations/015_phase353_handoff_receipts.sql"
ADAPTER = ROOT / "automation/v92/phase353_handoff_receipt.py"
spec = importlib.util.spec_from_file_location("phase353_handoff_receipt", ADAPTER)
receipt = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(receipt)


class Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = 200 <= status < 300
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class Session:
    def __init__(self, post_payload=None, get_payload=None):
        self.post_payload = post_payload
        self.get_payload = get_payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Response(self.post_payload)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Response(self.get_payload)


class Phase353HandoffReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.sql_lower = cls.sql.lower()

    def claim(self, payload):
        session = Session(post_payload=[payload])
        result = receipt.claim_handoff(
            repository="rchu9246/GPT", producer_workflow="producer.yml",
            producer_run_id=123, producer_run_attempt=2, consumer="355",
            producer_sha="a" * 40, business_date="2026-09-30", authority_hash="digest",
            base_url="https://example.supabase.co", service_role_key="secret", session=session,
        )
        return result, session

    def test_01_first_claim_succeeds(self):
        result, _ = self.claim({"claim_result": "CLAIM_ACQUIRED", "receipt_id": 1,
                                "receipt_status": "CLAIMED"})
        self.assertEqual(result["claim_result"], "CLAIM_ACQUIRED")

    def test_02_identical_replay_does_not_acquire(self):
        result, _ = self.claim({"claim_result": "ALREADY_CLAIMED", "receipt_id": 1,
                                "receipt_status": "CLAIMED"})
        self.assertEqual(result["claim_result"], "ALREADY_CLAIMED")

    def test_03_conflicting_producer_sha_fails_closed(self):
        self.assertIn("v_receipt.producer_sha <> lower(p_producer_sha)", self.sql)
        self.assertIn("PHASE353_HANDOFF_IMMUTABLE_IDENTITY_CONFLICT", self.sql)

    def test_04_conflicting_authority_hash_fails_when_supplied(self):
        self.assertIn("p_authority_hash is not null and v_receipt.authority_hash is distinct from p_authority_hash", self.sql)

    def test_05_concurrent_claim_is_guarded_by_database_constraint(self):
        self.assertIn("constraint phase353_handoff_receipts_identity_key unique", self.sql_lower)
        self.assertIn("on conflict (repository, producer_workflow, producer_run_id, producer_run_attempt, consumer)", self.sql_lower)
        self.assertIn("do nothing", self.sql_lower)

    def test_06_claimed_is_not_dispatch_accepted(self):
        self.assertIn("default 'CLAIMED'", self.sql)
        self.assertIn("if v_receipt.status = 'CLAIMED' then", self.sql)

    def test_07_http_204_semantics_are_dispatch_accepted_only(self):
        source = ADAPTER.read_text(encoding="utf-8")
        self.assertIn("HTTP 204 may", source)
        self.assertIn("DISPATCH_ACCEPTED", source)
        self.assertIn("never represents downstream completion", source)

    def test_08_dispatch_acceptance_cannot_set_completed(self):
        marker = "create or replace function public.mark_phase353_handoff_dispatch_accepted"
        body = self.sql[self.sql_lower.index(marker):self.sql_lower.index("revoke all on table")]
        self.assertNotIn("set status = 'COMPLETED'", body)
        self.assertIn("set status = 'DISPATCH_ACCEPTED'", body)

    def test_09_immutable_identity_has_update_trigger(self):
        self.assertIn("before update on public.phase353_handoff_receipts", self.sql_lower)
        for column in ("repository", "producer_workflow", "producer_run_id", "producer_run_attempt",
                       "consumer", "producer_sha", "business_date", "authority_hash"):
            self.assertIn(f"new.{column} is distinct from old.{column}", self.sql_lower)

    def test_10_untrusted_roles_cannot_execute_mutations(self):
        for function in ("claim_phase353_handoff", "mark_phase353_handoff_dispatch_accepted"):
            signature = self.sql_lower[self.sql_lower.index(f"revoke all on function public.{function}"):]
            self.assertIn("from public, anon, authenticated", signature.split(";", 1)[0])
        self.assertEqual(self.sql_lower.count("to service_role;"), 3)

    def test_11_migration_is_transactional(self):
        stripped = self.sql_lower.strip()
        self.assertTrue(stripped.startswith("begin;"))
        self.assertTrue(stripped.endswith("commit;"))

    def test_12_migration_is_idempotent(self):
        self.assertIn("create table if not exists", self.sql_lower)
        self.assertEqual(self.sql_lower.count("create or replace function"), 3)
        self.assertIn("drop trigger if exists", self.sql_lower)

    def test_13_no_historical_trading_rows_are_touched(self):
        self.assertNotIn("delete from", self.sql_lower)
        self.assertNotIn("truncate", self.sql_lower)
        updates = [line.strip() for line in self.sql_lower.splitlines() if line.strip().startswith("update ")]
        self.assertEqual(updates, ["update public.phase353_handoff_receipts"])

    def test_14_no_production_workflow_integration_exists(self):
        workflow_text = "\n".join(path.read_text(encoding="utf-8-sig")
                                  for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertNotIn("phase353_handoff_receipt", workflow_text)
        self.assertNotIn("claim_phase353_handoff", workflow_text)

    def test_15_safety_flags_unchanged_and_no_broker_path(self):
        changed_sources = MIGRATION.read_text(encoding="utf-8") + ADAPTER.read_text(encoding="utf-8")
        for unsafe in ("BROKER_ORDER_SUBMISSION_ENABLED=True", "REAL_MONEY_TRADING_ENABLED=True",
                       "HISTORICAL_REWRITE_ALLOWED=True"):
            self.assertNotIn(unsafe, changed_sources)
        self.assertNotIn("broker", changed_sources.lower())

    def test_runtime_acceptance_adapter_calls_only_transition_rpc(self):
        session = Session(post_payload=[{"transition_result": "DISPATCH_ACCEPTED",
                                        "receipt_id": 1, "receipt_status": "DISPATCH_ACCEPTED"}])
        result = receipt.mark_dispatch_accepted(
            receipt_id=1, repository="rchu9246/GPT", producer_workflow="producer.yml",
            producer_run_id=123, producer_run_attempt=2, consumer="355", producer_sha="a" * 40,
            base_url="https://example.supabase.co", service_role_key="secret", session=session,
        )
        self.assertEqual(result["receipt_status"], "DISPATCH_ACCEPTED")
        self.assertTrue(session.calls[0][1].endswith("/rpc/mark_phase353_handoff_dispatch_accepted"))

    def test_read_receipt_uses_exact_identity(self):
        session = Session(get_payload=[])
        result = receipt.read_receipt(
            repository="rchu9246/GPT", producer_workflow="producer.yml", producer_run_id=123,
            producer_run_attempt=2, consumer="355", base_url="https://example.supabase.co",
            service_role_key="secret", session=session,
        )
        self.assertIsNone(result)
        params = session.calls[0][2]["params"]
        self.assertEqual(params["producer_run_id"], "eq.123")
        self.assertEqual(params["producer_run_attempt"], "eq.2")


if __name__ == "__main__":
    unittest.main()
