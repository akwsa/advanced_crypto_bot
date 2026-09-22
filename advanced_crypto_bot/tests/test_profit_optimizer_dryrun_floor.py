"""Regression test: R/R floor mode-aware (dry-run vs live).

Konteks 2026-06-10: di dry-run, floor R/R after fees diturunkan ke
PROFIT_AUTOTRADE_DRYRUN_MIN_RR (default 1.20) supaya setup
moderate (saharaidr-class) bisa lolos untuk observasi. LIVE tetap pakai
max(RISK_REWARD_RATIO*0.75, 1.35) = 1.50.

Test ini memastikan:
1. Dengan AUTO_TRADE_DRY_RUN=True, min_rr_required <= 1.20.
2. Dengan AUTO_TRADE_DRY_RUN=False, min_rr_required tetap 1.50 (no regression real-trading).
3. Setup R/R=1.25 di dry-run TIDAK di-skip karena RR floor (lolos floor; bisa diskip karena edge_score, itu jalur terpisah).
4. Setup R/R=1.25 di LIVE diblokir karena di bawah 1.50.
5. Setup R/R=1.10 di dry-run tetap diblokir (di bawah 1.20).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.config import Config
from core.profit_optimizer import evaluate_autotrade_setup


def _high_edge_signal():
    """Signal dengan ml_confidence + combined_strength tinggi supaya edge_score
    cukup untuk lolos PROFIT_AUTOTRADE_MIN_EDGE_SCORE (default 56)."""
    return {
        "ml_confidence": 0.85,
        "combined_strength": 0.6,
    }


def _high_edge_market():
    return {
        "overall_signal": "BULLISH",
        "volume_ratio": 2.5,
        "buy_sell_ratio": 1.8,
    }


def _calm_regime():
    return {"is_trending": True, "trend_direction": "UP"}


class TestDryRunRRFloor(unittest.TestCase):
    def test_dry_run_floor_uses_dryrun_min_rr_constant(self):
        with patch.object(Config, "AUTO_TRADE_DRY_RUN", True), patch.object(
            Config, "PROFIT_AUTOTRADE_DRYRUN_MIN_RR", 1.20
        ):
            decision = evaluate_autotrade_setup(
                signal=_high_edge_signal(),
                market_conditions=_high_edge_market(),
                regime=_calm_regime(),
                rr_after_fees=2.0,
            )
        self.assertAlmostEqual(decision.min_rr_required, 1.20, places=4)

    def test_live_floor_unchanged_at_1_50(self):
        with patch.object(Config, "AUTO_TRADE_DRY_RUN", False), patch.object(
            Config, "RISK_REWARD_RATIO", 2.0
        ):
            decision = evaluate_autotrade_setup(
                signal=_high_edge_signal(),
                market_conditions=_high_edge_market(),
                regime=_calm_regime(),
                rr_after_fees=2.0,
            )
        self.assertAlmostEqual(decision.min_rr_required, 1.50, places=4)

    def test_dryrun_setup_rr_1_25_passes_rr_gate(self):
        """saharaidr-class setup (R/R sedikit di atas 1.20) harus lolos floor di dry-run."""
        with patch.object(Config, "AUTO_TRADE_DRY_RUN", True), patch.object(
            Config, "PROFIT_AUTOTRADE_DRYRUN_MIN_RR", 1.20
        ):
            decision = evaluate_autotrade_setup(
                signal=_high_edge_signal(),
                market_conditions=_high_edge_market(),
                regime=_calm_regime(),
                rr_after_fees=1.25,
            )
        # Floor 1.20 → R/R 1.25 lolos, reason TIDAK boleh "R/R after fees below dynamic floor"
        self.assertNotIn("R/R after fees below dynamic floor", decision.reason)

    def test_live_setup_rr_1_25_blocked_by_rr_floor(self):
        """Setup yang sama di LIVE harus tetap diblokir floor 1.50."""
        with patch.object(Config, "AUTO_TRADE_DRY_RUN", False), patch.object(
            Config, "RISK_REWARD_RATIO", 2.0
        ):
            decision = evaluate_autotrade_setup(
                signal=_high_edge_signal(),
                market_conditions=_high_edge_market(),
                regime=_calm_regime(),
                rr_after_fees=1.25,
            )
        self.assertTrue(decision.should_skip)
        self.assertIn("R/R after fees below dynamic floor", decision.reason)
        self.assertIn("1.25", decision.reason)
        self.assertIn("1.50", decision.reason)

    def test_dryrun_setup_rr_1_10_still_blocked(self):
        """R/R di bawah floor dry-run (1.20) tetap diblokir — tidak melonggarkan ke 0."""
        with patch.object(Config, "AUTO_TRADE_DRY_RUN", True), patch.object(
            Config, "PROFIT_AUTOTRADE_DRYRUN_MIN_RR", 1.20
        ):
            decision = evaluate_autotrade_setup(
                signal=_high_edge_signal(),
                market_conditions=_high_edge_market(),
                regime=_calm_regime(),
                rr_after_fees=1.10,
            )
        self.assertTrue(decision.should_skip)
        self.assertIn("R/R after fees below dynamic floor", decision.reason)
        self.assertIn("1.10", decision.reason)
        self.assertIn("1.20", decision.reason)

    def test_dryrun_floor_env_overridable(self):
        """User bisa naikkan floor dry-run via env var tanpa redeploy."""
        with patch.object(Config, "AUTO_TRADE_DRY_RUN", True), patch.object(
            Config, "PROFIT_AUTOTRADE_DRYRUN_MIN_RR", 1.40
        ):
            decision = evaluate_autotrade_setup(
                signal=_high_edge_signal(),
                market_conditions=_high_edge_market(),
                regime=_calm_regime(),
                rr_after_fees=1.30,
            )
        self.assertTrue(decision.should_skip)
        self.assertIn("1.30", decision.reason)
        self.assertIn("1.40", decision.reason)


if __name__ == "__main__":
    unittest.main()
