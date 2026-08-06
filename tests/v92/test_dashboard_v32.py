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


SCORE = load("enterprise_research_score_v32")


class DashboardTests(unittest.TestCase):
    def test_sharpe_score(self) -> None:
        self.assertAlmostEqual(SCORE.score_sharpe(2.0), 25.0)

    def test_drawdown_score(self) -> None:
        self.assertEqual(SCORE.score_drawdown(-8.0), 20.0)

    def test_validation_only(self) -> None:
        state, recommendation = SCORE.readiness(
            95,
            False,
            True,
        )
        self.assertEqual(state, "VALIDATION_ONLY")
        self.assertIn("validation", recommendation.lower())


if __name__ == "__main__":
    unittest.main()
