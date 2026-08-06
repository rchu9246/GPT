from pathlib import Path
import argparse,json,py_compile
p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path('.')); a=p.parse_args(); errors=[]
for f in a.root.rglob('*.py'):
    if '.git' in f.parts or '__pycache__' in f.parts or 'venv' in f.parts or '.venv' in f.parts: continue
    try: py_compile.compile(str(f),doraise=True)
    except Exception as e: errors.append(f'{f}: {e}')
for f in a.root.rglob('*.json'):
    if '.git' in f.parts: continue
    try: json.loads(f.read_text(encoding='utf-8-sig'))
    except Exception as e: errors.append(f'{f}: {e}')
if errors:
    print('\n'.join(errors)); raise SystemExit(1)
print('Build validation passed')
