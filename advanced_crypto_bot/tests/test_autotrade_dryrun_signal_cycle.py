# Tujuan: Regression tests untuk auto-promote dan sizing nominal AutoTrade DRY RUN berdasarkan tier harga pair.
# Caller: unittest focused autotrade runtime behavior.

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
    def _make_dryrun_bot(self, pair="btcidr"):
        db = _FakeDryRunDB()
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: [pair]},
            subscribers={123: [pair]},
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
                get_ticker=Mock(return_value={"last": 100.0, "bid": 100.0}),
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
            price_monitor=SimpleNamespace(set_price_level=Mock(), remove_price_level=Mock()),
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
        return bot, db, optimization

    async def _run_dryrun_signal(self, bot, pair, signal, optimization):
        with patch("autotrade.runtime.Config.AUTO_TRADE_DRY_RUN", True), \
             patch("autotrade.runtime.Config.ADMIN_IDS", [123]), \
             patch("autotrade.runtime.Config.CORRELATION_AVOIDANCE_ENABLED", False), \
             patch("autotrade.runtime.Config.RL_ENABLED", False), \
             patch("autotrade.runtime.Config.SMART_ROUTING_ENABLED", False), \
             patch("autotrade.runtime.Config.PORTFOLIO_RISK_ADJUSTED", False), \
             patch("autotrade.runtime.Config.LIMIT_ORDER_MIN_EDGE_PCT", 0.0), \
             patch("autotrade.runtime.Config.AUTOTRADE_CHASE_THRESHOLD_PCT", 1.5), \
             patch("autotrade.runtime.Config.TRADING_FEE_RATE", 0.0), \
             patch("autotrade.runtime.Config.AUTOTRADE_LIQUIDITY_WHITELIST", []), \
             patch("autotrade.runtime.Config.AUTOTRADE_LIQUIDITY_PROMOTE_REQUIRE_BIDASK", False), \
             patch("api.indodax_api.IndodaxAPI", Mock(return_value=bot.indodax)), \
             patch("autotrade.runtime._calculate_entry_zone", Mock(return_value=100.0)), \
             patch("autotrade.runtime.analyze_market_intelligence", AsyncMock(return_value={"passes_entry_filter": True, "overall_signal": "BULLISH"})), \
             patch("autotrade.runtime.detect_market_regime", Mock(return_value={"regime": "RANGE", "volatility": 0.01, "is_high_vol": False, "is_trending": False, "trend_direction": "NEUTRAL"})), \
             patch("autotrade.runtime.get_support_resistance_for_pair", AsyncMock(return_value=None)), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            await check_trading_opportunity(bot, pair, signal=signal)

    async def test_duplicate_filtered_signal_does_not_open_dryrun_trade(self):
        bot, db, optimization = self._make_dryrun_bot("btcidr")

        await self._run_dryrun_signal(
            bot,
            "btcidr",
            {
                "pair": "btcidr",
                "recommendation": "HOLD",
                "pre_sr_recommendation": "STRONG_BUY",
                "display_recommendation": "HOLD",
                "duplicate_filtered": True,
                "duplicate_filtered_reason": "duplicate buy signal tanpa improvement",
                "ml_confidence": 0.8,
                "price": 100.0,
                "indicators": {},
            },
            optimization,
        )

        self.assertEqual(db.get_open_trades(123), [])
        bot.trading_engine.should_execute_trade.assert_not_called()

    async def test_execution_allowed_false_signal_does_not_open_dryrun_trade(self):
        bot, db, optimization = self._make_dryrun_bot("btcidr")

        await self._run_dryrun_signal(
            bot,
            "btcidr",
            {
                "pair": "btcidr",
                "recommendation": "BUY",
                "pre_sr_recommendation": "BUY",
                "display_recommendation": "BUY",
                "execution_allowed": False,
                "decision_reason": "decision layer blocked execution",
                "ml_confidence": 0.8,
                "price": 100.0,
                "indicators": {},
            },
            optimization,
        )

        self.assertEqual(db.get_open_trades(123), [])
        bot.trading_engine.should_execute_trade.assert_not_called()

    async def test_pre_sr_override_promotes_hold_to_buy_and_opens_dryrun_trade(self):
        """REGRESSION 2026-06-11: signal[recommendation]=HOLD with
        pre_sr_recommendation=BUY/STRONG_BUY must be overridden so the
        downstream gates (`should_execute_trade`, MI filter, execution
        path) treat it as the autotrade-relevant pre-SR recommendation.

        Without the override, signals downgraded by SR_VALIDATION
        (which is a Telegram-notification filter, not an autotrade
        filter) silently bypassed every gate after the weak-signal
        check, resulting in 0 entries despite valid pre-SR BUY signals.
        """
        bot, db, optimization = self._make_dryrun_bot("btcidr")

        await self._run_dryrun_signal(
            bot,
            "btcidr",
            {
                "pair": "btcidr",
                "recommendation": "HOLD",
                "pre_sr_recommendation": "STRONG_BUY",
                "display_recommendation": "STRONG_BUY",
                "ml_confidence": 0.8,
                "price": 100.0,
                "indicators": {},
            },
            optimization,
        )

        # Override harus aktif: gate `should_execute_trade` dipanggil
        # (artinya signal["recommendation"] di-promote dari HOLD ke STRONG_BUY).
        bot.trading_engine.should_execute_trade.assert_called()
        # Posisi DRY RUN terbuka.
        self.assertEqual(len(db.get_open_trades(123)), 1)

    async def test_pre_sr_override_does_not_promote_when_pre_sr_is_hold(self):
        """Sanity: pre_sr_recommendation=HOLD harus tetap di-skip sebagai
        weak signal — override hanya berlaku saat pre_sr ∈ BUY/STRONG_BUY/SELL/STRONG_SELL.
        """
        bot, db, optimization = self._make_dryrun_bot("btcidr")

        await self._run_dryrun_signal(
            bot,
            "btcidr",
            {
                "pair": "btcidr",
                "recommendation": "HOLD",
                "pre_sr_recommendation": "HOLD",
                "display_recommendation": "HOLD",
                "ml_confidence": 0.8,
                "price": 100.0,
                "indicators": {},
            },
            optimization,
        )

        bot.trading_engine.should_execute_trade.assert_not_called()
        self.assertEqual(db.get_open_trades(123), [])

    async def test_pantau_display_signal_does_not_open_dryrun_trade_even_when_pre_sr_buy(self):
        bot, db, optimization = self._make_dryrun_bot("btcidr")

        await self._run_dryrun_signal(
            bot,
            "btcidr",
            {
                "pair": "btcidr",
                "recommendation": "BUY",
                "pre_sr_recommendation": "STRONG_BUY",
                "display_recommendation": "PANTAU",
                "display_reason": "momentum belum konfirmasi",
                "ml_confidence": 0.8,
                "price": 100.0,
                "indicators": {},
            },
            optimization,
        )

        self.assertEqual(db.get_open_trades(123), [])
        bot.trading_engine.should_execute_trade.assert_not_called()

    async def test_dryrun_only_strong_buy_opens_and_buy_does_not_open_position(self):
        """DRY RUN: BUY dan STRONG_BUY keduanya bisa buka posisi (validasi realistis).
        Dulu BUY diblokir, sekarang diizinkan agar DRY RUN representatif untuk real trading."""
        db = _FakeDryRunDB()
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["testidr"]},
            subscribers={123: ["testidr"]},
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
            price_monitor=SimpleNamespace(set_price_level=Mock(), remove_price_level=Mock()),
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
                "testidr",
                signal={"pair": "testidr", "recommendation": "BUY", "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
            )
            # BUY now opens a position in DRY RUN (was previously blocked)
            self.assertEqual(len(db.get_open_trades(123)), 1)

            await check_trading_opportunity(
                bot,
                "testidr",
                signal={"pair": "testidr", "recommendation": "STRONG_BUY", "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
            )

        open_trades = db.get_open_trades(123)
        # Still only 1 trade — duplicate-position guard blocks the second entry
        self.assertEqual(len(open_trades), 1)
        self.assertEqual(open_trades[0]["type"], "BUY")

    async def test_dryrun_strong_buy_does_not_double_entry_before_sell(self):
        """Kalau sudah BUY dan belum SELL, STRONG_BUY berikutnya harus di-skip agar tidak double-entry."""
        db = _FakeDryRunDB()
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["testidr"]},
            subscribers={123: ["testidr"]},
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
            price_monitor=SimpleNamespace(set_price_level=Mock(), remove_price_level=Mock()),
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
            for _ in range(2):
                await check_trading_opportunity(
                    bot,
                    "testidr",
                    signal={"pair": "testidr", "recommendation": "STRONG_BUY", "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
                )

        open_trades = db.get_open_trades(123)
        self.assertEqual(len(open_trades), 1)

    async def test_strong_buy_signal_opens_dryrun_position_then_sell_signal_closes_same_pair(self):
        """STRONG_BUY harus membuka posisi DRY RUN, lalu SELL/STRONG_SELL
        untuk pair yang sama harus tetap diproses walau interval auto-trade belum lewat.
        """
        db = _FakeDryRunDB()
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["testidr"]},
            subscribers={123: ["testidr"]},
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
                "testidr",
                signal={"pair": "testidr", "recommendation": "STRONG_BUY", "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
            )
            self.assertEqual(len(db.get_open_trades(123)), 1)

            await check_trading_opportunity(
                bot,
                "testidr",
                signal={"pair": "testidr", "recommendation": "SELL", "ml_confidence": 0.8, "price": 110.0, "indicators": {}},
            )

        self.assertEqual(db.get_open_trades(123), [])
        self.assertEqual(db.closed_trade_ids, [1])
        bot.price_monitor.remove_price_level.assert_called_once_with(123, 1)

    async def test_watched_buy_signal_auto_promotes_and_saves_dryrun_trade_to_db(self):
        """Saat /autotrade dryrun aktif, BUY/STRONG_BUY dari pair watchlist
        harus otomatis masuk auto_trade_pairs. Jika recommendation final adalah
        BUY/STRONG_BUY (bukan HOLD), trade DRY RUN juga harus tersimpan di DB.

        FIX 2026-06-11: Bahkan ketika recommendation=HOLD (misal di-downgrade
        oleh SR_VALIDATION) tapi pre_sr_recommendation=STRONG_BUY, trade tetap
        dieksekusi karena override pre_sr di check_trading_opportunity.
        SR_VALIDATION adalah filter notifikasi Telegram, bukan filter autotrade —
        autotrade punya 17 entry gate sendiri yang lebih appropriate."""
        db = _FakeDryRunDB()
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={},
            subscribers={123: ["testidr"]},
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
            price_monitor=SimpleNamespace(set_price_level=Mock(), remove_price_level=Mock()),
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
             patch("autotrade.runtime.Config.AUTOTRADE_LIQUIDITY_WHITELIST", []), \
             patch("autotrade.runtime.Config.AUTOTRADE_LIQUIDITY_PROMOTE_REQUIRE_BIDASK", False), \
             patch("api.indodax_api.IndodaxAPI", Mock(return_value=bot.indodax)), \
             patch("autotrade.runtime.analyze_market_intelligence", AsyncMock(return_value={"passes_entry_filter": True, "overall_signal": "BULLISH"})), \
             patch("autotrade.runtime.detect_market_regime", Mock(return_value={"regime": "RANGE", "volatility": 0.01, "is_high_vol": False, "is_trending": False, "trend_direction": "NEUTRAL"})), \
             patch("autotrade.runtime.get_support_resistance_for_pair", AsyncMock(return_value=None)), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            # Signal with recommendation=HOLD (di-downgrade oleh SR_VALIDATION).
            # FIX 2026-06-11: pre_sr_recommendation=STRONG_BUY harus override
            # signal["recommendation"] supaya autotrade execution path tetap
            # jalan (SR_VALIDATION adalah filter notifikasi Telegram, bukan
            # filter autotrade).
            await check_trading_opportunity(
                bot,
                "testidr",
                signal={"pair": "testidr", "recommendation": "HOLD", "pre_sr_recommendation": "STRONG_BUY", "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
            )

        # Auto-promote should happen (pair added to auto_trade_pairs).
        self.assertEqual(bot.auto_trade_pairs[123], ["testidr"])
        # FIX 2026-06-11: Trade DRY RUN HARUS terbuka karena pre_sr override
        # mempromosikan recommendation HOLD → STRONG_BUY untuk autotrade path.
        open_trades = db.get_open_trades(123)
        self.assertEqual(len(open_trades), 1)
        bot.price_monitor.set_price_level.assert_called()

    async def test_low_price_pair_uses_price_times_1000_as_dryrun_nominal(self):
        db = _FakeDryRunDB()
        current_price = 370.0
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["pippinidr"]},
            subscribers={123: ["pippinidr"]},
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
                get_ticker=Mock(return_value={"last": current_price, "bid": current_price}),
                get_orderbook=Mock(return_value={"bids": [], "asks": []}),
            ),
            price_data={},
            historical_data={},
            ml_model_v4=None,
            _quant_kelly_engine=None,
            _quant_momentum_engine=None,
            trading_engine=SimpleNamespace(
                should_execute_trade=Mock(return_value=(True, "ok")),
                calculate_position_size=Mock(return_value=(1.0, 12345.0)),
                calculate_stop_loss_take_profit=Mock(return_value={
                    "stop_loss": current_price - 10,
                    "take_profit_1": current_price + 20,
                    "take_profit_2": current_price + 40,
                    "rr_ratio": 2.0,
                    "method": "fixed",
                }),
            ),
            price_monitor=SimpleNamespace(set_price_level=Mock(), remove_price_level=Mock()),
            sr_detector=SimpleNamespace(),
            _broadcast_to_subscribers=AsyncMock(),
            _find_liquidity_zones=Mock(return_value=[]),
            _elite_signal=Mock(return_value=("BUY", 0.8, 1.0)),
            _fee_aware_net_price=Mock(return_value=(current_price, 0.0, 0.0)),
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
             patch("autotrade.runtime.Config.AUTOTRADE_CHASE_THRESHOLD_PCT", 10.0), \
             patch("autotrade.runtime.Config.TRADING_FEE_RATE", 0.0), \
             patch("api.indodax_api.IndodaxAPI", Mock(return_value=bot.indodax)), \
             patch("autotrade.runtime.analyze_market_intelligence", AsyncMock(return_value={"passes_entry_filter": True, "overall_signal": "BULLISH"})), \
             patch("autotrade.runtime.detect_market_regime", Mock(return_value={"regime": "RANGE", "volatility": 0.01, "is_high_vol": False, "is_trending": False, "trend_direction": "NEUTRAL"})), \
             patch("autotrade.runtime.get_support_resistance_for_pair", AsyncMock(return_value=None)), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            await check_trading_opportunity(
                bot,
                "pippinidr",
                signal={"pair": "pippinidr", "recommendation": "STRONG_BUY", "ml_confidence": 0.9, "price": current_price, "indicators": {}},
            )

        open_trades = db.get_open_trades(123)
        self.assertEqual(len(open_trades), 1)
        # FIX 2026-06-07: MAX_TOTAL=2.000.000 with slippage 0.1%
        # Price=370, min coins=10000, total=370*10000=3.700.000 → clamped to 2.000.000 max
        self.assertAlmostEqual(open_trades[0]["total"], 2000000.0, delta=20000.0)

    async def test_mid_price_pair_uses_price_times_100_as_dryrun_nominal(self):
        """Mid-price pair uses new formula: target total 1.000.000-1.500.000 IDR.
        For price=25000: target=1.250.000 IDR, amount=50 coins."""
        db = _FakeDryRunDB()
        current_price = 25000.0
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["midpriceidr"]},
            subscribers={123: ["midpriceidr"]},
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
                get_ticker=Mock(return_value={"last": current_price, "bid": current_price}),
                get_orderbook=Mock(return_value={"bids": [], "asks": []}),
            ),
            price_data={},
            historical_data={},
            ml_model_v4=None,
            _quant_kelly_engine=None,
            _quant_momentum_engine=None,
            trading_engine=SimpleNamespace(
                should_execute_trade=Mock(return_value=(True, "ok")),
                calculate_position_size=Mock(return_value=(1.0, 99999.0)),
                calculate_stop_loss_take_profit=Mock(return_value={
                    "stop_loss": current_price - 100,
                    "take_profit_1": current_price + 200,
                    "take_profit_2": current_price + 400,
                    "rr_ratio": 2.0,
                    "method": "fixed",
                }),
            ),
            price_monitor=SimpleNamespace(set_price_level=Mock(), remove_price_level=Mock()),
            sr_detector=SimpleNamespace(),
            _broadcast_to_subscribers=AsyncMock(),
            _find_liquidity_zones=Mock(return_value=[]),
            _elite_signal=Mock(return_value=("BUY", 0.8, 1.0)),
            _fee_aware_net_price=Mock(return_value=(current_price, 0.0, 0.0)),
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
             patch("autotrade.runtime.Config.AUTOTRADE_CHASE_THRESHOLD_PCT", 10.0), \
             patch("autotrade.runtime.Config.TRADING_FEE_RATE", 0.0), \
             patch("api.indodax_api.IndodaxAPI", Mock(return_value=bot.indodax)), \
             patch("autotrade.runtime.analyze_market_intelligence", AsyncMock(return_value={"passes_entry_filter": True, "overall_signal": "BULLISH"})), \
             patch("autotrade.runtime.detect_market_regime", Mock(return_value={"regime": "RANGE", "volatility": 0.01, "is_high_vol": False, "is_trending": False, "trend_direction": "NEUTRAL"})), \
             patch("autotrade.runtime.get_support_resistance_for_pair", AsyncMock(return_value=None)), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            await check_trading_opportunity(
                bot,
                "midpriceidr",
                signal={"pair": "midpriceidr", "recommendation": "STRONG_BUY", "ml_confidence": 0.9, "price": current_price, "indicators": {}},
            )

        open_trades = db.get_open_trades(123)
        self.assertEqual(len(open_trades), 1)
        # Accept approximate value due to slippage realism (DRYRUN_SLIPPAGE_PCT)
        self.assertAlmostEqual(open_trades[0]["total"], 1250000.0, delta=12500.0)

    async def test_high_price_pair_uses_price_times_10_as_dryrun_nominal(self):
        db = _FakeDryRunDB()
        current_price = 150000.0
        bot = SimpleNamespace(
            is_trading=True,
            auto_trade_pairs={123: ["testidr"]},
            subscribers={123: ["testidr"]},
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
                get_ticker=Mock(return_value={"last": current_price, "bid": current_price}),
                get_orderbook=Mock(return_value={"bids": [], "asks": []}),
            ),
            price_data={},
            historical_data={},
            ml_model_v4=None,
            _quant_kelly_engine=None,
            _quant_momentum_engine=None,
            trading_engine=SimpleNamespace(
                should_execute_trade=Mock(return_value=(True, "ok")),
                calculate_position_size=Mock(return_value=(1.0, 55555.0)),
                calculate_stop_loss_take_profit=Mock(return_value={
                    "stop_loss": current_price - 500,
                    "take_profit_1": current_price + 1000,
                    "take_profit_2": current_price + 2000,
                    "rr_ratio": 2.0,
                    "method": "fixed",
                }),
            ),
            price_monitor=SimpleNamespace(set_price_level=Mock(), remove_price_level=Mock()),
            sr_detector=SimpleNamespace(),
            _broadcast_to_subscribers=AsyncMock(),
            _find_liquidity_zones=Mock(return_value=[]),
            _elite_signal=Mock(return_value=("BUY", 0.8, 1.0)),
            _fee_aware_net_price=Mock(return_value=(current_price, 0.0, 0.0)),
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
             patch("autotrade.runtime.Config.AUTOTRADE_CHASE_THRESHOLD_PCT", 10.0), \
             patch("autotrade.runtime.Config.TRADING_FEE_RATE", 0.0), \
             patch("api.indodax_api.IndodaxAPI", Mock(return_value=bot.indodax)), \
             patch("autotrade.runtime.analyze_market_intelligence", AsyncMock(return_value={"passes_entry_filter": True, "overall_signal": "BULLISH"})), \
             patch("autotrade.runtime.detect_market_regime", Mock(return_value={"regime": "RANGE", "volatility": 0.01, "is_high_vol": False, "is_trending": False, "trend_direction": "NEUTRAL"})), \
             patch("autotrade.runtime.get_support_resistance_for_pair", AsyncMock(return_value=None)), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            await check_trading_opportunity(
                bot,
                "testidr",
                signal={"pair": "testidr", "recommendation": "STRONG_BUY", "ml_confidence": 0.9, "price": current_price, "indicators": {}},
            )

        open_trades = db.get_open_trades(123)
        self.assertEqual(len(open_trades), 1)
        # New formula: target 1.250.000 IDR + slippage (DRYRUN_SLIPPAGE_PCT=0.1%)
        self.assertAlmostEqual(open_trades[0]["total"], 1250000.0, delta=12500.0)


if __name__ == "__main__":
    unittest.main()
