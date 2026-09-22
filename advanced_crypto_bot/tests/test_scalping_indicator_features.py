"""
Regression tests for scalping-optimized technical indicator features
added to MLTradingModelV2.prepare_features().

Covers:
- EMA scalping suite (EMA 5, 9, 20 + crossover signals)
- RSI fast period 7
- Stochastic RSI (StochRSI)
- RSI crypto aggressive levels (80/20 binary flags)

These are FEATURE-ONLY additions (no trading execution path changes).
"""

import pandas as pd
import numpy as np
import pytest


def _make_ohlcv(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for indicator tests."""
    rng = np.random.RandomState(seed)
    close = 10_000 + np.cumsum(rng.randn(n) * 100)
    high = close + np.abs(rng.randn(n) * 50)
    low = close - np.abs(rng.randn(n) * 50)
    volume = np.abs(rng.randn(n) * 1_000_000) + 100_000
    return pd.DataFrame({
        "close": close,
        "high": high,
        "low": low,
        "open": close - rng.randn(n) * 20,
        "volume": volume,
    })


class TestEMAScalpingSuite:
    """EMA 5, 9, 20 and EMA9×EMA20 crossover features."""

    def test_ema5_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "ema_5" in features.columns, "ema_5 feature missing"

    def test_ema9_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "ema_9" in features.columns, "ema_9 feature missing"

    def test_ema20_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "ema_20" in features.columns, "ema_20 feature missing"

    def test_ema_crossover_signal_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "ema9_ema20_crossover" in features.columns, \
            "ema9_ema20_crossover feature missing"

    def test_ema_crossover_values_binary(self):
        """Crossover should be 1 (bullish cross), -1 (bearish cross), or 0."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        valid = {-1.0, 0.0, 1.0}
        unique_vals = set(features["ema9_ema20_crossover"].dropna().unique())
        assert unique_vals.issubset(valid), \
            f"ema9_ema20_crossover has invalid values: {unique_vals - valid}"

    def test_ema_is_exponential_not_simple(self):
        """EMA should differ from SMA for the same period."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        # EMA 9 should NOT equal SMA 9 (already in features as sma_9)
        if "sma_9" in features.columns:
            diff = (features["ema_9"] - features["sma_9"]).abs()
            # At least some rows should differ
            assert diff.sum() > 0, "ema_9 identical to sma_9 — not exponential!"


class TestRSIFastPeriod7:
    """RSI with fast period 7 for scalping."""

    def test_rsi_fast_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "rsi_7" in features.columns, "rsi_7 feature missing"

    def test_rsi_fast_range(self):
        """RSI 7 should be between 0 and 100."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        rsi7 = features["rsi_7"].dropna()
        assert (rsi7 >= 0).all() and (rsi7 <= 100).all(), \
            f"rsi_7 out of range: min={rsi7.min()}, max={rsi7.max()}"

    def test_rsi_fast_differs_from_rsi14(self):
        """RSI 7 should be more reactive than RSI 14 (different values)."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        diff = (features["rsi_7"] - features["rsi"]).abs()
        # Not identical — RSI 7 reacts faster
        assert diff.sum() > 0, "rsi_7 identical to rsi (period 14) — not faster!"


class TestStochRSI:
    """Stochastic RSI — most sensitive oscillator for scalping."""

    def test_stochrsi_k_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "stochrsi_k" in features.columns, "stochrsi_k feature missing"

    def test_stochrsi_d_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "stochrsi_d" in features.columns, "stochrsi_d feature missing"

    def test_stochrsi_range(self):
        """StochRSI should oscillate between 0 and 100."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        k = features["stochrsi_k"].dropna()
        d = features["stochrsi_d"].dropna()
        assert (k >= 0).all() and (k <= 100).all(), \
            f"stochrsi_k out of range: min={k.min()}, max={k.max()}"
        assert (d >= 0).all() and (d <= 100).all(), \
            f"stochrsi_d out of range: min={d.min()}, max={d.max()}"

    def test_stochrsi_not_same_as_standard_stoch(self):
        """StochRSI applies stochastic formula to RSI, not to price.
        Should differ from the existing stoch_k (which uses price)."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        if "stoch_k" in features.columns:
            diff = (features["stochrsi_k"] - features["stoch_k"]).abs()
            assert diff.sum() > 0, \
                "stochrsi_k identical to stoch_k — not applying to RSI!"


class TestRSICryptoLevels:
    """RSI crypto-aggressive overbought/oversold levels (80/20)."""

    def test_rsi_overbought_crypto_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "rsi_overbought_crypto" in features.columns, \
            "rsi_overbought_crypto feature missing"

    def test_rsi_oversold_crypto_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        assert "rsi_oversold_crypto" in features.columns, \
            "rsi_oversold_crypto feature missing"

    def test_rsi_crypto_flags_are_binary(self):
        """Overbought/oversold flags should be 0 or 1."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        ob = features["rsi_overbought_crypto"].dropna()
        os_ = features["rsi_oversold_crypto"].dropna()
        assert set(ob.unique()).issubset({0.0, 1.0}), \
            f"rsi_overbought_crypto not binary: {ob.unique()}"
        assert set(os_.unique()).issubset({0.0, 1.0}), \
            f"rsi_oversold_crypto not binary: {os_.unique()}"

    def test_rsi_overbought_crypto_uses_80_not_70(self):
        """Crypto aggressive uses RSI > 80, not traditional 70.
        Verify by creating data where RSI is between 70-80 —
        flag should NOT be set."""
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        # Rows where RSI is 70-80 should NOT be flagged overbought
        between_70_80 = (features["rsi"] >= 70) & (features["rsi"] < 80)
        if between_70_80.any():
            flagged = features.loc[between_70_80, "rsi_overbought_crypto"]
            assert (flagged == 0).all(), \
                "rsi_overbought_crypto triggered at RSI 70-80 — should use 80!"


class TestFeatureCountIncreased:
    """Verify new features are added without removing existing ones."""

    def test_existing_features_still_present(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        # Key existing features that must NOT be removed
        must_keep = [
            "sma_9", "sma_20", "sma_50",
            "rsi", "rsi_divergence",
            "macd", "macd_signal", "macd_hist",
            "atr", "atr_pct",
            "bb_width", "bb_position",
            "volume_ratio", "volume_zscore",
            "stoch_k", "stoch_d",
            "volatility", "trend_strength",
        ]
        missing = [f for f in must_keep if f not in features.columns]
        assert not missing, f"Existing features removed: {missing}"

    def test_new_features_count(self):
        from analysis.ml_model_v2 import MLTradingModelV2
        model = MLTradingModelV2()
        df = _make_ohlcv(120)
        features = model.prepare_features(df)
        new_scalping = [
            "ema_5", "ema_9", "ema_20",
            "ema9_ema20_crossover",
            "rsi_7",
            "stochrsi_k", "stochrsi_d",
            "rsi_overbought_crypto", "rsi_oversold_crypto",
        ]
        missing = [f for f in new_scalping if f not in features.columns]
        assert not missing, f"New scalping features missing: {missing}"
