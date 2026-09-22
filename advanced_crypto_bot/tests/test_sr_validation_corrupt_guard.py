"""Regression tests untuk perbaikan S/R validation 2026-06-09.

Konteks (lihat CHANGELOG 2026-06-09):
- Bot berjalan ~58 menit di Google VM, 0 entry DRY RUN.
- 851 dari 1103 BUY (77%) di-downgrade ke HOLD oleh `SR_VALIDATION` karena
  `SR_NEAR_RESISTANCE_PCT = 2.5` terlalu agresif untuk pair low-cap.
- Beberapa pair memiliki orderbook corrupt (R1=0, price=0) namun tetap masuk
  validation dan auto-reject karena ekspresi `0 >= 0 * (1 - X)` selalu True.

Tests:
1. `SR_NEAR_RESISTANCE_PCT` diturunkan ke 1.0 (loosen 2.5 → 1.0).
2. Threshold lain tidak berubah (regression guard).
3. SR_VALIDATION harus tetap enabled.
"""

import unittest

from core.config import Config


class TestSRNearResistanceThreshold20260609(unittest.TestCase):
    """SR_NEAR_RESISTANCE_PCT diturunkan 2.5 → 1.0 untuk mengurangi false reject."""

    def test_sr_near_resistance_pct_is_relaxed_to_1_0(self):
        self.assertEqual(Config.SR_NEAR_RESISTANCE_PCT, 1.0)

    def test_sr_near_support_pct_unchanged_at_2_5(self):
        """SR_NEAR_SUPPORT_PCT tetap 2.5 — perubahan hanya di sisi resistance."""
        self.assertEqual(Config.SR_NEAR_SUPPORT_PCT, 2.5)

    def test_sr_min_rr_ratio_unchanged_at_1_2(self):
        """SR_MIN_RR_RATIO tetap 1.2 (perubahan terpisah dari Prioritas 1)."""
        self.assertEqual(Config.SR_MIN_RR_RATIO, 1.2)

    def test_sr_validation_remains_enabled(self):
        """SR_VALIDATION wajib tetap aktif untuk filter notifikasi Telegram."""
        self.assertTrue(Config.ENABLE_SR_VALIDATION)


if __name__ == "__main__":
    unittest.main()
