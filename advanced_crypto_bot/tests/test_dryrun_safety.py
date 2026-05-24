# Tujuan: Test safety dry-run lintas modul yang bisa menyentuh API real.
# Caller: unittest focused dry-run safety checks.
# Dependensi: autotrade.price_monitor, autohunter.smart_profit_hunter.
# Main Functions: class TestDryRunSafety.
# Side Effects: Temporary in-memory DB fake; no network/API call.
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from autohunter.smart_profit_hunter import SmartProfitHunter
from autotrade.price_monitor import PriceMonitor


class _FakeDb:
    def __init__(self):
        self.closed = []

    def get_trade(self, trade_id):
        return {"amount": 100}

    def close_trade(self, **kwargs):
        self.closed.append(kwargs)


class TestDryRunSafety(unittest.IsolatedAsyncioTestCase):
    async def test_price_monitor_dryrun_auto_sell_does_not_call_indodax(self):
        db = _FakeDb()
        monitor = PriceMonitor(db)
        level = {
            "user_id": 123,
            "trade_id": 77,
            "pair": "l3idr",
            "amount": 100,
            "entry_price": 100,
        }

        with patch("autotrade.price_monitor.Config.AUTO_TRADE_DRY_RUN", True), \
             patch("api.indodax_api.IndodaxAPI", side_effect=AssertionError("real API called")):
            await monitor._execute_auto_sell(level, 120, "TAKE_PROFIT")

        self.assertEqual(len(db.closed), 1)
        self.assertEqual(db.closed[0]["order_id"], "DRY-PM-77-TAKE_PROFIT")
        self.assertNotIn("123_77", monitor.price_levels)

    def test_smart_hunter_dryrun_balance_uses_virtual_balance_without_private_api(self):
        hunter = SmartProfitHunter(dry_run=True)
        hunter.session = SimpleNamespace(post=Mock(side_effect=AssertionError("private API called")))

        self.assertTrue(hunter.get_balance())
        self.assertEqual(hunter.balance_idr, 10_000_000)
        hunter.session.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
