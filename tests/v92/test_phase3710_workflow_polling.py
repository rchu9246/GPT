"""Offline regression tests for Phase 3.7.10 GitHub run-state polling."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

WORKFLOW = Path(__file__).resolve().parents[2] / '.github/workflows/gpt-quant-v92-paper-trading-phase3710-production-paper-multi-day-qualification-accumulation-automatic-promotion-transition.yml'


class Phase3710PollingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = WORKFLOW.read_text(encoding='utf-8')
        cls.loops = re.findall(r'(?ms)^ *for i in \$\(seq 1 180\); do\n.*?^ *done', source)
        assert len(cls.loops) == 2, 'Expected both Phase 3.7.8 and promotion-transition polling loops'

    def test_single_atomic_status_conclusion_query(self):
        for loop in self.loops:
            with self.subTest(loop=loop[:80]):
                self.assertEqual(loop.count('gh api -H "Accept: application/vnd.github+json"'), 1)
                self.assertIn("--jq '[.status, (.conclusion // \"\")] | @tsv'", loop)
                self.assertIn('if [ "$status" = "completed" ] && [ -n "$conclusion" ]; then', loop)

    def _run_mocked_poll(self, loop, states):
        with tempfile.TemporaryDirectory() as tmp:
            mock = Path(tmp) / 'gh'
            mock.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
p = Path(os.environ['MOCK_COUNTER'])
n = int(p.read_text()) if p.exists() else 0
states = os.environ['MOCK_STATES'].split('|')
p.write_text(str(n + 1))
print(states[min(n, len(states) - 1)].replace('\\\\t', '\\t'))
''', encoding='utf-8')
            mock.chmod(0o755)
            counter = Path(tmp) / 'counter'
            script = '\n'.join([
                'set -euo pipefail',
                'seq() { echo 1; echo 2; echo 3; }',
                'sleep() { :; }',
                'GITHUB_REPOSITORY=rchu9246/GPT',
                'run_id=123',
                'label=Child',
                'poll() {',
                loop,
                '  return 1',
                '}',
                'poll',
            ])
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'],
                       MOCK_COUNTER=str(counter), MOCK_STATES='|'.join(states))
            result = subprocess.run(['bash', '-c', script], env=env,
                                    capture_output=True, text=True, check=False)
            return result.returncode, int(counter.read_text()), result.stdout

    def test_completed_pending_then_success_is_not_failure(self):
        for loop in self.loops:
            with self.subTest(loop=loop[:80]):
                code, calls, output = self._run_mocked_poll(loop, ['completed\\t', 'completed\\tsuccess'])
                self.assertEqual(code, 0, output)
                self.assertEqual(calls, 2)

    def test_completed_failure_blocks(self):
        for loop in self.loops:
            with self.subTest(loop=loop[:80]):
                code, calls, output = self._run_mocked_poll(loop, ['completed\\tfailure'])
                self.assertNotEqual(code, 0, output)
                self.assertEqual(calls, 1)

    def test_permanently_missing_conclusion_times_out(self):
        for loop in self.loops:
            with self.subTest(loop=loop[:80]):
                code, calls, output = self._run_mocked_poll(loop, ['completed\\t'])
                self.assertNotEqual(code, 0, output)
                self.assertEqual(calls, 3)


if __name__ == '__main__':
    unittest.main()
