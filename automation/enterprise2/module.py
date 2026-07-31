from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .client import SupabaseRestClient

@dataclass
class ModuleResult:
    module_key: str
    status: str
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

class QuantModule(ABC):
    module_key = "base"
    version = "2.0.0"

    def __init__(self, client: SupabaseRestClient, account_name: str) -> None:
        self.client = client
        self.account_name = account_name

    @abstractmethod
    def run(self, run_date: str) -> ModuleResult:
        raise NotImplementedError

    def audit(
        self,
        run_id: str,
        event_type: str,
        message: str,
        *,
        severity: str = "INFO",
        entity_type: str | None = None,
        entity_key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.client.insert(
            "quant_audit_logs",
            {
                "account_name": self.account_name,
                "run_id": run_id,
                "module_key": self.module_key,
                "event_type": event_type,
                "severity": severity,
                "entity_type": entity_type,
                "entity_key": entity_key,
                "message": message,
                "details": details or {},
            },
        )
