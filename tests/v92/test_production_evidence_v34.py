from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def load(name: str):
    path = (
        Path(__file__).resolve().parents[2]
        / "automation"
        / "v92"
        / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ADAPTER = load("production_evidence_adapter_v34")


class ProductionEvidenceAdapterTests(unittest.TestCase):
    def test_decimal_percent_conversion(self) -> None:
        result = ADAPTER.normalize_metrics({
            "return": 0.24,
            "max_dd": -0.12,
            "sharpe_ratio": 1.5,
            "pf": 1.6,
            "trade_count": 100,
        })
        self.assertEqual(result["total_return"], 24.0)
        self.assertEqual(result["max_drawdown"], -12.0)

    def test_metric_aliases(self) -> None:
        result = ADAPTER.normalize_metrics({
            "net_return": 18,
            "drawdown": -9,
            "sharpe": 1.8,
            "profit_factor": 1.7,
            "trades": 80,
        })
        self.assertEqual(result["total_trades"], 80)

    def test_missing_required_metric(self) -> None:
        with self.assertRaises(ValueError):
            ADAPTER.normalize_metrics({"sharpe": 1.2})


if __name__ == "__main__":
    unittest.main()
