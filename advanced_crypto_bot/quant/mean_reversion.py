#!/usr/bin/env python3
# Tujuan: Z-Score Mean Reversion engine untuk signal scoring dan confluence boost.
# Caller: signal_pipeline.py, signal_quality_engine.py.
# Dependensi: numpy, pandas (sudah ada di project).
# Main Functions: class MeanReversionEngine.
# Side Effects: none; pure computation only.
"""
Z-Score Mean Reversion Module
==============================
Quantitative mean reversion scoring menggunakan:
- Z-Score dari harga vs rolling mean (multiple lookback periods)
- Bollinger Band %B normalization
- RSI deviation scoring
- VWAP deviation (jika data volume tersedia)
- Multi-timeframe z-score consensus

Scoring System:
- z_score < -2.0 → Strong mean reversion BUY signal (+2 confluence)
- z_score < -1.5 → Moderate mean reversion BUY signal (+1 confluence)
- z_score > +2.0 → Strong mean reversion SELL signal (+2 confluence)
- z_score > +1.5 → Moderate mean reversion SELL signal (+1 confluence)
- |z_score| < 0.5 → Neutral (no confluence bonus)

Usage:
    from quant.mean_reversion import MeanReversionEngine

    mr = MeanReversionEngine()
    result = mr.analyze(df, current_price=1500000)

    # result.z_score → float (-3.0 to +3.0 typical)
    # result.signal → 'STRONG_BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG_SELL'
    # result.confluence_bonus → int (0, 1, or 2)
    # result.confidence_boost → float (0.0 to 0.05)
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("crypto_bot")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Z-Score lookback periods (candles) — multi-timeframe approach
ZSCORE_FAST_PERIOD = 20      # Short-term mean reversion (fast)
ZSCORE_MEDIUM_PERIOD = 50    # Medium-term mean reversion
ZSCORE_SLOW_PERIOD = 100     # Long-term mean reversion (slow)

# Z-Score thresholds for signal generation
ZSCORE_STRONG_BUY = -2.0     # Extreme oversold → strong mean reversion BUY
ZSCORE_BUY = -1.5            # Moderate oversold → mean reversion BUY
ZSCORE_SELL = 1.5            # Moderate overbought → mean reversion SELL
ZSCORE_STRONG_SELL = 2.0     # Extreme overbought → strong mean reversion SELL
ZSCORE_NEUTRAL_BAND = 0.5    # Inside this band = no signal

# Confluence bonus points
CONFLUENCE_STRONG = 2        # Strong z-score adds 2 points
CONFLUENCE_MODERATE = 1      # Moderate z-score adds 1 point

# Confidence boost for signal enhancement
CONFIDENCE_BOOST_STRONG = 0.04   # +4% confidence for strong mean reversion
CONFIDENCE_BOOST_MODERATE = 0.02  # +2% confidence for moderate mean reversion

# Multi-timeframe weights
WEIGHT_FAST = 0.50           # 50% weight to fast z-score (most responsive)
WEIGHT_MEDIUM = 0.30         # 30% weight to medium z-score
WEIGHT_SLOW = 0.20           # 20% weight to slow z-score (trend context)

# Bollinger %B integration
BB_PERIOD = 20
BB_STD = 2.0
BB_EXTREME_LOW = 0.0         # %B <= 0 = below lower band
BB_EXTREME_HIGH = 1.0        # %B >= 1 = above upper band

# Volume-weighted mean reversion (VWAP deviation)
VWAP_ENABLED = True
VWAP_ZSCORE_WEIGHT = 0.15   # Additional weight for VWAP z-score

# Minimum data requirement
MIN_CANDLES_REQUIRED = 60    # Need at least 60 candles for reliable z-score


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MeanReversionResult:
    """Result dari mean reversion analysis."""
    # Core z-scores
    z_score_fast: float          # Z-score period 20
    z_score_medium: float        # Z-score period 50
    z_score_slow: float          # Z-score period 100
    z_score_composite: float     # Weighted composite z-score

    # Bollinger %B
    bb_pct_b: float              # Bollinger %B (0-1, bisa di luar range)

    # VWAP deviation
    vwap_z_score: Optional[float]  # Z-score dari VWAP (None jika no volume data)

    # Signal output
    signal: str                  # 'STRONG_BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG_SELL'
    confluence_bonus: int        # 0, 1, or 2 points to add to confluence score
    confidence_boost: float      # 0.0 to 0.05 boost to ML confidence

    # Metadata
    mean_price: float            # Rolling mean price used
    std_price: float             # Rolling std used
    current_price: float         # Current price analyzed
    regime_alignment: bool       # True if z-score aligns with market regime

    @property
    def is_actionable(self) -> bool:
        """Return True if z-score suggests actionable mean reversion."""
        return self.signal != 'NEUTRAL'

    @property
    def direction(self) -> str:
        """Return 'BUY', 'SELL', or 'NEUTRAL'."""
        if self.signal in ('STRONG_BUY', 'BUY'):
            return 'BUY'
        elif self.signal in ('STRONG_SELL', 'SELL'):
            return 'SELL'
        return 'NEUTRAL'

    def to_dict(self) -> Dict:
        """Convert to dict for signal enrichment."""
        return {
            'z_score_fast': round(self.z_score_fast, 3),
            'z_score_medium': round(self.z_score_medium, 3),
            'z_score_slow': round(self.z_score_slow, 3),
            'z_score_composite': round(self.z_score_composite, 3),
            'bb_pct_b': round(self.bb_pct_b, 3),
            'vwap_z_score': round(self.vwap_z_score, 3) if self.vwap_z_score is not None else None,
            'mr_signal': self.signal,
            'mr_confluence_bonus': self.confluence_bonus,
            'mr_confidence_boost': round(self.confidence_boost, 4),
            'mr_regime_alignment': self.regime_alignment,
        }


# =============================================================================
# MAIN ENGINE
# =============================================================================

class MeanReversionEngine:
    """
    Quantitative Mean Reversion Engine.

    Computes multi-timeframe z-scores and generates confluence bonuses
    for the signal quality engine.
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize with optional config overrides."""
        self.config = config or {}
        self._stats_cache: Dict[str, Dict] = {}  # Per-pair stats cache
        logger.info("✅ Quant Mean Reversion Engine initialized")

    def analyze(
        self,
        df: pd.DataFrame,
        current_price: Optional[float] = None,
        pair: str = "UNKNOWN",
        market_regime: str = "UNKNOWN",
    ) -> Optional[MeanReversionResult]:
        """
        Perform full mean reversion analysis on price data.

        Args:
            df: DataFrame with at least 'close' column (and optionally 'volume', 'high', 'low')
            current_price: Current real-time price (uses last close if None)
            pair: Trading pair name for logging
            market_regime: Current market regime ('TRENDING_UP', 'TRENDING_DOWN', 'RANGING', etc.)

        Returns:
            MeanReversionResult or None if insufficient data
        """
        if df is None or len(df) < MIN_CANDLES_REQUIRED:
            logger.debug(f"[MEAN_REV] {pair}: Insufficient data ({len(df) if df is not None else 0} < {MIN_CANDLES_REQUIRED})")
            return None

        try:
            close = df['close'].astype(float)
            price = current_price if current_price is not None else float(close.iloc[-1])

            # Calculate multi-timeframe z-scores
            z_fast = self._calculate_z_score(close, ZSCORE_FAST_PERIOD)
            z_medium = self._calculate_z_score(close, ZSCORE_MEDIUM_PERIOD)
            z_slow = self._calculate_z_score(close, ZSCORE_SLOW_PERIOD)

            # Weighted composite z-score
            z_composite = (
                z_fast * WEIGHT_FAST +
                z_medium * WEIGHT_MEDIUM +
                z_slow * WEIGHT_SLOW
            )

            # Bollinger %B
            bb_pct_b = self._calculate_bollinger_pct_b(close)

            # VWAP z-score (if volume data available)
            vwap_z = None
            if VWAP_ENABLED and 'volume' in df.columns:
                vwap_z = self._calculate_vwap_z_score(df, price)
                if vwap_z is not None:
                    # Blend VWAP z-score into composite
                    z_composite = z_composite * (1 - VWAP_ZSCORE_WEIGHT) + vwap_z * VWAP_ZSCORE_WEIGHT

            # Determine signal and bonuses
            signal, confluence_bonus, confidence_boost = self._score_z_signal(z_composite, bb_pct_b)

            # Check regime alignment
            regime_alignment = self._check_regime_alignment(signal, market_regime)

            # If regime is counter to mean reversion signal, reduce bonus
            if not regime_alignment and confluence_bonus > 0:
                # Don't penalize, but don't give full bonus in strong trends
                if market_regime in ('TRENDING_UP', 'TRENDING_DOWN'):
                    confluence_bonus = max(0, confluence_bonus - 1)
                    confidence_boost *= 0.5
                    logger.info(
                        f"📉 [MEAN_REV] {pair}: Regime {market_regime} opposes MR signal {signal}, "
                        f"reduced bonus to {confluence_bonus}"
                    )

            # Get mean/std for metadata
            period = ZSCORE_FAST_PERIOD
            mean_price = float(close.rolling(period).mean().iloc[-1])
            std_price = float(close.rolling(period).std().iloc[-1])

            result = MeanReversionResult(
                z_score_fast=z_fast,
                z_score_medium=z_medium,
                z_score_slow=z_slow,
                z_score_composite=z_composite,
                bb_pct_b=bb_pct_b,
                vwap_z_score=vwap_z,
                signal=signal,
                confluence_bonus=confluence_bonus,
                confidence_boost=confidence_boost,
                mean_price=mean_price,
                std_price=std_price,
                current_price=price,
                regime_alignment=regime_alignment,
            )

            # Log result
            if result.is_actionable:
                logger.info(
                    f"📊 [MEAN_REV] {pair}: z_composite={z_composite:+.2f} | "
                    f"signal={signal} | bonus=+{confluence_bonus} | "
                    f"bb%b={bb_pct_b:.2f} | regime_align={regime_alignment}"
                )
            else:
                logger.debug(
                    f"[MEAN_REV] {pair}: z_composite={z_composite:+.2f} (neutral)"
                )

            # Cache stats for pair
            self._stats_cache[pair] = {
                'z_composite': z_composite,
                'signal': signal,
                'timestamp': pd.Timestamp.now(),
            }

            return result

        except Exception as e:
            logger.warning(f"⚠️ [MEAN_REV] {pair}: Analysis failed: {e}")
            return None

    def _calculate_z_score(self, close: pd.Series, period: int) -> float:
        """
        Calculate z-score of current price vs rolling mean/std.

        Z = (price - mean) / std

        Positive z → price above mean (overbought)
        Negative z → price below mean (oversold)
        """
        if len(close) < period:
            return 0.0

        rolling_mean = close.rolling(period).mean()
        rolling_std = close.rolling(period).std()

        mean_val = rolling_mean.iloc[-1]
        std_val = rolling_std.iloc[-1]

        if pd.isna(mean_val) or pd.isna(std_val) or std_val == 0:
            return 0.0

        current = close.iloc[-1]
        z_score = (current - mean_val) / std_val

        # Clamp to reasonable range to avoid extreme outliers
        return float(np.clip(z_score, -4.0, 4.0))

    def _calculate_bollinger_pct_b(self, close: pd.Series) -> float:
        """
        Calculate Bollinger %B indicator.

        %B = (Price - Lower Band) / (Upper Band - Lower Band)

        %B < 0 → below lower band (extreme oversold)
        %B > 1 → above upper band (extreme overbought)
        %B = 0.5 → at middle band (neutral)
        """
        if len(close) < BB_PERIOD:
            return 0.5  # Neutral default

        sma = close.rolling(BB_PERIOD).mean()
        std = close.rolling(BB_PERIOD).std()

        upper = sma + (BB_STD * std)
        lower = sma - (BB_STD * std)

        upper_val = upper.iloc[-1]
        lower_val = lower.iloc[-1]

        if pd.isna(upper_val) or pd.isna(lower_val):
            return 0.5

        band_width = upper_val - lower_val
        if band_width <= 0:
            return 0.5

        current = close.iloc[-1]
        pct_b = (current - lower_val) / band_width

        return float(np.clip(pct_b, -0.5, 1.5))

    def _calculate_vwap_z_score(self, df: pd.DataFrame, current_price: float) -> Optional[float]:
        """
        Calculate z-score of price deviation from VWAP.

        VWAP = cumsum(price * volume) / cumsum(volume)
        Z = (price - VWAP) / std(price - VWAP)
        """
        try:
            if 'volume' not in df.columns or len(df) < 20:
                return None

            close = df['close'].astype(float)
            volume = df['volume'].astype(float)

            # Skip if volume is all zeros
            if volume.sum() == 0:
                return None

            # Calculate rolling VWAP (last 20 candles)
            period = min(20, len(df))
            recent_close = close.iloc[-period:]
            recent_volume = volume.iloc[-period:]

            # Typical price (use close as proxy if high/low not reliable)
            if 'high' in df.columns and 'low' in df.columns:
                typical = (df['high'].iloc[-period:].astype(float) +
                          df['low'].iloc[-period:].astype(float) +
                          recent_close) / 3
            else:
                typical = recent_close

            cum_vol = recent_volume.cumsum()
            cum_tp_vol = (typical * recent_volume).cumsum()

            # Avoid division by zero
            if cum_vol.iloc[-1] == 0:
                return None

            vwap = cum_tp_vol.iloc[-1] / cum_vol.iloc[-1]

            # Calculate deviation std
            deviations = recent_close - vwap
            dev_std = deviations.std()

            if dev_std == 0 or pd.isna(dev_std):
                return None

            vwap_z = (current_price - vwap) / dev_std
            return float(np.clip(vwap_z, -4.0, 4.0))

        except Exception as e:
            logger.debug(f"[MEAN_REV] VWAP z-score calculation failed: {e}")
            return None

    def _score_z_signal(
        self,
        z_composite: float,
        bb_pct_b: float,
    ) -> Tuple[str, int, float]:
        """
        Score the z-score into signal, confluence bonus, and confidence boost.

        Uses both z-score and Bollinger %B for confirmation.

        Returns:
            (signal, confluence_bonus, confidence_boost)
        """
        # Strong BUY: z < -2.0 AND %B confirms oversold
        if z_composite <= ZSCORE_STRONG_BUY:
            if bb_pct_b <= 0.15:  # %B near/below lower band confirms
                return 'STRONG_BUY', CONFLUENCE_STRONG, CONFIDENCE_BOOST_STRONG
            else:
                # Z-score extreme but BB doesn't fully confirm → moderate
                return 'BUY', CONFLUENCE_MODERATE, CONFIDENCE_BOOST_MODERATE

        # Moderate BUY: z < -1.5
        elif z_composite <= ZSCORE_BUY:
            if bb_pct_b <= 0.30:  # %B in lower region confirms
                return 'BUY', CONFLUENCE_MODERATE, CONFIDENCE_BOOST_MODERATE
            else:
                return 'BUY', CONFLUENCE_MODERATE, CONFIDENCE_BOOST_MODERATE * 0.5

        # Strong SELL: z > +2.0 AND %B confirms overbought
        elif z_composite >= ZSCORE_STRONG_SELL:
            if bb_pct_b >= 0.85:  # %B near/above upper band confirms
                return 'STRONG_SELL', CONFLUENCE_STRONG, CONFIDENCE_BOOST_STRONG
            else:
                return 'SELL', CONFLUENCE_MODERATE, CONFIDENCE_BOOST_MODERATE

        # Moderate SELL: z > +1.5
        elif z_composite >= ZSCORE_SELL:
            if bb_pct_b >= 0.70:  # %B in upper region confirms
                return 'SELL', CONFLUENCE_MODERATE, CONFIDENCE_BOOST_MODERATE
            else:
                return 'SELL', CONFLUENCE_MODERATE, CONFIDENCE_BOOST_MODERATE * 0.5

        # Neutral zone
        return 'NEUTRAL', 0, 0.0

    def _check_regime_alignment(self, mr_signal: str, market_regime: str) -> bool:
        """
        Check if mean reversion signal aligns with market regime.

        Mean reversion works best in RANGING markets.
        In strong trends, mean reversion signals can be false (trend continuation).

        Returns:
            True if signal is aligned (safe to use full bonus)
        """
        if market_regime == 'RANGING':
            # Mean reversion is ideal in ranging markets
            return True

        if market_regime == 'TRENDING_UP':
            # In uptrend, BUY mean reversion (dip buying) is aligned
            # SELL mean reversion is counter-trend (risky)
            return mr_signal in ('BUY', 'STRONG_BUY', 'NEUTRAL')

        if market_regime == 'TRENDING_DOWN':
            # In downtrend, SELL mean reversion (rally selling) is aligned
            # BUY mean reversion is counter-trend (risky)
            return mr_signal in ('SELL', 'STRONG_SELL', 'NEUTRAL')

        # VOLATILE or UNKNOWN — be cautious
        return mr_signal == 'NEUTRAL'

    def get_pair_stats(self, pair: str) -> Optional[Dict]:
        """Get cached stats for a pair (for display/logging)."""
        return self._stats_cache.get(pair)

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get all cached pair stats."""
        return self._stats_cache.copy()
