"""Completion-bound GitHub wiring; no database or trading operations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests

from paper_trading_phase353_production_paper_position_sizing_risk_budget_allocation_engine import (
    AUTHORITY_REPOSITORY, AUTHORITY_WORKFLOW, load_explicit_producer_result,
)

CONSUMERS = {
    "353": "gpt-quant-v92-paper-trading-phase353-production-paper-position-sizing-risk-budget-allocation-engine.yml",
    "354": "gpt-quant-v92-paper-trading-phase354-production-paper-order-intent-simulated-execution-lifecycle-engine.yml",
    "355": "gpt-quant-v92-paper-trading-phase355-production-paper-position-reconciliation-execution-settlement-engine.yml",
}


def dispatch(workflow: str, inputs: dict[str, str]) -> None:
    if os.getenv("GITHUB_REPOSITORY") != AUTHORITY_REPOSITORY:
        raise RuntimeError("AUTHORITY_WRONG_REPOSITORY")
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("AUTHORITY_ARTIFACT_READ_TOKEN_REQUIRED")
    response = requests.post(
        f"https://api.github.com/repos/{AUTHORITY_REPOSITORY}/actions/workflows/{workflow}/dispatches",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        json={"ref": "main", "inputs": inputs}, timeout=30,
    )
    if response.status_code != 204:
        raise RuntimeError(f"AUTHORITY_DISPATCH_FAILED HTTP={response.status_code}")


def request_producer(consumer: str) -> None:
    if os.getenv("GITHUB_EVENT_NAME") != "schedule" or consumer not in CONSUMERS:
        raise RuntimeError("INVALID_SCHEDULED_AUTHORITY_REQUEST")
    # No run discovery: only the producer's eventual completion event selects a run.
    dispatch(AUTHORITY_WORKFLOW.rsplit("/", 1)[1], {"handoff_consumer": consumer})
    print("Producer requested; sizing is pending validated producer completion.")


def completed_producer_reference(event: dict) -> tuple[str, str, str]:
    run = event.get("workflow_run", {})
    if (os.getenv("GITHUB_EVENT_NAME") != "workflow_run" or event.get("action") != "completed"
            or event.get("repository", {}).get("full_name") != AUTHORITY_REPOSITORY
            or run.get("head_repository", {}).get("full_name") != AUTHORITY_REPOSITORY
            or run.get("path", "").split("@", 1)[0] != AUTHORITY_WORKFLOW
            or run.get("head_branch") != "main" or run.get("event") != "workflow_dispatch"
            or run.get("status") != "completed" or run.get("conclusion") != "success"):
        raise RuntimeError("INVALID_PRODUCER_COMPLETION_EVENT")
    for key in ("id", "run_attempt"):
        if type(run.get(key)) is not int or run[key] <= 0:
            raise RuntimeError("INVALID_PRODUCER_COMPLETION_IDENTITY")
    return str(run["id"]), str(run["run_attempt"]), run.get("head_sha", "")


def complete_handoff(event: dict) -> None:
    run_id, attempt, sha = completed_producer_reference(event)
    # Event identity wins; never trust inherited dispatch inputs on workflow_run.
    os.environ["PHASE353_PRODUCER_RUN_ID"] = run_id
    os.environ["PHASE353_PRODUCER_RUN_ATTEMPT"] = attempt
    result = load_explicit_producer_result()
    if result["canonical_authority"]["producer_commit_sha"] != sha:
        raise RuntimeError("PRODUCER_COMPLETION_SHA_MISMATCH")
    consumer = result.get("handoff_consumer")
    if consumer == "none":
        print("Producer requested no consumer handoff.")
        return
    if consumer not in CONSUMERS:
        raise RuntimeError("INVALID_AUTHORITY_HANDOFF_CONSUMER")
    # Target is covered by the producer result hash and the exact artifact digest.
    dispatch(CONSUMERS[consumer], {"producer_run_id": run_id, "producer_run_attempt": attempt})
    print(f"Dispatched Phase {consumer} with producer={run_id} attempt={attempt}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("request", "complete", "validate"))
    parser.add_argument("--consumer", choices=tuple(CONSUMERS))
    args = parser.parse_args()
    if args.operation == "request":
        request_producer(args.consumer)
    elif args.operation == "complete":
        complete_handoff(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")))
    else:
        load_explicit_producer_result()


if __name__ == "__main__":
    main()
