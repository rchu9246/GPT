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


SCORE = load("enterprise_dashboard_score_v33")
DASH = load("build_enterprise_dashboard_v33")


class DashboardV33Tests(unittest.TestCase):
    def test_validation_only_cannot_deploy(self) -> None:
        state, recommendation, _ = SCORE.classify(99, False, True)
        self.assertEqual(state, "VALIDATION_ONLY")
        self.assertIn("validation", recommendation.lower())

    def test_ready_for_paper_trading(self) -> None:
        state, recommendation, _ = SCORE.classify(92, True, True)
        self.assertEqual(state, "READY_FOR_PAPER_TRADING")
        self.assertIn("paper trading", recommendation.lower())

    def test_drawdown_series(self) -> None:
        output = DASH.drawdown_series([
            {"timestamp": "1", "equity": 100.0},
            {"timestamp": "2", "equity": 120.0},
            {"timestamp": "3", "equity": 90.0},
        ])
        self.assertAlmostEqual(output[-1]["drawdown"], -25.0)


if __name__ == "__main__":
    unittest.main()
