"""Regression tests for Prioritas 1 signal-entry tuning (2026-05-22 Sesi 4).

Goal: longgarkan jalur signal entry agar lebih banyak signal actionable
sampai ke Telegram tanpa mengubah risk management. Tests di file ini
mengunci nilai baru dari empat tuning supaya tidak regresi:

1. core/config.py — SR_MIN_RR_RATIO turun 1.5 → 1.2
2. signals/signal_filter_v2.py — defaults selaras dengan signal_rules
   (cosmetic: filter_v2 tidak di-import di pipeline live, tapi tetap
   dijaga konsisten supaya audit/skill notes tidak menyesatkan)
3. signals/signal_quality_engine.py — MINIMUM_SIGNAL_INTERVAL_MINUTES 15 → 10
4. autotrade/runtime.py — cooldown notifikasi Telegram 5 → 3 menit
   (extracted ke konstanta modul SIGNAL_NOTIFICATION_COOLDOWN_MINUTES dan
   SIGNAL_CHECK_COOLDOWN_MINUTES untuk testability)

Tidak ada perubahan ke MAX_DRAWDOWN_PCT, MAX_DAILY_LOSS_PCT, AUTO_TRADE_DRY_RUN,
atau circuit breaker lain.
"""

import unittest

from core.config import Config
from signals import signal_quality_engine
from signals.signal_filter_v2 import SignalFilterV2
from autotrade import runtime as autotrade_runtime


class TestSRMinRRRatioPriority1(unittest.TestCase):
    """SR_MIN_RR_RATIO harus 1.2 supaya signal RR moderate tetap lolos S/R gate."""

    def test_sr_min_rr_ratio_is_relaxed_to_1_2(self):
        self.assertEqual(Config.SR_MIN_RR_RATIO, 1.2)

    def test_sr_validation_remains_enabled(self):
        """Validasi prinsip SR tetap aktif — yang berubah hanya thresholdnya."""
        self.assertTrue(Config.ENABLE_SR_VALIDATION)


class TestSignalQualityEngineCooldownPriority1(unittest.TestCase):
    """Pipeline-level cooldown turun 15 → 10 menit supaya signal tidak ditahan terlalu lama."""

    def test_minimum_signal_interval_is_10_minutes(self):
        self.assertEqual(signal_quality_engine.MINIMUM_SIGNAL_INTERVAL_MINUTES, 10)


class TestAutotradeRuntimeCooldownPriority1(unittest.TestCase):
    """Cooldown notifikasi Telegram per pair / per (pair,recommendation) turun 5 → 3 menit."""

    def test_signal_notification_cooldown_is_3_minutes(self):
        self.assertEqual(autotrade_runtime.SIGNAL_NOTIFICATION_COOLDOWN_MINUTES, 3)

    def test_signal_check_cooldown_is_3_minutes(self):
        self.assertEqual(autotrade_runtime.SIGNAL_CHECK_COOLDOWN_MINUTES, 3)


class TestSignalFilterV2DefaultsPriority1(unittest.TestCase):
    """Defaults SignalFilterV2 selaras dengan signal_rules (BUY 0.50, STRONG_BUY 0.64)."""

    def setUp(self):
        self.cfg = SignalFilterV2()._default_config()

    def test_ml_confidence_min_is_0_50(self):
        self.assertEqual(self.cfg["ml_confidence_min"], 0.50)

    def test_ml_confidence_buy_is_0_50(self):
        self.assertEqual(self.cfg["ml_confidence_buy"], 0.50)

    def test_ml_confidence_strong_buy_is_0_64(self):
        self.assertEqual(self.cfg["ml_confidence_strong_buy"], 0.64)

    def test_ml_confidence_sell_unchanged_at_0_65(self):
        """SELL/STRONG_SELL DIBIARKAN lebih ketat dari signal_rules (asimetri Opsi B —
        BUY-side dilonggarkan, SELL-side dipertahankan ketat untuk lawan bias bearish)."""
        self.assertEqual(self.cfg["ml_confidence_sell"], 0.65)

    def test_ml_confidence_strong_sell_unchanged_at_0_80(self):
        self.assertEqual(self.cfg["ml_confidence_strong_sell"], 0.80)

    def test_combined_strength_buy_relaxed_to_0_10(self):
        self.assertEqual(self.cfg["combined_strength_buy"], 0.10)

    def test_combined_strength_strong_buy_relaxed_to_0_35(self):
        self.assertEqual(self.cfg["combined_strength_strong_buy"], 0.35)


if __name__ == "__main__":
    unittest.main()
