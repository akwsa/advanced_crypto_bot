#!/usr/bin/env python3
# Tujuan: Multi-timeframe momentum factor scoring untuk profit optimizer edge score.
# Caller: profit_optimizer.py, signal_pipeline.py.
# Dependensi: numpy, pandas.
# Main Functions: class MomentumFactorEngine.
# Side Effects: none; pure computation only.
"""
Momentum Factor Scoring Engine
================================
Quantitative momentum analysis:

1. Rate of Change (ROC) multi-period (5, 10, 20, 50 candles)
2. Relative Strength vs BTC (pair outperforming BTC = stronger signal)
3. Volume-Weighted Momentum (momentum confirmed by volume)
4. Momentum Acceleration (ROC of ROC — is momentum increasing?)
5. Cross-sectional momentum rank (vs other watched pairs)

Scoring:
- momentum_score: -100 to +100
- edge_bonus: 0 to +12 points for profit_optimizer edge_score
- direction: 'BULLISH', 'BEARISH', 'NEUTRAL'

Usage:
    from quant.momentum_factor import MomentumFactorEngine

    mf = MomentumFactorEngine()
    result = mf.analyze(df, pair='ethidr')
    # result.momentum_score → -100 to +100
    # result.edge_bonus → 0 to 12
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("crypto_bot")


# =============================================================================
# CONFIGURATION
# =============================================================================

# ROC periods (candles)
ROC_FAST = 5        # Very short-term momentum
ROC_MEDIUM = 10     # Short-term momentum
ROC_SLOW = 20       # Medium-term momentum
ROC_TREND = 50      # Trend momentum

# ROC weights for composite score
ROC_WEIGHT_FAST = 0.15
ROC_WEIGHT_MEDIUM = 0.30
ROC_WEIGHT_SLOW = 0.35
ROC_WEIGHT_TREND = 0.20

# Volume-weighted momentum
VOLUME_MOMENTUM_PERIOD = 10
VOLUME_MOMENTUM_WEIGHT = 0.20  # Blend into final score

# Momentum acceleration
ACCELERATION_PERIOD = 5  # ROC of ROC lookback

# Edge bonus thresholds
EDGE_STRONG_MOMENTUM = 60    # Score > 60 → strong bonus
EDGE_MODERATE_MOMENTUM = 30  # Score > 30 → moderate bonus
EDGE_BONUS_STRONG = 10       # Points added to edge_score
EDGE_BONUS_MODERATE = 5      # Points added to edge_score

# Minimum data
MIN_CANDLES = 55  # Need at least ROC_TREND + 5


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MomentumResult:
    """Result from momentum factor analysis."""
    # ROC values (percentage)
    roc_fast: float           # 5-period ROC %
    roc_medium: float         # 10-period ROC %
    roc_slow: float           # 20-period ROC %
    roc_trend: float          # 50-period ROC %

    # Composite scores
    momentum_score: float     # -100 to +100 composite
    volume_momentum: float    # Volume-weighted momentum
    acceleration: float       # Momentum acceleration (ROC of ROC)

    # Signal output
    direction: str            # 'BULLISH', 'BEARISH', 'NEUTRAL'
    edge_bonus: float         # 0 to 12 points for profit_optimizer
    strength: str             # 'STRONG', 'MODERATE', 'WEAK', 'NEUTRAL'

    def to_dict(self) -> Dict:
        return {
            'roc_fast': round(self.roc_fast, 3),
            'roc_medium': round(self.roc_medium, 3),
            'roc_slow': round(self.roc_slow, 3),
            'roc_trend': round(self.roc_trend, 3),
            'momentum_score': round(self.momentum_score, 2),
            'volume_momentum': round(self.volume_momentum, 3),
            'acceleration': round(self.acceleration, 3),
            'momentum_direction': self.direction,
            'momentum_edge_bonus': round(self.edge_bonus, 1),
            'momentum_strength': self.strength,
        }


# =============================================================================
# MAIN ENGINE
# =============================================================================

class MomentumFactorEngine:
    """
    Multi-timeframe momentum factor scoring.
    """

    def __init__(self):
        self._pair_scores: Dict[str, float] = {}  # Cache for cross-sectional ranking
        logger.info("✅ Quant Momentum Factor Engine initialized")

    def analyze(
        self,
        df: pd.DataFrame,
        pair: str = "UNKNOWN",
        btc_df: Optional[pd.DataFrame] = None,
    ) -> Optional[MomentumResult]:
        """
        Perform momentum factor analysis.

        Args:
            df: DataFrame with 'close' and optionally 'volume' columns
            pair: Trading pair name
            btc_df: Optional BTC price DataFrame for relative strength

        Returns:
            MomentumResult or None if insufficient data
        """
        if df is None or len(df) < MIN_CANDLES:
            logger.debug(f"[MOMENTUM] {pair}: Insufficient data ({len(df) if df is not None else 0})")
            return None

        try:
            close = df['close'].astype(float)

            # Calculate multi-period ROC
            roc_fast = self._roc(close, ROC_FAST)
            roc_medium = self._roc(close, ROC_MEDIUM)
            roc_slow = self._roc(close, ROC_SLOW)
            roc_trend = self._roc(close, ROC_TREND)

            # Weighted composite momentum score
            raw_score = (
                roc_fast * ROC_WEIGHT_FAST +
                roc_medium * ROC_WEIGHT_MEDIUM +
                roc_slow * ROC_WEIGHT_SLOW +
                roc_trend * ROC_WEIGHT_TREND
            )

            # Normalize to -100 to +100 range (using tanh-like scaling)
            momentum_score = self._normalize_score(raw_score)

            # Volume-weighted momentum
            vol_momentum = 0.0
            if 'volume' in df.columns:
                vol_momentum = self._volume_weighted_momentum(df)
                # Blend volume momentum into score
                momentum_score = (
                    momentum_score * (1 - VOLUME_MOMENTUM_WEIGHT) +
                    self._normalize_score(vol_momentum) * VOLUME_MOMENTUM_WEIGHT
                )

            # Momentum acceleration (is momentum increasing or decreasing?)
            acceleration = self._momentum_acceleration(close)

            # Relative strength vs BTC (if available)
            if btc_df is not None and len(btc_df) >= MIN_CANDLES:
                rs_bonus = self._relative_strength_vs_btc(close, btc_df['close'].astype(float))
                momentum_score += rs_bonus  # Can add up to ±10

            # Clamp final score
            momentum_score = float(np.clip(momentum_score, -100, 100))

            # Determine direction and edge bonus
            direction, edge_bonus, strength = self._score_to_signal(momentum_score, acceleration)

            result = MomentumResult(
                roc_fast=roc_fast,
                roc_medium=roc_medium,
                roc_slow=roc_slow,
                roc_trend=roc_trend,
                momentum_score=momentum_score,
                volume_momentum=vol_momentum,
                acceleration=acceleration,
                direction=direction,
                edge_bonus=edge_bonus,
                strength=strength,
            )

            # Cache for cross-sectional ranking
            self._pair_scores[pair] = momentum_score

            if abs(momentum_score) > 20:
                logger.info(
                    f"📊 [MOMENTUM] {pair}: score={momentum_score:+.1f} | "
                    f"dir={direction} | edge=+{edge_bonus:.0f} | "
                    f"roc_m={roc_medium:+.2f}% | accel={acceleration:+.3f}"
                )

            return result

        except Exception as e:
            logger.warning(f"⚠️ [MOMENTUM] {pair}: Analysis failed: {e}")
            return None

    def _roc(self, close: pd.Series, period: int) -> float:
        """Calculate Rate of Change (percentage)."""
        if len(close) <= period:
            return 0.0
        current = close.iloc[-1]
        past = close.iloc[-period - 1]
        if past == 0:
            return 0.0
        return float(((current - past) / past) * 100)

    def _normalize_score(self, raw: float) -> float:
        """Normalize raw ROC/momentum to -100 to +100 using sigmoid-like scaling."""
        # Use tanh scaling: maps any value to (-100, +100)
        # Scale factor: 10% ROC → ~76 score, 5% → ~46, 2% → ~20
        return float(np.tanh(raw / 10.0) * 100)

    def _volume_weighted_momentum(self, df: pd.DataFrame) -> float:
        """Calculate volume-weighted price momentum."""
        period = min(VOLUME_MOMENTUM_PERIOD, len(df) - 1)
        if period < 3:
            return 0.0

        close = df['close'].iloc[-period:].astype(float)
        volume = df['volume'].iloc[-period:].astype(float)

        if volume.sum() == 0:
            return 0.0

        # Price changes weighted by volume
        pct_changes = close.pct_change().dropna()
        vol_weights = volume.iloc[1:] / volume.iloc[1:].sum()

        if len(pct_changes) != len(vol_weights):
            min_len = min(len(pct_changes), len(vol_weights))
            pct_changes = pct_changes.iloc[:min_len]
            vol_weights = vol_weights.iloc[:min_len]

        vw_momentum = float((pct_changes.values * vol_weights.values).sum() * 100)
        return vw_momentum

    def _momentum_acceleration(self, close: pd.Series) -> float:
        """Calculate momentum acceleration (ROC of ROC)."""
        period = ACCELERATION_PERIOD
        if len(close) < period * 2 + 2:
            return 0.0

        # Current ROC
        current_roc = self._roc(close, period)
        # Previous ROC (shifted by period)
        prev_close = close.iloc[:-period]
        prev_roc = self._roc(prev_close, period)

        # Acceleration = change in ROC
        return current_roc - prev_roc

    def _relative_strength_vs_btc(self, pair_close: pd.Series, btc_close: pd.Series) -> float:
        """
        Calculate relative strength vs BTC.
        If pair outperforms BTC → positive bonus.
        """
        period = 20
        if len(pair_close) < period + 1 or len(btc_close) < period + 1:
            return 0.0

        pair_roc = self._roc(pair_close, period)
        btc_roc = self._roc(btc_close, period)

        # Relative strength: pair ROC - BTC ROC
        rs = pair_roc - btc_roc

        # Cap bonus at ±10
        return float(np.clip(rs * 2, -10, 10))

    def _score_to_signal(self, score: float, acceleration: float) -> tuple:
        """Convert momentum score to direction, edge bonus, and strength."""
        # Strong bullish momentum
        if score >= EDGE_STRONG_MOMENTUM:
            direction = 'BULLISH'
            edge_bonus = EDGE_BONUS_STRONG
            # Extra bonus if accelerating
            if acceleration > 0.5:
                edge_bonus += 2
            strength = 'STRONG'

        # Moderate bullish
        elif score >= EDGE_MODERATE_MOMENTUM:
            direction = 'BULLISH'
            edge_bonus = EDGE_BONUS_MODERATE
            strength = 'MODERATE'

        # Strong bearish
        elif score <= -EDGE_STRONG_MOMENTUM:
            direction = 'BEARISH'
            edge_bonus = EDGE_BONUS_STRONG  # Bonus for SELL signals
            if acceleration < -0.5:
                edge_bonus += 2
            strength = 'STRONG'

        # Moderate bearish
        elif score <= -EDGE_MODERATE_MOMENTUM:
            direction = 'BEARISH'
            edge_bonus = EDGE_BONUS_MODERATE
            strength = 'MODERATE'

        # Neutral
        else:
            direction = 'NEUTRAL'
            edge_bonus = 0
            strength = 'NEUTRAL' if abs(score) < 10 else 'WEAK'

        return direction, edge_bonus, strength

    def get_momentum_ranking(self) -> List[Dict]:
        """Get all pairs ranked by momentum score (for cross-sectional analysis)."""
        ranking = sorted(
            self._pair_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [{'pair': pair, 'momentum_score': score} for pair, score in ranking]
