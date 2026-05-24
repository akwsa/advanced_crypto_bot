import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from bot import AdvancedCryptoBot


class _Order(dict):
    def keys(self):
        return super().keys()


class TestPendingOrders(unittest.IsolatedAsyncioTestCase):
    async def test_check_pending_orders_handles_none_order_id_without_crashing(self):
        bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
        order = _Order(
            id=1,
            order_id=None,
            pair="btcidr",
            limit_price=100.0,
            placed_at="2026-05-22T00:00:00",
            amount=1.0,
            user_id=123,
        )
        bot.db = SimpleNamespace(
            get_pending_orders=Mock(return_value=[order]),
            update_pending_order_cancelled=Mock(),
            update_pending_order_filled=Mock(),
            close_trade=Mock(),
        )
        bot.indodax = SimpleNamespace(
            get_open_orders=Mock(return_value=[]),
            get_ticker=Mock(return_value={"last": 110.0}),
            cancel_order=Mock(return_value={"success": 1}),
        )
        bot.price_data = {}
        bot.price_monitor = SimpleNamespace(remove_price_level=Mock())

        await bot.check_pending_orders()

        bot.db.get_pending_orders.assert_called_once_with(status="PENDING")
        bot.db.update_pending_order_filled.assert_called_once_with(
            1,
            fill_price=100.0,
            notes="Filled (order no longer in open orders)",
        )


if __name__ == "__main__":
    unittest.main()
