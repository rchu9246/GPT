from __future__ import annotations

from .module import ModuleResult, QuantModule

class SystemHealthModule(QuantModule):
    module_key = "system_health"
    version = "2.0.0"

    def run(self, run_date: str) -> ModuleResult:
        issues: list[str] = []

        checks = {
            "data_score": self._score_table("daily_prices"),
            "signal_score": self._score_table("signals"),
            "execution_score": self._score_table("trade_orders_v13"),
            "portfolio_score": self._score_table("paper_accounts_v13"),
            "risk_score": self._score_table("risk_snapshots_v19"),
            "automation_score": self._score_table("institutional_reports_v20"),
        }

        for key, score in checks.items():
            if score < 100:
                issues.append(f"{key} is incomplete")

        overall = sum(checks.values()) / len(checks)
        status = "HEALTHY" if overall >= 85 else "DEGRADED" if overall >= 60 else "CRITICAL"

        self.client.upsert(
            "quant_system_health",
            {
                "account_name": self.account_name,
                "health_date": run_date,
                "overall_score": overall,
                **checks,
                "status": status,
                "issues": issues,
            },
            "account_name,health_date",
        )

        return ModuleResult(
            module_key=self.module_key,
            status="SUCCESS",
            summary={
                "overall_score": overall,
                "status": status,
                "issues": issues,
            },
        )

    def _score_table(self, table: str) -> float:
        try:
            rows = self.client.get(table, "select=id&limit=1")
            return 100.0 if rows else 50.0
        except Exception:
            return 0.0
