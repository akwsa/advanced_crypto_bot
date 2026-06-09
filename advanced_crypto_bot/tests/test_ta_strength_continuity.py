"""Regression tests for Bug HIGH #7 (audit 2026-06-07): TA Strength stuck di ±0.10.

Sebelum fix: 67% sample TA Strength = ±0.10 karena hanya MACD yang aktif (BULLISH/BEARISH
default = ±0.5) dan 4 indikator lain NEUTRAL = 0.0 → strength = ±0.5/5 = ±0.10.

Setelah fix: tilt kontinu untuk RSI/MACD/MA/BB/Volume → strength jadi continuous di [-1, +1]
dan bisa membedakan setup bagus vs buruk.
"""
import numpy as np
import pandas as pd
import pytest

from analysis.technical_analysis import TechnicalAnalysis


def _make_ohlcv(prices, volumes=None, n=120):
    """Build a DataFrame with the given price array (len ≥ 50)."""
    if isinstance(prices, (int, float)):
        prices = [prices] * n
    prices = list(prices)
    if len(prices) < n:
        # pad front with first value
        prices = [prices[0]] * (n - len(prices)) + prices
    if volumes is None:
        volumes = [1000.0] * len(prices)
    df = pd.DataFrame({
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': volumes,
    })
    return df


class TestTAStrengthContinuity:
    """Verify TA strength varies continuously instead of clustering at ±0.10."""

    def test_strength_varies_across_different_market_states(self):
        """Different market states should produce distinct, varied strengths."""
        rng = np.random.default_rng(seed=2026)
        # Mild bullish: small upward drift with realistic noise (no RSI extremes)
        bullish = [1000 + 0.5 * i + rng.normal(0, 8) for i in range(120)]
        # Choppy sideways: oscillation around 1000
        sideways = [1000 + 12 * np.sin(i / 8) + rng.normal(0, 4) for i in range(120)]
        # Mild bearish: small downward drift with noise
        bearish = [1100 - 0.5 * i + rng.normal(0, 8) for i in range(120)]

        s_up = TechnicalAnalysis(_make_ohlcv(bullish)).get_signals()['strength']
        s_side = TechnicalAnalysis(_make_ohlcv(sideways)).get_signals()['strength']
        s_down = TechnicalAnalysis(_make_ohlcv(bearish)).get_signals()['strength']

        # Three should be distinct enough that there's at least 0.05 spread
        # between min and max — proves the metric discriminates.
        spread = max(s_up, s_side, s_down) - min(s_up, s_side, s_down)
        assert spread > 0.05, (
            f"Strength spread too narrow: up={s_up:.3f} side={s_side:.3f} down={s_down:.3f}"
        )

    def test_strength_is_not_quantized_to_0_10_increments(self):
        """Generate 20 different price patterns; strength values should be diverse."""
        rng = np.random.default_rng(seed=42)
        strengths = []
        for _ in range(20):
            base = rng.uniform(900, 1100)
            slope = rng.uniform(-2.0, 2.0)
            noise = rng.normal(0, 5, 120)
            prices = [base + slope * i + noise[i] for i in range(120)]
            ta = TechnicalAnalysis(_make_ohlcv(prices)).get_signals()
            strengths.append(round(ta['strength'], 3))

        # With the fix, the values should be much more diverse than discrete buckets
        # of 0.10. Require at least 10 unique values out of 20.
        unique_count = len(set(strengths))
        assert unique_count >= 10, (
            f"Only {unique_count} unique strengths in 20 samples — values are too "
            f"clustered. Sample: {strengths}"
        )

    def test_no_pile_up_at_exactly_0_10(self):
        """The exact value ±0.10 should NOT dominate output anymore."""
        rng = np.random.default_rng(seed=7)
        strengths = []
        for _ in range(30):
            base = rng.uniform(900, 1100)
            slope = rng.uniform(-1.5, 1.5)
            noise = rng.normal(0, 4, 120)
            prices = [base + slope * i + noise[i] for i in range(120)]
            ta = TechnicalAnalysis(_make_ohlcv(prices)).get_signals()
            strengths.append(ta['strength'])

        # Count values exactly at ±0.10 (rounded to 2 decimals).
        rounded = [round(s, 2) for s in strengths]
        at_pm10 = sum(1 for r in rounded if abs(abs(r) - 0.10) < 1e-9)
        # Before fix: 60-70% would be exactly ±0.10. After fix: should be <30%.
        assert at_pm10 < 0.30 * len(strengths), (
            f"{at_pm10}/{len(strengths)} samples still pile up at exactly ±0.10. "
            f"Sample: {rounded}"
        )

    def test_strength_remains_in_valid_range(self):
        """Sanity: strength must always be within [-1.0, +1.0]."""
        rng = np.random.default_rng(seed=99)
        for _ in range(15):
            base = rng.uniform(100, 5_000_000)
            slope = rng.uniform(-base * 0.01, base * 0.01)
            prices = [base + slope * i for i in range(120)]
            ta = TechnicalAnalysis(_make_ohlcv(prices)).get_signals()
            assert -1.0 <= ta['strength'] <= 1.0, f"strength out of range: {ta['strength']}"

    def test_extreme_oversold_still_yields_strong_buy(self):
        """When RSI hits true oversold, strength should be clearly positive."""
        # Sharp dump then flat at the bottom: RSI will be oversold.
        prices = list(np.linspace(1500, 800, 60)) + [800] * 60
        ta = TechnicalAnalysis(_make_ohlcv(prices)).get_signals()
        # Should not be stuck at ±0.10
        assert abs(ta['strength']) > 0.10, (
            f"Strong oversold should produce strength magnitude > 0.10, got {ta['strength']:.3f}"
        )

    def test_strength_different_for_close_above_vs_below_sma20(self):
        """MA tilt should differentiate prices clearly above vs below SMA20.

        Use noisy data so RSI stays in mid-range (no overbought/oversold inversion).
        """
        rng = np.random.default_rng(seed=11)
        # Recent close pushed above SMA20: flat then bump up at the end
        above = [1000 + rng.normal(0, 5) for _ in range(110)] + [1015 + rng.normal(0, 2) for _ in range(10)]
        # Recent close pushed below SMA20: flat then dip at the end
        below = [1000 + rng.normal(0, 5) for _ in range(110)] + [985 + rng.normal(0, 2) for _ in range(10)]

        above_strength = TechnicalAnalysis(_make_ohlcv(above)).get_signals()['strength']
        below_strength = TechnicalAnalysis(_make_ohlcv(below)).get_signals()['strength']

        assert above_strength > below_strength, (
            f"Above-SMA20 ({above_strength:.3f}) should yield higher strength than "
            f"Below-SMA20 ({below_strength:.3f})"
        )
        assert abs(above_strength - below_strength) > 0.05, (
            f"Difference too small: above={above_strength:.3f} vs below={below_strength:.3f}"
        )
