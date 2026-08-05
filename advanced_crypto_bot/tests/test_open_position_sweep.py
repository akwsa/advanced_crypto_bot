# Tujuan: Regression test untuk PriceMonitor sweep posisi OPEN yang tidak ada di WATCH_PAIRS.
# Caller: pytest/unittest focused open-position exit watchdog.
# Dependensi: bot.AdvancedCryptoBot, autotrade.price_monitor.
# Side Effects: Tidak ada; DB/API/PriceMonitor di-fake.
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from autotrade.price_monitor import PriceMonitor


class _FakeDb:
    def __init__(self):
        self.closed = []

    def get_open_trades(self, user_id):
        return [
            {"id": 1, "pair": "penguidr", "status": "OPEN", "price": 100, "amount": 10},
            {"id": 2, "pair": "btcidr", "status": "CLOSED", "price": 100, "amount": 10},
        ]

    def get_trade(self, trade_id):
        return {"amount": 10}

    def close_trade(self, **kwargs):
        self.closed.append(kwargs)


class _FakeIndodax:
    def __init__(self):
        self.requested = []

    def get_ticker(self, pair):
        self.requested.append(pair)
        return {"last": 112.0, "bid": 111.0, "ask": 113.0}


class _FakeDbOpenBtc:
    def get_open_trades(self, user_id):
        return [
            {"id": 10, "pair": "btcidr", "status": "OPEN", "price": 1_500_000_000, "amount": 0.001},
        ]


class _FakeIndodaxBadMajorPrice:
    def __init__(self):
        self.requested = []

    def get_ticker(self, pair):
        self.requested.append(pair)
        return {"last": 100.0, "bid": 100.0, "ask": 101.0}


class _FakePriceMonitor:
    def __init__(self):
        self.rebuilt = False
        self.checked = []

    def rebuild_from_open_trades(self, db, trading_engine):
        self.rebuilt = True

    async def check_price_levels(self, pair, current_price):
        self.checked.append((pair, current_price))


class TestOpenPositionSweep(unittest.IsolatedAsyncioTestCase):
    async def test_sweep_checks_open_trade_pair_even_without_watchlist_tick(self):
        from bot import AdvancedCryptoBot

        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.db = _FakeDb()
        bot.trading_engine = object()
        bot.indodax = _FakeIndodax()
        bot.price_monitor = _FakePriceMonitor()

        with patch("bot.Config.ADMIN_IDS", [256024600]):
            await bot._sweep_open_position_price_levels()

        self.assertTrue(bot.price_monitor.rebuilt)
        self.assertEqual(bot.indodax.requested, ["penguidr"])
        self.assertEqual(bot.price_monitor.checked, [("penguidr", 112.0)])

    async def test_sweep_rejects_insane_major_pair_price(self):
        from bot import AdvancedCryptoBot

        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        bot.db = _FakeDbOpenBtc()
        bot.trading_engine = object()
        bot.indodax = _FakeIndodaxBadMajorPrice()
        bot.price_monitor = _FakePriceMonitor()

        with patch("bot.Config.ADMIN_IDS", [256024600]):
            await bot._sweep_open_position_price_levels()

        self.assertTrue(bot.price_monitor.rebuilt)
        self.assertEqual(bot.indodax.requested, ["btcidr"])
        self.assertEqual(bot.price_monitor.checked, [])

    async def test_time_exit_hold_does_not_disable_final_take_profit(self):
        db = _FakeDb()
        monitor = PriceMonitor(db)
        key = "256024600_1"
        monitor.price_levels[key] = {
            "user_id": 256024600,
            "trade_id": 1,
            "pair": "penguidr",
            "entry_price": 100.0,
            "amount": 10.0,
            "stop_loss": 90.0,
            "take_profit_1": 105.0,
            "take_profit_2": 112.0,
            "partial_1_triggered": True,
            "partial_2_triggered": False,
            "created_at": datetime.now() - timedelta(hours=25),
            "triggered": False,
            "support_1": 98.0,
            "resistance_1": 120.0,
            "sr_hold_count": 0,
        }
        monitor.trailing_stops[key] = {
            "highest_price": 100.0,
            "trailing_stop_price": 90.0,
            "is_active": False,
        }
        monitor.notified_drops[key] = set()

        with patch("autotrade.price_monitor.Config.SR_MAX_HOLD_HOURS", 24), \
             patch("autotrade.price_monitor.Config.TRADING_FEE_RATE", 0.003), \
             patch("autotrade.price_monitor.Config.SR_MAX_HOLD_LOSS_PCT", 8.0), \
             patch("autotrade.price_monitor.Config.AUTO_TRADE_DRY_RUN", True):
            await monitor.check_price_levels("penguidr", 99.0)

        self.assertFalse(monitor.price_levels[key]["partial_2_triggered"])
        self.assertFalse(monitor.price_levels[key]["triggered"])
        self.assertEqual(db.closed, [])


if __name__ == "__main__":
    unittest.main()
