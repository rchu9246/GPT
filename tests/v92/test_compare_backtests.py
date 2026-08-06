import importlib.util,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[2]/'automation'/'v92'/'compare_backtests.py'; s=importlib.util.spec_from_file_location('m',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
class T(unittest.TestCase):
    def test_drawdown(self): self.assertGreater(m.qdelta('max_drawdown',-12,-8),0)
    def test_sharpe(self): self.assertGreater(m.qdelta('sharpe',1.2,1.5),0)
    def test_percent(self): self.assertEqual(m.norm({'total_return':0.24})['total_return'],24.0)
if __name__=='__main__': unittest.main()
