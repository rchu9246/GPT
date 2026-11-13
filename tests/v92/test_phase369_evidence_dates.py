"""Offline regression: no live database, workflow dispatch, or historical writes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]


def load_phase(pattern):
    path = next((ROOT / 'automation/v92').glob(pattern))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LifecycleDates(unittest.TestCase):
    def setUp(self):
        self.phase = load_phase('paper_trading_phase369_*.py')
        self.controller = dict(controller_date='2026-11-12', controller_state='COMPLETED',
            controller_passed=True, autonomous_daily_operations_authorized=True,
            daily_paper_cycle_executed=True, safety_revocation_triggered=False,
            activation_state='ACTIVE', qualification_state='QUALIFIED',
            runtime_supervision_state='CONTINUE_ACTIVE')

    def run_case(self, controller, master):
        sb = Mock()
        sb.get.side_effect = [[controller] if controller else [], [master] if master else [], []]
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(self.phase, 'Supabase', return_value=sb))
            stack.enter_context(patch.dict(os.environ, {'SUPABASE_URL':'https://invalid.example',
                'SUPABASE_SERVICE_ROLE_KEY':'offline-test'}))
            stack.enter_context(patch('sys.argv', ['phase369', '--evidence-date', '2026-11-12']))
            stack.enter_context(contextlib.chdir(temp))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            try:
                result = self.phase.main()
            except RuntimeError as exc:
                sb.upsert.assert_not_called()
                sb.request.assert_not_called()
                self.assertFalse(Path('artifacts').exists())
                return str(exc), sb
            return result, sb

    def test_observed_stale_controller_stops_before_writes(self):
        self.controller['controller_date'] = '2026-09-11'
        error, _ = self.run_case(self.controller, {'cycle_date':'2026-11-12'})
        self.assertIn('expected=2026-11-12, actual=2026-09-11', error)

    def test_missing_controller(self):
        error, _ = self.run_case(None, None)
        self.assertIn('controller evidence missing', error)

    def test_missing_master(self):
        error, _ = self.run_case(self.controller, None)
        self.assertIn('master cycle evidence missing', error)

    def test_stale_future_or_missing_master_date(self):
        for day in ['2026-11-11', '2026-11-13', None]:
            with self.subTest(day=day):
                error, _ = self.run_case(self.controller, {'cycle_date':day})
                self.assertIn('master cycle date mismatch', error)

    def test_same_date_keeps_source_hashes_and_safety_locks(self):
        result, sb = self.run_case(self.controller, {'cycle_date':'2026-11-12', 'evidence_sha256':'master'})
        self.assertEqual(result, 0)
        payload = sb.upsert.call_args.args[1]
        self.assertTrue(payload['lifecycle_passed'])
        self.assertEqual(payload['source_master_evidence_sha256'], 'master')
        for key in ['broker_order_submission_enabled','real_money_trading_enabled','live_money_release_authorized']:
            self.assertIs(payload[key], False)

    def test_missing_authorization_remains_fail_closed(self):
        self.controller['autonomous_daily_operations_authorized'] = False
        result = self.phase.evaluate(self.controller)
        self.assertFalse(result['lifecycle_passed'])
        self.assertIn('AUTONOMOUS_DAILY_OPERATIONS_NOT_AUTHORIZED', result['reason_codes'])


class ExistingReadinessGuards(unittest.TestCase):
    def test_phase343_observed_waiting_state_remains_blocked(self):
        phase = load_phase('paper_trading_phase343_approval_readiness.py')
        data = dict(status='PASS', qualification_state='QUALIFIED',
            release_state='AWAITING_HUMAN_APPROVAL', consecutive_pass_days=60,
            latest_market_date='2026-11-11', market_stale_days=1,
            pass_day_source='distinct_run_date_snapshot_status', mode=phase.MODE)
        valid, errors = phase.validate_source(data)
        self.assertFalse(valid)
        self.assertIn('release_not_locked_before_human_approval', errors)
        summary = phase.build_summary(data, valid, errors)
        self.assertEqual(summary['approval_readiness'], 'BLOCKED')
        self.assertFalse(summary['automatic_approval'])

    def test_phase37111_same_day_counter_inflation_stays_blocked(self):
        phase = load_phase('paper_trading_phase37111_*.py')
        baseline = dict(observed=1, valid=1, blocked=0, distinct_cycle_dates=1,
            distinct_dates=['2026-11-12'], duplicate_rows=0,
            runtime_supervision_pass=True, paper_only_boundary_pass=True)
        current = dict(baseline, observed=2, valid=2)
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            folder = Path(temp)
            for name, filename in [('ART_DIR','.'),('BASELINE_PATH','baseline.json'),
                                   ('RESULT_PATH','result.json'),('SUMMARY_PATH','summary.md')]:
                stack.enter_context(patch.object(phase, name, folder / filename))
            phase.BASELINE_PATH.write_text(json.dumps({'qualification':baseline}))
            stack.enter_context(patch.object(phase, 'qualification_snapshot', return_value=current))
            stack.enter_context(patch.object(phase, 'readiness_snapshot', return_value={}))
            stack.enter_context(patch.object(phase, 'request', side_effect=AssertionError('network forbidden')))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.assertEqual(phase.validate_waiting_state(), 1)
            result = json.loads(phase.RESULT_PATH.read_text())
            self.assertIn('SAME_DAY_COUNTER_ADVANCE_DETECTED', result['blockers'])
            self.assertFalse(result['safety']['qualification_threshold_bypass_allowed'])


if __name__ == '__main__':
    unittest.main()
