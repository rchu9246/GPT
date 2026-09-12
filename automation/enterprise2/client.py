from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote

import requests

class SupabaseRestClient:
    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.url or not self.key:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def endpoint(self, table: str, query: str = "") -> str:
        return f"{self.url}/rest/v1/{table}" + (f"?{query}" if query else "")

    def _raise_for_status(
        self, response: requests.Response, method: str, table: str
    ) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError:
            # Do not expose the host, query, request payload, or headers.
            path = table if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) else "[redacted]"
            message = f"HTTP {response.status_code} {method} /rest/v1/{path}: {response.text}"
            secrets = {self.key, self.url}
            secrets.update(
                value for name, value in os.environ.items()
                if re.search(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH", name, re.I)
            )
            for secret in sorted(filter(None, secrets), key=len, reverse=True):
                for encoded in (secret, quote(secret, safe=""), json.dumps(secret)[1:-1]):
                    message = message.replace(encoded, "[redacted]")
            # Also remove recognizable credentials echoed by an upstream service.
            message = re.sub(r"https?://[^\s\"'<>]+", "[redacted-url]", message)
            message = re.sub(
                r"(?i)\bBearer\s+[^\s\"',;]+", "Bearer [redacted]", message
            )
            message = re.sub(
                r"(?i)(\b(?:authorization|apikey|api_key|access_token|refresh_token|"
                r"password|secret)\b[\"']?\s*[:=]\s*)"
                r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)",
                r'\1"[redacted]"', message,
            )
            message = re.sub(
                r"\b(?:eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|"
                r"sb_(?:secret|publishable)_[A-Za-z0-9_-]+)\b",
                "[redacted]", message,
            )
            # Suppress the original exception, which includes the full URL.
            raise requests.HTTPError(
                message, response=response, request=response.request
            ) from None

    def get(self, table: str, query: str = "") -> list[dict[str, Any]]:
        response = requests.get(
            self.endpoint(table, query),
            headers=self.headers,
            timeout=45,
        )
        self._raise_for_status(response, "GET", table)
        return response.json()

    def insert(self, table: str, payload: Any) -> list[dict[str, Any]]:
        headers = {**self.headers, "Prefer": "return=representation"}
        response = requests.post(
            self.endpoint(table),
            headers=headers,
            json=payload,
            timeout=45,
        )
        self._raise_for_status(response, "POST", table)
        return response.json()

    def upsert(
        self,
        table: str,
        payload: Any,
        conflict: str,
    ) -> list[dict[str, Any]]:
        headers = {
            **self.headers,
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        response = requests.post(
            self.endpoint(table, f"on_conflict={quote(conflict)}"),
            headers=headers,
            json=payload,
            timeout=45,
        )
        self._raise_for_status(response, "POST", table)
        return response.json()

    def patch(
        self,
        table: str,
        query: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        headers = {**self.headers, "Prefer": "return=representation"}
        response = requests.patch(
            self.endpoint(table, query),
            headers=headers,
            json=payload,
            timeout=45,
        )
        self._raise_for_status(response, "PATCH", table)
        return response.json()
