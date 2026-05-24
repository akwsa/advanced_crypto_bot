import unittest

from signals.signal_filter_v2 import SignalFilterV2
from signals.signal_rules import (
    BUY_MIN_CONFIDENCE,
    SELL_MIN_CONFIDENCE,
    get_final_actionable_rejection_reason,
    is_buy_support_entry_zone,
    should_block_actionable_on_stale_price,
)


class TestBatch3RuleRejections(unittest.TestCase):
    def setUp(self):
        self.filter = SignalFilterV2()
        self.market_data = {
            "volume_24h_idr": 10_000_000_000,
            "ath_price": 1_500,
            "market_cap_idr": 50_000_000_000,
        }

    def _base_signal(self):
        return {
            "pair": "testidr",
            "price": 100.0,
            "recommendation": "BUY",
            "ml_confidence": 0.85,
            "combined_strength": 0.50,
            "rsi": "NEUTRAL",
            "macd": "BULLISH",
            "ma_trend": "BULLISH",
            "bollinger": "NEUTRAL",
            "support_1": 90.0,
            "support_2": 85.0,
            "resistance_1": 130.0,
            "resistance_2": 140.0,
        }

    def test_reject_buy_near_resistance(self):
        signal = self._base_signal()
        signal["price"] = 129.0  # < 1% to R1=130

        result = self.filter.validate_signal(signal, self.market_data)
        self.assertFalse(result.passed)
        self.assertTrue(any("BUY terlalu dekat resistance" in r for r in result.rejection_reasons))

    def test_reject_sell_near_support(self):
        signal = self._base_signal()
        signal.update(
            {
                "recommendation": "SELL",
                "ml_confidence": 0.85,
                "combined_strength": -0.40,
                "rsi": "NEUTRAL",
                "macd": "BEARISH",
                "ma_trend": "BEARISH",
                "price": 91.0,  # ~1.1% from S1=90
            }
        )

        result = self.filter.validate_signal(signal, self.market_data)
        self.assertFalse(result.passed)
        self.assertTrue(any("SELL terlalu dekat support" in r for r in result.rejection_reasons))

    def test_reject_buy_low_confidence(self):
        # Prioritas 1 (2026-05-22): BUY baseline turun ke 0.50 supaya selaras dengan
        # signal_rules.py BUY_MIN_CONFIDENCE; signal dengan ML 0.45 harus tetap di-reject.
        signal = self._base_signal()
        signal["ml_confidence"] = 0.45

        result = self.filter.validate_signal(signal, self.market_data)
        self.assertFalse(result.passed)
        self.assertTrue(any("ML confidence terlalu rendah" in r for r in result.rejection_reasons))

    def test_reject_buy_negative_combined_strength(self):
        signal = self._base_signal()
        signal["combined_strength"] = -0.20

        result = self.filter.validate_signal(signal, self.market_data)
        self.assertFalse(result.passed)
        self.assertTrue(any("Konflik sinyal" in r for r in result.rejection_reasons))

    def test_stale_price_blocks_actionable(self):
        self.assertTrue(should_block_actionable_on_stale_price(True, "BUY"))
        self.assertTrue(should_block_actionable_on_stale_price(True, "STRONG_SELL"))
        self.assertTrue(should_block_actionable_on_stale_price(False, "BUY", stale_realtime_price=True))
        self.assertFalse(should_block_actionable_on_stale_price(True, "HOLD"))
        self.assertFalse(should_block_actionable_on_stale_price(False, "BUY"))

    def test_buy_support_entry_zone_allows_s2_to_s1_tolerance(self):
        self.assertTrue(is_buy_support_entry_zone(1121, 1120, 1119, near_support_pct=2.0))
        self.assertTrue(is_buy_support_entry_zone(1025, 1035, 1014, near_support_pct=2.0))

    def test_buy_support_entry_zone_rejects_middle_or_resistance_area(self):
        self.assertFalse(is_buy_support_entry_zone(1056, 1035, 1014, near_support_pct=2.0))
        self.assertFalse(is_buy_support_entry_zone(4439, 4350, 4261, near_support_pct=2.0))

    def test_final_policy_rejects_low_final_confidence(self):
        reason = get_final_actionable_rejection_reason(
            {
                "recommendation": "BUY",
                "ml_confidence": BUY_MIN_CONFIDENCE - 0.01,
                "combined_strength": 0.45,
            }
        )
        self.assertIn("final ML confidence too low", reason)

    def test_final_policy_allows_buy_at_new_asymmetric_threshold(self):
        reason = get_final_actionable_rejection_reason(
            {
                "recommendation": "BUY",
                "ml_confidence": BUY_MIN_CONFIDENCE + 0.01,
                "combined_strength": 0.45,
            }
        )
        self.assertIsNone(reason)

    def test_final_policy_rejects_sell_below_active_threshold(self):
        reason = get_final_actionable_rejection_reason(
            {
                "recommendation": "SELL",
                "ml_confidence": SELL_MIN_CONFIDENCE - 0.01,
                "combined_strength": -0.20,
            }
        )
        self.assertIsNotNone(reason)
        self.assertIn("final ML confidence too low", reason)

    def test_final_policy_rejects_sell_with_positive_strength_conflict(self):
        reason = get_final_actionable_rejection_reason(
            {
                "recommendation": "SELL",
                "ml_confidence": 0.72,
                "combined_strength": 0.41,
            }
        )
        self.assertIn("combined_strength too positive", reason)


if __name__ == "__main__":
    unittest.main()
