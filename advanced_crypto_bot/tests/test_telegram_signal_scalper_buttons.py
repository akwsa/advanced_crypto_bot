# Tujuan: Test tombol signal Telegram yang mengacu official Indodax pair dan posisi/balance.
# Caller: unittest focused Telegram signal action policy.
# Dependensi: bot.AdvancedCryptoBot, fake Indodax/scalper snapshots.
# Side Effects: Tidak ada; semua API dimock.
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from bot import AdvancedCryptoBot
from core.config import Config


class TestTelegramSignalScalperButtons(unittest.TestCase):
    def _bot(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot._official_indodax_pairs_cache = {"btcidr", "ethidr", "solidr"}
        bot._official_indodax_pairs_cached_at = 9999999999
        bot._indodax_balance_cache = {
            "available": {"idr": "1000000", "eth": "0.25"},
            "hold": {},
            "available_unavailable": False,
        }
        bot._indodax_balance_cached_at = 9999999999
        bot.scalper = SimpleNamespace(active_positions={})
        return bot

    def _button_texts(self, markup):
        return [button.text for row in markup.inline_keyboard for button in row]

    def _callback_data(self, markup):
        return [button.callback_data for row in markup.inline_keyboard for button in row]

    def test_buy_button_requires_official_indodax_pair(self):
        bot = self._bot()

        markup = bot._build_signal_action_markup({
            "pair": "BTC/IDR",
            "recommendation": "BUY",
        })

        self.assertIsNotNone(markup)
        self.assertIn("🟢 BUY BTCIDR via Scalper", self._button_texts(markup))
        self.assertIn("s_buy:btcidr", self._callback_data(markup))

        self.assertIsNone(bot._build_signal_action_markup({
            "pair": "FAKEIDR",
            "recommendation": "BUY",
        }))

    def test_sell_button_requires_indodax_coin_amount(self):
        bot = self._bot()

        eth_markup = bot._build_signal_action_markup({
            "pair": "ethidr",
            "recommendation": "SELL",
        })
        self.assertIsNotNone(eth_markup)
        self.assertIn("🔴 SELL ETHIDR via Scalper", self._button_texts(eth_markup))
        self.assertIn("s_sell:ethidr", self._callback_data(eth_markup))

        btc_markup = bot._build_signal_action_markup({
            "pair": "btcidr",
            "recommendation": "SELL",
        })
        self.assertIsNone(btc_markup)

    def test_sell_button_allows_scalper_local_position_when_balance_zero(self):
        bot = self._bot()
        bot.scalper = SimpleNamespace(active_positions={
            "solidr": {"amount": 12.5, "entry": 100, "capital": 1250}
        })

        markup = bot._build_signal_action_markup({
            "pair": "SOL_IDR",
            "recommendation": "STRONG_SELL",
        })

        self.assertIsNotNone(markup)
        self.assertIn("🔴 SELL SOLIDR via Scalper", self._button_texts(markup))
        self.assertIn("s_sell:solidr", self._callback_data(markup))

    def test_no_buttons_when_official_pair_list_unavailable(self):
        bot = self._bot()
        bot._official_indodax_pairs_cache = set()

        markup = bot._build_signal_action_markup({
            "pair": "btcidr",
            "recommendation": "BUY",
        })

        self.assertIsNone(markup)

    def test_lock_no_money_automation_forces_dryrun_and_off(self):
        bot = self._bot()
        bot.is_trading = True
        bot.db = SimpleNamespace(set_auto_trade_mode=Mock())

        bot._lock_no_money_automation("unit-test")

        self.assertFalse(bot.is_trading)
        bot.db.set_auto_trade_mode.assert_called_once_with(True)

    def test_startup_dryrun_autotrade_forces_dryrun_on(self):
        bot = self._bot()
        bot.is_trading = False
        bot.db = SimpleNamespace(set_auto_trade_mode=Mock())
        Config.AUTO_TRADE_DRY_RUN = False

        bot._enable_startup_dryrun_autotrade()

        self.assertTrue(bot.is_trading)
        self.assertTrue(Config.AUTO_TRADE_DRY_RUN)
        bot.db.set_auto_trade_mode.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
