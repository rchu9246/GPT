from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import json
import subprocess
import unittest
from unittest.mock import Mock

from scripts.resolve_phase378_dispatch import resolve


def runs(*ids):
    rows = [{"id": i, "display_title": "phase378-parent-42"} for i in ids]
    rows.append({"id": 999, "display_title": "unrelated"})
    return subprocess.CompletedProcess([], 0, json.dumps([{"workflow_runs": rows}]))


class DispatchCorrelationTests(unittest.TestCase):
    def resolve(self, run, attempt="1"):
        return resolve("child.yml", "test/repo", "42", attempt, run=run, sleep=Mock())

    def test_504_with_child_resolves_without_retry(self):
        run = Mock(side_effect=[runs(), subprocess.CompletedProcess([], 1), runs(123)])
        self.assertEqual(self.resolve(run), 123)
        self.assertEqual(run.call_count, 3)
        self.assertIn("dispatch_correlation=phase378-parent-42", run.call_args_list[1].args[0])

    def test_504_with_only_unrelated_runs_fails_closed(self):
        run = Mock(side_effect=[runs(), subprocess.CompletedProcess([], 1)] + [runs()] * 30)
        with self.assertRaisesRegex(ValueError, "could not be correlated"):
            self.resolve(run)
        self.assertEqual(sum(c.args[0][1] == "workflow" for c in run.call_args_list), 1)

    def test_rerun_reuses_correlated_child(self):
        run = Mock(return_value=runs(456))
        self.assertEqual(self.resolve(run, "2"), 456)
        run.assert_called_once()

    def test_rerun_with_no_child_refuses_dispatch(self):
        run = Mock(return_value=runs())
        with self.assertRaisesRegex(ValueError, "Previous attempt"):
            self.resolve(run, "2")
        run.assert_called_once()

    def test_duplicate_children_refuse_dispatch(self):
        run = Mock(return_value=runs(123, 456))
        with self.assertRaisesRegex(ValueError, "Multiple"):
            self.resolve(run)
        run.assert_called_once()

    def test_failed_initial_read_refuses_dispatch(self):
        run = Mock(side_effect=subprocess.CalledProcessError(1, "gh"))
        with self.assertRaises(subprocess.CalledProcessError):
            self.resolve(run)
        run.assert_called_once()

    def test_timeout_and_transient_read_errors_reconcile_without_second_post(self):
        run = Mock(side_effect=[
            runs(), subprocess.TimeoutExpired("gh", 30),
            subprocess.CalledProcessError(1, "gh"),
            subprocess.TimeoutExpired("gh", 15), runs(123),
        ])
        self.assertEqual(self.resolve(run), 123)
        self.assertEqual(sum(c.args[0][1] == "workflow" for c in run.call_args_list), 1)

    def test_duplicate_on_second_page_blocks(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps([
            {"workflow_runs": [{"id": 123, "display_title": "phase378-parent-42"}]},
            {"workflow_runs": [{"id": 456, "display_title": "phase378-parent-42"}]},
        ])))
        with self.assertRaisesRegex(ValueError, "Multiple"):
            self.resolve(run)
        run.assert_called_once()

    def test_parallel_parents_resolve_only_their_own_children(self):
        children = []
        lock = Lock()
        dispatched = Barrier(2)

        def simulated_gh(args, **kwargs):
            if args[1] == "workflow":
                title = args[-1].split("=", 1)[1]
                with lock:
                    children.append({"id": int(title.rsplit("-", 1)[1]), "display_title": title})
                dispatched.wait(timeout=5)
                raise subprocess.TimeoutExpired("gh", 30)
            with lock:
                return subprocess.CompletedProcess([], 0, json.dumps([{"workflow_runs": children}]))

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(resolve, "child.yml", "test/repo", str(i), "1",
                                   run=simulated_gh, sleep=Mock()) for i in (42, 43)]
            self.assertEqual([future.result() for future in futures], [42, 43])
        self.assertEqual(len(children), 2)
