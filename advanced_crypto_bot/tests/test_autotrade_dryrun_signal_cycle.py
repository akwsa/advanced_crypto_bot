# Tujuan: Regression test AutoTrade DRY RUN BUY→wait→SELL cycle.
# Caller: unittest focused autotrade runtime behavior.
# Dependensi: autotrade.runtime.check_trading_opportunity dengan semua I/O dimock.
# Side Effects: Tidak ada; DB/Telegram/Indodax dimock in-memory.
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from autotrade.runtime import check_trading_opportunity


class _FakeDryRunDB:
    def __init__(self):
        self.trades = []
        self.closed_trade_ids = []

    def get_pair_performance(self, pair):
        return None

    def get_balance(self, user_id):
        return 10_000_000

    def get_open_trades(self, user_id):
        return [trade for trade in self.trades if trade["user_id"] == user_id and trade["status"] == "OPEN"]

    def add_trade(self, user_id, pair, trade_type, price, amount, total, fee, signal_source, ml_confidence, notes=None):
        trade_id = len(self.trades) + 1
        self.trades.append({
            "id": trade_id,
            "user_id": user_id,
            "pair": pair,
            "type": trade_type,
            "price": price,
            "amount": amount,
            "total": total,
            "fee": fee,
            "signal_source": signal_source,
            "ml_confidence": ml_confidence,
            "status": "OPEN",
            "notes": notes,
        })
        return trade_id

    def add_pending_order(self, **kwargs):
        return 1

    def close_trade(self, trade_id, sell_price=None, sell_amount=None, order_id=None, reason=None, **kwargs):
        for trade in self.trades:
            if trade["id"] == trade_id:
                trade["status"] = "CLOSED"
                trade["closed_price"] = sell_price
                trade["closed_amount"] = sell_amount
                trade["close_order_id"] = order_id
                trade["close_reason"] = reason
                self.closed_trade_ids.append(trade_id)
                return True
        return False


class TestAutoTradeDryRunSignalCycle(unittest.IsolatedAsyncioTestCase):
    async def test_buy_signal_opens_dryrun_position_then_sell_signal_closes_same_pair(self):
        """BUY/STRONG_BUY harus membuka posisi DRY RUN, lalu SELL/STRONG_SELL
        untuk pair yang sama harus tetap diproses walau interval auto-trade belum lewat.
        """
        db = _FakeDryRunDB()
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["btcidr"]},
            subscribers={123: ["btcidr"]},
            last_ml_update={},
            auto_trade_interval_minutes=5,
            signal_notifications_enabled=False,
            signal_notification_filter="actionable",
            db=db,
            risk_manager=SimpleNamespace(check_daily_loss_limit=Mock(return_value=(True, "ok"))),
            _check_max_drawdown=Mock(return_value=(True, "ok")),
            _format_signal_message_html=Mock(return_value="signal text"),
            app=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
            indodax=SimpleNamespace(
                get_ticker=Mock(return_value={"last": 100.0, "bid": 110.0}),
                get_orderbook=Mock(return_value={"bids": [], "asks": []}),
            ),
            price_data={},
            historical_data={},
            ml_model_v4=None,
            _quant_kelly_engine=None,
            _quant_momentum_engine=None,
            trading_engine=SimpleNamespace(
                should_execute_trade=Mock(return_value=(True, "ok")),
                calculate_position_size=Mock(return_value=(10.0, 1000.0)),
                calculate_stop_loss_take_profit=Mock(return_value={
                    "stop_loss": 98.0,
                    "take_profit_1": 104.0,
                    "take_profit_2": 108.0,
                    "rr_ratio": 2.0,
                    "method": "fixed",
                }),
            ),
            price_monitor=SimpleNamespace(
                set_price_level=Mock(),
                remove_price_level=Mock(),
            ),
            sr_detector=SimpleNamespace(),
            _broadcast_to_subscribers=AsyncMock(),
            _find_liquidity_zones=Mock(return_value=[]),
            _elite_signal=Mock(return_value=("BUY", 0.8, 1.0)),
            _fee_aware_net_price=Mock(return_value=(100.0, 0.0, 0.0)),
        )

        optimization = SimpleNamespace(
            should_skip=False,
            reason="ok",
            position_multiplier=1.0,
            stop_loss_multiplier=1.0,
            tp1_multiplier=1.0,
            tp2_multiplier=1.0,
            min_rr_required=1.0,
            edge_score=10.0,
        )

        with patch("autotrade.runtime.Config.AUTO_TRADE_DRY_RUN", True), \
             patch("autotrade.runtime.Config.ADMIN_IDS", [123]), \
             patch("autotrade.runtime.Config.CORRELATION_AVOIDANCE_ENABLED", False), \
             patch("autotrade.runtime.Config.RL_ENABLED", False), \
             patch("autotrade.runtime.Config.SMART_ROUTING_ENABLED", False), \
             patch("autotrade.runtime.Config.PORTFOLIO_RISK_ADJUSTED", False), \
             patch("autotrade.runtime.Config.LIMIT_ORDER_MIN_EDGE_PCT", 0.0), \
             patch("autotrade.runtime.Config.AUTOTRADE_CHASE_THRESHOLD_PCT", 1.5), \
             patch("autotrade.runtime.Config.TRADING_FEE_RATE", 0.0), \
             patch("api.indodax_api.IndodaxAPI", Mock(return_value=bot.indodax)), \
             patch("autotrade.runtime.analyze_market_intelligence", AsyncMock(return_value={"passes_entry_filter": True, "overall_signal": "BULLISH"})), \
             patch("autotrade.runtime.detect_market_regime", Mock(return_value={"regime": "RANGE", "volatility": 0.01, "is_high_vol": False, "is_trending": False, "trend_direction": "NEUTRAL"})), \
             patch("autotrade.runtime.get_support_resistance_for_pair", AsyncMock(return_value=None)), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            await check_trading_opportunity(
                bot,
                "btcidr",
                signal={"pair": "btcidr", "recommendation": "BUY", "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
            )
            self.assertEqual(len(db.get_open_trades(123)), 1)

            await check_trading_opportunity(
                bot,
                "btcidr",
                signal={"pair": "btcidr", "recommendation": "SELL", "ml_confidence": 0.8, "price": 110.0, "indicators": {}},
            )

        self.assertEqual(db.get_open_trades(123), [])
        self.assertEqual(db.closed_trade_ids, [1])
        bot.price_monitor.remove_price_level.assert_called_once_with(123, 1)


if __name__ == "__main__":
    unittest.main()
