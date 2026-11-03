"""Portable all-suite runner, including legacy discovery/import compatibility."""
from pathlib import Path
import sys,unittest
root=Path(__file__).resolve().parents[1]
if sys.platform=='win32' and not str(root).startswith('\\\\?\\'):
    root=Path('\\\\?\\'+str(root))
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests/v10'))
success=True
for folder in ('tests','tests/v92'):
    suite=unittest.TestLoader().discover(str(root/folder))
    success=unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() and success
raise SystemExit(not success)
