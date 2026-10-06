"""Restore the richest compatible append-only evidence, including the committed seed."""
import argparse, json, shutil
from pathlib import Path
from .ledger import AppendOnlyLedger

def restore(seed: Path, downloaded: Path, output: Path):
    artifact=downloaded if (downloaded/"forward_boundary.json").exists() else downloaded/"v10_forward_store"
    chosen=seed
    if artifact.exists():
        for name in ("forward_boundary.json","strategy_registry.json"):
            if json.loads((seed/name).read_text())!=json.loads((artifact/name).read_text()):
                raise RuntimeError("restored artifact conflicts with sealed seed")
        for p in (seed/"runs").glob("*.json"):
            other=artifact/"runs"/p.name
            if other.exists() and json.loads(p.read_text())!=json.loads(other.read_text()):
                raise RuntimeError("conflicting run history")
        paths=["benchmark.jsonl"]+[str(p.relative_to(seed)) for p in (seed/"accounts").glob("*.jsonl")]
        seed_richer=artifact_richer=True
        for name in paths:
            a=AppendOnlyLedger.load(seed/name).events
            b=AppendOnlyLedger.load(artifact/name).events
            if a[:min(len(a),len(b))]!=b[:min(len(a),len(b))]:
                raise RuntimeError("restored account hash-chain prefix conflict")
            seed_richer &= len(a)>=len(b)
            artifact_richer &= len(b)>=len(a)
        if artifact_richer and set(p.name for p in (seed/"runs").glob("*.json"))<=set(p.name for p in (artifact/"runs").glob("*.json")):
            chosen=artifact
        elif not seed_richer:
            raise RuntimeError("incomparable partial forward stores")
    shutil.copytree(chosen,output,dirs_exist_ok=True)
    print(f"Restored compatible forward evidence: {chosen.name}")

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--downloaded",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();restore(a.seed,a.downloaded,a.output)
