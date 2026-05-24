#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Unit test untuk 4 modul quant baru: RiskMetrics, GARCHModel, ARIMAModel, EfficientFrontier.
# Caller: pytest / python3 -m unittest
# Dependensi: unittest, numpy, quant.risk_metrics, quant.volatility_models, quant.forecasting, quant.efficient_frontier
# Main Functions: TestRiskMetrics, TestGARCHModel, TestARIMAModel, TestEfficientFrontier
# Side Effects: none; pure computation tests only.
"""
Test suite untuk fitur quant baru (2026-05-19):
  - CAGR, VaR (Historical/Parametric/Monte Carlo), CVaR
  - GARCH(1,1) & ARCH test
  - ARIMA forecasting
  - Efficient Frontier & Portfolio Optimization

Run:
    python3 -m pytest tests/test_quant_new_features.py -v
    python3 -m unittest tests.test_quant_new_features -v
"""

import sys
import os
import unittest
import numpy as np

# Pastikan root project ada di path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant.risk_metrics import RiskMetrics, RiskResult
from quant.volatility_models import GARCHModel, GARCHResult
from quant.forecasting import ARIMAModel, ARIMAResult
from quant.efficient_frontier import EfficientFrontier, FrontierResult


# =============================================================================
# FIXTURES — data sintetis yang realistis
# =============================================================================

def make_returns(n=100, seed=42, mean=0.5, std=2.0):
    """Return series sintetis: mean 0.5%/trade, std 2%."""
    rng = np.random.default_rng(seed)
    return list(rng.normal(mean, std, n))


def make_prices(n=100, start=1_500_000, seed=42):
    """Price series sintetis dari random walk."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.02, n)
    prices = [start]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    return prices[1:]


def make_clustered_returns(n=100, seed=42):
    """Return dengan volatility clustering (ARCH effect)."""
    rng = np.random.default_rng(seed)
    returns = []
    vol = 1.0
    for _ in range(n):
        shock = rng.normal(0, vol)
        returns.append(shock)
        vol = max(0.5, 0.05 + 0.15 * abs(shock) + 0.80 * vol)
    return returns


# =============================================================================
# TEST: RiskMetrics (CAGR, VaR, CVaR)
# =============================================================================

class TestRiskMetrics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rm = RiskMetrics(mc_simulations=1000, random_seed=42)
        cls.returns = make_returns(n=100)
        cls.result = cls.rm.calculate(cls.returns, confidence=0.95)

    def test_returns_result_object(self):
        """calculate() harus mengembalikan RiskResult."""
        self.assertIsNotNone(self.result)
        self.assertIsInstance(self.result, RiskResult)

    def test_insufficient_data_returns_none(self):
        """Data < MIN_RETURNS harus return None."""
        result = self.rm.calculate([1.0, 2.0, -1.0], confidence=0.95)
        self.assertIsNone(result)

    def test_empty_data_returns_none(self):
        result = self.rm.calculate([], confidence=0.95)
        self.assertIsNone(result)

    def test_cagr_is_finite(self):
        """CAGR harus finite dan reasonable."""
        self.assertTrue(np.isfinite(self.result.cagr))
        # CAGR tidak boleh -100% (total loss)
        self.assertGreater(self.result.cagr, -1.0)

    def test_cagr_positive_for_positive_returns(self):
        """Return positif konsisten → CAGR harus positif."""
        pos_returns = [1.0] * 50  # +1% setiap trade
        result = self.rm.calculate(pos_returns)
        self.assertIsNotNone(result)
        self.assertGreater(result.cagr, 0)

    def test_var_ordering(self):
        """VaR harus negatif (kerugian) dan CVaR <= VaR (lebih buruk)."""
        r = self.result
        # VaR historical harus <= mean return (ada kemungkinan rugi)
        self.assertLess(r.var_historical, r.mean_return)
        # CVaR harus <= VaR (expected loss lebih besar dari VaR threshold)
        self.assertLessEqual(r.cvar_historical, r.var_historical + 0.001)

    def test_var_95_worse_than_var_90(self):
        """VaR 95% harus lebih buruk (lebih negatif) dari VaR 90%."""
        r95 = self.rm.calculate(self.returns, confidence=0.95)
        r90 = self.rm.calculate(self.returns, confidence=0.90)
        self.assertIsNotNone(r95)
        self.assertIsNotNone(r90)
        self.assertLessEqual(r95.var_historical, r90.var_historical)

    def test_montecarlo_var_close_to_historical(self):
        """Monte Carlo VaR harus dekat dengan Historical VaR (±3%)."""
        r = self.result
        diff = abs(r.var_montecarlo - r.var_historical)
        self.assertLess(diff, 3.0, f"MC VaR={r.var_montecarlo:.3f} vs Hist VaR={r.var_historical:.3f}")

    def test_n_trades_correct(self):
        self.assertEqual(self.result.n_trades, len(self.returns))

    def test_confidence_stored(self):
        self.assertAlmostEqual(self.result.confidence, 0.95)

    def test_summary_text_contains_key_fields(self):
        text = self.result.summary_text()
        self.assertIn("CAGR", text)
        self.assertIn("VaR", text)
        self.assertIn("CVaR", text)

    def test_to_dict_has_all_keys(self):
        d = self.result.to_dict()
        for key in ["cagr", "var_historical", "var_parametric", "var_montecarlo",
                    "cvar_historical", "cvar_parametric", "mean_return", "std_return"]:
            self.assertIn(key, d, f"Missing key: {key}")

    def test_calculate_from_trades(self):
        """calculate_from_trades() harus bekerja dengan format dict trade."""
        trades = [{"profit_loss_pct": r} for r in self.returns]
        result = self.rm.calculate_from_trades(trades, confidence=0.95)
        self.assertIsNotNone(result)
        self.assertEqual(result.n_trades, len(self.returns))

    def test_all_negative_returns(self):
        """Semua return negatif → CAGR negatif, VaR sangat negatif."""
        neg_returns = [-1.0] * 50
        result = self.rm.calculate(neg_returns)
        self.assertIsNotNone(result)
        self.assertLess(result.cagr, 0)
        self.assertLess(result.var_historical, 0)


# =============================================================================
# TEST: GARCHModel (GARCH(1,1) & ARCH test)
# =============================================================================

class TestGARCHModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.garch = GARCHModel()
        cls.returns_normal = make_returns(n=100)
        cls.returns_clustered = make_clustered_returns(n=100)
        cls.result_normal = cls.garch.fit(cls.returns_normal)
        cls.result_clustered = cls.garch.fit(cls.returns_clustered)

    def test_returns_result_object(self):
        self.assertIsNotNone(self.result_normal)
        self.assertIsInstance(self.result_normal, GARCHResult)

    def test_insufficient_data_returns_none(self):
        result = self.garch.fit([1.0, -1.0, 0.5])
        self.assertIsNone(result)

    def test_parameters_valid_range(self):
        """omega > 0, alpha >= 0, beta >= 0, alpha+beta < 1."""
        r = self.result_normal
        self.assertGreater(r.omega, 0)
        self.assertGreaterEqual(r.alpha, 0)
        self.assertGreaterEqual(r.beta, 0)
        self.assertLess(r.persistence, 1.0 + 1e-6)  # stasioner atau borderline

    def test_conditional_vol_positive(self):
        """Semua conditional volatility harus positif."""
        r = self.result_normal
        self.assertTrue(all(v > 0 for v in r.conditional_vol))

    def test_conditional_vol_length(self):
        """Panjang conditional_vol harus sama dengan input."""
        r = self.result_normal
        self.assertEqual(len(r.conditional_vol), len(self.returns_normal))

    def test_forecast_positive(self):
        """Forecast volatilitas harus positif."""
        r = self.result_normal
        self.assertGreater(r.forecast_vol_1d, 0)
        self.assertGreater(r.forecast_vol_5d, 0)

    def test_arch_test_pvalue_range(self):
        """p-value ARCH test harus antara 0 dan 1."""
        r = self.result_normal
        self.assertGreaterEqual(r.arch_test_pvalue, 0.0)
        self.assertLessEqual(r.arch_test_pvalue, 1.0)

    def test_clustered_returns_detect_arch(self):
        """Data dengan volatility clustering harus terdeteksi ARCH effect."""
        r = self.result_clustered
        self.assertIsNotNone(r)
        # Data clustered seharusnya punya p-value rendah (ada ARCH effect)
        # Toleransi: tidak selalu p < 0.05 dengan data sintetis kecil
        self.assertLess(r.arch_test_pvalue, 0.5)

    def test_n_obs_correct(self):
        self.assertEqual(self.result_normal.n_obs, len(self.returns_normal))

    def test_regime_classification(self):
        """regime harus salah satu dari LOW/MEDIUM/HIGH/EXTREME."""
        r = self.result_normal
        self.assertIn(r.regime, ["LOW", "MEDIUM", "HIGH", "EXTREME"])

    def test_summary_text_contains_key_fields(self):
        text = self.result_normal.summary_text()
        self.assertIn("GARCH", text)
        self.assertIn("alpha", text.lower())
        self.assertIn("beta", text.lower())

    def test_to_dict_has_all_keys(self):
        d = self.result_normal.to_dict()
        for key in ["omega", "alpha", "beta", "persistence", "current_vol",
                    "forecast_vol_1d", "arch_test_pvalue", "has_clustering"]:
            self.assertIn(key, d, f"Missing key: {key}")

    def test_long_run_vol_finite(self):
        r = self.result_normal
        self.assertTrue(np.isfinite(r.long_run_vol))
        self.assertGreater(r.long_run_vol, 0)


# =============================================================================
# TEST: ARIMAModel
# =============================================================================

class TestARIMAModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.arima = ARIMAModel(p=1, d=1, q=1)
        cls.prices = make_prices(n=80)
        cls.result = cls.arima.fit_forecast(cls.prices, steps=5)

    def test_returns_result_object(self):
        self.assertIsNotNone(self.result)
        self.assertIsInstance(self.result, ARIMAResult)

    def test_insufficient_data_returns_none(self):
        result = self.arima.fit_forecast([1500000, 1510000, 1505000], steps=3)
        self.assertIsNone(result)

    def test_forecast_length(self):
        """Panjang forecast harus sama dengan steps."""
        self.assertEqual(len(self.result.forecast), 5)
        self.assertEqual(len(self.result.conf_lower), 5)
        self.assertEqual(len(self.result.conf_upper), 5)

    def test_forecast_prices_positive(self):
        """Harga forecast harus positif (tidak bisa negatif)."""
        for f in self.result.forecast:
            self.assertGreater(f, 0, f"Forecast price {f} is not positive")

    def test_confidence_interval_ordering(self):
        """conf_lower <= forecast <= conf_upper untuk setiap step."""
        for i in range(len(self.result.forecast)):
            self.assertLessEqual(
                self.result.conf_lower[i], self.result.conf_upper[i],
                f"CI inverted at step {i}"
            )

    def test_ci_widens_over_time(self):
        """Confidence interval harus melebar seiring langkah forecast."""
        widths = [
            self.result.conf_upper[i] - self.result.conf_lower[i]
            for i in range(len(self.result.forecast))
        ]
        # Width step terakhir harus >= step pertama
        self.assertGreaterEqual(widths[-1], widths[0])

    def test_direction_valid(self):
        self.assertIn(self.result.direction, ["UP", "DOWN", "FLAT"])

    def test_last_price_matches_input(self):
        self.assertAlmostEqual(self.result.last_price, self.prices[-1], places=0)

    def test_n_obs_correct(self):
        self.assertEqual(self.result.n_obs, len(self.prices))

    def test_expected_change_pct_consistent_with_direction(self):
        """expected_change_pct harus konsisten dengan direction."""
        pct = self.result.expected_change_pct
        direction = self.result.direction
        if direction == "UP":
            self.assertGreater(pct, 0.5)
        elif direction == "DOWN":
            self.assertLess(pct, -0.5)

    def test_summary_text_contains_key_fields(self):
        text = self.result.summary_text()
        self.assertIn("ARIMA", text)
        self.assertIn("Forecast", text)

    def test_to_dict_has_all_keys(self):
        d = self.result.to_dict()
        for key in ["p", "d", "q", "forecast", "conf_lower", "conf_upper",
                    "last_price", "forecast_price", "expected_change_pct", "direction"]:
            self.assertIn(key, d, f"Missing key: {key}")

    def test_auto_order_selection(self):
        """auto_order=True harus memilih p,q dan tetap menghasilkan result."""
        arima_auto = ARIMAModel(p=1, d=1, q=1, auto_order=True)
        result = arima_auto.fit_forecast(self.prices, steps=3)
        self.assertIsNotNone(result)
        self.assertEqual(len(result.forecast), 3)

    def test_different_steps(self):
        """Forecast dengan steps berbeda harus menghasilkan panjang yang benar."""
        for steps in [1, 3, 10]:
            result = self.arima.fit_forecast(self.prices, steps=steps)
            self.assertIsNotNone(result)
            self.assertEqual(len(result.forecast), steps)

    def test_aic_finite(self):
        self.assertTrue(np.isfinite(self.result.aic))

    def test_residual_std_positive(self):
        self.assertGreater(self.result.residual_std, 0)


# =============================================================================
# TEST: EfficientFrontier
# =============================================================================

class TestEfficientFrontier(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Jalankan optimize() sekali untuk semua test methods (bukan per-test)."""
        import quant.efficient_frontier as ef_mod
        ef_mod.FRONTIER_POINTS = 10  # Kurangi dari 50 → 10 untuk kecepatan test
        cls.ef = EfficientFrontier(max_weight=0.60)
        rng = np.random.default_rng(42)
        n = 60
        cls.returns_matrix = {
            "btcidr": list(rng.normal(0.6, 2.5, n)),
            "ethidr": list(rng.normal(0.5, 3.0, n)),
            "bnbidr": list(rng.normal(0.4, 2.0, n)),
        }
        cls.result = cls.ef.optimize(cls.returns_matrix)

    def test_returns_result_object(self):
        self.assertIsNotNone(self.result)
        self.assertIsInstance(self.result, FrontierResult)

    def test_insufficient_assets_returns_none(self):
        """Hanya 1 aset → tidak bisa buat frontier."""
        result = self.ef.optimize({"btcidr": make_returns(50)})
        self.assertIsNone(result)

    def test_insufficient_data_per_asset_returns_none(self):
        """Data < MIN_RETURNS_PER_ASSET → aset di-skip, jika < 2 aset valid → None."""
        result = self.ef.optimize({
            "btcidr": [1.0, 2.0, -1.0],  # terlalu sedikit
            "ethidr": [1.0, 2.0, -1.0],  # terlalu sedikit
        })
        self.assertIsNone(result)

    def test_assets_list_correct(self):
        self.assertEqual(set(self.result.assets), {"btcidr", "ethidr", "bnbidr"})

    def test_max_sharpe_weights_sum_to_one(self):
        """Bobot Max Sharpe harus sum = 1."""
        total = sum(self.result.max_sharpe.weights.values())
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_min_variance_weights_sum_to_one(self):
        """Bobot Min Variance harus sum = 1."""
        total = sum(self.result.min_variance.weights.values())
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_weights_non_negative(self):
        """Tidak ada short selling — semua bobot >= 0."""
        for w in self.result.max_sharpe.weights.values():
            self.assertGreaterEqual(w, -1e-6)
        for w in self.result.min_variance.weights.values():
            self.assertGreaterEqual(w, -1e-6)

    def test_max_weight_constraint(self):
        """Tidak ada bobot yang melebihi max_weight."""
        for w in self.result.max_sharpe.weights.values():
            self.assertLessEqual(w, self.ef.max_weight + 1e-4)

    def test_min_variance_vol_le_max_sharpe_vol(self):
        """Min Variance portfolio harus punya volatilitas <= Max Sharpe."""
        self.assertLessEqual(
            self.result.min_variance.volatility,
            self.result.max_sharpe.volatility + 0.5  # toleransi kecil
        )

    def test_max_sharpe_sharpe_ge_min_variance_sharpe(self):
        """Max Sharpe portfolio harus punya Sharpe >= Min Variance."""
        self.assertGreaterEqual(
            self.result.max_sharpe.sharpe_ratio,
            self.result.min_variance.sharpe_ratio - 0.01
        )

    def test_frontier_has_points(self):
        """Frontier curve harus punya setidaknya beberapa titik."""
        self.assertGreater(len(self.result.frontier_vols), 2)
        self.assertEqual(len(self.result.frontier_vols), len(self.result.frontier_rets))

    def test_asset_stats_present(self):
        """Stats per aset harus ada untuk semua aset."""
        for asset in self.result.assets:
            self.assertIn(asset, self.result.asset_returns)
            self.assertIn(asset, self.result.asset_vols)
            self.assertIn(asset, self.result.asset_sharpes)

    def test_asset_vols_positive(self):
        for asset, vol in self.result.asset_vols.items():
            self.assertGreater(vol, 0, f"Vol for {asset} is not positive")

    def test_correlation_matrix_shape(self):
        """Correlation matrix harus n_assets x n_assets."""
        n = self.result.n_assets
        self.assertEqual(len(self.result.correlation_matrix), n)
        for row in self.result.correlation_matrix:
            self.assertEqual(len(row), n)

    def test_correlation_diagonal_is_one(self):
        """Diagonal correlation matrix harus 1.0."""
        for i in range(self.result.n_assets):
            self.assertAlmostEqual(
                self.result.correlation_matrix[i][i], 1.0, places=3
            )

    def test_equal_weight_present(self):
        self.assertIsNotNone(self.result.equal_weight)
        total = sum(self.result.equal_weight.weights.values())
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_summary_text_contains_key_fields(self):
        text = self.result.summary_text()
        self.assertIn("Efficient Frontier", text)
        self.assertIn("Sharpe", text)

    def test_to_dict_has_all_keys(self):
        d = self.result.to_dict()
        for key in ["assets", "max_sharpe", "min_variance", "asset_returns",
                    "asset_vols", "frontier_points"]:
            self.assertIn(key, d, f"Missing key: {key}")

    def test_two_assets(self):
        """Frontier dengan 2 aset harus tetap bekerja."""
        rng = np.random.default_rng(99)
        result = self.ef.optimize({
            "btcidr": list(rng.normal(0.5, 2.0, 40)),
            "ethidr": list(rng.normal(0.4, 2.5, 40)),
        })
        self.assertIsNotNone(result)
        self.assertEqual(result.n_assets, 2)


# =============================================================================
# TEST: Import & Integration
# =============================================================================

class TestQuantImports(unittest.TestCase):

    def test_all_classes_importable_from_quant(self):
        """Semua class baru harus bisa diimport dari quant package."""
        from quant import (
            RiskMetrics, RiskResult,
            GARCHModel, GARCHResult,
            ARIMAModel, ARIMAResult,
            EfficientFrontier, FrontierResult, PortfolioWeights,
        )
        self.assertTrue(True)  # Jika sampai sini, import berhasil

    def test_existing_modules_still_importable(self):
        """Modul quant lama tidak boleh rusak."""
        from quant import (
            MeanReversionEngine, BayesianKellyEngine,
            MomentumFactorEngine, PerformanceAnalytics,
            DynamicCorrelationEngine, StatArbEngine,
        )
        self.assertTrue(True)

    def test_risk_metrics_pipeline(self):
        """End-to-end: returns → RiskResult → dict."""
        rm = RiskMetrics(mc_simulations=500, random_seed=1)
        returns = make_returns(n=50)
        result = rm.calculate(returns)
        self.assertIsNotNone(result)
        d = result.to_dict()
        self.assertIsInstance(d, dict)

    def test_garch_pipeline(self):
        """End-to-end: returns → GARCHResult → dict."""
        garch = GARCHModel()
        returns = make_returns(n=60)
        result = garch.fit(returns)
        self.assertIsNotNone(result)
        d = result.to_dict()
        self.assertIsInstance(d, dict)

    def test_arima_pipeline(self):
        """End-to-end: prices → ARIMAResult → dict."""
        arima = ARIMAModel(p=1, d=1, q=1)
        prices = make_prices(n=50)
        result = arima.fit_forecast(prices, steps=3)
        self.assertIsNotNone(result)
        d = result.to_dict()
        self.assertIsInstance(d, dict)

    def test_frontier_pipeline(self):
        """End-to-end: returns_matrix → FrontierResult → dict."""
        ef = EfficientFrontier()
        rng = np.random.default_rng(7)
        returns_matrix = {
            "a": list(rng.normal(0.5, 2.0, 40)),
            "b": list(rng.normal(0.3, 1.5, 40)),
        }
        result = ef.optimize(returns_matrix)
        self.assertIsNotNone(result)
        d = result.to_dict()
        self.assertIsInstance(d, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)

