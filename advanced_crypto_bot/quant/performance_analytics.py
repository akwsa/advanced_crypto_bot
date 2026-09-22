#!/usr/bin/env python3
# Tujuan: Quantitative performance metrics (Sharpe, Sortino, Calmar, rolling stats).
# Caller: risk_manager.py get_risk_metrics, bot.py /performance command.
# Dependensi: numpy, pandas.
# Main Functions: class PerformanceAnalytics.
# Side Effects: none; pure computation only.
"""
Performance Analytics Engine
==============================
Comprehensive quantitative performance metrics:

1. Sharpe Ratio (risk-adjusted return)
2. Sortino Ratio (downside risk only)
3. Calmar Ratio (return / max drawdown)
4. Profit Factor (gross profit / gross loss)
5. Maximum Drawdown (peak-to-trough)
6. Win Rate & Expectancy
7. Rolling metrics (7d, 30d windows)
8. Recovery Factor (net profit / max drawdown)

Usage:
    from quant.performance_analytics import PerformanceAnalytics

    pa = PerformanceAnalytics()
    metrics = pa.calculate_all(trade_history)
    # metrics.sharpe_ratio → float
    # metrics.sortino_ratio → float
    # metrics.max_drawdown_pct → float
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("crypto_bot")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Annualization factor (crypto trades 24/7)
# Assuming ~4 trades per day average
TRADES_PER_YEAR = 365 * 4
RISK_FREE_RATE = 0.0  # Assume 0% risk-free for crypto

# Rolling window sizes
ROLLING_SHORT = 7     # 7-day rolling
ROLLING_MEDIUM = 30   # 30-day rolling

# Minimum trades for meaningful metrics
MIN_TRADES_SHARPE = 10
MIN_TRADES_SORTINO = 10
MIN_TRADES_CALMAR = 20


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    # Core ratios
    sharpe_ratio: float          # Return / volatility (annualized)
    sortino_ratio: float         # Return / downside volatility
    calmar_ratio: float          # Annual return / max drawdown

    # Profit metrics
    profit_factor: float         # Gross profit / gross loss
    expectancy: float            # Average profit per trade (IDR)
    expectancy_pct: float        # Average profit per trade (%)

    # Win/loss stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float              # 0.0 to 1.0
    avg_win_pct: float           # Average winning trade %
    avg_loss_pct: float          # Average losing trade % (negative)
    best_trade_pct: float        # Best single trade %
    worst_trade_pct: float       # Worst single trade %
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Drawdown
    max_drawdown_pct: float      # Maximum drawdown %
    max_drawdown_duration: int   # Trades to recover from max DD
    current_drawdown_pct: float  # Current drawdown from peak

    # Recovery
    recovery_factor: float       # Net profit / max drawdown
    net_profit_pct: float        # Total net profit %

    # Rolling (recent performance)
    sharpe_7d: Optional[float]   # 7-day Sharpe
    sharpe_30d: Optional[float]  # 30-day Sharpe
    win_rate_7d: Optional[float] # 7-day win rate

    def to_dict(self) -> Dict:
        return {
            'sharpe_ratio': round(self.sharpe_ratio, 3),
            'sortino_ratio': round(self.sortino_ratio, 3),
            'calmar_ratio': round(self.calmar_ratio, 3),
            'profit_factor': round(self.profit_factor, 3),
            'expectancy_pct': round(self.expectancy_pct, 3),
            'total_trades': self.total_trades,
            'win_rate': round(self.win_rate, 4),
            'avg_win_pct': round(self.avg_win_pct, 3),
            'avg_loss_pct': round(self.avg_loss_pct, 3),
            'max_drawdown_pct': round(self.max_drawdown_pct, 3),
            'current_drawdown_pct': round(self.current_drawdown_pct, 3),
            'recovery_factor': round(self.recovery_factor, 3),
            'net_profit_pct': round(self.net_profit_pct, 3),
            'max_consecutive_wins': self.max_consecutive_wins,
            'max_consecutive_losses': self.max_consecutive_losses,
            'sharpe_7d': round(self.sharpe_7d, 3) if self.sharpe_7d is not None else None,
            'sharpe_30d': round(self.sharpe_30d, 3) if self.sharpe_30d is not None else None,
            'win_rate_7d': round(self.win_rate_7d, 4) if self.win_rate_7d is not None else None,
        }

    def summary_text(self) -> str:
        """Human-readable summary for Telegram display."""
        return (
            f"📊 Performance Analytics\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Sharpe Ratio: {self.sharpe_ratio:.2f}\n"
            f"Sortino Ratio: {self.sortino_ratio:.2f}\n"
            f"Calmar Ratio: {self.calmar_ratio:.2f}\n"
            f"Profit Factor: {self.profit_factor:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Win Rate: {self.win_rate:.1%} ({self.winning_trades}W/{self.losing_trades}L)\n"
            f"Avg Win: +{self.avg_win_pct:.2f}%\n"
            f"Avg Loss: {self.avg_loss_pct:.2f}%\n"
            f"Expectancy: {self.expectancy_pct:+.3f}%/trade\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Max Drawdown: {self.max_drawdown_pct:.2f}%\n"
            f"Current DD: {self.current_drawdown_pct:.2f}%\n"
            f"Net Profit: {self.net_profit_pct:+.2f}%\n"
            f"Recovery Factor: {self.recovery_factor:.2f}\n"
        )


# =============================================================================
# MAIN ENGINE
# =============================================================================

class PerformanceAnalytics:
    """
    Quantitative performance analytics engine.
    """

    def __init__(self):
        logger.info("✅ Quant Performance Analytics Engine initialized")

    def calculate_all(
        self,
        trade_returns_pct: List[float],
        initial_balance: float = 10_000_000,
    ) -> Optional[PerformanceMetrics]:
        """
        Calculate all performance metrics from trade returns.

        Args:
            trade_returns_pct: List of trade returns in percentage
                               (e.g., [3.5, -1.2, 2.1, -0.8, ...])
            initial_balance: Starting balance for drawdown calculation

        Returns:
            PerformanceMetrics or None if insufficient data
        """
        if not trade_returns_pct or len(trade_returns_pct) < 3:
            logger.debug("[PERF] Insufficient trades for analytics")
            return None

        returns = np.array(trade_returns_pct, dtype=float)
        n = len(returns)

        # Basic stats
        wins = returns[returns > 0]
        losses = returns[returns <= 0]
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / n if n > 0 else 0

        avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
        avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
        best_trade = float(np.max(returns))
        worst_trade = float(np.min(returns))

        # Consecutive wins/losses
        max_consec_wins, max_consec_losses = self._max_consecutive(returns)

        # Profit Factor
        gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
        gross_loss = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.001
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # Expectancy
        expectancy_pct = float(np.mean(returns))
        expectancy = expectancy_pct / 100 * initial_balance

        # Net profit
        net_profit_pct = float(np.sum(returns))

        # Sharpe Ratio
        sharpe = self._sharpe_ratio(returns) if n >= MIN_TRADES_SHARPE else 0.0

        # Sortino Ratio
        sortino = self._sortino_ratio(returns) if n >= MIN_TRADES_SORTINO else 0.0

        # Drawdown analysis
        max_dd, dd_duration, current_dd = self._drawdown_analysis(returns, initial_balance)

        # Calmar Ratio
        calmar = 0.0
        if n >= MIN_TRADES_CALMAR and max_dd > 0:
            annualized_return = expectancy_pct * TRADES_PER_YEAR / 100
            calmar = annualized_return / (max_dd / 100) if max_dd > 0 else 0.0

        # Recovery Factor
        recovery_factor = net_profit_pct / max_dd if max_dd > 0 else 0.0

        # Rolling metrics
        sharpe_7d = self._sharpe_ratio(returns[-ROLLING_SHORT:]) if n >= ROLLING_SHORT else None
        sharpe_30d = self._sharpe_ratio(returns[-ROLLING_MEDIUM:]) if n >= ROLLING_MEDIUM else None
        win_rate_7d = None
        if n >= ROLLING_SHORT:
            recent = returns[-ROLLING_SHORT:]
            win_rate_7d = float(np.sum(recent > 0) / len(recent))

        metrics = PerformanceMetrics(
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            profit_factor=profit_factor,
            expectancy=expectancy,
            expectancy_pct=expectancy_pct,
            total_trades=n,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            best_trade_pct=best_trade,
            worst_trade_pct=worst_trade,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            max_drawdown_pct=max_dd,
            max_drawdown_duration=dd_duration,
            current_drawdown_pct=current_dd,
            recovery_factor=recovery_factor,
            net_profit_pct=net_profit_pct,
            sharpe_7d=sharpe_7d,
            sharpe_30d=sharpe_30d,
            win_rate_7d=win_rate_7d,
        )

        logger.info(
            f"📊 [PERF] Sharpe={sharpe:.2f} | Sortino={sortino:.2f} | "
            f"PF={profit_factor:.2f} | WR={win_rate:.1%} | "
            f"MaxDD={max_dd:.1f}% | Net={net_profit_pct:+.1f}%"
        )

        return metrics

    def _sharpe_ratio(self, returns: np.ndarray) -> float:
        """Calculate Sharpe Ratio (annualized)."""
        if len(returns) < 3:
            return 0.0
        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)
        if std_return == 0:
            return 0.0
        # Annualize: multiply by sqrt(trades_per_year)
        sharpe = (mean_return - RISK_FREE_RATE) / std_return
        annualized = sharpe * np.sqrt(min(TRADES_PER_YEAR, len(returns) * 12))
        return float(np.clip(annualized, -10, 10))

    def _sortino_ratio(self, returns: np.ndarray) -> float:
        """Calculate Sortino Ratio (uses downside deviation only)."""
        if len(returns) < 3:
            return 0.0
        mean_return = np.mean(returns)
        downside = returns[returns < 0]
        if len(downside) < 2:
            return float(mean_return * 10) if mean_return > 0 else 0.0  # No losses = great
        downside_std = np.std(downside, ddof=1)
        if downside_std == 0:
            return 0.0
        sortino = (mean_return - RISK_FREE_RATE) / downside_std
        annualized = sortino * np.sqrt(min(TRADES_PER_YEAR, len(returns) * 12))
        return float(np.clip(annualized, -10, 10))

    def _drawdown_analysis(
        self, returns: np.ndarray, initial_balance: float
    ) -> tuple:
        """
        Calculate max drawdown, duration, and current drawdown.

        Returns:
            (max_drawdown_pct, max_dd_duration_trades, current_drawdown_pct)
        """
        # Build equity curve
        equity = [initial_balance]
        for r in returns:
            equity.append(equity[-1] * (1 + r / 100))

        equity = np.array(equity)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak * 100

        max_dd = float(np.max(drawdown))
        current_dd = float(drawdown[-1])

        # Duration: trades from peak to recovery
        max_dd_idx = int(np.argmax(drawdown))
        # Find recovery point after max DD
        dd_duration = 0
        for i in range(max_dd_idx, len(equity)):
            if equity[i] >= peak[max_dd_idx]:
                dd_duration = i - max_dd_idx
                break
        else:
            dd_duration = len(equity) - max_dd_idx  # Still in drawdown

        return max_dd, dd_duration, current_dd

    def _max_consecutive(self, returns: np.ndarray) -> tuple:
        """Calculate max consecutive wins and losses."""
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for r in returns:
            if r > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return max_wins, max_losses

    def calculate_from_trades(self, trade_history: List[Dict]) -> Optional[PerformanceMetrics]:
        """
        Calculate metrics from trade history dicts (as returned by database).

        Expects each trade dict to have 'profit_loss_pct' or 'profit_loss' + 'total' keys.
        """
        returns = []
        for trade in trade_history:
            pnl_pct = trade.get('profit_loss_pct')
            if pnl_pct is not None:
                returns.append(float(pnl_pct))
            elif trade.get('profit_loss') is not None and trade.get('total'):
                total = trade['total']
                if total > 0:
                    returns.append(float(trade['profit_loss'] / total * 100))

        if not returns:
            return None

        initial = trade_history[0].get('total', 10_000_000) if trade_history else 10_000_000
        return self.calculate_all(returns, initial_balance=initial)
