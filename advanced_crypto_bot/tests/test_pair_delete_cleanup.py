import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from autotrade.runtime import _is_auto_trade_pair, _is_watched, check_trading_opportunity
from bot import AdvancedCryptoBot


class _FakeQueue:
    def __init__(self):
        self.purged = []

    def purge_pair(self, pair):
        self.purged.append(pair)
        return 2


class TestPairDeleteCleanup(unittest.IsolatedAsyncioTestCase):
    def _bot_for_cleanup(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.price_data = {"BTCIDR": {"last": 1}}
        bot.historical_data = {"btcidr": object()}
        bot.previous_signals = {"BTC/IDR": {"recommendation": "BUY"}}
        bot.last_ml_update = {"btcidr": object()}
        bot.last_price_update = {"BTCIDR": object()}
        bot._signal_result_cache = {"btcidr": {"signal": {}}}
        bot._last_signal_checks = {"BTCIDR": object()}
        bot._notification_cooldown = {"btcidr_SELL": object(), "ethidr_BUY": object()}
        bot._last_scan_signals = {"btcidr_BUY": object()}
        bot._signal_inflight_tasks = {}
        bot.auto_trade_pairs = {123: ["btcidr", "ethidr"]}
        bot.subscribers = {123: ["BTCIDR"]}
        bot.signal_queue = _FakeQueue()
        return bot

    async def test_cleanup_pair_runtime_state_removes_stale_signal_state(self):
        bot = self._bot_for_cleanup()

        result = bot._cleanup_pair_runtime_state("BTC/IDR", remove_auto_trade=True, user_id=123)

        self.assertEqual(result, {"queue": 2, "auto_removed": 1})
        self.assertEqual(bot.auto_trade_pairs[123], ["ethidr"])
        self.assertEqual(bot.signal_queue.purged, ["btcidr"])
        self.assertNotIn("BTCIDR", bot.price_data)
        self.assertNotIn("btcidr", bot.historical_data)
        self.assertNotIn("BTC/IDR", bot.previous_signals)
        self.assertNotIn("btcidr_SELL", bot._notification_cooldown)
        self.assertIn("ethidr_BUY", bot._notification_cooldown)

    async def test_runtime_pair_checks_are_case_and_separator_insensitive(self):
        bot = SimpleNamespace(
            subscribers={1: ["BTCIDR"]},
            auto_trade_pairs={1: ["eth_idr"]},
        )

        self.assertTrue(_is_watched(bot, "btc_idr"))
        self.assertTrue(_is_auto_trade_pair(bot, "ETH/IDR"))

    async def test_autotrade_notification_signal_gets_pair_before_formatting(self):
        sent_messages = []

        async def fake_send_message(**kwargs):
            sent_messages.append(kwargs)

        def fake_formatter(signal):
            self.assertEqual(signal["pair"], "btcidr")
            self.assertEqual(signal["indicators"], {})
            return f"{signal['pair']} {signal['recommendation']}"

        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["btcidr"]},
            subscribers={123: ["BTCIDR"]},
            last_ml_update={},
            auto_trade_interval_minutes=0,
            _format_signal_message_html=fake_formatter,
            app=SimpleNamespace(bot=SimpleNamespace(send_message=fake_send_message)),
            risk_manager=SimpleNamespace(check_daily_loss_limit=lambda user_id: (False, "test stop")),
        )

        with patch("autotrade.runtime.Config.ADMIN_IDS", [123]):
            await check_trading_opportunity(
                bot,
                "btcidr",
                signal={
                    "recommendation": "SELL",
                    "ml_confidence": 0.3,
                    "price": 483,
                },
            )

        self.assertEqual(len(sent_messages), 1)
        self.assertIn("btcidr SELL", sent_messages[0]["text"])


if __name__ == "__main__":
    unittest.main()
