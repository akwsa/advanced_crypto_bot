# Tujuan: Verifikasi tombol BELI/JUAL ikut dikirim di jalur dispatch otomatis Telegram.
# Caller: unittest focused signal dispatch wiring after Sesi 5 (2026-05-22).
# Dependensi: autotrade.runtime, bot.AdvancedCryptoBot.
# Side Effects: Tidak ada; semua HTTP/Telegram di-mock.
"""Regression tests for signal dispatch wiring (2026-05-22 Sesi 5).

Goal: pastikan saat signal otomatis BUY/SELL dikirim ke Telegram, reply_markup
(tombol "🟢 BUY <PAIR> via Scalper" / "🔴 SELL <PAIR> via Scalper") yang sudah
dibangun oleh _build_signal_action_markup() ikut terlampir.

Sebelum patch ini:
- autotrade/runtime.py::monitor_strong_signal kirim raw HTTP POST tanpa reply_markup.
- autotrade/runtime.py::check_trading_opportunity panggil bot.app.bot.send_message
  juga tanpa reply_markup.

Test ini mengunci behavior baru.
"""

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from autotrade.runtime import check_trading_opportunity, monitor_strong_signal
from bot import AdvancedCryptoBot


def _make_bot():
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
    bot.subscribers = {123: ["btcidr", "ethidr", "solidr"]}
    bot.auto_trade_pairs = {123: ["btcidr"]}
    bot.is_trading = True
    bot.auto_trade_interval_minutes = 1
    bot.signal_notifications_enabled = True
    bot.signal_notification_filter = "all"
    bot._notification_cooldown = {}
    bot._last_signal_checks = {}
    bot.last_ml_update = {}

    bot._official_indodax_pairs_cache = {"btcidr", "ethidr", "solidr"}
    bot._official_indodax_pairs_cached_at = 9999999999
    bot._indodax_balance_cache = {
        "available": {"idr": "1000000", "eth": "0.25"},
        "hold": {},
        "available_unavailable": False,
    }
    bot._indodax_balance_cached_at = 9999999999
    bot.scalper = SimpleNamespace(active_positions={})

    bot._format_signal_message_html = Mock(
        side_effect=lambda signal: f"<b>{signal['pair'].upper()}</b> {signal['recommendation']}"
    )
    bot._signal_inflight_tasks = {}
    bot._signal_result_cache = {}
    return bot


class TestMonitorStrongSignalAttachesButtons(unittest.IsolatedAsyncioTestCase):
    """monitor_strong_signal harus attach reply_markup ke payload Telegram."""

    async def test_buy_signal_attaches_buy_button(self):
        bot = _make_bot()
        signal = {
            "pair": "btcidr",
            "recommendation": "BUY",
            "ml_confidence": 0.7,
            "price": 1_200_000_000,
        }

        with patch("autotrade.runtime.Config") as cfg, \
             patch("autotrade.runtime.requests") as fake_requests:
            cfg.ADMIN_IDS = [42]
            cfg.TELEGRAM_BOT_TOKEN = "test-token"
            cfg.CORRELATION_GROUPS = {}
            fake_response = SimpleNamespace(status_code=200, text="OK")
            fake_requests.post = Mock(return_value=fake_response)

            await monitor_strong_signal(bot, "btcidr", signal=signal)

        self.assertTrue(fake_requests.post.called, "requests.post should be called")
        _, kwargs = fake_requests.post.call_args
        payload = kwargs["json"]
        self.assertIn("reply_markup", payload, "reply_markup must be attached for BUY signal")
        markup_dict = payload["reply_markup"]
        self.assertIn("inline_keyboard", markup_dict)
        flat_callbacks = [
            btn.get("callback_data")
            for row in markup_dict["inline_keyboard"]
            for btn in row
        ]
        self.assertIn("s_buy:btcidr", flat_callbacks)

    async def test_sell_signal_attaches_sell_button_when_balance_present(self):
        bot = _make_bot()
        signal = {
            "pair": "ethidr",
            "recommendation": "SELL",
            "ml_confidence": 0.7,
            "price": 38_000_000,
        }

        with patch("autotrade.runtime.Config") as cfg, \
             patch("autotrade.runtime.requests") as fake_requests:
            cfg.ADMIN_IDS = [42]
            cfg.TELEGRAM_BOT_TOKEN = "test-token"
            cfg.CORRELATION_GROUPS = {}
            fake_requests.post = Mock(return_value=SimpleNamespace(status_code=200, text="OK"))

            await monitor_strong_signal(bot, "ethidr", signal=signal)

        _, kwargs = fake_requests.post.call_args
        payload = kwargs["json"]
        self.assertIn("reply_markup", payload)
        flat_callbacks = [
            btn.get("callback_data")
            for row in payload["reply_markup"]["inline_keyboard"]
            for btn in row
        ]
        self.assertIn("s_sell:ethidr", flat_callbacks)

    async def test_sell_signal_without_balance_omits_reply_markup(self):
        """SELL untuk pair yang tidak ada balance coin & tidak ada scalper position
        harus NOT melampirkan reply_markup (signal tetap dikirim, tapi tanpa tombol).
        Tombol JUAL dilarang oleh safety policy untuk hindari klik di pair yang tidak dimiliki.
        """
        bot = _make_bot()
        # btcidr tidak punya saldo coin di balance dan tidak ada scalper position
        signal = {
            "pair": "btcidr",
            "recommendation": "SELL",
            "ml_confidence": 0.7,
            "price": 1_200_000_000,
        }

        with patch("autotrade.runtime.Config") as cfg, \
             patch("autotrade.runtime.requests") as fake_requests:
            cfg.ADMIN_IDS = [42]
            cfg.TELEGRAM_BOT_TOKEN = "test-token"
            cfg.CORRELATION_GROUPS = {}
            fake_requests.post = Mock(return_value=SimpleNamespace(status_code=200, text="OK"))

            await monitor_strong_signal(bot, "btcidr", signal=signal)

        _, kwargs = fake_requests.post.call_args
        payload = kwargs["json"]
        self.assertNotIn(
            "reply_markup",
            payload,
            "SELL tanpa balance coin tidak boleh ada tombol JUAL",
        )


class TestCheckTradingOpportunityAttachesButtons(unittest.IsolatedAsyncioTestCase):
    """check_trading_opportunity (auto-trade path) juga harus attach reply_markup
    ketika notifikasi sinyal otomatis dikirim ke admin.
    """

    async def test_buy_signal_passes_reply_markup_to_send_message(self):
        bot = _make_bot()
        bot.app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        bot.db = SimpleNamespace(
            get_open_trades=Mock(return_value=[]),
            get_balance=Mock(return_value=10_000_000),
            get_pair_performance=Mock(return_value=None),
        )
        bot.risk_manager = SimpleNamespace(
            check_daily_loss_limit=Mock(return_value=(True, "ok")),
        )
        bot.trading_engine = SimpleNamespace(
            should_execute_trade=Mock(return_value=(False, "skip-trade-execution-for-test")),
        )
        bot._check_max_drawdown = Mock(return_value=(True, "ok"))
        bot.indodax = SimpleNamespace(get_ticker=Mock(return_value={"last": 1_200_000_000}))
        bot.price_data = {}

        signal = {
            "pair": "btcidr",
            "recommendation": "BUY",
            "ml_confidence": 0.7,
            "price": 1_200_000_000,
        }

        with patch("autotrade.runtime.Config") as cfg:
            cfg.ADMIN_IDS = [42]
            cfg.AUTO_TRADE_DRY_RUN = True
            cfg.CORRELATION_GROUPS = {}
            cfg.TELEGRAM_BOT_TOKEN = "test-token"

            await check_trading_opportunity(bot, "btcidr", signal=signal)

        bot.app.bot.send_message.assert_awaited()
        # Cari panggilan yang ke admin chat_id=42 (notifikasi signal)
        notif_calls = [
            call for call in bot.app.bot.send_message.await_args_list
            if call.kwargs.get("chat_id") == 42
        ]
        self.assertTrue(notif_calls, "send_message harus dipanggil untuk admin notif")
        first = notif_calls[0]
        self.assertIn(
            "reply_markup",
            first.kwargs,
            "auto-trade signal notif harus melampirkan reply_markup tombol",
        )
        markup = first.kwargs["reply_markup"]
        # Markup adalah InlineKeyboardMarkup dari python-telegram-bot
        callbacks = [
            btn.callback_data
            for row in markup.inline_keyboard
            for btn in row
        ]
        self.assertIn("s_buy:btcidr", callbacks)


if __name__ == "__main__":
    unittest.main()
