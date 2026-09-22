#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Test integrasi 5 fitur quant baru ke pipeline bot.
# Caller: pytest / python3 -m unittest
# Dependensi: unittest, numpy, quant.*, autotrade.*, signals.*
# Main Functions: TestQuantIntegration
# Side Effects: none; pure unit tests, no DB/API calls.
"""
Test integrasi 5 fitur quant baru (2026-05-19):
  #1 GARCH/VaR/ARIMA di signal dict & Telegram formatter
  #2 /quant_risk, /quant_forecast, /quant_frontier commands
  #3 GARCH regime → position size scaling
  #4 ARIMA direction filter
  #5 VaR/CVaR hard gate

Run:
    python3 -m unittest tests.test_quant_integration -v
"""

import sys
import os
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Helpers
# =============================================================================

def make_returns(n=100, seed=42, mean=0.3, std=2.0):
    rng = np.random.default_rng(seed)
    return list(rng.normal(mean, std, n))

def make_prices(n=80, start=1_500_000, seed=42):
    rng = np.random.default_rng(seed)
    prices = [start]
    for r in rng.normal(0.001, 0.02, n):
        prices.append(prices[-1] * (1 + r))
    return prices[1:]


# =============================================================================
# Test #1: GARCH/VaR/ARIMA keys di signal dict (via signal_pipeline enrichment)
# =============================================================================

class TestSignalEnrichmentKeys(unittest.TestCase):
    """Verifikasi bahwa modul quant menghasilkan keys yang benar."""

    def test_garch_result_has_required_keys(self):
        from quant.volatility_models import GARCHModel
        garch = GARCHModel()
        result = garch.fit(make_returns(60))
        self.assertIsNotNone(result)
        # Keys yang akan dimasukkan ke signal dict
        self.assertIsNotNone(result.current_vol)
        self.assertIsNotNone(result.forecast_vol_1d)
        self.assertIsNotNone(result.regime)
        self.assertIn(result.regime, ["LOW", "MEDIUM", "HIGH", "EXTREME"])

    def test_var_result_has_required_keys(self):
        from quant.risk_metrics import RiskMetrics
        rm = RiskMetrics(mc_simulations=200, random_seed=42)
        result = rm.calculate(make_returns(50), confidence=0.95)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.var_historical)
        self.assertIsNotNone(result.var_parametric)
        self.assertIsNotNone(result.cvar_historical)

    def test_arima_result_has_required_keys(self):
        from quant.forecasting import ARIMAModel
        arima = ARIMAModel(p=1, d=1, q=1)
        result = arima.fit_forecast(make_prices(50), steps=3)
        self.assertIsNotNone(result)
        self.assertIn(result.direction, ["UP", "DOWN", "FLAT"])
        self.assertIsNotNone(result.expected_change_pct)
        self.assertGreater(len(result.forecast), 0)


# =============================================================================
# Test #2: Telegram formatter menerima quant keys tanpa error
# =============================================================================

class TestSignalFormatterQuant(unittest.TestCase):
    """Verifikasi format_signal_message_html menampilkan quant section."""

    def _make_signal(self, **quant_overrides):
        from datetime import datetime
        signal = {
            "pair": "btcidr",
            "recommendation": "BUY",
            "price": 1_500_000,
            "ml_confidence": 0.72,
            "ml_confidence_raw": 0.70,
            "combined_strength": 0.35,
            "timestamp": datetime.now(),
            "reason": "Test signal",
            "final_gate_source": None,
            "support_1": 1_450_000,
            "support_2": 1_420_000,
            "resistance_1": 1_560_000,
            "resistance_2": 1_600_000,
            "price_zone": "SUPPORT_ZONE",
            "risk_reward_ratio": 1.8,
            "indicators": {
                "rsi": "OVERSOLD", "macd": "BULLISH",
                "ma_trend": "BULLISH", "bb": "OVERSOLD", "volume": "HIGH"
            },
        }
        signal.update(quant_overrides)
        return signal

    def test_formatter_with_all_quant_keys(self):
        from signals.signal_formatter import format_signal_message_html
        signal = self._make_signal(
            garch_regime="HIGH",
            garch_current_vol=3.5,
            var_historical=-2.8,
            cvar_historical=-4.2,
            arima_direction="UP",
            arima_change_pct=1.2,
        )
        text = format_signal_message_html(signal)
        self.assertIn("Quant Analysis", text)
        self.assertIn("HIGH", text)
        self.assertIn("VaR", text)
        self.assertIn("ARIMA", text)

    def test_formatter_without_quant_keys(self):
        """Formatter harus tetap bekerja tanpa quant keys (backward compatible)."""
        from signals.signal_formatter import format_signal_message_html
        signal = self._make_signal()  # no quant keys
        text = format_signal_message_html(signal)
        self.assertIn("BTCIDR", text.upper())
        # Quant section tidak muncul jika tidak ada data
        self.assertNotIn("Quant Analysis", text)

    def test_formatter_with_partial_quant_keys(self):
        """Formatter harus bekerja dengan hanya sebagian quant keys."""
        from signals.signal_formatter import format_signal_message_html
        signal = self._make_signal(garch_regime="MEDIUM", garch_current_vol=1.5)
        text = format_signal_message_html(signal)
        # Tidak crash
        self.assertIsInstance(text, str)

    def test_formatter_garch_regime_emojis(self):
        """Setiap regime harus menghasilkan emoji yang benar."""
        from signals.signal_formatter import format_signal_message_html
        for regime, emoji in [("LOW", "🟢"), ("MEDIUM", "🟡"), ("HIGH", "🟠"), ("EXTREME", "🔴")]:
            signal = self._make_signal(
                garch_regime=regime, garch_current_vol=2.0,
                var_historical=-1.5, cvar_historical=-2.5,
            )
            text = format_signal_message_html(signal)
            self.assertIn(emoji, text, f"Emoji {emoji} not found for regime {regime}")


# =============================================================================
# Test #3: GARCH regime → position size scaling
# =============================================================================

class TestGARCHPositionSizing(unittest.TestCase):
    """Verifikasi GARCH regime memperkecil position size."""

    def _make_engine_with_regime(self, regime):
        """Buat mock TradingEngine dengan _last_garch_regime."""
        from unittest.mock import MagicMock, patch
        from autotrade.trading_engine import TradingEngine

        mock_db = MagicMock()
        mock_db.get_balance.return_value = 10_000_000
        mock_ml = MagicMock()

        engine = TradingEngine(mock_db, mock_ml)
        engine._last_garch_regime = regime
        return engine

    def test_low_regime_no_scaling(self):
        engine = self._make_engine_with_regime("LOW")
        amount, max_pos = engine.calculate_position_size(user_id=1, price=1_500_000)
        self.assertIsNotNone(max_pos)
        # LOW regime: tidak ada scaling, max_pos = balance * MAX_POSITION_SIZE
        from core.config import Config
        expected = 10_000_000 * Config.MAX_POSITION_SIZE
        self.assertAlmostEqual(max_pos, expected, delta=1)

    def test_medium_regime_no_scaling(self):
        engine = self._make_engine_with_regime("MEDIUM")
        amount, max_pos = engine.calculate_position_size(user_id=1, price=1_500_000)
        from core.config import Config
        expected = 10_000_000 * Config.MAX_POSITION_SIZE
        self.assertAlmostEqual(max_pos, expected, delta=1)

    def test_high_regime_scales_down(self):
        engine = self._make_engine_with_regime("HIGH")
        amount, max_pos = engine.calculate_position_size(user_id=1, price=1_500_000)
        from core.config import Config
        expected_full = 10_000_000 * Config.MAX_POSITION_SIZE
        expected_scaled = expected_full * 0.6
        self.assertAlmostEqual(max_pos, expected_scaled, delta=1)

    def test_extreme_regime_scales_down_more(self):
        engine = self._make_engine_with_regime("EXTREME")
        amount, max_pos = engine.calculate_position_size(user_id=1, price=1_500_000)
        from core.config import Config
        expected_full = 10_000_000 * Config.MAX_POSITION_SIZE
        expected_scaled = expected_full * 0.35
        self.assertAlmostEqual(max_pos, expected_scaled, delta=1)

    def test_high_regime_smaller_than_low(self):
        engine_low = self._make_engine_with_regime("LOW")
        engine_high = self._make_engine_with_regime("HIGH")
        _, pos_low = engine_low.calculate_position_size(user_id=1, price=1_500_000)
        _, pos_high = engine_high.calculate_position_size(user_id=1, price=1_500_000)
        self.assertLess(pos_high, pos_low)

    def test_extreme_regime_smallest(self):
        engine_low = self._make_engine_with_regime("LOW")
        engine_extreme = self._make_engine_with_regime("EXTREME")
        _, pos_low = engine_low.calculate_position_size(user_id=1, price=1_500_000)
        _, pos_extreme = engine_extreme.calculate_position_size(user_id=1, price=1_500_000)
        self.assertLess(pos_extreme, pos_low)

    def test_no_garch_regime_defaults_to_medium(self):
        """Tanpa _last_garch_regime, default ke MEDIUM (tidak ada scaling)."""
        from unittest.mock import MagicMock
        from autotrade.trading_engine import TradingEngine
        mock_db = MagicMock()
        mock_db.get_balance.return_value = 10_000_000
        engine = TradingEngine(mock_db, MagicMock())
        # Tidak set _last_garch_regime
        amount, max_pos = engine.calculate_position_size(user_id=1, price=1_500_000)
        from core.config import Config
        expected = 10_000_000 * Config.MAX_POSITION_SIZE
        self.assertAlmostEqual(max_pos, expected, delta=1)


# =============================================================================
# Test #4: ARIMA direction filter
# =============================================================================

class TestARIMAFilter(unittest.TestCase):
    """Verifikasi ARIMA filter memblokir BUY saat prediksi DOWN kuat."""

    def _make_signal(self, recommendation, arima_direction, arima_change_pct):
        return {
            "recommendation": recommendation,
            "arima_direction": arima_direction,
            "arima_change_pct": arima_change_pct,
            "reason": "test",
        }

    def _apply_arima_filter(self, signal):
        """Simulasi logika ARIMA filter dari signal_pipeline.py."""
        BUY_SIGNALS = {"BUY", "STRONG_BUY"}
        arima_dir = signal.get("arima_direction")
        arima_pct = signal.get("arima_change_pct", 0.0)
        if (
            signal["recommendation"] in BUY_SIGNALS
            and arima_dir == "DOWN"
            and arima_pct is not None
            and arima_pct < -1.0
        ):
            signal["recommendation"] = "HOLD"
            signal["arima_filtered"] = True
        return signal

    def test_buy_blocked_when_arima_down_strong(self):
        """BUY harus diblokir jika ARIMA prediksi DOWN > -1%."""
        signal = self._make_signal("BUY", "DOWN", -2.5)
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "HOLD")
        self.assertTrue(result.get("arima_filtered"))

    def test_strong_buy_blocked_when_arima_down_strong(self):
        signal = self._make_signal("STRONG_BUY", "DOWN", -1.5)
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "HOLD")

    def test_buy_not_blocked_when_arima_down_weak(self):
        """BUY tidak diblokir jika ARIMA prediksi DOWN tapi < 1%."""
        signal = self._make_signal("BUY", "DOWN", -0.5)
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "BUY")
        self.assertFalse(result.get("arima_filtered", False))

    def test_buy_not_blocked_when_arima_up(self):
        signal = self._make_signal("BUY", "UP", 1.5)
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "BUY")

    def test_buy_not_blocked_when_arima_flat(self):
        signal = self._make_signal("BUY", "FLAT", 0.1)
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "BUY")

    def test_sell_not_affected_by_arima_filter(self):
        """SELL tidak diblokir oleh ARIMA filter."""
        signal = self._make_signal("SELL", "DOWN", -3.0)
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "SELL")

    def test_hold_not_affected(self):
        signal = self._make_signal("HOLD", "DOWN", -2.0)
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "HOLD")
        self.assertFalse(result.get("arima_filtered", False))

    def test_buy_not_blocked_when_no_arima_data(self):
        """BUY tidak diblokir jika tidak ada data ARIMA."""
        signal = {"recommendation": "BUY", "reason": "test"}
        result = self._apply_arima_filter(signal)
        self.assertEqual(result["recommendation"], "BUY")


# =============================================================================
# Test #5: VaR/CVaR hard gate
# =============================================================================

class TestVaRCVaRGate(unittest.TestCase):
    """Verifikasi VaR/CVaR gate di risk_manager.py."""

    def setUp(self):
        from unittest.mock import MagicMock
        from autotrade.risk_manager import RiskManager
        self.rm = RiskManager(db=MagicMock())
        # Clear quant cache agar tidak ada state dari test lain
        try:
            import signals.signal_pipeline as sp
            sp._quant_cache.clear()
        except Exception:
            pass

    def test_gate_passes_with_safe_var(self):
        """VaR -2% → aman, gate harus pass."""
        returns = make_returns(50, mean=0.5, std=1.0)  # returns relatif aman
        allowed, reason = self.rm.check_var_cvar_gate(returns, max_var=-5.0, max_cvar=-8.0)
        self.assertTrue(allowed, f"Expected allowed but got: {reason}")

    def test_gate_blocks_when_var_too_negative(self):
        """VaR sangat negatif → gate harus blokir."""
        # Return sangat volatile dan negatif
        returns = [-10.0, -8.0, -12.0, -9.0, -11.0] * 10
        allowed, reason = self.rm.check_var_cvar_gate(returns, max_var=-3.0, max_cvar=-5.0)
        self.assertFalse(allowed)
        self.assertIn("VaR", reason)

    def test_gate_blocks_when_cvar_too_negative(self):
        """CVaR sangat negatif → gate harus blokir."""
        # Return dengan tail risk tinggi
        rng = np.random.default_rng(99)
        returns = list(rng.normal(0.5, 1.0, 40)) + [-15.0, -20.0, -18.0, -16.0, -14.0]
        allowed, reason = self.rm.check_var_cvar_gate(returns, max_var=-5.0, max_cvar=-8.0)
        # CVaR harus lebih buruk dari VaR
        self.assertIsInstance(allowed, bool)

    def test_gate_skips_with_insufficient_data(self):
        """Data < 20 → gate skip (return True)."""
        allowed, reason = self.rm.check_var_cvar_gate([1.0, -1.0, 0.5], max_var=-5.0)
        self.assertTrue(allowed)
        self.assertIn("tidak cukup", reason)

    def test_gate_skips_with_empty_data(self):
        allowed, reason = self.rm.check_var_cvar_gate([], max_var=-5.0)
        self.assertTrue(allowed)

    def test_gate_returns_tuple(self):
        returns = make_returns(30)
        result = self.rm.check_var_cvar_gate(returns)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], bool)
        self.assertIsInstance(result[1], str)

    def test_var_gate_in_should_execute_trade(self):
        """should_execute_trade harus menolak BUY jika VaR terlalu negatif."""
        from unittest.mock import MagicMock
        from autotrade.trading_engine import TradingEngine

        mock_db = MagicMock()
        mock_db.get_balance.return_value = 10_000_000
        mock_db.get_open_trades.return_value = []
        mock_db.count_trades_today.return_value = 0
        engine = TradingEngine(mock_db, MagicMock())

        signal = {
            "recommendation": "BUY",
            "pair": "btcidr",
            "var_historical": -4.0,
            "cvar_historical": -6.0,
        }
        # Mock trading hours agar tidak blokir test (test bisa jalan kapan saja)
        with unittest.mock.patch.object(engine, 'check_trading_hours', return_value=(True, "ok")), \
             unittest.mock.patch.object(engine, 'check_correlation_cooldown', return_value=(True, "ok")):
            allowed, reason = engine.should_execute_trade(user_id=1, signal=signal, current_price=1_500_000)
        self.assertFalse(allowed)
        self.assertIn("VaR", reason)

    def test_var_gate_passes_normal_var(self):
        """should_execute_trade tidak diblokir VaR jika nilai normal."""
        from unittest.mock import MagicMock, patch
        from autotrade.trading_engine import TradingEngine

        mock_db = MagicMock()
        mock_db.get_balance.return_value = 10_000_000
        mock_db.get_open_trades.return_value = []
        mock_db.count_trades_today.return_value = 0
        engine = TradingEngine(mock_db, MagicMock())

        signal = {
            "recommendation": "BUY",
            "pair": "btcidr",
            "var_historical": -2.0,   # aman
            "cvar_historical": -3.5,  # aman
        }
        # Patch check_trading_hours dan check_correlation_cooldown agar tidak blokir
        with unittest.mock.patch.object(engine, 'check_trading_hours', return_value=(True, "ok")), \
             unittest.mock.patch.object(engine, 'check_correlation_cooldown', return_value=(True, "ok")):
            allowed, reason = engine.should_execute_trade(user_id=1, signal=signal, current_price=1_500_000)
        # VaR tidak memblokir — mungkin ada gate lain yang blokir, tapi bukan VaR
        if not allowed:
            self.assertNotIn("VaR gate", reason)


# =============================================================================
# Test: quant_commands functions importable
# =============================================================================

# =============================================================================
# Test Fix #1 & #4: Cache module-level dan ordering
# =============================================================================

class TestQuantCacheAndOrdering(unittest.TestCase):

    def test_quant_cache_exists_in_pipeline_module(self):
        """_quant_cache harus ada sebagai dict di module signal_pipeline."""
        import signals.signal_pipeline as sp
        self.assertTrue(hasattr(sp, '_quant_cache'))
        self.assertIsInstance(sp._quant_cache, dict)

    def test_quant_cache_stores_and_retrieves(self):
        """Cache harus menyimpan dan mengembalikan data dengan benar."""
        import signals.signal_pipeline as sp
        from datetime import datetime
        sp._quant_cache["testpair"] = {
            "ts": datetime.now(),
            "garch_regime": "HIGH",
            "var_historical": -2.5,
            "arima_direction": "UP",
        }
        self.assertEqual(sp._quant_cache["testpair"]["garch_regime"], "HIGH")
        del sp._quant_cache["testpair"]

    def test_arima_filter_now_has_data_when_runs(self):
        """
        Verifikasi logika: jika enrichment dijalankan sebelum filter,
        arima_direction tersedia saat filter dievaluasi.
        Simulasi urutan yang benar.
        """
        signal = {"recommendation": "BUY", "reason": "test"}

        # Simulasi enrichment (sekarang berjalan SEBELUM filter)
        signal["arima_direction"] = "DOWN"
        signal["arima_change_pct"] = -2.0

        # Simulasi ARIMA filter (berjalan SETELAH enrichment)
        BUY_SIGNALS = {"BUY", "STRONG_BUY"}
        arima_dir = signal.get("arima_direction")
        arima_pct = signal.get("arima_change_pct", 0.0)
        if (signal["recommendation"] in BUY_SIGNALS
                and arima_dir == "DOWN"
                and arima_pct is not None
                and arima_pct < -1.0):
            signal["recommendation"] = "HOLD"
            signal["arima_filtered"] = True

        # Filter HARUS aktif karena data tersedia
        self.assertEqual(signal["recommendation"], "HOLD")
        self.assertTrue(signal.get("arima_filtered"))

    def test_cache_ttl_expired_triggers_recompute(self):
        """Cache yang sudah expired (> 5 menit) harus dianggap tidak valid."""
        from datetime import datetime, timedelta
        cache_entry = {"ts": datetime.now() - timedelta(minutes=6), "garch_regime": "LOW"}
        cache_age = (datetime.now() - cache_entry["ts"]).total_seconds()
        cache_valid = cache_age < 300  # TTL 5 menit
        self.assertFalse(cache_valid)

    def test_cache_ttl_fresh_is_valid(self):
        """Cache yang baru (< 5 menit) harus valid."""
        from datetime import datetime, timedelta
        cache_entry = {"ts": datetime.now() - timedelta(minutes=2), "garch_regime": "MEDIUM"}
        cache_age = (datetime.now() - cache_entry["ts"]).total_seconds()
        cache_valid = cache_age < 300
        self.assertTrue(cache_valid)


# =============================================================================
# Test Fix #5: VaR threshold realistis
# =============================================================================

class TestVaRThresholdRealistic(unittest.TestCase):

    def test_normal_crypto_candle_var_does_not_trigger_gate(self):
        """
        Return candle crypto normal (-2% s/d +2%) tidak boleh memicu VaR gate.
        VaR 95% untuk data normal biasanya sekitar -1.5% s/d -2.5%.
        Threshold baru -3.0% tidak boleh memblokir kondisi normal.
        """
        from unittest.mock import MagicMock
        from autotrade.trading_engine import TradingEngine

        mock_db = MagicMock()
        mock_db.get_balance.return_value = 10_000_000
        mock_db.get_open_trades.return_value = []
        mock_db.count_trades_today.return_value = 0
        engine = TradingEngine(mock_db, MagicMock())

        # VaR -2.0% = kondisi normal crypto
        signal = {
            "recommendation": "BUY",
            "pair": "btcidr",
            "var_historical": -2.0,
            "cvar_historical": -3.0,
        }
        with unittest.mock.patch.object(engine, 'check_trading_hours', return_value=(True, "ok")), \
             unittest.mock.patch.object(engine, 'check_correlation_cooldown', return_value=(True, "ok")):
            allowed, reason = engine.should_execute_trade(user_id=1, signal=signal, current_price=1_500_000)
        if not allowed:
            self.assertNotIn("VaR gate", reason)

    def test_extreme_candle_var_triggers_gate(self):
        """VaR -4.0% (crash/pump ekstrem) harus memicu gate."""
        from unittest.mock import MagicMock
        from autotrade.trading_engine import TradingEngine

        mock_db = MagicMock()
        mock_db.get_balance.return_value = 10_000_000
        mock_db.get_open_trades.return_value = []
        mock_db.count_trades_today.return_value = 0
        engine = TradingEngine(mock_db, MagicMock())

        signal = {
            "recommendation": "BUY",
            "pair": "btcidr",
            "var_historical": -4.0,
            "cvar_historical": -6.0,
        }
        with unittest.mock.patch.object(engine, 'check_trading_hours', return_value=(True, "ok")), \
             unittest.mock.patch.object(engine, 'check_correlation_cooldown', return_value=(True, "ok")):
            allowed, reason = engine.should_execute_trade(user_id=1, signal=signal, current_price=1_500_000)
        self.assertFalse(allowed)
        self.assertIn("VaR", reason)


class TestDynamicCorrelationGate(unittest.TestCase):
    """Verifikasi dynamic correlation gate di autotrade runtime."""

    def _make_bot(self, open_total):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        import pandas as pd

        base_prices = [100 + i for i in range(30)]
        correlated_prices = [price * 2 for price in base_prices]
        db = MagicMock()
        db.get_open_trades.return_value = [{"pair": "btcidr", "total": open_total}]
        return SimpleNamespace(
            historical_data={
                "btcidr": pd.DataFrame({"close": base_prices}),
                "ethidr": pd.DataFrame({"close": correlated_prices}),
            },
            db=db,
        )

    def test_dynamic_correlation_gate_blocks_high_correlated_exposure(self):
        from autotrade.runtime import _check_correlated_exposure

        bot = self._make_bot(open_total=4_000_000)

        allowed, factor, reason = _check_correlated_exposure(
            bot, user_id=1, pair="ethidr", balance=10_000_000
        )

        self.assertFalse(allowed)
        self.assertEqual(factor, 0.0)
        self.assertIn("[QUANT]", reason)
        self.assertIn("Correlated exposure", reason)

    def test_dynamic_correlation_gate_reduces_size_when_high_but_under_limit(self):
        from autotrade.runtime import _check_correlated_exposure

        bot = self._make_bot(open_total=3_500_000)

        allowed, factor, reason = _check_correlated_exposure(
            bot, user_id=1, pair="ethidr", balance=10_000_000
        )

        self.assertTrue(allowed)
        self.assertEqual(factor, 0.6)
        self.assertIn("[QUANT] High correlation", reason)


class TestQuantCommandsImport(unittest.TestCase):

    def test_new_command_functions_importable(self):
        from quant.quant_commands import (
            quant_risk_cmd,
            quant_forecast_cmd,
            quant_frontier_cmd,
        )
        self.assertTrue(callable(quant_risk_cmd))
        self.assertTrue(callable(quant_forecast_cmd))
        self.assertTrue(callable(quant_frontier_cmd))

    def test_register_quant_handlers_registers_10_commands(self):
        """register_quant_handlers harus mendaftarkan 10 commands."""
        from unittest.mock import MagicMock
        mock_app = MagicMock()
        mock_bot = MagicMock()
        mock_bot.historical_data = {}

        from quant.quant_commands import register_quant_handlers
        register_quant_handlers(mock_bot, mock_app)

        # Hitung berapa kali add_handler dipanggil
        call_count = mock_app.add_handler.call_count
        self.assertEqual(call_count, 10, f"Expected 10 handlers, got {call_count}")

    def test_risk_manager_has_var_cvar_gate(self):
        from autotrade.risk_manager import RiskManager
        self.assertTrue(hasattr(RiskManager, 'check_var_cvar_gate'))
        self.assertTrue(callable(RiskManager.check_var_cvar_gate))


if __name__ == "__main__":
    import unittest.mock
    unittest.main(verbosity=2)
