#!/usr/bin/env python3
# Tujuan: Statistical Arbitrage (pair trading) engine untuk crypto pairs.
# Caller: signal_pipeline.py (optional layer), bot.py /statarb command.
# Dependensi: numpy, pandas, scipy (untuk cointegration test).
# Main Functions: class StatArbEngine.
# Side Effects: none; pure computation only.
"""
Statistical Arbitrage Engine
==============================
Pair trading strategy for correlated crypto pairs on Indodax:

1. Cointegration Test (Engle-Granger) — find pairs that move together
2. Spread Calculation — normalized spread between cointegrated pairs
3. Z-Score of Spread — detect when spread deviates from mean
4. Entry/Exit Signals — trade when spread is extreme, exit at mean
5. Half-life Estimation — how fast does spread revert?

Strategy:
- When spread z-score < -2.0: BUY pair A, SELL pair B (spread will revert up)
- When spread z-score > +2.0: SELL pair A, BUY pair B (spread will revert down)
- Exit when spread z-score crosses 0 (mean reversion complete)

Usage:
    from quant.stat_arb import StatArbEngine

    arb = StatArbEngine()
    arb.update_prices('btcidr', btc_prices)
    arb.update_prices('ethidr', eth_prices)

    opportunities = arb.scan_all_pairs()
    # Returns list of StatArbOpportunity with entry signals
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("crypto_bot")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Cointegration test parameters
COINT_LOOKBACK = 60            # Candles for cointegration test
COINT_PVALUE_THRESHOLD = 0.05  # p-value < 0.05 = cointegrated

# Spread z-score thresholds
SPREAD_ENTRY_Z = 2.0           # Enter when |z| > 2.0
SPREAD_EXIT_Z = 0.5            # Exit when |z| < 0.5
SPREAD_STOP_Z = 3.5            # Stop loss when |z| > 3.5 (spread diverging)

# Half-life filter
MIN_HALF_LIFE = 3              # Minimum 3 candles to revert (too fast = noise)
MAX_HALF_LIFE = 30             # Maximum 30 candles (too slow = capital inefficient)

# Minimum data
MIN_PRICES = 60                # Need at least 60 price points

# Spread calculation
SPREAD_WINDOW = 20             # Rolling window for spread z-score


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CointResult:
    """Cointegration test result for a pair."""
    pair_a: str
    pair_b: str
    is_cointegrated: bool
    p_value: float
    hedge_ratio: float         # Beta: how much of B to hedge 1 unit of A
    half_life: float           # Mean reversion speed (candles)
    correlation: float         # Price correlation

    def to_dict(self) -> Dict:
        return {
            'pair_a': self.pair_a,
            'pair_b': self.pair_b,
            'is_cointegrated': self.is_cointegrated,
            'p_value': round(self.p_value, 4),
            'hedge_ratio': round(self.hedge_ratio, 4),
            'half_life': round(self.half_life, 1),
            'correlation': round(self.correlation, 3),
        }


@dataclass
class StatArbOpportunity:
    """Statistical arbitrage trading opportunity."""
    pair_a: str                # Long/Short this pair
    pair_b: str                # Hedge with this pair
    signal: str                # 'LONG_A_SHORT_B', 'SHORT_A_LONG_B', 'EXIT', 'NONE'
    spread_z_score: float      # Current spread z-score
    hedge_ratio: float         # Hedge ratio (beta)
    half_life: float           # Expected reversion time
    confidence: float          # Signal confidence (0-1)
    expected_profit_pct: float # Expected profit when spread reverts

    def to_dict(self) -> Dict:
        return {
            'pair_a': self.pair_a,
            'pair_b': self.pair_b,
            'signal': self.signal,
            'spread_z_score': round(self.spread_z_score, 3),
            'hedge_ratio': round(self.hedge_ratio, 4),
            'half_life': round(self.half_life, 1),
            'confidence': round(self.confidence, 3),
            'expected_profit_pct': round(self.expected_profit_pct, 2),
        }


# =============================================================================
# MAIN ENGINE
# =============================================================================

class StatArbEngine:
    """
    Statistical Arbitrage Engine for crypto pair trading.
    """

    def __init__(self):
        self._price_data: Dict[str, List[float]] = {}
        self._coint_cache: Dict[str, CointResult] = {}
        logger.info("✅ Quant Statistical Arbitrage Engine initialized")

    def update_prices(self, pair: str, prices: List[float]):
        """Update price history for a pair."""
        self._price_data[pair] = prices[-200:]  # Keep last 200 prices
        # Invalidate cache for pairs involving this one
        keys_to_remove = [k for k in self._coint_cache if pair in k]
        for k in keys_to_remove:
            del self._coint_cache[k]

    def test_cointegration(self, pair_a: str, pair_b: str) -> Optional[CointResult]:
        """
        Test if two pairs are cointegrated (move together long-term).

        Uses simplified Engle-Granger method:
        1. Regress A on B to get hedge ratio
        2. Calculate spread (residuals)
        3. Test spread for stationarity (ADF test approximation)

        Returns:
            CointResult or None if insufficient data
        """
        cache_key = f"{pair_a}_{pair_b}"
        if cache_key in self._coint_cache:
            return self._coint_cache[cache_key]

        prices_a = self._price_data.get(pair_a)
        prices_b = self._price_data.get(pair_b)

        if not prices_a or not prices_b:
            return None
        if len(prices_a) < MIN_PRICES or len(prices_b) < MIN_PRICES:
            return None

        # Align lengths
        n = min(len(prices_a), len(prices_b), COINT_LOOKBACK)
        a = np.array(prices_a[-n:], dtype=float)
        b = np.array(prices_b[-n:], dtype=float)

        # Normalize prices (to make regression meaningful across different price scales)
        a_norm = a / a[0]
        b_norm = b / b[0]

        # OLS regression: A = beta * B + alpha + residual
        # hedge_ratio = beta
        try:
            beta, alpha = np.polyfit(b_norm, a_norm, 1)
        except (np.linalg.LinAlgError, ValueError):
            return None

        # Calculate spread (residuals)
        spread = a_norm - (beta * b_norm + alpha)

        # Test stationarity using simplified ADF
        # (full ADF requires statsmodels, this is a lightweight approximation)
        is_stationary, p_value = self._simplified_adf_test(spread)

        # Calculate half-life of mean reversion
        half_life = self._calculate_half_life(spread)

        # Correlation
        correlation = float(np.corrcoef(a_norm, b_norm)[0, 1])

        # Determine if cointegrated
        is_cointegrated = (
            is_stationary and
            p_value < COINT_PVALUE_THRESHOLD and
            MIN_HALF_LIFE <= half_life <= MAX_HALF_LIFE
        )

        result = CointResult(
            pair_a=pair_a,
            pair_b=pair_b,
            is_cointegrated=is_cointegrated,
            p_value=p_value,
            hedge_ratio=float(beta),
            half_life=half_life,
            correlation=correlation,
        )

        self._coint_cache[cache_key] = result

        if is_cointegrated:
            logger.info(
                f"📊 [STAT_ARB] Cointegrated: {pair_a}/{pair_b} | "
                f"p={p_value:.4f} | beta={beta:.3f} | "
                f"HL={half_life:.1f} | corr={correlation:.3f}"
            )

        return result

    def get_spread_signal(self, pair_a: str, pair_b: str) -> Optional[StatArbOpportunity]:
        """
        Get current spread signal for a cointegrated pair.

        Returns:
            StatArbOpportunity or None
        """
        coint = self.test_cointegration(pair_a, pair_b)
        if coint is None or not coint.is_cointegrated:
            return None

        prices_a = self._price_data.get(pair_a)
        prices_b = self._price_data.get(pair_b)
        if not prices_a or not prices_b:
            return None

        n = min(len(prices_a), len(prices_b), COINT_LOOKBACK)
        a = np.array(prices_a[-n:], dtype=float)
        b = np.array(prices_b[-n:], dtype=float)

        # Normalize
        a_norm = a / a[0]
        b_norm = b / b[0]

        # Calculate spread
        spread = a_norm - (coint.hedge_ratio * b_norm)

        # Z-score of spread
        spread_mean = np.mean(spread[-SPREAD_WINDOW:])
        spread_std = np.std(spread[-SPREAD_WINDOW:])

        if spread_std == 0:
            return None

        current_z = (spread[-1] - spread_mean) / spread_std

        # Determine signal
        signal = 'NONE'
        confidence = 0.0
        expected_profit = 0.0

        if current_z <= -SPREAD_ENTRY_Z:
            # Spread too low → expect reversion up
            # BUY A (undervalued), SELL B (overvalued)
            signal = 'LONG_A_SHORT_B'
            confidence = min(abs(current_z) / 3.0, 1.0)
            expected_profit = abs(current_z) * spread_std * 100  # Rough estimate

        elif current_z >= SPREAD_ENTRY_Z:
            # Spread too high → expect reversion down
            # SELL A (overvalued), BUY B (undervalued)
            signal = 'SHORT_A_LONG_B'
            confidence = min(abs(current_z) / 3.0, 1.0)
            expected_profit = abs(current_z) * spread_std * 100

        elif abs(current_z) <= SPREAD_EXIT_Z:
            signal = 'EXIT'
            confidence = 1.0 - abs(current_z)

        return StatArbOpportunity(
            pair_a=pair_a,
            pair_b=pair_b,
            signal=signal,
            spread_z_score=float(current_z),
            hedge_ratio=coint.hedge_ratio,
            half_life=coint.half_life,
            confidence=confidence,
            expected_profit_pct=expected_profit,
        )

    def scan_all_pairs(self) -> List[StatArbOpportunity]:
        """
        Scan all pair combinations for stat arb opportunities.

        Returns:
            List of opportunities sorted by confidence
        """
        pairs = list(self._price_data.keys())
        opportunities = []

        for i, pair_a in enumerate(pairs):
            for pair_b in pairs[i + 1:]:
                opp = self.get_spread_signal(pair_a, pair_b)
                if opp and opp.signal not in ('NONE', 'EXIT'):
                    opportunities.append(opp)

        # Sort by confidence (highest first)
        opportunities.sort(key=lambda x: x.confidence, reverse=True)

        if opportunities:
            logger.info(
                f"📊 [STAT_ARB] Found {len(opportunities)} opportunities "
                f"(top: {opportunities[0].pair_a}/{opportunities[0].pair_b} "
                f"z={opportunities[0].spread_z_score:+.2f})"
            )

        return opportunities

    def get_cointegrated_pairs(self) -> List[CointResult]:
        """Get all currently cointegrated pairs."""
        pairs = list(self._price_data.keys())
        results = []

        for i, pair_a in enumerate(pairs):
            for pair_b in pairs[i + 1:]:
                coint = self.test_cointegration(pair_a, pair_b)
                if coint and coint.is_cointegrated:
                    results.append(coint)

        return results

    def _simplified_adf_test(self, series: np.ndarray) -> Tuple[bool, float]:
        """
        Simplified Augmented Dickey-Fuller test approximation.

        Tests if a time series is stationary (mean-reverting).
        Uses the Dickey-Fuller regression: Δy_t = α + β*y_{t-1} + ε_t
        If β is significantly negative → stationary.

        Returns:
            (is_stationary, approximate_p_value)
        """
        if len(series) < 20:
            return False, 1.0

        # Dickey-Fuller regression
        y = series[1:]
        y_lag = series[:-1]
        dy = y - y_lag

        # OLS: dy = alpha + beta * y_lag
        n = len(dy)
        x = np.column_stack([np.ones(n), y_lag])

        try:
            # Solve normal equations
            beta_hat = np.linalg.lstsq(x, dy, rcond=None)[0]
            beta = beta_hat[1]  # Coefficient on y_lag

            # Calculate t-statistic
            residuals = dy - x @ beta_hat
            sse = np.sum(residuals ** 2)
            mse = sse / (n - 2)
            var_beta = mse * np.linalg.inv(x.T @ x)[1, 1]
            t_stat = beta / np.sqrt(var_beta) if var_beta > 0 else 0

            # Approximate p-value using critical values
            # ADF critical values (approximate): 1%=-3.43, 5%=-2.86, 10%=-2.57
            if t_stat < -3.43:
                p_value = 0.01
            elif t_stat < -2.86:
                p_value = 0.05
            elif t_stat < -2.57:
                p_value = 0.10
            elif t_stat < -1.94:
                p_value = 0.20
            else:
                p_value = 0.50

            is_stationary = t_stat < -2.86  # 5% significance

            return is_stationary, p_value

        except (np.linalg.LinAlgError, ValueError):
            return False, 1.0

    def _calculate_half_life(self, spread: np.ndarray) -> float:
        """
        Calculate half-life of mean reversion.

        Uses AR(1) model: spread_t = phi * spread_{t-1} + noise
        Half-life = -ln(2) / ln(phi)
        """
        if len(spread) < 10:
            return 999.0

        y = spread[1:]
        y_lag = spread[:-1]

        # OLS: y = phi * y_lag
        try:
            phi = np.sum(y * y_lag) / np.sum(y_lag ** 2)

            if phi <= 0 or phi >= 1:
                return 999.0

            half_life = -np.log(2) / np.log(phi)
            return float(max(0.5, min(half_life, 999.0)))

        except (ZeroDivisionError, ValueError):
            return 999.0

    def get_stats(self) -> Dict:
        """Get engine statistics."""
        cointegrated = self.get_cointegrated_pairs()
        return {
            'tracked_pairs': len(self._price_data),
            'pairs': list(self._price_data.keys()),
            'cointegrated_pairs': len(cointegrated),
            'cointegrated_list': [
                f"{c.pair_a}/{c.pair_b} (HL={c.half_life:.0f})"
                for c in cointegrated
            ],
        }
