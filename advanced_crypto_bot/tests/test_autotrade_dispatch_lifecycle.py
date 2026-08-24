import unittest
import tempfile

from autotrade.contracts import TradeIntent, acquire_process_singleton
from autotrade.runtime import _classify_autotrade_block_reason, classify_autotrade_block_reason


class TestTradeIntent(unittest.TestCase):
    def test_no_entry_taxonomy_is_specific(self):
        expected = {
            "Edge score too low (< 56)": "ENTRY_EDGE",
            "NO_OPEN_POSITION: SELL has no position": "NO_OPEN_POSITION",
            "POSITION_SIZING: invalid calculated size": "POSITION_SIZING",
            "LIQUIDITY: SPREAD_TOO_WIDE": "LIQUIDITY",
            "PAIR_BLACKLIST: temporary blacklist": "PAIR_GUARD",
            "PAIR_LOSS_STREAK: consecutive loss guard": "PAIR_GUARD",
            "fresh entry price unavailable": "PRICE_INVALID",
            "fresh price deviates 51% from signal price": "PRICE_INVALID",
            "SIGNAL_INVALID: recommendation missing": "SIGNAL_INVALID",
            "DUPLICATE_POSITION: already open": "DUPLICATE_POSITION",
            "MARKET_INTELLIGENCE: MI_FILTER": "MARKET_INTELLIGENCE",
            "[META_LABEL] prob_good_trade 20% < 55%": "META_LABEL",
            "[CALIBRATION] confidence overstates good-rate": "CALIBRATION",
            "DRAWDOWN: maximum drawdown exceeded": "RISK_DRAWDOWN",
            "Daily trade limit reached: 50/50": "DAILY_TRADE_LIMIT",
            "Correlated pair ethidr traded 30 min ago. Wait for cooldown.": "CORRELATION_COOLDOWN",
            "Risk-reward ratio too low: 1.00 < 1.50": "RISK_REWARD",
            "Error calculating risk metrics": "INTERNAL_ERROR",
            "Invalid signal format": "SIGNAL_INVALID",
            "Invalid price": "PRICE_INVALID",
        }
        for reason, bucket in expected.items():
            with self.subTest(reason=reason):
                self.assertEqual(_classify_autotrade_block_reason(reason), bucket)

    def test_unknown_reason_is_an_explicit_integrity_failure(self):
        self.assertEqual(
            classify_autotrade_block_reason("unexpected branch without taxonomy"),
            "UNCLASSIFIED_INTERNAL_ERROR",
        )

    def test_pair_loss_streak_code_is_specific_case_insensitive_and_precedence_safe(self):
        self.assertEqual(
            classify_autotrade_block_reason(
                "pair_loss_streak: consecutive loss guard; spread metric unavailable"
            ),
            "PAIR_GUARD",
        )
        self.assertEqual(
            classify_autotrade_block_reason("PORTFOLIO_LOSS_STREAK_METRIC_UNAVAILABLE"),
            "UNCLASSIFIED_INTERNAL_ERROR",
        )

    def test_exact_semantic_payload_is_preserved(self):
        raw = {"signal_id": "x", "pair": "btc_idr", "signal_type": "BUY",
               "confidence": .7, "price": 100, "created_at": 1_800_000_000,
               "data": {"signal": {"recommendation": "BUY", "indicators": {"rsi": 31},
                                   "pre_sr_recommendation": "STRONG_BUY"}}}
        intent = TradeIntent.from_signal(raw)
        self.assertEqual(intent.signal["indicators"], {"rsi": 31})
        self.assertEqual(intent.signal["pre_sr_recommendation"], "STRONG_BUY")
        self.assertIsNone(intent.validate(max_age_seconds=None, now=1_800_000_000))

    def test_invalid_payload_has_explicit_reason(self):
        intent = TradeIntent.from_signal({"pair": "btcidr", "signal_type": "HOLD", "price": 0})
        self.assertEqual(intent.validate(), "INVALID_RECOMMENDATION")

    def test_same_payload_has_same_idempotency_key(self):
        raw = {"pair": "btcidr", "signal_type": "BUY", "price": 100,
               "created_at": 1_800_000_000, "data": {"signal": {"recommendation": "BUY"}}}
        self.assertEqual(TradeIntent.from_signal(raw).idempotency_key,
                         TradeIntent.from_signal(raw).idempotency_key)

    def test_process_singleton_refuses_second_owner(self):
        with tempfile.NamedTemporaryFile() as lock_file:
            first = acquire_process_singleton(lock_file.name)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(acquire_process_singleton(lock_file.name))
            finally:
                first.close()
            replacement = acquire_process_singleton(lock_file.name)
            self.assertIsNotNone(replacement)
            replacement.close()

    def test_contract_rejects_version_nonfinite_and_future(self):
        base = {"pair":"btcidr","signal_type":"BUY","price":100,"created_at":1000}
        self.assertEqual(TradeIntent.from_signal(dict(base, version=2)).validate(now=1000), "UNSUPPORTED_CONTRACT_VERSION")
        self.assertEqual(TradeIntent.from_signal(dict(base, price=float("nan"))).validate(now=1000), "NON_FINITE_NUMERIC")
        self.assertEqual(TradeIntent.from_signal(dict(base, created_at=2000)).validate(now=1000), "FUTURE_SIGNAL")

    def test_source_mutation_does_not_change_intent(self):
        nested={"indicators":{"rsi":30}}
        intent=TradeIntent.from_signal({"pair":"btcidr","signal_type":"BUY","price":1,"data":{"signal":nested}})
        nested["indicators"]["rsi"]=99
        self.assertEqual(intent.signal["indicators"]["rsi"],30)
        exposed=intent.to_dict(); exposed["signal"]["indicators"]["rsi"]=77
        self.assertEqual(intent.signal["indicators"]["rsi"],30)

    def test_user_ownership_round_trip(self):
        intent=TradeIntent.from_signal({"pair":"btcidr","signal_type":"BUY","price":1,"source_user_id":42})
        self.assertEqual(intent.user_id,42)
        self.assertEqual(TradeIntent(**intent.to_dict()).user_id,42)
