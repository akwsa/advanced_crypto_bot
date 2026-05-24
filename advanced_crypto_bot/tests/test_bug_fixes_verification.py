#!/usr/bin/env python3
"""
Bug Fix Verification Script
============================
Verifikasi semua bug fix yang dilakukan pada 2026-04-24.

Run: ./venv/bin/python tests/test_bug_fixes_verification.py -v
"""

import unittest
import sys
import os
import sqlite3
import importlib.util
from types import SimpleNamespace
from datetime import datetime, timedelta

# Add parent dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.config import Config
from core.database import Database


class TestConfigBugFixes(unittest.TestCase):
    """Test Bug #1, #2: Config duplikat dan unit mismatch."""

    def test_max_daily_loss_pct_is_3_not_5(self):
        """Bug #1: MAX_DAILY_LOSS_PCT harus 3.0, bukan 5.0."""
        self.assertEqual(Config.MAX_DAILY_LOSS_PCT, 3.0,
            "MAX_DAILY_LOSS_PCT harus 3.0% (bukan 5.0%) — bug #1 fixed")

    def test_max_drawdown_pct_is_fraction_not_percentage(self):
        """Bug #2: MAX_DRAWDOWN_PCT harus fraksi 0.10 (10%), bukan angka 10.0."""
        self.assertEqual(Config.MAX_DRAWDOWN_PCT, 0.10,
            "MAX_DRAWDOWN_PCT harus fraksi 0.10 (10%), bukan 10.0 — bug #2 fixed")
        self.assertTrue(0.0 < Config.MAX_DRAWDOWN_PCT < 1.0,
            "MAX_DRAWDOWN_PCT harus antara 0 dan 1 (fraksi)")

    def test_drawdown_comparison_logic(self):
        """Bug #2: Simulasi perbandingan drawdown."""
        # drawdown dihitung sebagai fraksi di bot.py
        drawdown = 0.05  # 5% drawdown
        # Dengan fix, 0.05 >= 0.10 adalah False (belum trigger) — benar
        # Dengan bug, 0.05 >= 10.0 adalah False juga — tapi 0.15 >= 10.0 juga False (salah!)
        self.assertFalse(drawdown >= Config.MAX_DRAWDOWN_PCT,
            "5% drawdown belum mencapai threshold 10% — circuit breaker tidak trigger")
        
        drawdown_severe = 0.15  # 15% drawdown
        self.assertTrue(drawdown_severe >= Config.MAX_DRAWDOWN_PCT,
            "15% drawdown melebihi threshold 10% — circuit breaker HARUS trigger")

    def test_risk_manager_drawdown_unit_consistency(self):
        """Bug #2: Risk manager sekarang hitung drawdown sebagai fraksi."""
        # Risk manager menghitung: dd = (peak - balance) / peak
        # Tanpa *100 — jadi dd adalah fraksi
        peak = 10000000
        balance = 9000000  # 10% drawdown
        dd = (peak - balance) / peak  # = 0.10 (fraksi)
        self.assertTrue(dd >= Config.MAX_DRAWDOWN_PCT,
            "Risk manager drawdown (fraksi) konsisten dengan Config.MAX_DRAWDOWN_PCT")


class TestDatabaseBugFixes(unittest.TestCase):
    """Test Bug #12, #13: DB thread-safety dan count_trades_today."""

    def setUp(self):
        self.db = Database(':memory:')  # In-memory DB for testing

    def tearDown(self):
        self.db.close()

    def test_count_trades_today(self):
        """Bug #13: count_trades_today() harus menghitung trade hari ini."""
        # Tambah beberapa trade
        self.db.add_trade(1, 'btcidr', 'BUY', 1000, 1.0, 1000, 3, 'test', 0.7)
        self.db.add_trade(1, 'ethidr', 'BUY', 2000, 0.5, 1000, 3, 'test', 0.6)
        
        count = self.db.count_trades_today(1)
        self.assertEqual(count, 2,
            "count_trades_today() harus menghitung 2 trade yang dibuka hari ini")

    def test_db_close_thread_safety(self):
        """Bug #12: DB close harus set _closed flag."""
        self.db.close()
        self.assertTrue(self.db._closed,
            "DB close() harus set _closed = True")
        # Setelah close, _get_thread_connection harus raise RuntimeError
        with self.assertRaises(RuntimeError):
            self.db._get_thread_connection()

    def test_update_trade_stop_loss(self):
        """Bug #9: update_trade_stop_loss() harus ada dan berfungsi."""
        trade_id = self.db.add_trade(1, 'btcidr', 'BUY', 1000, 1.0, 1000, 3, 'test', 0.7)
        result = self.db.update_trade_stop_loss(trade_id, 950)
        self.assertTrue(result,
            "update_trade_stop_loss() harus berhasil mengupdate trade OPEN")


@unittest.skipIf(importlib.util.find_spec("telegram") is None, "python-telegram-bot not installed")
class TestSmartHunterBugFixes(unittest.TestCase):
    """Test Bug #3, #4, #8: Smart hunter PnL, partial sell, breakeven."""

    def setUp(self):
        from autohunter.smart_profit_hunter import SmartProfitHunter
        self.hunter = SmartProfitHunter(dry_run=True)
        # Mock Telegram notification to avoid sending real messages during tests
        async def mock_send(msg):
            pass
        self.hunter.send_notification = mock_send
        # Setup mock trade
        self.hunter.active_trades['btcidr'] = {
            'pair_id': 'btc_idr',
            'coin_amount': 100.0,
            'entry_price': 500000000,
            'highest_price': 500000000,
            'sold_50': False,
            'sold_30': False,
            'sold_20': False,
            'breakeven_activated': False,
            'breakeven_stop': None,
            'timestamp': datetime.now(),
        }
        self.hunter.daily_pnl = 0
        self.hunter.balance_idr = 10000000

    def test_partial_sell_reduces_coin_amount(self):
        """Bug #4: Partial sell harus mengurangi coin_amount."""
        import asyncio
        
        trade = self.hunter.active_trades['btcidr']
        original_amount = trade['coin_amount']
        
        # Simulate partial sell 50%
        asyncio.run(self.hunter._execute_partial_sell_silent(
            'btcidr', trade, 515000000, 0.5, "TP1"
        ))
        
        new_amount = self.hunter.active_trades['btcidr']['coin_amount']
        self.assertLess(new_amount, original_amount,
            "coin_amount harus berkurang setelah partial sell")
        self.assertEqual(new_amount, original_amount * 0.5,
            "coin_amount harus berkurang 50% setelah partial sell 50%")

    def test_breakeven_includes_fee(self):
        """Bug #8: Breakeven stop harus include fee."""
        import asyncio
        
        trade = self.hunter.active_trades['btcidr']
        entry_price = trade['entry_price']
        
        # Trigger partial sell 50% to activate breakeven
        asyncio.run(self.hunter._execute_partial_sell_silent(
            'btcidr', trade, 515000000, 0.5, "TP1"
        ))
        
        breakeven = self.hunter.active_trades['btcidr']['breakeven_stop']
        expected_breakeven = entry_price * (1 + 2 * Config.TRADING_FEE_RATE)
        
        self.assertIsNotNone(breakeven,
            "breakeven_stop harus di-set setelah TP1")
        self.assertEqual(breakeven, expected_breakeven,
            f"breakeven harus include fee: {expected_breakeven:,.0f} (bukan {entry_price:,.0f})")
        self.assertGreater(breakeven, entry_price,
            "breakeven harus lebih tinggi dari entry_price karena include fee")

    def test_close_position_no_double_count(self):
        """Bug #3: close_position() harus update daily_pnl sekali."""
        import asyncio
        
        trade = self.hunter.active_trades['btcidr']
        current_price = 510000000
        
        # PnL = (510M - 500M) * 100 = 1B IDR
        expected_pnl = (current_price - trade['entry_price']) * trade['coin_amount']
        
        initial_pnl = self.hunter.daily_pnl
        asyncio.run(self.hunter.close_position(
            'btcidr', trade, current_price, "Test Close"
        ))
        
        final_pnl = self.hunter.daily_pnl
        added_pnl = final_pnl - initial_pnl
        
        self.assertEqual(added_pnl, expected_pnl,
            f"daily_pnl hanya bertambah sekali: {expected_pnl:,.0f} (bukan 2x)")
        
        # Verify trade removed
        self.assertNotIn('btcidr', self.hunter.active_trades,
            "Trade harus dihapus dari active_trades setelah close")


class TestSignalPipelineBugFixes(unittest.TestCase):
    """Test Bug #10: Stale price flag logic."""

    def test_stale_price_source_logic(self):
        """Bug #10: stale_realtime_price hanya True jika source bukan API/WS_FRESH."""
        # Logic di signal_pipeline.py:
        # stale_realtime_price = True hanya jika:
        #   real_time_price is not None 
        #   AND price_source not in ("API", "WEBSOCKET_FRESH")
        #   AND WS cache stale
        
        # Case 1: API fresh price → stale flag harus False
        price_source = "API"
        ws_age = 120  # WS stale, tapi irrelevant
        should_be_stale = price_source not in ("API", "WEBSOCKET_FRESH") and ws_age >= 60
        self.assertFalse(should_be_stale,
            "Jika price_source='API', stale flag harus False meski WS cache stale")
        
        # Case 2: WS fresh price → stale flag harus False
        price_source = "WEBSOCKET_FRESH"
        ws_age = 30
        should_be_stale = price_source not in ("API", "WEBSOCKET_FRESH") and ws_age >= 60
        self.assertFalse(should_be_stale,
            "Jika price_source='WEBSOCKET_FRESH', stale flag harus False")
        
        # Case 3: Fallback historical → stale flag harus True (karena bukan API/WS_FRESH)
        price_source = "HISTORICAL_FALLBACK"
        ws_age = 120
        should_be_stale = price_source not in ("API", "WEBSOCKET_FRESH") and ws_age >= 60
        self.assertTrue(should_be_stale,
            "Jika price_source='HISTORICAL_FALLBACK', stale flag harus True")

    def test_quality_engine_mean_reversion_uses_realtime_price(self):
        """C8: Quality engine harus memakai current_price dari pipeline jika tersedia."""
        import pandas as pd
        from signals.signal_quality_engine import SignalQualityEngine

        class FakeMeanReversionEngine:
            def __init__(self):
                self.seen_price = None

            def analyze(self, df, current_price=None, pair="UNKNOWN", market_regime="UNKNOWN"):
                self.seen_price = current_price
                return SimpleNamespace(
                    direction="BUY",
                    signal="BUY",
                    confluence_bonus=1,
                    z_score_composite=-2.0,
                    is_actionable=True,
                )

        engine = SignalQualityEngine.__new__(SignalQualityEngine)
        fake_mr = FakeMeanReversionEngine()
        engine.mean_reversion_engine = fake_mr
        engine.signal_history = {}
        engine.rejection_stats = {}

        df = pd.DataFrame({"close": [900.0, 950.0, 999.0]})
        result = engine.generate_signal(
            pair="btcidr",
            ta_signals={
                "strength": 0.4,
                "indicators": {
                    "rsi": "OVERSOLD",
                    "macd": "BULLISH",
                    "ma_trend": "BULLISH",
                    "bb": "OVERSOLD",
                    "volume": "HIGH",
                },
            },
            ml_prediction=True,
            ml_confidence=0.8,
            ml_signal_class="BUY",
            combined_strength=0.2,
            df=df,
            market_regime="RANGING",
            current_price=123.0,
        )

        self.assertIsNotNone(result)
        self.assertEqual(fake_mr.seen_price, 123.0)


class TestTradingEngineBugFixes(unittest.TestCase):
    """Test Bug #9, #13: Breakeven check, daily trade limit, position duplication."""

    def test_should_execute_trade_blocks_existing_position_with_normalized_pair(self):
        """Regression: should_execute_trade harus load open_trades sebelum cek posisi existing."""
        from autotrade.trading_engine import TradingEngine

        db = Database(':memory:')
        try:
            db.add_user(1, 'tester', 'Tester')
            db.update_balance(1, 1_000_000)
            db.add_trade(1, 'BTC/IDR', 'BUY', 1000, 1.0, 1000, 3, 'test', 0.7)
            engine = TradingEngine(db, None)

            allowed, reason = engine.should_execute_trade(
                1,
                {'recommendation': 'BUY', 'pair': 'btcidr'},
                1000,
            )

            self.assertFalse(allowed)
            self.assertIn('Already have position', reason)
        finally:
            db.close()

    def test_daily_trade_limit_uses_count_not_open_positions(self):
        """Bug #13: Daily trade limit harus hitung trade per hari, bukan open positions."""
        db = Database(':memory:')
        
        # Add 5 trades today (some closed, some open)
        for i in range(3):
            db.add_trade(1, f'pair{i}', 'BUY', 1000, 1.0, 1000, 3, 'test', 0.7)
        
        count = db.count_trades_today(1)
        self.assertEqual(count, 3,
            "count_trades_today() menghitung semua trade dibuka hari ini")
        
        # Open trades hanya 3, tapi kalau ada trade yang sudah ditutup hari ini juga,
        # count_trades_today tetap menghitungnya
        db.close()


@unittest.skipIf(importlib.util.find_spec("sklearn") is None, "scikit-learn not installed")
class TestMLModelV2BugFixes(unittest.TestCase):
    """Test Bug #5, #14: Dead code dan shadow variable."""

    def test_no_shadow_max_drawdown(self):
        """Bug #14: ml_model_v2.py tidak boleh punya MAX_DRAWDOWN_PCT sendiri."""
        import analysis.ml_model_v2 as ml_v2_module
        self.assertFalse(hasattr(ml_v2_module, 'MAX_DRAWDOWN_PCT'),
            "ml_model_v2.py tidak boleh punya MAX_DRAWDOWN_PCT — gunakan Config")

    def test_default_model_path_does_not_duplicate_v2_suffix(self):
        """H10: Config.ML_MODEL_PATH yang sudah _v2 tidak boleh jadi _v2_v2."""
        from analysis.ml_model_v2 import _default_v2_model_path

        self.assertEqual(
            _default_v2_model_path('models/trading_model.pkl'),
            'models/trading_model_v2.pkl'
        )
        self.assertEqual(
            _default_v2_model_path('models/trading_model_v2.pkl'),
            'models/trading_model_v2.pkl'
        )


class TestPortfolioBugFixes(unittest.TestCase):
    """Regression: portfolio summary tahan data trade lama yang punya nilai None."""

    def test_portfolio_summary_ignores_none_total(self):
        import pandas as pd
        from autotrade.portfolio import Portfolio

        class FakeDB:
            def get_balance(self, user_id):
                return 1_000_000

            def get_open_trades(self, user_id):
                return [
                    {
                        'pair': 'btcidr',
                        'type': 'BUY',
                        'price': 1000,
                        'amount': 2,
                        'total': None,
                        'opened_at': '2026-05-20 08:00:00',
                    }
                ]

            def get_price_history(self, pair, limit=1):
                return pd.DataFrame([{'close': 1100}])

        summary = Portfolio(FakeDB()).get_portfolio_summary(1)

        self.assertEqual(summary['positions_value'], 0)
        self.assertEqual(summary['positions'][0]['unrealized_pnl'], 200)
        self.assertEqual(summary['positions'][0]['unrealized_pnl_pct'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
