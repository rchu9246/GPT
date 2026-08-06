from __future__ import annotations
import importlib.util,sys,tempfile,unittest,csv
from pathlib import Path

def load(name):
    path=Path(__file__).resolve().parents[2]/"automation"/"v92"/f"{name}.py"
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod; spec.loader.exec_module(mod); return mod

resolver=load("research_input_resolver_v31")
wfa=load("walk_forward_analysis_v31")

class Tests(unittest.TestCase):
    def test_drawdown(self): self.assertAlmostEqual(wfa.max_drawdown([100,120,90]),-25)
    def test_extended_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); resolver.generate_extended_smoke(out,points=40,trades=20)
            result=resolver.validate_outputs(out,30,20)
            self.assertTrue(result["sufficient"])
            self.assertEqual(result["counts"]["v91_equity_rows"],40)

if __name__=="__main__": unittest.main()
