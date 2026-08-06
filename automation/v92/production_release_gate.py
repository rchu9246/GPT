from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    approved = bool(report.get("passed"))

    payload = {
        "approved": approved,
        "decision": "APPROVE" if approved else "BLOCK",
        "reason": (
            "All production research gates passed"
            if approved
            else "One or more production research gates failed"
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(payload["decision"], "-", payload["reason"])
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
