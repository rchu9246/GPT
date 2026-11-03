"""Reproducible manual analysis; input files are read-only, output isolated."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from .baseline import audit,tree_hashes
from .research import Market,DataBlocked,evaluate,load_cache,write_once
from .specs import registry

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,required=True)
    p.add_argument('--baseline-zip',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-end',required=True)
    a=p.parse_args()
    output=a.output.resolve();source=a.baseline_root.resolve();cache=a.cache.resolve()
    if not output.name.startswith('v101_') or output==source or source in output.parents or output in source.parents or output==cache:
        raise DataBlocked('INDEPENDENT_RESEARCH_OUTPUT_REQUIRED')
    before=tree_hashes(source)
    frozen=json.loads(Path('config/v101_frozen_specs.json').read_text(encoding='utf-8-sig'))
    if frozen!=registry():raise DataBlocked('FROZEN_IMPLEMENTATION_OR_SPEC_CHANGED')
    baseline=audit(source,a.baseline_zip)
    market=Market(load_cache(cache),expected_end=a.expected_end)
    result=evaluate(market)
    if not result['folds']:raise DataBlocked('INSUFFICIENT_HISTORY_FOR_EMBARGOED_TESTS')
    result['baseline']=baseline
    result['registry']=frozen
    result['generated_at']=datetime.now(timezone.utc).isoformat()
    if tree_hashes(source)!=before:raise DataBlocked('SEALED_DATA_CHANGED')
    # Research artifacts are versioned/immutable per output directory, never forward history.
    write_once(output/'comparison.json',result)
    print(json.dumps(dict(output=str(output),sessions=len(market.sessions),folds=len(result['folds']),
        comparisons=len(result['results']),baseline_reconciled=True,promotion_enabled=False)))

if __name__=='__main__':main()
