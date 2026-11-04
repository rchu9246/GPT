"""Isolated fault-injection tests for Phase 3.7.6 evidence resolution.

Never runs the promotion gate or contacts GitHub.
"""
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/gpt-quant-v92-paper-trading-phase376-production-paper-multi-cycle-qualification-promotion-gate.yml"


def resolver_script():
    s = WORKFLOW.read_text()
    a = s.index("      - name: Resolve latest Phase 3.7.5 evidence")
    b = s.index("      - name: Execute Phase 3.7.6", a)
    raw = s[a:b].split("        run: |", 1)[1]
    return "\n".join(line[10:] if line.startswith("          ") else line for line in raw.splitlines())


class ResolverFaultTests(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bin").mkdir()
            (root / "artifacts").mkdir()
            counter = root / "calls"
            mock = root / "bin/gh"
            mock.write_text("""#!/usr/bin/env python3
import json, os, sys, zipfile
from pathlib import Path
scenario=os.environ['SCENARIO']
counter=Path(os.environ['CALL_COUNTER'])
n=int(counter.read_text()) if counter.exists() else 0
n+=1
counter.write_text(str(n))
endpoint=next((x for x in sys.argv if x.startswith('/repos/')), '')
if scenario == 'always503' or (scenario == 'recover503' and n == 1):
    print('gh: HTTP 503',file=sys.stderr)
    sys.exit(1)
if '/workflows/' in endpoint:
    print(json.dumps({'workflow_runs':[{'id':123}]}))
elif '/runs/' in endpoint and '/artifacts' in endpoint:
    print(json.dumps({'artifacts': [] if scenario == 'missing' else [{'id':456,'name':'phase375-production-paper-multi-cycle-stability-evidence','expired':False}]}))
elif '/artifacts/' in endpoint and endpoint.endswith('/zip'):
    if scenario == 'corrupt':
        sys.stdout.buffer.write(b'not a zip')
    else:
        import io
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('phase375_result.json','{}')
        sys.stdout.buffer.write(b.getvalue())
else:
    sys.exit(2)
""")
            mock.chmod(0o755)
            sleep = root / "bin/sleep"
            sleep.write_text("#!/bin/sh\nexit 0\n")
            sleep.chmod(0o755)
            env = os.environ.copy()
            env.update(PATH=str(root / "bin") + os.pathsep + env["PATH"],
                       SCENARIO=scenario, CALL_COUNTER=str(counter),
                       GITHUB_REPOSITORY="rchu9246/GPT")
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", resolver_script()],
                                    cwd=root, env=env, text=True, capture_output=True, timeout=20)
            output = root / "artifacts/phase376/input/phase375_result.json"
            return result, output.exists(), int(counter.read_text()) if counter.exists() else 0

    def test_transient_503_recovers(self):
        result, exists, calls = self.run_case("recover503")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(exists)
        self.assertGreaterEqual(calls, 4)

    def test_permanent_503_blocks(self):
        result, exists, calls = self.run_case("always503")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(exists)
        self.assertEqual(calls, 4)

    def test_missing_artifact_does_not_create_evidence(self):
        result, exists, _ = self.run_case("missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(exists)

    def test_corrupt_archive_blocks(self):
        result, exists, _ = self.run_case("corrupt")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(exists)


if __name__ == "__main__":
    unittest.main()
