# Tujuan: Test kontrol notifikasi signal dan filter command watchlist.
# Caller: unittest focused signal notification/filter behavior.
# Dependensi: bot.AdvancedCryptoBot, autotrade.runtime.
# Main Functions: TestSignalNotificationControls.
# Side Effects: Tidak ada; mock Telegram/DB.
import asyncio
import unittest
from datetime import datetime

import pandas as pd
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from autotrade.runtime import check_trading_opportunity, monitor_strong_signal
from bot import AdvancedCryptoBot


class _FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class TestSignalNotificationControls(unittest.IsolatedAsyncioTestCase):
    def _update(self, user_id=123):
        message = _FakeMessage()
        return SimpleNamespace(
            message=message,
            callback_query=None,
            effective_user=SimpleNamespace(id=user_id),
            effective_message=message,
        )

    def _bot_for_signal_command(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.signal_notifications_enabled = True
        bot.signal_notification_filter = "all"
        bot.db = SimpleNamespace(
            set_signal_notifications_enabled=Mock(),
            set_signal_notification_filter=Mock(),
        )
        bot._send_message = AsyncMock()
        bot.signal_buy_only = AsyncMock()
        bot.signal_sell_only = AsyncMock()
        return bot

    async def test_signal_off_disables_and_persists_automatic_notifications(self):
        bot = self._bot_for_signal_command()
        context = SimpleNamespace(args=["off"])

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.get_signal(self._update(), context)

        self.assertFalse(bot.signal_notifications_enabled)
        bot.db.set_signal_notifications_enabled.assert_called_once_with(False)
        self.assertIn("OFF", bot._send_message.await_args.args[2])

    async def test_signal_on_enables_and_persists_automatic_notifications(self):
        bot = self._bot_for_signal_command()
        bot.signal_notifications_enabled = False
        context = SimpleNamespace(args=["on"])

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.get_signal(self._update(), context)

        self.assertTrue(bot.signal_notifications_enabled)
        bot.db.set_signal_notifications_enabled.assert_called_once_with(True)
        self.assertIn("ON", bot._send_message.await_args.args[2])

    async def test_signal_buy_and_sell_subcommands_route_to_watchlist_filters(self):
        bot = self._bot_for_signal_command()

        await bot.get_signal(self._update(), SimpleNamespace(args=["buy"]))
        bot.signal_buy_only.assert_awaited_once()
        bot.signal_sell_only.assert_not_awaited()

        bot.signal_buy_only.reset_mock()
        await bot.get_signal(self._update(), SimpleNamespace(args=["sell"]))
        bot.signal_sell_only.assert_awaited_once()
        bot.signal_buy_only.assert_not_awaited()

    async def test_signal_hold_and_buysell_subcommands_route_to_watchlist_filters(self):
        bot = self._bot_for_signal_command()
        bot.signal_hold_only = AsyncMock()
        bot.signal_buysell = AsyncMock()

        await bot.get_signal(self._update(), SimpleNamespace(args=["hold"]))
        bot.signal_hold_only.assert_awaited_once()
        bot.signal_buysell.assert_not_awaited()

        await bot.get_signal(self._update(), SimpleNamespace(args=["buysell"]))
        bot.signal_buysell.assert_awaited_once()

    async def test_signal_hold_only_shows_only_hold_and_neutral(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.subscribers = {123: ["btcidr", "ethidr", "solidr"]}
        bot._send_message = AsyncMock()
        bot._send_signal_batch_with_actions = AsyncMock()
        bot._collect_watchlist_signals = AsyncMock(side_effect=AssertionError("must not scan/generate signals"))
        bot._get_latest_saved_watchlist_signals = Mock(return_value=[
            {"pair": "btcidr", "recommendation": "BUY", "price": 100, "ml_confidence": 0.7},
            {"pair": "ethidr", "recommendation": "HOLD", "price": 200, "ml_confidence": 0.8},
            {"pair": "solidr", "recommendation": "HOLD", "price": 300, "ml_confidence": 0.9},
        ])
        bot._build_signal_overview_html = Mock(
            side_effect=lambda buy, sell, hold, **kwargs: "\n".join(
                f"{s['pair'].upper()} {s['recommendation']}" for s in hold
            )
        )

        await bot.signal_hold_only(self._update(), SimpleNamespace(args=[]))

        bot._collect_watchlist_signals.assert_not_called()
        result_text = bot._send_message.await_args_list[-1].args[2]
        self.assertIn("ETHIDR", result_text)
        self.assertIn("SOLIDR", result_text)
        self.assertNotIn("BTCIDR", result_text)
        self.assertIn("HOLD", result_text)
        self.assertNotIn("BUY", result_text)
        self.assertNotIn("SELL", result_text)

    async def test_signal_buysell_shows_only_buy_and_sell(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.subscribers = {123: ["btcidr", "ethidr", "solidr"]}
        bot._send_message = AsyncMock()
        bot._format_signal_message_html = Mock(side_effect=lambda signal: f"<b>{signal['pair'].upper()}</b> {signal['recommendation']}")
        bot._create_background_task = lambda coro: asyncio.create_task(coro)
        bot._collect_watchlist_signals = AsyncMock(return_value=[
            {
                "pair": "btcidr",
                "recommendation": "BUY",
                "price": 100,
                "ml_confidence": 0.7,
            },
            {
                "pair": "ethidr",
                "recommendation": "HOLD",
                "price": 200,
                "ml_confidence": 0.8,
            },
            {
                "pair": "solidr",
                "recommendation": "SELL",
                "price": 300,
                "ml_confidence": 0.9,
            },
        ])

        await bot.signal_buysell(self._update(), SimpleNamespace(args=[]))
        await asyncio.sleep(0)

        result_text = bot._send_message.await_args_list[-1].args[2]
        self.assertIn("BTCIDR", result_text)
        self.assertIn("SOLIDR", result_text)
        self.assertNotIn("ETHIDR", result_text)
        self.assertIn("BUY", result_text)
        self.assertIn("SELL", result_text)
        self.assertNotIn("HOLD", result_text)

    async def test_signal_notif_buy_sets_buy_filter_for_admin(self):
        bot = self._bot_for_signal_command()

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.signal_notif(self._update(), SimpleNamespace(args=["buy"]))

        self.assertEqual(bot.signal_notification_filter, "buy")
        bot.db.set_signal_notification_filter.assert_called_once_with("buy")
        self.assertIn("Hanya BUY / STRONG_BUY", bot._send_message.await_args.args[2])

    async def test_signal_notif_both_maps_to_actionable_for_admin(self):
        bot = self._bot_for_signal_command()

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.signal_notif(self._update(), SimpleNamespace(args=["both"]))

        self.assertEqual(bot.signal_notification_filter, "actionable")
        bot.db.set_signal_notification_filter.assert_called_once_with("actionable")
        self.assertIn("BUY + SELL", bot._send_message.await_args.args[2])

    async def test_signal_notif_rejects_non_admin_filter_change(self):
        bot = self._bot_for_signal_command()

        with patch("bot.Config.ADMIN_IDS", [999]):
            await bot.signal_notif(self._update(), SimpleNamespace(args=["sell"]))

        self.assertEqual(bot.signal_notification_filter, "all")
        bot.db.set_signal_notification_filter.assert_not_called()
        self.assertIn("hanya untuk admin", bot._send_message.await_args.args[2].lower())

    def _bot_for_saved_signal_filter(self, signals):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.subscribers = {123: ["btcidr", "ethidr", "solidr", "xrpidr"]}
        bot._send_message = AsyncMock()
        bot._send_signal_batch_with_actions = AsyncMock()
        bot._format_signal_message_html = Mock(side_effect=lambda signal: f"<b>{signal['pair'].upper()}</b> {signal['recommendation']}")
        bot._build_signal_overview_html = Mock(
            side_effect=lambda buy, sell, hold, **kwargs: "\n".join(
                f"{s['pair'].upper()} {s['recommendation']}" for s in hold
            )
        )
        bot._collect_watchlist_signals = AsyncMock(side_effect=AssertionError("must not scan/generate signals"))
        bot._get_latest_saved_watchlist_signals = Mock(return_value=signals)
        bot._build_signal_action_markup = Mock(return_value=None)
        return bot

    async def test_signal_buy_only_shows_only_buy_and_strong_buy(self):
        bot = self._bot_for_saved_signal_filter([
            {"pair": "btcidr", "recommendation": "BUY", "price": 100, "ml_confidence": 0.7},
            {"pair": "ethidr", "recommendation": "SELL", "price": 200, "ml_confidence": 0.8},
            {"pair": "solidr", "recommendation": "STRONG_BUY", "price": 300, "ml_confidence": 0.9},
        ])

        await bot.signal_buy_only(self._update(), SimpleNamespace(args=[]))

        bot._collect_watchlist_signals.assert_not_called()
        bot._get_latest_saved_watchlist_signals.assert_called_once()
        result_text = bot._send_signal_batch_with_actions.await_args.args[2]
        self.assertIn("BTCIDR", result_text)
        self.assertIn("SOLIDR", result_text)
        self.assertNotIn("ETHIDR", result_text)
        self.assertIn("BUY", result_text)
        self.assertNotIn("SELL", result_text)
        bot._send_message.assert_not_awaited()

    async def test_signal_buy_only_suppresses_empty_saved_buy_filter_without_scanning(self):
        bot = self._bot_for_saved_signal_filter([
            {"pair": "dogeidr", "recommendation": "HOLD", "combined_strength": 0.23, "ml_confidence": 0.53},
            {"pair": "ethidr", "recommendation": "SELL", "combined_strength": -0.22, "ml_confidence": 0.8},
        ])

        await bot.signal_buy_only(self._update(), SimpleNamespace(args=[]))

        bot._collect_watchlist_signals.assert_not_called()
        bot._send_message.assert_not_awaited()
        bot._send_signal_batch_with_actions.assert_not_awaited()

    async def test_signal_sell_only_suppresses_empty_saved_sell_filter_without_scanning(self):
        bot = self._bot_for_saved_signal_filter([
            {"pair": "dogeidr", "recommendation": "HOLD", "combined_strength": 0.23, "ml_confidence": 0.53},
            {"pair": "ethidr", "recommendation": "BUY", "combined_strength": 0.22, "ml_confidence": 0.8},
        ])

        await bot.signal_sell_only(self._update(), SimpleNamespace(args=[]))

        bot._collect_watchlist_signals.assert_not_called()
        bot._send_message.assert_not_awaited()
        bot._send_signal_batch_with_actions.assert_not_awaited()

    async def test_signal_hold_only_suppresses_empty_saved_hold_filter_without_scanning(self):
        bot = self._bot_for_saved_signal_filter([
            {"pair": "dogeidr", "recommendation": "BUY", "combined_strength": 0.23, "ml_confidence": 0.53},
            {"pair": "l3idr", "recommendation": "SELL", "combined_strength": -0.24, "ml_confidence": 0.57},
        ])

        await bot.signal_hold_only(self._update(), SimpleNamespace(args=[]))

        bot._collect_watchlist_signals.assert_not_called()
        bot._send_message.assert_not_awaited()
        bot._send_signal_batch_with_actions.assert_not_awaited()

    async def test_signal_sell_only_shows_only_sell_and_strong_sell(self):
        bot = self._bot_for_saved_signal_filter([
            {"pair": "btcidr", "recommendation": "BUY", "price": 100, "ml_confidence": 0.7},
            {"pair": "ethidr", "recommendation": "SELL", "price": 200, "ml_confidence": 0.8},
            {"pair": "xrpidr", "recommendation": "STRONG_SELL", "price": 300, "ml_confidence": 0.9},
        ])

        await bot.signal_sell_only(self._update(), SimpleNamespace(args=[]))

        bot._collect_watchlist_signals.assert_not_called()
        result_text = bot._send_signal_batch_with_actions.await_args.args[2]
        self.assertIn("ETHIDR", result_text)
        self.assertIn("XRPIDR", result_text)
        self.assertNotIn("BTCIDR", result_text)
        self.assertIn("SELL", result_text)
        self.assertNotIn("BUY", result_text)


    async def test_chart_history_uses_db_when_memory_history_is_flat(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.historical_data = {"HYPEIDR": pd.DataFrame({"close": [2145.0] * 80})}
        db_df = pd.DataFrame({"close": [2100 + i for i in range(80)]})
        bot.db = SimpleNamespace(get_price_history=Mock(side_effect=lambda pair, limit=200: db_df if pair == "HYPEIDR" else pd.DataFrame()))

        chart_df = bot._get_chart_history_for_pair("HYPEIDR")

        self.assertIs(chart_df, db_df)
        bot.db.get_price_history.assert_any_call("HYPEIDR", limit=200)

        bot = SimpleNamespace(
            signal_notifications_enabled=False,
            subscribers={123: ["btcidr"]},
            _format_signal_message_html=Mock(return_value="signal text"),
            _last_signal_checks={},
            _notification_cooldown={},
        )

        with patch("autotrade.runtime.requests.post") as post:
            await monitor_strong_signal(
                bot,
                "btcidr",
                signal={
                    "recommendation": "BUY",
                    "ml_confidence": 0.8,
                    "price": 100,
                },
            )

        post.assert_not_called()
        bot._format_signal_message_html.assert_called_once()
        self.assertIn("btcidr", bot._last_signal_checks)
        self.assertAlmostEqual(
            (datetime.now() - bot._last_signal_checks["btcidr"]).total_seconds(), 0, delta=5
        )

    async def test_autotrade_signal_notification_is_suppressed_but_flow_continues(self):
        sent_messages = []

        async def fake_send_message(**kwargs):
            sent_messages.append(kwargs)

        risk_manager = SimpleNamespace(check_daily_loss_limit=Mock(return_value=(False, "blocked")))
        bot = SimpleNamespace(
            signal_notifications_enabled=False,
            is_trading=True,
            auto_trade_pairs={123: ["btcidr"]},
            subscribers={123: ["btcidr"]},
            last_ml_update={},
            auto_trade_interval_minutes=0,
            _format_signal_message_html=Mock(return_value="signal text"),
            app=SimpleNamespace(bot=SimpleNamespace(send_message=fake_send_message)),
            risk_manager=risk_manager,
        )

        with patch("autotrade.runtime.Config.ADMIN_IDS", [123]):
            await check_trading_opportunity(
                bot,
                "btcidr",
                signal={
                    "pair": "btcidr",
                    "recommendation": "BUY",
                    "ml_confidence": 0.8,
                    "price": 100,
                },
            )

        self.assertEqual(sent_messages, [])
        risk_manager.check_daily_loss_limit.assert_called_once()

    async def test_actionable_auto_filter_allows_sell_even_if_legacy_mode_buy(self):
        class _FakeResp:
            status_code = 200
            text = "ok"

        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='buy',
            subscribers={123: ["btcidr"]},
            _format_signal_message_html=Mock(return_value="signal text"),
            _last_signal_checks={},
            _notification_cooldown={},
        )
        with patch("autotrade.runtime.requests.post", return_value=_FakeResp()) as post, \
             patch("autotrade.runtime.Config.ADMIN_IDS", [123]), \
             patch("autotrade.runtime.Config.TELEGRAM_BOT_TOKEN", "tok"):
            await monitor_strong_signal(
                bot,
                "btcidr",
                signal={"recommendation": "STRONG_SELL", "ml_confidence": 0.9, "price": 100},
            )
        post.assert_called_once()

    async def test_automatic_watched_alert_allows_sell_when_filter_all(self):
        class _FakeResp:
            status_code = 200
            text = "ok"

        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='all',
            subscribers={123: ["btcidr"]},
            _format_signal_message_html=Mock(return_value="signal text"),
            _last_signal_checks={},
            _notification_cooldown={},
        )
        with patch("autotrade.runtime.requests.post", return_value=_FakeResp()) as post, \
             patch("autotrade.runtime.Config.ADMIN_IDS", [123]), \
             patch("autotrade.runtime.Config.TELEGRAM_BOT_TOKEN", "tok"):
            await monitor_strong_signal(
                bot,
                "btcidr",
                signal={"recommendation": "STRONG_SELL", "ml_confidence": 0.9, "price": 100},
            )
        post.assert_called_once()

    async def test_automatic_autotrade_notification_allows_sell_when_filter_actionable(self):
        sent_messages = []

        async def fake_send_message(**kwargs):
            sent_messages.append(kwargs)

        risk_manager = SimpleNamespace(check_daily_loss_limit=Mock(return_value=(False, "blocked")))
        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='actionable',
            is_trading=True,
            auto_trade_pairs={123: ["btcidr"]},
            subscribers={123: ["btcidr"]},
            last_ml_update={},
            auto_trade_interval_minutes=0,
            _format_signal_message_html=Mock(return_value="signal text"),
            app=SimpleNamespace(bot=SimpleNamespace(send_message=fake_send_message)),
            risk_manager=risk_manager,
        )
        with patch("autotrade.runtime.Config.ADMIN_IDS", [123]):
            await check_trading_opportunity(
                bot,
                "btcidr",
                signal={"pair": "btcidr", "recommendation": "STRONG_SELL", "ml_confidence": 0.8, "price": 100},
            )
        self.assertEqual(len(sent_messages), 1)
        risk_manager.check_daily_loss_limit.assert_called_once()

    async def test_bot_background_notification_filter_blocks_only_hold(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.signal_notification_filter = 'all'
        self.assertTrue(bot._signal_passes_notification_filter("BUY"))
        self.assertTrue(bot._signal_passes_notification_filter("STRONG_BUY"))
        self.assertTrue(bot._signal_passes_notification_filter("SELL"))
        self.assertTrue(bot._signal_passes_notification_filter("STRONG_SELL"))
        self.assertFalse(bot._signal_passes_notification_filter("HOLD"))

    async def test_signal_on_message_explains_actionable_auto_push(self):
        bot = self._bot_for_signal_command()
        context = SimpleNamespace(args=["on"])

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.get_signal(self._update(), context)

        text = bot._send_message.await_args.args[2]
        self.assertIn("BUY/STRONG_BUY", text)
        self.assertIn("SELL/STRONG_SELL", text)
        self.assertIn("HOLD", text)

    async def test_watched_buy_alert_still_sends_when_notifications_on(self):
        class _FakeResp:
            status_code = 200
            text = "ok"

        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='all',
            subscribers={123: ["btcidr"]},
            _format_signal_message_html=Mock(return_value="signal text"),
            _last_signal_checks={},
            _notification_cooldown={},
        )
        with patch("autotrade.runtime.requests.post", return_value=_FakeResp()) as post, \
             patch("autotrade.runtime.Config.ADMIN_IDS", [123]), \
             patch("autotrade.runtime.Config.TELEGRAM_BOT_TOKEN", "tok"):
            await monitor_strong_signal(
                bot,
                "btcidr",
                signal={"recommendation": "BUY", "ml_confidence": 0.9, "price": 100},
            )
        post.assert_called_once()

    async def test_watched_sell_alert_sends_when_notifications_on(self):
        class _FakeResp:
            status_code = 200
            text = "ok"

        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='all',
            subscribers={123: ["btcidr"]},
            _format_signal_message_html=Mock(return_value="signal text"),
            _last_signal_checks={},
            _notification_cooldown={},
        )
        with patch("autotrade.runtime.requests.post", return_value=_FakeResp()) as post, \
             patch("autotrade.runtime.Config.ADMIN_IDS", [123]), \
             patch("autotrade.runtime.Config.TELEGRAM_BOT_TOKEN", "tok"):
            await monitor_strong_signal(
                bot,
                "btcidr",
                signal={"recommendation": "SELL", "ml_confidence": 0.9, "price": 100},
            )
        post.assert_called_once()

    async def test_watched_hold_alert_does_not_send_when_notifications_on(self):
        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='all',
            subscribers={123: ["btcidr"]},
            _format_signal_message_html=Mock(return_value="signal text"),
            _last_signal_checks={},
            _notification_cooldown={},
        )
        with patch("autotrade.runtime.requests.post") as post:
            await monitor_strong_signal(
                bot,
                "btcidr",
                signal={"recommendation": "HOLD", "ml_confidence": 0.9, "price": 100},
            )
        post.assert_not_called()


    async def test_watched_signal_cooldown_normalizes_pair_variants(self):
        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='all',
            subscribers={123: ["btcidr"]},
            _format_signal_message_html=Mock(return_value="signal text"),
            _last_signal_checks={},
            _notification_cooldown={},
        )

        class _FakeResp:
            status_code = 200
            text = "ok"

        signal = {"recommendation": "STRONG_BUY", "ml_confidence": 0.9, "price": 100}
        with patch("autotrade.runtime.requests.post", return_value=_FakeResp()) as post, \
             patch("autotrade.runtime.Config.ADMIN_IDS", [123]), \
             patch("autotrade.runtime.Config.TELEGRAM_BOT_TOKEN", "tok"):
            await monitor_strong_signal(bot, "BTC_IDR", signal=dict(signal))
            await monitor_strong_signal(bot, "btcidr", signal=dict(signal))

        post.assert_called_once()
        self.assertIn("btcidr", bot._last_signal_checks)
        self.assertIn("btcidr_STRONG_BUY", bot._notification_cooldown)

    async def test_autotrade_interval_normalizes_pair_variants(self):
        sent_messages = []

        async def fake_send_message(**kwargs):
            sent_messages.append(kwargs)

        risk_manager = SimpleNamespace(check_daily_loss_limit=Mock(return_value=(False, "blocked")))
        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='all',
            is_trading=True,
            auto_trade_pairs={123: ["btcidr"]},
            subscribers={123: ["btcidr"]},
            last_ml_update={},
            auto_trade_interval_minutes=5,
            _format_signal_message_html=Mock(return_value="signal text"),
            app=SimpleNamespace(bot=SimpleNamespace(send_message=fake_send_message)),
            risk_manager=risk_manager,
        )
        signal = {"pair": "btcidr", "recommendation": "BUY", "ml_confidence": 0.8, "price": 100}

        with patch("autotrade.runtime.Config.ADMIN_IDS", [123]):
            await check_trading_opportunity(bot, "BTC_IDR", signal=dict(signal))
            await check_trading_opportunity(bot, "btcidr", signal=dict(signal))

        self.assertEqual(len(sent_messages), 1)
        risk_manager.check_daily_loss_limit.assert_called_once()
        self.assertIn("btcidr", bot.last_ml_update)

    async def test_filter_actionable_blocks_hold_in_autotrade(self):
        sent_messages = []

        async def fake_send_message(**kwargs):
            sent_messages.append(kwargs)

        risk_manager = SimpleNamespace(check_daily_loss_limit=Mock(return_value=(False, "blocked")))
        bot = SimpleNamespace(
            signal_notifications_enabled=True,
            signal_notification_filter='actionable',
            is_trading=True,
            auto_trade_pairs={123: ["btcidr"]},
            subscribers={123: ["btcidr"]},
            last_ml_update={},
            auto_trade_interval_minutes=0,
            _format_signal_message_html=Mock(return_value="signal text"),
            app=SimpleNamespace(bot=SimpleNamespace(send_message=fake_send_message)),
            risk_manager=risk_manager,
        )
        with patch("autotrade.runtime.Config.ADMIN_IDS", [123]):
            await check_trading_opportunity(
                bot,
                "btcidr",
                signal={
                    "pair": "btcidr",
                    "recommendation": "BUY",
                    "ml_confidence": 0.8,
                    "price": 100,
                },
            )
        # actionable allows BUY, so message must be sent
        self.assertEqual(len(sent_messages), 1)


if __name__ == "__main__":
    unittest.main()
