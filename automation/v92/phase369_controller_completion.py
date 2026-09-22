"""Consume one exact, completed Phase 3.6.8 run. No run discovery or fallback."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile

import requests

from paper_trading_phase369_production_paper_autonomous_daily_evidence_lifecycle_governance_engine import main as govern, stable_hash

REPOSITORY = "rchu9246/GPT"
WORKFLOW = ".github/workflows/gpt-quant-v92-paper-trading-phase368-production-paper-daily-autonomous-operations-controller.yml"
CONTRACT = "PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER"
FINAL_STATES = {"COMPLETED", "COMPLETED_WITH_OBSERVATION", "FAIL_CLOSED", "BLOCKED", "FAILED"}


def completion_reference(event: dict) -> tuple[str, str, str]:
    run = event.get("workflow_run", {})
    if (os.getenv("GITHUB_EVENT_NAME") != "workflow_run" or event.get("action") != "completed"
            or event.get("repository", {}).get("full_name") != REPOSITORY
            or run.get("head_repository", {}).get("full_name") != REPOSITORY
            or str(run.get("path", "")).split("@", 1)[0] != WORKFLOW
            or run.get("head_branch") != "main" or run.get("event") != "workflow_dispatch"
            or run.get("status") != "completed" or run.get("conclusion") not in {"success", "failure"}):
        raise RuntimeError("INVALID_CONTROLLER_COMPLETION_EVENT")
    for key in ("id", "run_attempt"):
        if type(run.get(key)) is not int or run[key] < 1:
            raise RuntimeError("INVALID_CONTROLLER_RUN_IDENTITY")
    return str(run["id"]), str(run["run_attempt"]), str(run.get("head_sha") or "")


def load_exact_artifact(event: dict) -> dict:
    run_id, attempt, sha = completion_reference(event)
    token = os.getenv("GH_TOKEN", "")
    if not token:
        raise RuntimeError("CONTROLLER_ARTIFACT_READ_TOKEN_REQUIRED")
    base = f"https://api.github.com/repos/{REPOSITORY}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}

    def get_json(path: str, params=None) -> dict:
        response = requests.get(base + path, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"CONTROLLER_METADATA_UNAVAILABLE HTTP={response.status_code}")
        return response.json()

    run = get_json(f"/actions/runs/{run_id}/attempts/{attempt}")
    if (str(run.get("id")) != run_id or str(run.get("run_attempt")) != attempt
            or run.get("repository", {}).get("full_name") != REPOSITORY
            or run.get("head_repository", {}).get("full_name") != REPOSITORY
            or str(run.get("path", "")).split("@", 1)[0] != WORKFLOW
            or run.get("head_branch") != "main" or run.get("event") != "workflow_dispatch"
            or run.get("status") != "completed" or run.get("conclusion") != event["workflow_run"]["conclusion"]
            or run.get("head_sha") != sha or not re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise RuntimeError("CONTROLLER_EVENT_RUN_MISMATCH")

    artifacts = []
    for page in range(1, 1001):
        listing = get_json(f"/actions/runs/{run_id}/artifacts", {"per_page": 100, "page": page})
        entries = listing["artifacts"]
        artifacts.extend(entries)
        if len(artifacts) == listing["total_count"]:
            break
        if not entries or len(artifacts) > listing["total_count"]:
            raise RuntimeError("AMBIGUOUS_CONTROLLER_ARTIFACT_LIST")
    else:
        raise RuntimeError("INCOMPLETE_CONTROLLER_ARTIFACT_LIST")
    name = f"phase368-controller-{run_id}-attempt-{attempt}"
    matches = [artifact for artifact in artifacts if artifact.get("name") == name]
    if len(matches) != 1 or matches[0].get("expired") is not False:
        raise RuntimeError("MISSING_EXPIRED_OR_MULTIPLE_CONTROLLER_ARTIFACT")
    artifact = matches[0]
    if (type(artifact.get("id")) is not int or str(artifact.get("workflow_run", {}).get("id")) != run_id
            or artifact["workflow_run"].get("head_sha") != sha):
        raise RuntimeError("CONTROLLER_ARTIFACT_PROVENANCE_MISMATCH")
    response = requests.get(base + f"/actions/artifacts/{artifact['id']}/zip", headers=headers, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"CONTROLLER_ARTIFACT_UNAVAILABLE HTTP={response.status_code}")
    if artifact.get("digest") != "sha256:" + hashlib.sha256(response.content).hexdigest():
        raise RuntimeError("CONTROLLER_ARTIFACT_DIGEST_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        matches = [entry for entry in archive.infolist()
                   if entry.filename == "daily_autonomous_controller_evidence.json"]
        if len(matches) != 1 or matches[0].file_size > 1024 * 1024:
            raise RuntimeError("MISSING_OR_MULTIPLE_CONTROLLER_RESULT")
        result = json.loads(archive.read(matches[0]))
    result_hash = result.pop("artifact_sha256", None)
    if result_hash != stable_hash(result):
        raise RuntimeError("CONTROLLER_RESULT_HASH_MISMATCH")
    result["artifact_sha256"] = result_hash
    if (result.get("contract") != CONTRACT or result.get("strategy_version") != "V9.1"
            or str(result.get("controller_run_id")) != run_id
            or str(result.get("controller_run_attempt")) != attempt
            or result.get("controller_state") not in FINAL_STATES
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(result.get("business_date")))
            or not re.fullmatch(r"[1-9]\d*", str(result.get("producer_run_id")))
            or not re.fullmatch(r"[1-9]\d*", str(result.get("producer_run_attempt")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(result.get("canonical_authority_hash")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(result.get("controller_input_sha256")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(result.get("controller_evidence_sha256")))):
        raise RuntimeError("INVALID_CONTROLLER_RESULT_IDENTITY")
    if (run["conclusion"] == "success") != (result["controller_state"] in {"COMPLETED", "COMPLETED_WITH_OBSERVATION"}):
        raise RuntimeError("CONTROLLER_RESULT_CONCLUSION_MISMATCH")
    return result


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    raise SystemExit(govern(load_exact_artifact(event)))
