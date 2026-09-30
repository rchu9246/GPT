"""Dormant Phase 3.5.3 durable handoff receipt adapter.

No production workflow imports this module. Dispatch callers must claim first and
may dispatch only when the database returns CLAIM_ACQUIRED. A GitHub HTTP 204 may
then be recorded as DISPATCH_ACCEPTED; it never represents downstream completion.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests


TABLE = "phase353_handoff_receipts"
CLAIM_RPC = "claim_phase353_handoff"
ACCEPT_RPC = "mark_phase353_handoff_dispatch_accepted"


def _connection(base_url: str | None, service_role_key: str | None) -> tuple[str, str]:
    url = (base_url or os.getenv("SUPABASE_URL", "")).strip().rstrip("/")
    key = (service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return url, key


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _one(response: requests.Response, operation: str) -> dict[str, Any]:
    if not response.ok:
        raise RuntimeError(f"{operation} failed with HTTP {response.status_code}: {response.text[:500]}")
    payload = response.json()
    if isinstance(payload, list):
        if len(payload) != 1:
            raise RuntimeError(f"{operation} returned {len(payload)} rows; expected one")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} returned an invalid payload")
    return payload


def claim_handoff(*, repository: str, producer_workflow: str, producer_run_id: int,
                  producer_run_attempt: int, consumer: str, producer_sha: str,
                  business_date: str | None = None, authority_hash: str | None = None,
                  base_url: str | None = None, service_role_key: str | None = None,
                  session: Any = requests) -> dict[str, Any]:
    """Atomically claim a producer tuple; only CLAIM_ACQUIRED permits dispatch."""
    url, key = _connection(base_url, service_role_key)
    response = session.post(
        f"{url}/rest/v1/rpc/{CLAIM_RPC}", headers=_headers(key), timeout=30,
        json={"p_repository": repository, "p_producer_workflow": producer_workflow,
              "p_producer_run_id": producer_run_id,
              "p_producer_run_attempt": producer_run_attempt, "p_consumer": consumer,
              "p_producer_sha": producer_sha, "p_business_date": business_date,
              "p_authority_hash": authority_hash},
    )
    return _one(response, "handoff claim")


def mark_dispatch_accepted(*, receipt_id: int, repository: str, producer_workflow: str,
                           producer_run_id: int, producer_run_attempt: int, consumer: str,
                           producer_sha: str, base_url: str | None = None,
                           service_role_key: str | None = None,
                           session: Any = requests) -> dict[str, Any]:
    """Record GitHub dispatch HTTP 204 as acceptance, never completion."""
    url, key = _connection(base_url, service_role_key)
    response = session.post(
        f"{url}/rest/v1/rpc/{ACCEPT_RPC}", headers=_headers(key), timeout=30,
        json={"p_receipt_id": receipt_id, "p_repository": repository,
              "p_producer_workflow": producer_workflow, "p_producer_run_id": producer_run_id,
              "p_producer_run_attempt": producer_run_attempt, "p_consumer": consumer,
              "p_producer_sha": producer_sha},
    )
    return _one(response, "dispatch acceptance transition")


def read_receipt(*, repository: str, producer_workflow: str, producer_run_id: int,
                 producer_run_attempt: int, consumer: str, base_url: str | None = None,
                 service_role_key: str | None = None,
                 session: Any = requests) -> dict[str, Any] | None:
    """Read one exact receipt with the trusted execution role."""
    url, key = _connection(base_url, service_role_key)
    params = {"repository": f"eq.{repository}", "producer_workflow": f"eq.{producer_workflow}",
              "producer_run_id": f"eq.{producer_run_id}",
              "producer_run_attempt": f"eq.{producer_run_attempt}",
              "consumer": f"eq.{consumer}", "select": "*", "limit": "2"}
    response = session.get(
        f"{url}/rest/v1/{quote(TABLE, safe='')}", headers=_headers(key), params=params, timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"receipt read failed with HTTP {response.status_code}: {response.text[:500]}")
    rows = response.json()
    if not isinstance(rows, list) or len(rows) > 1:
        raise RuntimeError("receipt read violated unique identity")
    return rows[0] if rows else None
