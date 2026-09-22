#!/usr/bin/env python3
# Tujuan: Dynamic rolling correlation matrix untuk portfolio risk management.
# Caller: risk_manager.py, autotrade runtime.
# Dependensi: numpy, pandas.
# Main Functions: class DynamicCorrelationEngine.
# Side Effects: none; pure computation only.
"""
Dynamic Correlation Engine
============================
Replaces hardcoded correlation groups with real-time rolling correlation:

1. Rolling correlation matrix (20-period window)
2. Correlation regime detection (stable vs shifting)
3. Portfolio heat calculation (total correlated exposure)
4. Dynamic correlation groups (auto-detect from data)
5. Diversification score (how well-diversified is portfolio)

Usage:
    from quant.dynamic_correlation import DynamicCorrelationEngine

    corr = DynamicCorrelationEngine()
    corr.update_prices('btcidr', [1500000, 1510000, ...])
    corr.update_prices('ethidr', [45000000, 45500000, ...])

    matrix = corr.get_correlation_matrix()
    heat = corr.calculate_portfolio_heat(open_positions)
    allowed = corr.check_correlation_limit('ethidr', open_positions)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("crypto_bot")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Rolling correlation window
CORRELATION_WINDOW = 20        # 20 candles for rolling correlation
MIN_DATA_POINTS = 15           # Minimum data points for valid correlation

# Correlation thresholds
HIGH_CORRELATION = 0.70        # Pairs with corr > 0.70 are "highly correlated"
MODERATE_CORRELATION = 0.50    # Pairs with corr > 0.50 are "moderately correlated"

# Portfolio heat limits
MAX_CORRELATED_EXPOSURE = 0.40  # Max 40% of balance in highly correlated group
MAX_SINGLE_GROUP_PAIRS = 3      # Max 3 positions in same correlation group

# Diversification scoring
IDEAL_CORRELATION = 0.0         # Perfect diversification = 0 correlation
DIVERSIFICATION_PENALTY = 0.30  # Reduce score if avg correlation > 0.30


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CorrelationCheckResult:
    """Result from correlation limit check."""
    allowed: bool
    reason: str
    current_exposure_pct: float    # Current correlated exposure %
    max_allowed_pct: float         # Maximum allowed %
    correlated_pairs: List[str]    # List of correlated open pairs
    correlation_value: float       # Highest correlation with open positions

    def to_dict(self) -> Dict:
        return {
            'allowed': self.allowed,
            'reason': self.reason,
            'current_exposure_pct': round(self.current_exposure_pct, 2),
            'max_allowed_pct': round(self.max_allowed_pct, 2),
            'correlated_pairs': self.correlated_pairs,
            'correlation_value': round(self.correlation_value, 3),
        }


@dataclass
class PortfolioHeatResult:
    """Portfolio heat analysis result."""
    total_heat: float              # 0.0 (cold/diversified) to 1.0 (hot/concentrated)
    diversification_score: float   # 0.0 (concentrated) to 1.0 (diversified)
    correlation_groups: Dict[str, List[str]]  # Auto-detected groups
    avg_correlation: float         # Average pairwise correlation
    max_correlation: float         # Highest pairwise correlation
    risk_level: str                # 'LOW', 'MODERATE', 'HIGH', 'CRITICAL'

    def to_dict(self) -> Dict:
        return {
            'total_heat': round(self.total_heat, 3),
            'diversification_score': round(self.diversification_score, 3),
            'correlation_groups': self.correlation_groups,
            'avg_correlation': round(self.avg_correlation, 3),
            'max_correlation': round(self.max_correlation, 3),
            'risk_level': self.risk_level,
        }


# =============================================================================
# MAIN ENGINE
# =============================================================================

class DynamicCorrelationEngine:
    """
    Dynamic rolling correlation engine for portfolio risk management.
    """

    def __init__(self):
        # Price history per pair (rolling window)
        self._price_history: Dict[str, List[float]] = {}
        self._max_history = CORRELATION_WINDOW * 3  # Keep 3x window for stability
        # Cached correlation matrix
        self._correlation_matrix: Optional[pd.DataFrame] = None
        self._matrix_stale = True
        logger.info("✅ Quant Dynamic Correlation Engine initialized")

    def update_prices(self, pair: str, prices: List[float]):
        """
        Update price history for a pair.

        Args:
            pair: Trading pair (e.g., 'btcidr')
            prices: List of recent close prices
        """
        self._price_history[pair] = prices[-self._max_history:]
        self._matrix_stale = True

    def add_price(self, pair: str, price: float):
        """Add single price point to pair history."""
        if pair not in self._price_history:
            self._price_history[pair] = []
        self._price_history[pair].append(price)
        if len(self._price_history[pair]) > self._max_history:
            self._price_history[pair] = self._price_history[pair][-self._max_history:]
        self._matrix_stale = True

    def get_correlation_matrix(self) -> Optional[pd.DataFrame]:
        """
        Calculate rolling correlation matrix for all tracked pairs.

        Returns:
            DataFrame with pairwise correlations, or None if insufficient data
        """
        if not self._matrix_stale and self._correlation_matrix is not None:
            return self._correlation_matrix

        # Filter pairs with enough data
        valid_pairs = {
            pair: prices for pair, prices in self._price_history.items()
            if len(prices) >= MIN_DATA_POINTS
        }

        if len(valid_pairs) < 2:
            return None

        # Build returns DataFrame
        min_len = min(len(v) for v in valid_pairs.values())
        min_len = min(min_len, CORRELATION_WINDOW)

        returns_dict = {}
        for pair, prices in valid_pairs.items():
            recent = prices[-min_len:]
            returns = pd.Series(recent).pct_change().dropna()
            if len(returns) >= MIN_DATA_POINTS - 1:
                returns_dict[pair] = returns.values[:min_len - 1]

        if len(returns_dict) < 2:
            return None

        # Align lengths
        min_ret_len = min(len(v) for v in returns_dict.values())
        df = pd.DataFrame({k: v[:min_ret_len] for k, v in returns_dict.items()})

        # Calculate correlation matrix
        self._correlation_matrix = df.corr()
        self._matrix_stale = False

        return self._correlation_matrix

    def get_pair_correlation(self, pair1: str, pair2: str) -> float:
        """Get correlation between two specific pairs."""
        matrix = self.get_correlation_matrix()
        if matrix is None:
            return 0.0
        if pair1 not in matrix.columns or pair2 not in matrix.columns:
            return 0.0
        corr = matrix.loc[pair1, pair2]
        return float(corr) if not pd.isna(corr) else 0.0

    def check_correlation_limit(
        self,
        new_pair: str,
        open_positions: List[Dict],
        balance: float = 0,
    ) -> CorrelationCheckResult:
        """
        Check if opening a new position would exceed correlation limits.

        Args:
            new_pair: Pair to potentially open
            open_positions: List of open position dicts with 'pair' and 'total' keys
            balance: Total portfolio balance

        Returns:
            CorrelationCheckResult
        """
        if not open_positions:
            return CorrelationCheckResult(
                allowed=True,
                reason="No open positions",
                current_exposure_pct=0.0,
                max_allowed_pct=MAX_CORRELATED_EXPOSURE * 100,
                correlated_pairs=[],
                correlation_value=0.0,
            )

        matrix = self.get_correlation_matrix()
        correlated_pairs = []
        max_corr = 0.0
        correlated_exposure = 0.0

        for pos in open_positions:
            pos_pair = pos.get('pair', '').lower()
            if pos_pair == new_pair:
                continue

            # Get correlation
            if matrix is not None and new_pair in matrix.columns and pos_pair in matrix.columns:
                corr = abs(float(matrix.loc[new_pair, pos_pair]))
            else:
                # Fallback: check if in same hardcoded group
                corr = self._fallback_correlation(new_pair, pos_pair)

            if corr >= HIGH_CORRELATION:
                correlated_pairs.append(pos_pair)
                correlated_exposure += pos.get('total', 0)
                max_corr = max(max_corr, corr)

        # Calculate exposure percentage
        total_portfolio = balance if balance > 0 else sum(p.get('total', 0) for p in open_positions)
        exposure_pct = (correlated_exposure / total_portfolio * 100) if total_portfolio > 0 else 0

        # Check limits
        max_allowed = MAX_CORRELATED_EXPOSURE * 100
        allowed = True
        reason = "Within correlation limits"

        if exposure_pct >= max_allowed:
            allowed = False
            reason = (
                f"Correlated exposure {exposure_pct:.1f}% >= {max_allowed:.0f}% "
                f"(correlated with: {', '.join(correlated_pairs)})"
            )
        elif len(correlated_pairs) >= MAX_SINGLE_GROUP_PAIRS:
            allowed = False
            reason = (
                f"Too many correlated positions ({len(correlated_pairs)} >= {MAX_SINGLE_GROUP_PAIRS})"
            )

        return CorrelationCheckResult(
            allowed=allowed,
            reason=reason,
            current_exposure_pct=exposure_pct,
            max_allowed_pct=max_allowed,
            correlated_pairs=correlated_pairs,
            correlation_value=max_corr,
        )

    def calculate_portfolio_heat(
        self,
        open_positions: List[Dict],
    ) -> PortfolioHeatResult:
        """
        Calculate portfolio heat (concentration risk).

        Args:
            open_positions: List of position dicts with 'pair' and 'total' keys

        Returns:
            PortfolioHeatResult
        """
        if not open_positions or len(open_positions) < 2:
            return PortfolioHeatResult(
                total_heat=0.0,
                diversification_score=1.0,
                correlation_groups={},
                avg_correlation=0.0,
                max_correlation=0.0,
                risk_level='LOW',
            )

        pairs = [p.get('pair', '').lower() for p in open_positions]
        matrix = self.get_correlation_matrix()

        # Calculate pairwise correlations
        correlations = []
        for i, p1 in enumerate(pairs):
            for p2 in pairs[i + 1:]:
                if matrix is not None and p1 in matrix.columns and p2 in matrix.columns:
                    corr = abs(float(matrix.loc[p1, p2]))
                else:
                    corr = self._fallback_correlation(p1, p2)
                correlations.append(corr)

        avg_corr = float(np.mean(correlations)) if correlations else 0.0
        max_corr = float(np.max(correlations)) if correlations else 0.0

        # Auto-detect correlation groups
        groups = self._detect_groups(pairs, matrix)

        # Calculate heat (0 = cold/diversified, 1 = hot/concentrated)
        heat = avg_corr  # Simple: heat = average correlation

        # Diversification score (inverse of heat)
        div_score = max(0.0, 1.0 - heat)

        # Risk level
        if heat >= 0.70:
            risk_level = 'CRITICAL'
        elif heat >= 0.50:
            risk_level = 'HIGH'
        elif heat >= 0.30:
            risk_level = 'MODERATE'
        else:
            risk_level = 'LOW'

        return PortfolioHeatResult(
            total_heat=heat,
            diversification_score=div_score,
            correlation_groups=groups,
            avg_correlation=avg_corr,
            max_correlation=max_corr,
            risk_level=risk_level,
        )

    def _detect_groups(
        self, pairs: List[str], matrix: Optional[pd.DataFrame]
    ) -> Dict[str, List[str]]:
        """Auto-detect correlation groups using simple clustering."""
        groups: Dict[str, List[str]] = {}
        assigned: Set[str] = set()

        for i, p1 in enumerate(pairs):
            if p1 in assigned:
                continue
            group = [p1]
            assigned.add(p1)

            for p2 in pairs[i + 1:]:
                if p2 in assigned:
                    continue
                if matrix is not None and p1 in matrix.columns and p2 in matrix.columns:
                    corr = abs(float(matrix.loc[p1, p2]))
                else:
                    corr = self._fallback_correlation(p1, p2)

                if corr >= MODERATE_CORRELATION:
                    group.append(p2)
                    assigned.add(p2)

            if len(group) > 1:
                groups[f"group_{len(groups) + 1}"] = group

        return groups

    def _fallback_correlation(self, pair1: str, pair2: str) -> float:
        """Fallback correlation using hardcoded groups (from Config)."""
        # Known high-correlation groups
        groups = {
            'btc_related': {'btcidr', 'wrxidr'},
            'eth_related': {'ethidr', 'maticidr', 'solidr'},
            'alt_meme': {'dogeidr', 'shibidr', 'pepeidr', 'flokiidr'},
            'alt_major': {'xrpidr', 'adaidr', 'bnbidr'},
        }

        for group_pairs in groups.values():
            if pair1 in group_pairs and pair2 in group_pairs:
                return 0.75  # Assume high correlation within group

        # Default: moderate correlation for all crypto (they tend to move together)
        return 0.35

    def get_all_pairs(self) -> List[str]:
        """Get all tracked pairs."""
        return list(self._price_history.keys())

    def get_stats(self) -> Dict:
        """Get engine statistics."""
        matrix = self.get_correlation_matrix()
        return {
            'tracked_pairs': len(self._price_history),
            'pairs': list(self._price_history.keys()),
            'matrix_available': matrix is not None,
            'matrix_size': f"{matrix.shape[0]}x{matrix.shape[1]}" if matrix is not None else "N/A",
        }
