import json
import os
import subprocess
import sys
import time


def resolve(workflow, repository, parent_id, attempt, *, run=subprocess.run, sleep=time.sleep):
    correlation = f"phase378-parent-{parent_id}"
    endpoint = f"/repos/{repository}/actions/workflows/{workflow}/runs"
    query = f"{endpoint}?branch=main&event=workflow_dispatch&per_page=100"

    def lookup():
        response = run(["gh", "api", query], check=True, capture_output=True, text=True)
        matches = [row["id"] for row in json.loads(response.stdout)["workflow_runs"]
                   if row["display_title"] == correlation]
        if len(matches) > 1:
            raise ValueError("Multiple correlated Phase 3.7.8 runs")
        return matches[0] if matches else None

    existing = lookup()
    if existing is not None:
        return existing
    if attempt != "1":
        raise ValueError("Previous attempt has no verifiable child")
    response = run(["gh", "workflow", "run", workflow, "--ref", "main",
                    "-f", f"dispatch_correlation={correlation}"], stdout=sys.stderr)
    if response.returncode:
        print("Dispatch outcome uncertain. Checking correlation.", file=sys.stderr)
    for _ in range(30):
        try:
            child = lookup()
        except subprocess.CalledProcessError:
            child = None
        if child is not None:
            return child
        sleep(2)
    raise ValueError("Phase 3.7.8 dispatch could not be correlated")


if __name__ == "__main__":
    print(resolve(sys.argv[1], os.environ["GITHUB_REPOSITORY"],
                  os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]))
