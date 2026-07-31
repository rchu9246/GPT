from __future__ import annotations

import math
from typing import Any

from .module import ModuleResult, QuantModule

def number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError):
        return fallback

class LegacyDecisionBridge(QuantModule):
    module_key = "legacy_decision_bridge"
    version = "2.0.0"

    def run(self, run_date: str) -> ModuleResult:
        migrated = 0

        sources = [
            {
                "table": "trading_directives_v22",
                "scope": "PORTFOLIO",
                "entity_type": "ACCOUNT",
                "module_key": "director",
                "engine_version": "22",
                "date_field": "directive_date",
                "action_field": "directive",
                "score_field": "confidence",
                "confidence_field": "confidence",
                "risk_field": None,
                "weight_field": "deploy_capital_pct",
                "cash_field": "target_cash_pct",
                "rationale_field": "rationale",
            },
            {
                "table": "investment_council_decisions_v21",
                "scope": "SECURITY",
                "entity_type": "STOCK",
                "module_key": "council",
                "engine_version": "21",
                "date_field": "council_date",
                "action_field": "final_decision",
                "score_field": "consensus_score",
                "confidence_field": "agreement_pct",
                "risk_field": None,
                "weight_field": "target_weight",
                "cash_field": None,
                "rationale_field": "cio_memo",
            },
            {
                "table": "ai_committee_decisions_v18",
                "scope": "SECURITY",
                "entity_type": "STOCK",
                "module_key": "ai_fund",
                "engine_version": "18",
                "date_field": "decision_date",
                "action_field": "decision",
                "score_field": "committee_score",
                "confidence_field": None,
                "risk_field": None,
                "weight_field": "target_weight",
                "cash_field": None,
                "rationale_field": "memo",
            },
        ]

        for source in sources:
            try:
                rows = self.client.get(
                    source["table"],
                    f"account_name=eq.{self.account_name}"
                    f"&{source['date_field']}=eq.{run_date}&limit=500",
                )
            except Exception:
                continue

            for row in rows:
                symbol = str(row.get("symbol") or self.account_name)
                payload = {
                    "account_name": self.account_name,
                    "decision_date": run_date,
                    "decision_scope": source["scope"],
                    "entity_type": source["entity_type"],
                    "entity_key": symbol,
                    "module_key": source["module_key"],
                    "engine_version": source["engine_version"],
                    "action": str(row.get(source["action_field"]) or "UNKNOWN"),
                    "score": number(row.get(source["score_field"]))
                    if source["score_field"]
                    else None,
                    "confidence": number(row.get(source["confidence_field"]))
                    if source["confidence_field"]
                    else None,
                    "risk_score": number(row.get(source["risk_field"]))
                    if source["risk_field"]
                    else None,
                    "target_weight": number(row.get(source["weight_field"]))
                    if source["weight_field"]
                    else None,
                    "target_cash_pct": number(row.get(source["cash_field"]))
                    if source["cash_field"]
                    else None,
                    "rationale": str(
                        row.get(source["rationale_field"])
                        or f"Migrated from {source['table']}"
                    ),
                    "evidence": row,
                    "source_record": {
                        "legacy_table": source["table"],
                        "legacy_id": row.get("id"),
                    },
                }
                self.client.upsert(
                    "quant_decisions",
                    payload,
                    (
                        "account_name,decision_date,decision_scope,"
                        "entity_type,entity_key,module_key,engine_version"
                    ),
                )
                migrated += 1

        return ModuleResult(
            module_key=self.module_key,
            status="SUCCESS",
            summary={"migrated_decisions": migrated},
        )

class LegacyPortfolioBridge(QuantModule):
    module_key = "legacy_portfolio_bridge"
    version = "2.0.0"

    def run(self, run_date: str) -> ModuleResult:
        positions = self.client.get(
            "paper_positions_v13",
            f"account_name=eq.{self.account_name}&limit=1000",
        )
        migrated = 0

        for row in positions:
            self.client.upsert(
                "quant_positions",
                {
                    "account_name": self.account_name,
                    "symbol": str(row.get("symbol")),
                    "quantity": int(row.get("quantity") or 0),
                    "average_price": number(row.get("average_price")),
                    "cost_basis": number(row.get("cost_basis")),
                    "last_price": number(row.get("last_price")),
                    "market_value": number(row.get("market_value")),
                    "unrealized_pnl": number(row.get("unrealized_pnl")),
                    "realized_pnl": number(row.get("realized_pnl")),
                    "high_watermark_price": number(
                        row.get("high_watermark_price")
                    ),
                    "holding_days": int(row.get("holding_days") or 0),
                    "status": "OPEN",
                    "metadata": {
                        "legacy_table": "paper_positions_v13",
                        "legacy_id": row.get("id"),
                    },
                },
                "account_name,symbol",
            )
            migrated += 1

        snapshots = self.client.get(
            "paper_equity_snapshots_v13",
            f"account_name=eq.{self.account_name}"
            f"&snapshot_date=eq.{run_date}&limit=1",
        )
        if snapshots:
            row = snapshots[0]
            risk_rows = []
            try:
                risk_rows = self.client.get(
                    "risk_snapshots_v19",
                    f"account_name=eq.{self.account_name}"
                    f"&snapshot_date=eq.{run_date}&limit=1",
                )
            except Exception:
                pass
            risk = risk_rows[0] if risk_rows else {}

            equity = number(row.get("equity"))
            market_value = number(row.get("market_value"))
            self.client.upsert(
                "quant_portfolio_snapshots",
                {
                    "account_name": self.account_name,
                    "snapshot_date": run_date,
                    "equity": equity,
                    "cash": number(row.get("cash")),
                    "market_value": market_value,
                    "gross_exposure_pct": (
                        market_value / equity * 100 if equity else 0
                    ),
                    "net_exposure_pct": (
                        market_value / equity * 100 if equity else 0
                    ),
                    "realized_pnl": number(row.get("realized_pnl")),
                    "unrealized_pnl": number(row.get("unrealized_pnl")),
                    "daily_return": number(row.get("daily_return")),
                    "total_return": number(row.get("total_return")),
                    "max_drawdown": number(risk.get("max_drawdown")),
                    "var_95": number(risk.get("daily_var_95")),
                    "expected_shortfall_95": number(
                        risk.get("expected_shortfall_95")
                    ),
                    "sharpe": number(risk.get("sharpe_20d")),
                    "positions_count": int(row.get("positions_count") or 0),
                    "metadata": {
                        "legacy_snapshot_id": row.get("id"),
                        "legacy_risk_id": risk.get("id"),
                    },
                },
                "account_name,snapshot_date",
            )

        return ModuleResult(
            module_key=self.module_key,
            status="SUCCESS",
            summary={"migrated_positions": migrated},
        )
