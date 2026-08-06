from __future__ import annotations
import importlib.util,sys,tempfile,unittest
from pathlib import Path
path=Path(__file__).resolve().parents[2]/"automation"/"v92"/"real_backtest_adapter.py"
spec=importlib.util.spec_from_file_location("real_backtest_adapter",path)
module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
class Phase2Tests(unittest.TestCase):
    def test_required_metrics(self): self.assertIn("sharpe",module.REQUIRED_METRICS)
    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError): module.load_metrics(Path(d)/"x.json")
if __name__=="__main__": unittest.main()
