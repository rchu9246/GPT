import importlib.util,sys,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[2]/'automation/v92/production_evidence_adapter_v341.py';s=importlib.util.spec_from_file_location('a',p);a=importlib.util.module_from_spec(s);sys.modules['a']=a;s.loader.exec_module(a)
class T(unittest.TestCase):
 def test_derive(self):
  r=a.derive([{'pnl':100},{'pnl':-50},{'pnl':200}],[{'equity':1000},{'equity':1050},{'equity':1100}]);self.assertEqual(r['profit_factor'],6);self.assertAlmostEqual(r['total_return'],10)
 def test_mdd(self):self.assertAlmostEqual(a.mdd([100,120,90]),-25)
if __name__=='__main__':unittest.main()
