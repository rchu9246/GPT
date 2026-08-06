from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v9", type=Path, required=True)
    parser.add_argument("--v91", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    v9 = load(args.v9)
    v91 = load(args.v91)

    production = bool(
        v9.get("production_evidence")
        and v91.get("production_evidence")
    )

    payload = {
        "adapter_version": "3.4",
        "source_type": "production_backtest" if production else "invalid_production_evidence",
        "production_evidence": production,
        "v9": v9,
        "v91": v91,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if production else 2


if __name__ == "__main__":
    raise SystemExit(main())
