import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram import InlineKeyboardMarkup, ReplyKeyboardRemove

from bot import AdvancedCryptoBot


class _FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class _FakeCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.answers = 0
        self.edits = []
        self.message = _FakeMessage("")

    async def answer(self):
        self.answers += 1

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class TestHelpQuickActions(unittest.IsolatedAsyncioTestCase):
    def _bot_with_mocks(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.db = SimpleNamespace(add_user=lambda *args, **kwargs: None)
        bot.scalper = None
        bot.is_trading = False
        bot.auto_trade_pairs = {123: ["btcidr"]}
        bot.subscribers = {123: ["btcidr"]}
        bot.menu = AsyncMock()
        bot.settings = AsyncMock()
        bot.market_scan = AsyncMock()
        bot.portfolio = AsyncMock()
        bot.notifications = AsyncMock()
        bot.signals = AsyncMock()
        bot.price = AsyncMock()
        bot.watch = AsyncMock()
        bot.get_signal = AsyncMock()
        return bot

    def _text_update(self, text):
        message = _FakeMessage(text)
        return SimpleNamespace(
            message=message,
            callback_query=None,
            effective_user=SimpleNamespace(id=123, username="budi", first_name="Budi"),
            effective_message=message,
        )

    def _callback_update(self, data):
        query = _FakeCallbackQuery(data)
        return SimpleNamespace(
            message=None,
            callback_query=query,
            effective_user=SimpleNamespace(id=123),
            effective_message=query.message,
        )

    def test_help_keyboard_buttons_match_requested_actions(self):
        bot = self._bot_with_mocks()
        keyboard = bot._build_quick_keyboard(is_admin=True).inline_keyboard
        callbacks = {
            button.text: button.callback_data
            for row in keyboard
            for button in row
            if button.callback_data
        }

        self.assertEqual(callbacks["📊 Market"], "market_scan_quick")
        self.assertEqual(callbacks["💼 Portfolio"], "portfolio_quick")
        self.assertEqual(callbacks["🔔 Alerts"], "notifications_quick")
        self.assertEqual(callbacks["📈 Signal"], "signals_quick")
        self.assertEqual(callbacks["💰 Price"], "price_quick")
        self.assertEqual(callbacks["📘 Panduan"], "help")
        self.assertEqual(callbacks["🤖 Auto-Trade"], "autotrade_quick")
        self.assertEqual(callbacks["⚙️ Admin"], "admin_panel")

    def test_android_keyboard_matches_requested_actions(self):
        bot = self._bot_with_mocks()
        keyboard = bot._build_android_reply_keyboard(is_admin=True).keyboard
        labels = [button.text for row in keyboard for button in row]

        self.assertEqual(
            labels,
            [
                "📊 Market",
                "💼 Portfolio",
                "🔔 Alerts",
                "📈 Signal",
                "💰 Price",
                "📘 Panduan",
                "🤖 Auto-Trade",
                "⚙️ Admin",
            ],
        )

    def test_telegram_keyboard_helpers_are_available_without_bot_instance(self):
        from bot_parts.telegram_keyboards import (
            build_android_reply_keyboard,
            build_menu_panel_keyboard,
            build_quick_keyboard,
        )

        quick_callbacks = {
            button.text: button.callback_data
            for row in build_quick_keyboard(is_admin=True).inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertEqual(quick_callbacks["📊 Market"], "market_scan_quick")
        self.assertEqual(quick_callbacks["🤖 Auto-Trade"], "autotrade_quick")
        self.assertEqual(quick_callbacks["⚙️ Admin"], "admin_panel")

        reply_labels = [
            button.text
            for row in build_android_reply_keyboard(is_admin=True).keyboard
            for button in row
        ]
        self.assertEqual(reply_labels[-2:], ["🤖 Auto-Trade", "⚙️ Admin"])

        menu_callbacks = {
            button.text: button.callback_data
            for row in build_menu_panel_keyboard("market", is_admin=False).inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertEqual(menu_callbacks["🔎 Scan"], "market_scan_quick")
        self.assertEqual(menu_callbacks["📈 Signal"], "signal_quick")
        self.assertEqual(menu_callbacks["💰 Price"], "price_quick")
        self.assertEqual(menu_callbacks["⬅️ Menu Utama"], "menu_home")

    async def test_start_uses_inline_menu_and_removes_persistent_reply_keyboard(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._text_update("/start")

        with patch("bot.Config.ADMIN_IDS", [123]), patch("bot.Config.DASHBOARD_URL", ""):
            await bot.start(update, context)

        self.assertEqual(len(update.message.replies), 2)
        self.assertIsInstance(update.message.replies[0][1]["reply_markup"], ReplyKeyboardRemove)
        self.assertIsInstance(update.message.replies[1][1]["reply_markup"], InlineKeyboardMarkup)
        self.assertIn("Keyboard cepat bawah disembunyikan", update.message.replies[0][0])

    async def test_main_help_buttons_call_expected_commands(self):
        bot = self._bot_with_mocks()

        for callback_data, expected_mock in [
            ("market_scan_quick", bot.market_scan),
            ("portfolio_quick", bot.portfolio),
            ("notifications_quick", bot.notifications),
            ("signals_quick", bot.signals),
        ]:
            context = SimpleNamespace(user_data={}, args=["stale"])
            await bot.callback_handler(self._callback_update(callback_data), context)
            expected_mock.assert_awaited_once()

        self.assertEqual(context.args, [])

    async def test_android_text_buttons_call_expected_commands(self):
        bot = self._bot_with_mocks()
        bot.help = AsyncMock()

        for label, expected_mock in [
            ("📊 Market", bot.market_scan),
            ("💼 Portfolio", bot.portfolio),
            ("🔔 Alerts", bot.notifications),
            ("📈 Signal", bot.signals),
            ("📘 Panduan", bot.help),
        ]:
            context = SimpleNamespace(user_data={}, args=["stale"] if label == "📈 Signal" else [])
            await bot.handle_text_input(self._text_update(label), context)
            expected_mock.assert_awaited_once()
            if label == "📈 Signal":
                self.assertEqual(context.args, [])

    async def test_android_price_button_sets_pending_price_action(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._text_update("💰 Price")

        await bot.handle_text_input(update, context)

        self.assertEqual(context.user_data["pending_quick_action"], "price")
        self.assertIn("Harga pair apa", update.message.replies[-1][0])

    async def test_help_callback_routes_through_help_method(self):
        bot = self._bot_with_mocks()
        bot.help = AsyncMock()
        context = SimpleNamespace(user_data={}, args=[])

        await bot.callback_handler(self._callback_update("help"), context)

        bot.help.assert_awaited_once()

    async def test_android_autotrade_button_shows_safe_panel_without_toggling(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._text_update("🤖 Auto-Trade")

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.handle_text_input(update, context)

        self.assertFalse(bot.is_trading)
        self.assertIn("Auto-Trade", update.message.replies[-1][0])
        self.assertIn("tidak toggle otomatis", update.message.replies[-1][0])

    async def test_android_admin_button_shows_admin_panel(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._text_update("⚙️ Admin")

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.handle_text_input(update, context)

        self.assertIn("Admin Panel", update.message.replies[-1][0])
        self.assertIn("/status", update.message.replies[-1][0])

    async def test_price_quick_callback_sets_pending_price_action(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._callback_update("price_quick")

        await bot.callback_handler(update, context)

        self.assertEqual(context.user_data["pending_quick_action"], "price")
        self.assertIn("Harga pair apa", update.callback_query.edits[-1][0])

    async def test_autotrade_quick_shows_safe_panel_without_toggling(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._callback_update("autotrade_quick")

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.callback_handler(update, context)

        self.assertFalse(bot.is_trading)
        self.assertIn("Auto-Trade", update.callback_query.edits[-1][0])
        self.assertIn("tidak toggle otomatis", update.callback_query.edits[-1][0])

    async def test_admin_panel_explains_admin_actions(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._callback_update("admin_panel")

        with patch("bot.Config.ADMIN_IDS", [123]):
            await bot.callback_handler(update, context)

        self.assertIn("Admin Panel", update.callback_query.edits[-1][0])
        self.assertIn("/status", update.callback_query.edits[-1][0])

    async def test_signal_quick_callback_sets_pending_signal_action(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._callback_update("signal_quick")

        await bot.callback_handler(update, context)

        self.assertEqual(context.user_data["pending_quick_action"], "signal")
        self.assertIn("Signal untuk pair apa", update.callback_query.edits[-1][0])

    async def test_pending_price_button_routes_next_pair_to_price(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={"pending_quick_action": "price"}, args=[])

        await bot.handle_text_input(self._text_update("btcidr"), context)

        bot.price.assert_awaited_once()
        bot.get_signal.assert_not_awaited()
        self.assertEqual(context.args, ["btcidr"])
        self.assertNotIn("pending_quick_action", context.user_data)

    async def test_pending_watch_button_routes_next_pair_to_watch(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={"pending_quick_action": "watch"}, args=[])

        await bot.handle_text_input(self._text_update("ethidr"), context)

        bot.watch.assert_awaited_once()
        bot.get_signal.assert_not_awaited()
        self.assertEqual(context.args, ["ethidr"])
        self.assertNotIn("pending_quick_action", context.user_data)

    async def test_plain_pair_text_still_defaults_to_signal(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])

        await bot.handle_text_input(self._text_update("solidr"), context)

        bot.get_signal.assert_awaited_once()
        bot.price.assert_not_awaited()
        self.assertEqual(context.args, ["solidr"])

    async def test_start_keyboard_uses_direct_action_callbacks(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._text_update("/start")

        with patch("bot.Config.ADMIN_IDS", [123]), patch("bot.Config.DASHBOARD_URL", ""):
            await bot.start(update, context)

        start_keyboard = update.message.replies[1][1]["reply_markup"].inline_keyboard

        callbacks = {
            button.text: button.callback_data
            for row in start_keyboard
            for button in row
            if button.callback_data
        }

        self.assertEqual(callbacks["📊 Market"], "market_scan_quick")
        self.assertEqual(callbacks["💼 Portfolio"], "portfolio_quick")
        self.assertEqual(callbacks["🔔 Alerts"], "notifications_quick")
        self.assertEqual(callbacks["📈 Signal"], "signals_quick")
        self.assertEqual(callbacks["💰 Price"], "price_quick")
        self.assertEqual(callbacks["🤖 Auto-Trade"], "autotrade_quick")
        self.assertEqual(callbacks["⚙️ Admin"], "admin_panel")

    async def test_all_menu_panel_keyboards_produce_valid_markup(self):
        bot = self._bot_with_mocks()

        for section in ("market", "portfolio", "alerts", "settings"):
            markup = bot._build_menu_panel_keyboard(section, is_admin=True)
            self.assertIsInstance(markup, InlineKeyboardMarkup)
            self.assertGreater(len(markup.inline_keyboard), 0)

        markup_fallback = bot._build_menu_panel_keyboard("home", is_admin=True)
        self.assertIsInstance(markup_fallback, InlineKeyboardMarkup)
        self.assertIn("⬅️ Menu Utama", markup_fallback.inline_keyboard[-1][0].text)

    async def test_start_keyboard_nav_settings_opens_settings_panel(self):
        bot = self._bot_with_mocks()
        context = SimpleNamespace(user_data={}, args=[])
        update = self._callback_update("nav_settings")

        with patch("bot.Config.DASHBOARD_URL", ""):
            await bot.callback_handler(update, context)

        self.assertIn("Settings", update.callback_query.edits[-1][0])
        reply_markup = update.callback_query.edits[-1][1].get("reply_markup")
        self.assertIsInstance(reply_markup, InlineKeyboardMarkup)

    def test_settings_panel_autotrade_button_opens_safe_panel(self):
        bot = self._bot_with_mocks()
        markup = bot._build_menu_panel_keyboard("settings", is_admin=True)
        callbacks = {
            button.text: button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertEqual(callbacks["🤖 Auto-Trade"], "autotrade_quick")

    def test_admin_panel_helpers_are_available_without_bot_instance(self):
        from bot_parts.admin_panels import build_admin_panel_markup, build_admin_panel_text

        text = build_admin_panel_text()
        self.assertIn("Admin Panel", text)
        self.assertIn("/status", text)
        self.assertIn("/autotrade_status", text)
        self.assertIn("/retrain", text)
        self.assertIn("/backtest btcidr 30", text)

        callbacks = {
            button.text: button.callback_data
            for row in build_admin_panel_markup().inline_keyboard
            for button in row
            if button.callback_data
        }
        self.assertEqual(callbacks["⚙️ Status"], "status_quick")
        self.assertEqual(callbacks["📊 Logs"], "admin_logs")
        self.assertEqual(callbacks["🤖 Retrain"], "admin_retrain")
        self.assertEqual(callbacks["📈 Backtest"], "admin_backtest")
        self.assertEqual(callbacks["⬅️ Menu Utama"], "menu_home")


if __name__ == "__main__":
    unittest.main()
