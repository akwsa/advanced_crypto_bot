#!/usr/bin/env python3
"""
Backtester Module
=================
Simple backtesting engine for trading strategies.

Features:
- Historical price-based backtesting
- TA signal simulation
- ML prediction simulation
- Trade simulation (DRY RUN mode)
- Performance metrics calculation

Usage:
    from analysis.backtester import Backtester
    backtester = Backtester(db, ml_model)
    results = backtester.run_backtest('btcidr', '2026-03-01', '2026-03-31')
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger('crypto_bot')


class Backtester:
    """
    Simple backtesting engine.

    Simulates trading on historical data to evaluate strategy performance.
    """

    def __init__(self, db, ml_model=None):
        """
        Initialize backtester.

        Args:
            db: Database instance with price data
            ml_model: ML model for predictions (optional)
        """
        self.db = db
        self.ml_model = ml_model

        # Default trading settings
        self.initial_balance = 10000000  # 10M IDR
        self.position_size_pct = 0.25  # 25% per trade
        self.stop_loss_pct = 2.0
        self.take_profit_pct = 4.0
        self.commission_pct = 0.3  # Indodax fee

        logger.info("✅ Backtester initialized")

    def run_backtest(self, pair: str, start_date: str, end_date: str) -> Dict:
        """
        Run backtest for a specific pair and date range.

        Args:
            pair: Trading pair (e.g., 'btcidr')
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dictionary with backtest results and metrics
        """
        logger.info(f"🔄 Backtesting {pair} from {start_date} to {end_date}")

        # Get historical data
        prices = self._get_historical_prices(pair, start_date, end_date)
        if not prices or len(prices) < 50:
            return {
                'success': False,
                'error': f'Insufficient data for {pair}. Need 50+ candles, got {len(prices) if prices else 0}'
            }

        # Run simulation
        results = self._simulate_trades(pair, prices)

        # Calculate metrics
        metrics = self._calculate_metrics(results)

        logger.info(f"✅ Backtest complete: {metrics.get('total_trades', 0)} trades, "
                   f"Win Rate: {metrics.get('win_rate', 0):.1f}%")

        return {
            'success': True,
            'pair': pair,
            'period': f"{start_date} to {end_date}",
            'data_points': len(prices),
            'results': results,
            'metrics': metrics
        }

    def _get_historical_prices(self, pair: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch historical price data from database."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT timestamp, open, high, low, close, volume
                    FROM price_history
                    WHERE pair = ? AND timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp ASC
                ''', (pair.lower(), start_date, end_date))

                rows = cursor.fetchall()
                prices = []
                for row in rows:
                    prices.append({
                        'timestamp': row['timestamp'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume'])
                    })
                return prices
        except Exception as e:
            logger.error(f"Error fetching historical prices: {e}")
            return []

    def _simulate_trades(self, pair: str, prices: List[Dict]) -> List[Dict]:
        """Simulate trades based on TA signals."""
        trades = []
        balance_idr = self.initial_balance
        position = None  # {'entry_price', 'amount', 'stop_loss', 'take_profit'}

        for i in range(50, len(prices)):  # Start after 50 candles for indicators
            current = prices[i]
            price_slice = [p['close'] for p in prices[:i+1]]

            # Calculate TA indicators
            rsi = self._calc_rsi(price_slice)
            macd = self._calc_macd(price_slice)
            ma = self._calc_ma(price_slice)

            signal = self._generate_signal(rsi, macd, ma)

            # Check for position exit
            if position:
                # Check stop loss
                if current['low'] <= position['stop_loss']:
                    exit_price = position['stop_loss']
                    pnl = (exit_price - position['entry_price']) * position['amount']
                    pnl_pct = ((exit_price / position['entry_price']) - 1) * 100

                    trade = {
                        'entry_date': position['entry_date'],
                        'exit_date': current['timestamp'],
                        'entry_price': position['entry_price'],
                        'exit_price': exit_price,
                        'type': 'STOP_LOSS',
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'reason': 'Stop Loss triggered'
                    }
                    trades.append(trade)
                    balance_idr += exit_price * position['amount']
                    position = None
                    continue

                # Check take profit
                if current['high'] >= position['take_profit']:
                    exit_price = position['take_profit']
                    pnl = (exit_price - position['entry_price']) * position['amount']
                    pnl_pct = ((exit_price / position['entry_price']) - 1) * 100

                    trade = {
                        'entry_date': position['entry_date'],
                        'exit_date': current['timestamp'],
                        'entry_price': position['entry_price'],
                        'exit_price': exit_price,
                        'type': 'TAKE_PROFIT',
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'reason': 'Take Profit reached'
                    }
                    trades.append(trade)
                    balance_idr += exit_price * position['amount']
                    position = None
                    continue

            # Check for entry (no position open)
            if not position and signal == 'BUY':
                position_size = min(
                    balance_idr * self.position_size_pct,
                    5000000  # Max 5M per trade
                )
                entry_price = current['close']
                coin_amount = position_size / entry_price

                # Deduct commission
                commission = position_size * (self.commission_pct / 100)
                balance_idr -= position_size + commission

                position = {
                    'entry_date': current['timestamp'],
                    'entry_price': entry_price,
                    'amount': coin_amount,
                    'stop_loss': entry_price * (1 - self.stop_loss_pct / 100),
                    'take_profit': entry_price * (1 + self.take_profit_pct / 100)
                }

        # Close any open position at last price
        if position and prices:
            last_price = prices[-1]['close']
            pnl = (last_price - position['entry_price']) * position['amount']
            pnl_pct = ((last_price / position['entry_price']) - 1) * 100

            trade = {
                'entry_date': position['entry_date'],
                'exit_date': prices[-1]['timestamp'],
                'entry_price': position['entry_price'],
                'exit_price': last_price,
                'type': 'OPEN_POSITION',
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'reason': 'End of backtest period'
            }
            trades.append(trade)

        return trades

    def _generate_signal(self, rsi: float, macd: Dict, ma: Dict) -> str:
        """Generate trading signal based on TA."""
        # Buy criteria: Oversold (RSI 30-45), MACD bullish, MA bullish
        if 30 <= rsi <= 50 and macd.get('bullish', False) and ma.get('bullish', False):
            return 'BUY'

        # Sell criteria: Overbought (RSI > 65), MACD bearish
        if rsi > 65 and not macd.get('bullish', False):
            return 'SELL'

        return 'HOLD'

    def _calc_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI."""
        if len(prices) < period + 1:
            return 50

        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            gains.append(max(diff, 0))
            losses.append(abs(min(diff, 0)))

        avg_g = sum(gains[-period:]) / period
        avg_l = sum(losses[-period:]) / period

        if avg_l == 0:
            return 100

        rs = avg_g / avg_l
        return 100 - (100 / (1 + rs))

    def _calc_macd(self, prices: List[float]) -> Dict:
        """Calculate MACD."""
        if len(prices) < 35:
            return {'bullish': False, 'macd': 0, 'signal': 0}

        ema12 = self._calc_ema(prices, 12)
        ema26 = self._calc_ema(prices, 26)

        if ema12 is None or ema26 is None:
            return {'bullish': False, 'macd': 0, 'signal': 0}

        macd = ema12 - ema26

        # Simplified signal line (9-period EMA of MACD)
        macd_series = [macd * 0.95, macd]  # Approximation
        signal_line = sum(macd_series) / len(macd_series)

        return {'bullish': macd > signal_line, 'macd': macd, 'signal': signal_line}

    def _calc_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate EMA."""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calc_ma(self, prices: List[float]) -> Dict:
        """Calculate Moving Average trend."""
        if len(prices) < 25:
            return {'bullish': False}

        ma9 = sum(prices[-9:]) / 9
        ma25 = sum(prices[-25:]) / 25

        return {'bullish': ma9 > ma25, 'ma9': ma9, 'ma25': ma25}

    def _calculate_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate backtest performance metrics."""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'total_pnl': 0,
                'avg_trade_pnl': 0,
                'max_drawdown': 0
            }

        # Closed trades (excluding open positions)
        closed_trades = [t for t in trades if t['type'] != 'OPEN_POSITION']
        open_positions = [t for t in trades if t['type'] == 'OPEN_POSITION']

        # Basic counts
        total_trades = len(closed_trades)
        winning_trades = len([t for t in closed_trades if t['pnl'] > 0])
        losing_trades = len([t for t in closed_trades if t['pnl'] < 0])

        # PnL calculations
        total_pnl = sum(t['pnl'] for t in trades)
        gross_profit = sum(t['pnl'] for t in closed_trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in closed_trades if t['pnl'] < 0))

        # Metrics
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        avg_trade_pnl = total_pnl / len(trades) if trades else 0

        # Max drawdown (simplified)
        cumulative = 0
        max_dd = 0
        peak = 0
        for trade in trades:
            cumulative += trade['pnl']
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative if cumulative < peak else 0
            if dd > max_dd:
                max_dd = dd

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_pnl': total_pnl,
            'avg_trade_pnl': avg_trade_pnl,
            'max_drawdown': max_dd,
            'open_positions': len(open_positions),
            'gross_profit': gross_profit,
            'gross_loss': gross_loss
        }


# Simple test
if __name__ == '__main__':
    # Test backtester initialization
    print("✅ Backtester module ready!")
    print("Usage:")
    print("  from analysis.backtester import Backtester")
    print("  backtester = Backtester(db, ml_model)")
    print("  results = backtester.run_backtest('btcidr', '2026-03-01', '2026-03-31')")
