# Tujuan: Regression test untuk Bug Critical #2 audit 2026-06-07 — amount
# inflasi 2.5-3x antara DRY RUN SIZE dan FILL log akibat Bayesian Kelly /
# v4_boost / position multipliers menggabungkan total dan amount secara
# independen. Reconciliation guard di runtime.py harus:
#   (a) cap total di DRY_RUN_MAX_TOTAL_IDR untuk DRY RUN
#   (b) recompute amount = total / entry_zone_price sebelum FILL
# sehingga amount/total tetap konsisten apapun path upstream.

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from autotrade.runtime import check_trading_opportunity


class _FakeDB:
    def __init__(self):
        self.trades = []

    def get_pair_performance(self, pair):
        return None

    def get_balance(self, user_id):
        return 10_000_000

    def get_open_trades(self, user_id):
        return [t for t in self.trades if t["user_id"] == user_id and t["status"] == "OPEN"]

    def add_trade(self, user_id, pair, trade_type, price, amount, total, fee,
                  signal_source, ml_confidence, notes=None):
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
            "status": "OPEN",
        })
        return trade_id

    def add_pending_order(self, **kwargs):
        return 1

    def close_trade(self, **kwargs):
        return True


def _make_bot(db, kelly_engine=None):
    return SimpleNamespace(
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
            get_ticker=Mock(return_value={"last": 100.0, "bid": 100.0}),
            get_orderbook=Mock(return_value={"bids": [], "asks": []}),
        ),
        price_data={},
        historical_data={},
        ml_model_v4=None,
        _quant_kelly_engine=kelly_engine,
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


def _patches(extra=None):
    """Default Config patches that disable downstream gates so tests focus
    purely on sizing reconciliation."""
    return [
        patch("autotrade.runtime.Config.AUTO_TRADE_DRY_RUN", True),
        patch("autotrade.runtime.Config.ADMIN_IDS", [123]),
        patch("autotrade.runtime.Config.CORRELATION_AVOIDANCE_ENABLED", False),
        patch("autotrade.runtime.Config.RL_ENABLED", False),
        patch("autotrade.runtime.Config.SMART_ROUTING_ENABLED", False),
        patch("autotrade.runtime.Config.PORTFOLIO_RISK_ADJUSTED", False),
        patch("autotrade.runtime.Config.LIMIT_ORDER_MIN_EDGE_PCT", 0.0),
        patch("autotrade.runtime.Config.AUTOTRADE_CHASE_THRESHOLD_PCT", 10.0),
        patch("autotrade.runtime.Config.TRADING_FEE_RATE", 0.0),
        patch("api.indodax_api.IndodaxAPI", Mock(return_value=SimpleNamespace(
            get_ticker=Mock(return_value={"last": 100.0, "bid": 100.0}),
            get_orderbook=Mock(return_value={"bids": [], "asks": []}),
        ))),
        patch("autotrade.runtime.analyze_market_intelligence", AsyncMock(return_value={
            "passes_entry_filter": True, "overall_signal": "BULLISH"
        })),
        patch("autotrade.runtime.detect_market_regime", Mock(return_value={
            "regime": "RANGE", "volatility": 0.01, "is_high_vol": False,
            "is_trending": False, "trend_direction": "NEUTRAL"
        })),
        patch("autotrade.runtime.get_support_resistance_for_pair", AsyncMock(return_value=None)),
    ]


class TestFillReconciliation(unittest.IsolatedAsyncioTestCase):
    """Bug Critical #2: amount inflasi 2.5-3x SIZE→FILL."""

    async def test_dry_run_total_capped_to_max(self):
        """Optimization multiplier 5x mencoba inflate total; cap harus tahan."""
        db = _FakeDB()
        bot = _make_bot(db)

        # Optimization tries to push total to 5x = 6.25M IDR but cap is 2M.
        optimization = SimpleNamespace(
            should_skip=False,
            reason="ok",
            position_multiplier=5.0,  # 5x inflation attempt
            stop_loss_multiplier=1.0,
            tp1_multiplier=1.0,
            tp2_multiplier=1.0,
            min_rr_required=1.0,
            edge_score=10.0,
        )

        with patch("autotrade.runtime.Config.DRY_RUN_MAX_TOTAL_IDR", 2_000_000), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            for p in _patches():
                p.start()
            try:
                await check_trading_opportunity(
                    bot,
                    "testidr",
                    signal={"pair": "testidr", "recommendation": "STRONG_BUY",
                            "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
                )
            finally:
                for p in _patches():
                    try:
                        p.stop()
                    except RuntimeError:
                        pass

        open_trades = db.get_open_trades(123)
        self.assertEqual(len(open_trades), 1, "Trade harus terbuka meski multiplier ekstrim")
        trade = open_trades[0]
        # Cap aktif: total ≤ 2M IDR
        self.assertLessEqual(trade["total"], 2_000_000,
                             f"total {trade['total']} melebihi DRY_RUN_MAX_TOTAL_IDR cap")

    async def test_amount_total_invariant_after_fill(self):
        """Setelah FILL: amount * entry_price ≈ total (toleransi 1%).
        Ini invariant utama dari reconciliation: amount = total/entry.
        """
        db = _FakeDB()
        bot = _make_bot(db)

        optimization = SimpleNamespace(
            should_skip=False, reason="ok",
            position_multiplier=1.5,  # mild inflation
            stop_loss_multiplier=1.0, tp1_multiplier=1.0, tp2_multiplier=1.0,
            min_rr_required=1.0, edge_score=10.0,
        )

        with patch("autotrade.runtime.Config.DRY_RUN_MAX_TOTAL_IDR", 2_000_000), \
             patch("autotrade.runtime.evaluate_autotrade_setup", Mock(return_value=optimization)):
            for p in _patches():
                p.start()
            try:
                await check_trading_opportunity(
                    bot,
                    "testidr",
                    signal={"pair": "testidr", "recommendation": "STRONG_BUY",
                            "ml_confidence": 0.8, "price": 100.0, "indicators": {}},
                )
            finally:
                for p in _patches():
                    try:
                        p.stop()
                    except RuntimeError:
                        pass

        open_trades = db.get_open_trades(123)
        self.assertEqual(len(open_trades), 1)
        trade = open_trades[0]
        # Invariant: amount * entry_price ≈ total. Entry zone < market price
        # (limit order discount) but the relationship must hold within 1%.
        if trade["amount"] > 0 and trade["price"] > 0:
            implied_total = trade["amount"] * trade["price"]
            drift = abs(implied_total - trade["total"]) / trade["total"]
            self.assertLess(drift, 0.01,
                f"amount*price={implied_total:,.2f} drift {drift*100:.2f}% "
                f"dari total={trade['total']:,.2f}")


if __name__ == "__main__":
    unittest.main()
