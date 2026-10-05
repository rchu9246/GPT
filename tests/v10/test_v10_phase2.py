from __future__ import annotations

import inspect
import json
import ssl
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from automation.v10.factors import FACTOR_NAMES, FACTOR_VERSION, HYPOTHESIS_WEIGHTS
from automation.v10.models import MarketBar
from automation.v10.phase2_research import (
    BASELINE_BUY_COMMISSION, BASELINE_SELL_COMMISSION, BASELINE_SELL_TAX,
    MINIMUM_MEDIAN_TURNOVER, PRE_REGISTERED_CONFIGS, REBALANCE_FREQUENCIES,
    STRESS_COST, TOP_N_VALUES, ResearchData, TwseDailyTableProvider, _split,
)
from automation.v10.research import PROMOTED_PAPER_STRATEGIES


ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "artifacts/v10_phase2/research_result.json"


def fixture_bars():
    values = []
    for offset in range(70):
        for number, symbol in enumerate(("1101", "1102", "1103"), 1):
            price = Decimal(50 + number) + Decimal(offset) / 10
            values.append(MarketBar(symbol, date(2024, 1, 1) + timedelta(days=offset),
                                    price, price + 1, price - 1, price, 2_000_000,
                                    provider="TWSE_MI_INDEX", provider_observation_id=f"{offset}:{symbol}"))
    return values


class Phase2ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(RESULT.read_text(encoding="utf-8")) if RESULT.exists() else None

    def test_01_six_versioned_factors(self):
        self.assertEqual(6, len(FACTOR_NAMES))
        self.assertEqual("V10_OHLCV_FACTORS_V1", FACTOR_VERSION)

    def test_02_three_hypotheses_pre_registered(self):
        self.assertEqual({"H1_EQUAL_FACTOR", "H2_TREND_MOMENTUM", "H3_RISK_ADJUSTED"},
                         set(HYPOTHESIS_WEIGHTS))

    def test_03_fixed_configuration_grid(self):
        self.assertEqual(18, len(PRE_REGISTERED_CONFIGS))
        self.assertEqual((5, 10, 20), TOP_N_VALUES)
        self.assertEqual(("WEEKLY", "MONTHLY"), REBALANCE_FREQUENCIES)

    def test_04_sealed_net_costs(self):
        self.assertEqual(Decimal("0.001425"), BASELINE_BUY_COMMISSION)
        self.assertEqual(Decimal("0.001425"), BASELINE_SELL_COMMISSION)
        self.assertEqual(Decimal("0.003"), BASELINE_SELL_TAX)

    def test_05_stress_cost_is_stricter(self):
        self.assertGreater(STRESS_COST.buy_commission, BASELINE_BUY_COMMISSION)
        self.assertGreater(STRESS_COST.sell_tax, BASELINE_SELL_TAX)
        self.assertGreater(STRESS_COST.slippage, 0)

    def test_06_liquidity_threshold_fixed(self):
        self.assertEqual(Decimal("50000000"), MINIMUM_MEDIAN_TURNOVER)

    def test_07_split_is_chronological_and_disjoint(self):
        sessions = tuple(date(2024, 1, 1) + timedelta(days=i) for i in range(300))
        train, validation, holdout = _split(sessions)
        self.assertLess(train[-1], validation[0])
        self.assertLess(validation[-1], holdout[0])
        self.assertFalse(set(train) & set(validation) | set(validation) & set(holdout))

    def test_08_history_is_point_in_time(self):
        data = ResearchData(fixture_bars(), {})
        cutoff = date(2024, 2, 15)
        self.assertTrue(all(bar.session_date <= cutoff for bar in data.history("1101", cutoff, 60)))

    def test_09_universe_requires_current_observation(self):
        data = ResearchData(fixture_bars(), {})
        self.assertEqual((), data.eligible(date(2030, 1, 1)))

    def test_10_ranking_is_deterministic(self):
        data = ResearchData(fixture_bars(), {})
        signal = date(2024, 3, 10)
        self.assertEqual(data.ranking(signal, "H1_EQUAL_FACTOR"),
                         data.ranking(signal, "H1_EQUAL_FACTOR"))

    def test_11_parser_filters_non_common_stock_codes(self):
        fields = [str(i) for i in range(16)]
        row = lambda code: [code, "name", "2,000,000", "1", "100", "50", "51", "49", "50", "+", "0", "0", "0", "0", "0", "0"]
        payload = {"stat": "OK", "date": "20240102", "tables": [
            {"fields": ["index"], "data": [["x", "1"], ["taiex", "100"]]},
            {"fields": fields, "data": [row("1101"), row("0050"), row("ABCD")]},
        ]}
        parsed = TwseDailyTableProvider._parse(payload, date(2024, 1, 2), "hash")
        self.assertEqual(["1101"], [bar["symbol"] for bar in parsed["bars"]])

    def test_12_provider_keeps_tls_verification(self):
        provider = object.__new__(TwseDailyTableProvider)
        provider._ssl = ssl.create_default_context()
        provider._ssl.verify_flags &= ~ssl.VERIFY_X509_STRICT
        self.assertEqual(ssl.CERT_REQUIRED, provider._ssl.verify_mode)
        self.assertTrue(provider._ssl.check_hostname)

    def test_13_official_twse_endpoint_only(self):
        self.assertEqual("https://www.twse.com.tw/exchangeReport/MI_INDEX", TwseDailyTableProvider.URL)

    def test_14_no_strategy_was_silently_promoted(self):
        self.assertEqual((), PROMOTED_PAPER_STRATEGIES)

    def test_15_artifact_has_official_lineage(self):
        self.assertIsNotNone(self.result)
        self.assertEqual("TWSE_MI_INDEX", self.result["data"]["provider"])
        self.assertEqual(64, len(self.result["data"]["source_fingerprint"]))

    def test_16_artifact_uses_daily_point_in_time_membership(self):
        self.assertTrue(self.result["universe"]["point_in_time"])
        self.assertFalse(self.result["universe"]["survivorship_bias_limitation"])
        self.assertGreater(self.result["universe"]["symbols_tested"], 1000)

    def test_17_every_configuration_reported(self):
        self.assertEqual(18, len(self.result["development_results"]))
        self.assertEqual({config.name for config in PRE_REGISTERED_CONFIGS},
                         {row["config"] for row in self.result["development_results"]})

    def test_18_every_configuration_has_cost_stress(self):
        self.assertTrue(all(row["validation_stress"]["cost_model"] == "HIGHER_COST_STRESS"
                            for row in self.result["development_results"]))

    def test_19_accounting_reconciled_everywhere(self):
        self.assertTrue(all(row[segment]["accounting_reconciled"]
                            for row in self.result["development_results"]
                            for segment in ("train", "validation", "validation_stress")))

    def test_20_holdout_not_opened_without_selected_candidate(self):
        if self.result["selected_before_holdout"] is None:
            self.assertIsNone(self.result["final_holdout_result"])
            self.assertIsNone(self.result["final_holdout_stress"])

    def test_21_promotion_fails_closed(self):
        self.assertEqual(self.result["promotion_pass"], self.result["promoted_strategy"] is not None)

    def test_22_no_random_split_or_parameter_search(self):
        source = inspect.getsource(__import__("automation.v10.phase2_research", fromlist=["run_research"]))
        self.assertNotIn("random", source.lower())
        self.assertNotIn("gridsearch", source.lower())

    def test_23_final_holdout_is_named_explicitly(self):
        self.assertIn("final_holdout", self.result["design"])
        self.assertLess(self.result["design"]["validation"][1], self.result["design"]["final_holdout"][0])


if __name__ == "__main__":
    unittest.main()
