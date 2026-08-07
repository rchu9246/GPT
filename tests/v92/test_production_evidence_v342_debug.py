import importlib.util,sys,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[2]/'automation/v92/production_evidence_adapter_v342_debug.py'
s=importlib.util.spec_from_file_location('d',p);d=importlib.util.module_from_spec(s);sys.modules['d']=d;s.loader.exec_module(d)
class T(unittest.TestCase):
 def test_mask(self): self.assertIn('***',d.mask('API_KEY','abcdefghijkl'))
 def test_tree(self): self.assertIn('<MISSING>',d.tree('not-existing')[0])
if __name__=='__main__':unittest.main()
