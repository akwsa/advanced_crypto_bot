# Tujuan: Regression tests untuk /autotrade_status diagnostic reason summary.
# Caller: unittest/pytest focused Telegram command behavior.
# Dependensi: bot.AdvancedCryptoBot dengan fake DB/risk manager/update.

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot import AdvancedCryptoBot


class _FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class TestAutotradeStatusAndWatchlist(unittest.IsolatedAsyncioTestCase):
    def _update(self, user_id=123):
        message = _FakeMessage()
        return SimpleNamespace(
            message=message,
            callback_query=None,
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id, username="admin"),
        )

    def _bot(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.is_trading = False
        bot.subscribers = {123: ["btcidr", "ETH/IDR"]}
        bot.auto_trade_pairs = {}
        bot.last_ml_update = {}
        bot.db = SimpleNamespace(
            set_auto_trade_mode=Mock(),
            get_trade_history=Mock(return_value=[]),
            get_open_trades=Mock(return_value=[]),
        )
        bot.risk_manager = SimpleNamespace(get_risk_metrics=Mock(return_value={}))
        bot._save_auto_trade_mode = Mock(side_effect=lambda is_dry: setattr(bot, "_saved_dry", is_dry))
        bot._send_message = AsyncMock()
        return bot

    async def test_autotrade_dryrun_imports_existing_watchlist_pairs(self):
        bot = self._bot()
        update = self._update()

        with patch("bot.Config.ADMIN_IDS", [123]), patch("bot.Config.AUTO_TRADE_DRY_RUN", True):
            await bot.autotrade(update, SimpleNamespace(args=["dryrun"]))

        self.assertTrue(bot.is_trading)
        self.assertEqual(bot.auto_trade_pairs[123], ["btcidr", "ETH/IDR"])
        bot._save_auto_trade_mode.assert_called_once_with(True)
        sent = bot._send_message.await_args.args[2]
        self.assertIn("Existing Watchlist Imported", sent)
        self.assertIn("BTCIDR", sent)
        self.assertIn("ETH/IDR", sent)

    async def test_autotrade_status_no_trade_message_is_valid_markdown_and_no_literal_slashes(self):
        bot = self._bot()
        bot.is_trading = True
        bot.auto_trade_pairs = {123: ["btcidr", "ETH/IDR"]}
        update = self._update()

        with patch("bot.Config.ADMIN_IDS", [123]), patch("bot.Config.AUTO_TRADE_DRY_RUN", True), patch("bot.Config.MAX_DAILY_LOSS_PCT", 5):
            await bot.autotrade_status(update, SimpleNamespace(args=[]))

        sent_text = bot._send_message.await_args.args[2]
        kwargs = bot._send_message.await_args.kwargs

        self.assertEqual(kwargs.get("parse_mode"), "Markdown")
        self.assertNotIn("<i>", sent_text)
        self.assertNotIn("<b>", sent_text)
        self.assertNotIn("\\\\n", sent_text)
        self.assertIn("Auto-trading aktif, tapi belum ada trade otomatis hari ini", sent_text)
        self.assertIn("Pair aktif dari watchlist", sent_text)
        self.assertIn("BTCIDR", sent_text)
        self.assertIn("ETH/IDR", sent_text)

    async def test_autotrade_status_shows_block_reason_summary_when_available(self):
        bot = self._bot()
        bot.is_trading = True
        bot.auto_trade_pairs = {123: ["zkjidr", "jellyjellyidr"]}
        bot._autotrade_block_reasons = {
            "zkjidr": {
                "pair": "ZKJIDR",
                "bucket": "V4_FILTER",
                "reason": "[V4_FILTER] Entry blocked for zkjidr: predicted bad outcome (BAD_BUY)",
                "timestamp": "2026-05-27 11:58:55",
            },
            "jellyjellyidr": {
                "pair": "JELLYJELLYIDR",
                "bucket": "R/R_FLOOR",
                "reason": "Trade blocked for jellyjellyidr: R/R after fees below dynamic floor (1.19 < 1.50)",
                "timestamp": "2026-05-27 12:01:27",
            },
            "skyaiidr": {
                "pair": "SKYAIIDR",
                "bucket": "CVAR",
                "reason": "Entry blocked for skyaiidr: CVaR gate: CVaR95=-7.47% < -5.0%",
                "timestamp": "2026-05-27 12:07:30",
            },
        }
        update = self._update()

        with patch("bot.Config.ADMIN_IDS", [123]), patch("bot.Config.AUTO_TRADE_DRY_RUN", True), patch("bot.Config.MAX_DAILY_LOSS_PCT", 5):
            await bot.autotrade_status(update, SimpleNamespace(args=[]))

        sent_text = bot._send_message.await_args.args[2]
        self.assertIn("Ringkasan blokir entry DRY RUN terbaru", sent_text)
        self.assertIn("V4_FILTER: 1", sent_text)
        self.assertIn("R/R_FLOOR: 1", sent_text)
        self.assertIn("CVAR: 1", sent_text)
        self.assertIn("ZKJIDR", sent_text)
        self.assertIn("JELLYJELLYIDR", sent_text)
        self.assertIn("SKYAIIDR", sent_text)


if __name__ == "__main__":
    unittest.main()
