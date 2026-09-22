#!/usr/bin/env python3
# Tujuan: Bayesian Kelly Criterion position sizing dengan per-pair adaptive learning.
# Caller: trading_engine.py calculate_position_size.
# Dependensi: numpy (sudah ada di project).
# Main Functions: class BayesianKellyEngine.
# Side Effects: none; pure computation only (state in-memory).
"""
Bayesian Kelly Criterion Position Sizing
==========================================
Improvement dari simple Kelly yang sudah ada di trading_engine:

1. Per-pair win rate tracking (bukan global)
2. Exponential decay weighting (recent trades lebih penting)
3. Bayesian prior (mulai dari conservative, update seiring data)
4. Confidence-adjusted Kelly (scale by ML confidence)
5. Volatility-adjusted Kelly (reduce size in high vol)
6. Drawdown-aware Kelly (reduce size saat drawdown)

Formula:
    Kelly% = W - (1-W)/R
    Bayesian Kelly% = Kelly% * confidence_factor * volatility_factor * drawdown_factor
    Final = Fractional Kelly (25-50% of full Kelly)

Usage:
    from quant.bayesian_kelly import BayesianKellyEngine

    kelly = BayesianKellyEngine()
    kelly.update_trade_outcome('btcidr', won=True, pnl_pct=3.5)
    kelly.update_trade_outcome('btcidr', won=False, pnl_pct=-1.8)

    result = kelly.calculate_position_size(
        pair='btcidr',
        balance=10_000_000,
        entry_price=1_500_000,
        ml_confidence=0.75,
        volatility_pct=2.5,
        current_drawdown_pct=5.0,
    )
    # result.position_value → IDR amount to allocate
    # result.kelly_fraction → fraction of balance
"""

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("crypto_bot")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Bayesian prior (start conservative before enough data)
PRIOR_WIN_RATE = 0.50          # Assume 50% win rate initially
PRIOR_WEIGHT = 10              # Equivalent to 10 "virtual" trades of prior
MIN_TRADES_FOR_KELLY = 5       # Need at least 5 real trades before using Kelly

# Exponential decay for recent trade weighting
DECAY_FACTOR = 0.92            # Each older trade weighted 92% of the next
MAX_TRADE_HISTORY = 100        # Keep last 100 trades per pair

# Kelly fraction (safety)
KELLY_FRACTION_MIN = 0.25      # Minimum fraction of Kelly to use
KELLY_FRACTION_MAX = 0.50      # Maximum fraction of Kelly to use
KELLY_MAX_ALLOCATION = 0.25    # Never allocate more than 25% of balance

# Confidence scaling
CONFIDENCE_SCALE_MIN = 0.5     # At 50% ML confidence → 50% of Kelly
CONFIDENCE_SCALE_MAX = 1.0     # At 90%+ ML confidence → 100% of Kelly
CONFIDENCE_THRESHOLD = 0.60    # Below this → use minimum allocation

# Volatility adjustment
VOL_LOW_THRESHOLD = 1.5        # Below this = low vol (full Kelly)
VOL_HIGH_THRESHOLD = 4.0       # Above this = high vol (minimum Kelly)

# Drawdown adjustment
DRAWDOWN_REDUCE_START = 5.0    # Start reducing at 5% drawdown
DRAWDOWN_REDUCE_MAX = 15.0     # Maximum reduction at 15% drawdown
DRAWDOWN_MIN_FACTOR = 0.25     # At max drawdown, use 25% of Kelly


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TradeOutcome:
    """Single trade outcome for Kelly calculation."""
    won: bool
    pnl_pct: float             # Profit/loss percentage
    timestamp: float = 0.0     # Unix timestamp (for decay)


@dataclass
class KellyResult:
    """Result from Bayesian Kelly position sizing."""
    pair: str
    position_value: float       # IDR amount to allocate
    position_amount: float      # Coin amount (value / price)
    kelly_fraction: float       # Final fraction of balance (0.0 to 0.25)

    # Components
    raw_kelly_pct: float        # Raw Kelly % before adjustments
    bayesian_win_rate: float    # Bayesian-adjusted win rate
    win_loss_ratio: float       # Average win / average loss
    confidence_factor: float    # ML confidence scaling (0.5 to 1.0)
    volatility_factor: float    # Volatility scaling (0.25 to 1.0)
    drawdown_factor: float      # Drawdown scaling (0.25 to 1.0)

    # Metadata
    total_trades: int           # Number of trades used
    effective_trades: float     # Decay-weighted effective sample size
    method: str                 # 'bayesian_kelly', 'prior_only', 'fixed_fallback'

    def to_dict(self) -> Dict:
        return {
            'pair': self.pair,
            'position_value': round(self.position_value, 0),
            'kelly_fraction': round(self.kelly_fraction, 4),
            'raw_kelly_pct': round(self.raw_kelly_pct, 4),
            'bayesian_win_rate': round(self.bayesian_win_rate, 4),
            'win_loss_ratio': round(self.win_loss_ratio, 3),
            'confidence_factor': round(self.confidence_factor, 3),
            'volatility_factor': round(self.volatility_factor, 3),
            'drawdown_factor': round(self.drawdown_factor, 3),
            'total_trades': self.total_trades,
            'method': self.method,
        }


# =============================================================================
# MAIN ENGINE
# =============================================================================

class BayesianKellyEngine:
    """
    Bayesian Kelly Criterion with per-pair adaptive learning.
    """

    def __init__(self):
        # Per-pair trade history
        self._trade_history: Dict[str, List[TradeOutcome]] = defaultdict(list)
        # Global trade history (for pairs with insufficient data)
        self._global_history: List[TradeOutcome] = []
        logger.info("✅ Quant Bayesian Kelly Engine initialized")

    def update_trade_outcome(self, pair: str, won: bool, pnl_pct: float):
        """
        Record a trade outcome for Kelly calculation.

        Args:
            pair: Trading pair (e.g., 'btcidr')
            won: True if trade was profitable
            pnl_pct: Profit/loss percentage (e.g., 3.5 for +3.5%, -1.8 for -1.8%)
        """
        import time
        outcome = TradeOutcome(won=won, pnl_pct=pnl_pct, timestamp=time.time())

        # Add to pair history
        self._trade_history[pair].append(outcome)
        if len(self._trade_history[pair]) > MAX_TRADE_HISTORY:
            self._trade_history[pair] = self._trade_history[pair][-MAX_TRADE_HISTORY:]

        # Add to global history
        self._global_history.append(outcome)
        if len(self._global_history) > MAX_TRADE_HISTORY * 3:
            self._global_history = self._global_history[-(MAX_TRADE_HISTORY * 3):]

        logger.debug(
            f"[KELLY] {pair}: Recorded {'WIN' if won else 'LOSS'} {pnl_pct:+.2f}% "
            f"(total: {len(self._trade_history[pair])} trades)"
        )

    def calculate_position_size(
        self,
        pair: str,
        balance: float,
        entry_price: float,
        ml_confidence: float = 0.65,
        volatility_pct: float = 2.0,
        current_drawdown_pct: float = 0.0,
        max_position_pct: float = None,
    ) -> KellyResult:
        """
        Calculate optimal position size using Bayesian Kelly.

        Args:
            pair: Trading pair
            balance: Available balance (IDR)
            entry_price: Entry price per unit
            ml_confidence: ML model confidence (0.0 to 1.0)
            volatility_pct: Current ATR as % of price
            current_drawdown_pct: Current drawdown from peak (0-100)
            max_position_pct: Override max position % (default from config)

        Returns:
            KellyResult with position sizing details
        """
        if balance <= 0 or entry_price <= 0:
            return self._empty_result(pair, 'invalid_input')

        max_alloc = max_position_pct if max_position_pct else KELLY_MAX_ALLOCATION

        # Get trade history (pair-specific or global fallback)
        pair_trades = self._trade_history.get(pair, [])
        use_global = len(pair_trades) < MIN_TRADES_FOR_KELLY

        if use_global and len(self._global_history) >= MIN_TRADES_FOR_KELLY:
            trades = self._global_history
            method = 'bayesian_kelly_global'
        elif not use_global:
            trades = pair_trades
            method = 'bayesian_kelly'
        else:
            # Not enough data anywhere → use prior only
            return self._prior_only_result(pair, balance, entry_price, ml_confidence, max_alloc)

        # Calculate Bayesian win rate with exponential decay
        bayesian_wr, effective_n = self._bayesian_win_rate(trades)

        # Calculate win/loss ratio with decay
        wl_ratio = self._decay_weighted_wl_ratio(trades)

        # Raw Kelly calculation
        if wl_ratio <= 0:
            raw_kelly = 0.0
        else:
            raw_kelly = bayesian_wr - ((1 - bayesian_wr) / wl_ratio)

        # Clamp raw Kelly
        raw_kelly = max(0.0, min(raw_kelly, 0.50))

        # If Kelly says don't bet (negative edge), use minimum
        if raw_kelly <= 0.01:
            return self._empty_result(pair, 'negative_edge')

        # Apply adjustment factors
        conf_factor = self._confidence_factor(ml_confidence)
        vol_factor = self._volatility_factor(volatility_pct)
        dd_factor = self._drawdown_factor(current_drawdown_pct)

        # Fractional Kelly with adjustments
        fraction_base = KELLY_FRACTION_MIN + (
            (KELLY_FRACTION_MAX - KELLY_FRACTION_MIN) *
            min(effective_n / 30.0, 1.0)  # More data → closer to max fraction
        )

        kelly_fraction = raw_kelly * fraction_base * conf_factor * vol_factor * dd_factor

        # Cap at maximum allocation
        kelly_fraction = min(kelly_fraction, max_alloc)

        # Calculate position
        position_value = balance * kelly_fraction
        position_amount = position_value / entry_price

        result = KellyResult(
            pair=pair,
            position_value=position_value,
            position_amount=position_amount,
            kelly_fraction=kelly_fraction,
            raw_kelly_pct=raw_kelly,
            bayesian_win_rate=bayesian_wr,
            win_loss_ratio=wl_ratio,
            confidence_factor=conf_factor,
            volatility_factor=vol_factor,
            drawdown_factor=dd_factor,
            total_trades=len(trades),
            effective_trades=effective_n,
            method=method,
        )

        logger.info(
            f"📊 [KELLY] {pair}: fraction={kelly_fraction:.1%} | "
            f"raw_kelly={raw_kelly:.1%} | wr={bayesian_wr:.1%} | "
            f"wl_ratio={wl_ratio:.2f} | conf={conf_factor:.2f} | "
            f"vol={vol_factor:.2f} | dd={dd_factor:.2f} | "
            f"position={position_value:,.0f} IDR"
        )

        return result

    def _bayesian_win_rate(self, trades: List[TradeOutcome]) -> Tuple[float, float]:
        """
        Calculate Bayesian win rate with exponential decay weighting.

        Returns:
            (win_rate, effective_sample_size)
        """
        if not trades:
            return PRIOR_WIN_RATE, 0.0

        # Apply exponential decay (most recent trade = weight 1.0)
        n = len(trades)
        weights = np.array([DECAY_FACTOR ** (n - 1 - i) for i in range(n)])
        wins = np.array([1.0 if t.won else 0.0 for t in trades])

        weighted_wins = np.sum(wins * weights)
        total_weight = np.sum(weights)

        # Bayesian update: combine prior with observed data
        # Prior: PRIOR_WIN_RATE with PRIOR_WEIGHT pseudo-observations
        posterior_wins = weighted_wins + (PRIOR_WIN_RATE * PRIOR_WEIGHT)
        posterior_total = total_weight + PRIOR_WEIGHT

        bayesian_wr = posterior_wins / posterior_total if posterior_total > 0 else PRIOR_WIN_RATE

        # Effective sample size (accounts for decay)
        effective_n = total_weight

        return float(bayesian_wr), float(effective_n)

    def _decay_weighted_wl_ratio(self, trades: List[TradeOutcome]) -> float:
        """
        Calculate decay-weighted average win / average loss ratio.
        """
        if not trades:
            return 1.0

        n = len(trades)
        weights = np.array([DECAY_FACTOR ** (n - 1 - i) for i in range(n)])
        pnls = np.array([t.pnl_pct for t in trades])
        wins_mask = np.array([t.won for t in trades])
        losses_mask = ~wins_mask

        # Weighted average win
        if np.any(wins_mask):
            win_weights = weights[wins_mask]
            win_pnls = pnls[wins_mask]
            avg_win = np.sum(win_pnls * win_weights) / np.sum(win_weights)
        else:
            avg_win = 2.0  # Default assumption: 2% average win

        # Weighted average loss (absolute value)
        if np.any(losses_mask):
            loss_weights = weights[losses_mask]
            loss_pnls = np.abs(pnls[losses_mask])
            avg_loss = np.sum(loss_pnls * loss_weights) / np.sum(loss_weights)
        else:
            avg_loss = 1.5  # Default assumption: 1.5% average loss

        if avg_loss <= 0:
            return 2.0  # Avoid division by zero

        return float(avg_win / avg_loss)

    def _confidence_factor(self, ml_confidence: float) -> float:
        """Scale Kelly by ML confidence."""
        if ml_confidence < CONFIDENCE_THRESHOLD:
            return CONFIDENCE_SCALE_MIN

        # Linear scale from CONFIDENCE_THRESHOLD to 0.90
        scale = (ml_confidence - CONFIDENCE_THRESHOLD) / (0.90 - CONFIDENCE_THRESHOLD)
        scale = max(0.0, min(1.0, scale))

        return CONFIDENCE_SCALE_MIN + scale * (CONFIDENCE_SCALE_MAX - CONFIDENCE_SCALE_MIN)

    def _volatility_factor(self, volatility_pct: float) -> float:
        """Reduce position size in high volatility."""
        if volatility_pct <= VOL_LOW_THRESHOLD:
            return 1.0
        elif volatility_pct >= VOL_HIGH_THRESHOLD:
            return 0.25

        # Linear interpolation
        scale = (volatility_pct - VOL_LOW_THRESHOLD) / (VOL_HIGH_THRESHOLD - VOL_LOW_THRESHOLD)
        return 1.0 - (scale * 0.75)  # 1.0 → 0.25

    def _drawdown_factor(self, drawdown_pct: float) -> float:
        """Reduce position size during drawdown."""
        if drawdown_pct <= DRAWDOWN_REDUCE_START:
            return 1.0
        elif drawdown_pct >= DRAWDOWN_REDUCE_MAX:
            return DRAWDOWN_MIN_FACTOR

        # Linear interpolation
        scale = (drawdown_pct - DRAWDOWN_REDUCE_START) / (DRAWDOWN_REDUCE_MAX - DRAWDOWN_REDUCE_START)
        return 1.0 - (scale * (1.0 - DRAWDOWN_MIN_FACTOR))

    def _prior_only_result(
        self, pair: str, balance: float, entry_price: float,
        ml_confidence: float, max_alloc: float
    ) -> KellyResult:
        """Return conservative result when insufficient trade data."""
        # Use minimum allocation scaled by confidence
        conf_factor = self._confidence_factor(ml_confidence)
        kelly_fraction = min(0.10 * conf_factor, max_alloc)  # Max 10% with prior only
        position_value = balance * kelly_fraction
        position_amount = position_value / entry_price

        return KellyResult(
            pair=pair,
            position_value=position_value,
            position_amount=position_amount,
            kelly_fraction=kelly_fraction,
            raw_kelly_pct=0.0,
            bayesian_win_rate=PRIOR_WIN_RATE,
            win_loss_ratio=1.0,
            confidence_factor=conf_factor,
            volatility_factor=1.0,
            drawdown_factor=1.0,
            total_trades=0,
            effective_trades=0.0,
            method='prior_only',
        )

    def _empty_result(self, pair: str, method: str) -> KellyResult:
        """Return zero-allocation result."""
        return KellyResult(
            pair=pair,
            position_value=0.0,
            position_amount=0.0,
            kelly_fraction=0.0,
            raw_kelly_pct=0.0,
            bayesian_win_rate=PRIOR_WIN_RATE,
            win_loss_ratio=0.0,
            confidence_factor=0.0,
            volatility_factor=0.0,
            drawdown_factor=0.0,
            total_trades=0,
            effective_trades=0.0,
            method=method,
        )

    def get_pair_stats(self, pair: str) -> Dict:
        """Get Kelly stats for a specific pair."""
        trades = self._trade_history.get(pair, [])
        if not trades:
            return {'pair': pair, 'total_trades': 0, 'win_rate': PRIOR_WIN_RATE}

        wr, eff_n = self._bayesian_win_rate(trades)
        wl = self._decay_weighted_wl_ratio(trades)
        raw_kelly = max(0, wr - ((1 - wr) / wl)) if wl > 0 else 0

        return {
            'pair': pair,
            'total_trades': len(trades),
            'effective_trades': round(eff_n, 1),
            'bayesian_win_rate': round(wr, 4),
            'win_loss_ratio': round(wl, 3),
            'raw_kelly_pct': round(raw_kelly, 4),
            'recent_wins': sum(1 for t in trades[-10:] if t.won),
            'recent_total': min(10, len(trades)),
        }

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get Kelly stats for all tracked pairs."""
        return {pair: self.get_pair_stats(pair) for pair in self._trade_history}
