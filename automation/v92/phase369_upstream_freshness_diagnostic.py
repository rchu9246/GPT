"""Read-only Phase 3.6.9 evidence freshness diagnostic.

Never creates evidence or changes qualification state.
"""
import argparse
import json
from datetime import date


def assess(controller_date: str | None, evidence_date: str) -> dict:
    date.fromisoformat(evidence_date)
    if not controller_date:
        return {"status": "BLOCKED_MISSING_UPSTREAM", "safe_to_run_phase369": False,
                "reason": "No Phase 3.6.8 controller evidence exists for the requested date"}
    try:
        date.fromisoformat(controller_date)
    except (ValueError, TypeError):
        return {"status": "BLOCKED_INVALID_UPSTREAM_DATE", "safe_to_run_phase369": False,
                "reason": "Controller evidence date is invalid"}
    if controller_date != evidence_date:
        return {"status": "BLOCKED_STALE_UPSTREAM", "safe_to_run_phase369": False,
                "reason": f"Expected {evidence_date}, got {controller_date}"}
    return {"status": "DATE_MATCH_ONLY", "safe_to_run_phase369": False,
            "reason": "Date matches; provenance, master cycle, and safety gates remain unverified"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-date", required=True)
    parser.add_argument("--controller-date", default="")
    args = parser.parse_args()
    result = assess(args.controller_date, args.evidence_date)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "DATE_MATCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
