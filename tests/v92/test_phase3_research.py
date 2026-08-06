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


WFA = load("walk_forward_analysis")
MC = load("monte_carlo_analysis")


class Phase3Tests(unittest.TestCase):
    def test_drawdown(self) -> None:
        self.assertAlmostEqual(
            WFA.max_drawdown([100, 120, 90]),
            -25.0,
        )

    def test_percentile(self) -> None:
        self.assertEqual(MC.percentile([1, 2, 3], 0.5), 2)

    def test_positive_window(self) -> None:
        result = WFA.analyze_window([100, 105, 110])
        self.assertGreater(result["total_return"], 0)


if __name__ == "__main__":
    unittest.main()
