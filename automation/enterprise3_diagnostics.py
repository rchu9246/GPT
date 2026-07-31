from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REQUIRED_ENV = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
REQUIRED_FILES = [
    "package.json",
    "requirements.txt",
    "automation/enterprise3_stable.py",
    "src/app/App.tsx",
]

def result(name: str, status: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details,
    }

def main() -> None:
    checks: list[dict[str, Any]] = []
    root = Path(__file__).resolve().parents[1]

    for rel in REQUIRED_FILES:
        path = root / rel
        checks.append(
            result(
                f"file:{rel}",
                "PASS" if path.exists() else "FAIL",
                "File exists." if path.exists() else "Required file is missing.",
            )
        )

    for key in REQUIRED_ENV:
        present = bool(os.environ.get(key))
        checks.append(
            result(
                f"env:{key}",
                "PASS" if present else "FAIL",
                "Environment variable is configured."
                if present
                else "Environment variable is missing.",
            )
        )

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if url and key:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
        }
        try:
            response = requests.get(
                f"{url}/rest/v1/quant_stable_readiness?select=*",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            ready = bool(payload and payload[0].get("all_required_objects_ready"))
            checks.append(
                result(
                    "supabase:stable_readiness",
                    "PASS" if ready else "FAIL",
                    "Stable readiness view is healthy."
                    if ready
                    else "Stable readiness view reports missing objects.",
                    payload=payload,
                )
            )
        except Exception as exc:
            checks.append(
                result(
                    "supabase:stable_readiness",
                    "FAIL",
                    f"Supabase readiness request failed: {exc}",
                )
            )

    failed = [c for c in checks if c["status"] == "FAIL"]
    report = {
        "version": "3.0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "PASS" if not failed else "FAIL",
        "checks": checks,
    }

    report_path = root / "enterprise3-diagnostics.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
