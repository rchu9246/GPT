from __future__ import annotations

import os
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

    def get(self, table: str, query: str = "") -> list[dict[str, Any]]:
        response = requests.get(
            self.endpoint(table, query),
            headers=self.headers,
            timeout=45,
        )
        response.raise_for_status()
        return response.json()

    def insert(self, table: str, payload: Any) -> list[dict[str, Any]]:
        headers = {**self.headers, "Prefer": "return=representation"}
        response = requests.post(
            self.endpoint(table),
            headers=headers,
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
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
        response.raise_for_status()
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
        response.raise_for_status()
        return response.json()
