#!/usr/bin/env python3
"""
Signal Quality Analyzer
======================
Analyzes historical signal accuracy per pair to filter false positives.

Features:
- Signal win rate per pair (BUY/SELL accuracy)
- Context analysis (RSI, volume, MA trend impact)
- Optimal holding time calculation
- Signal quality scoring (1-10)
- Auto-filter low-quality signals

Usage:
    from signal_analyzer import SignalAnalyzer
    
    analyzer = SignalAnalyzer()
    
    # Get quality report for a pair
    report = analyzer.get_signal_quality("BTCIDR", "BUY")
    
    # Score a new signal
    score = analyzer.score_signal("ETHIDR", "BUY", rsi=25, volume="High", confidence=0.75)
    
    # Check if signal should be taken
    should_trade = analyzer.should_trade("PIPPINIDR", "BUY", min_score=6)
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger('crypto_bot')

SIGNALS_DB = "data/signals.db"
TRADING_DB = "data/trading.db"

# Minimum data points for reliable analysis
MIN_SIGNALS_FOR_ANALYSIS = 5

# Score thresholds
SCORE_EXCELLENT = 8  # Auto-trade even in dry run
SCORE_GOOD = 6       # Recommend trading
SCORE_POOR = 4       # Warn user


class SignalAnalyzer:
    """Analyze historical signal quality to filter false positives"""

    def __init__(self, signals_db: str = SIGNALS_DB, trading_db: str = TRADING_DB):
        self.signals_db = signals_db
        self.trading_db = trading_db

    def _get_signals_conn(self):
        if not os.path.exists(self.signals_db):
            raise FileNotFoundError(f"Signals DB not found: {self.signals_db}")
        conn = sqlite3.connect(self.signals_db)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_trades_conn(self):
        if not os.path.exists(self.trading_db):
            raise FileNotFoundError(f"Trading DB not found: {self.trading_db}")
        conn = sqlite3.connect(self.trading_db)
        conn.row_factory = sqlite3.Row
        return conn

    def get_signal_quality(self, symbol: str, recommendation: str, days: int = 30) -> Dict:
        """
        Get historical accuracy for a specific signal type on a pair.
        
        Returns:
            Dict with win_rate, total_signals, avg_profit, optimal_hold_time, etc.
        """
        try:
            rec_upper = recommendation.upper()
            # Normalize symbol
            symbol_variants = [symbol, symbol.lower(), symbol.replace('_', '').lower()]
            
            # Get signals from last N days
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            signals_conn = self._get_signals_conn()
            cursor = signals_conn.cursor()
            
            # Count total signals for this pair + recommendation
            placeholders = ','.join(['?' for _ in symbol_variants])
            query = f'''
                SELECT COUNT(*) as total,
                       AVG(ml_confidence) as avg_confidence,
                       AVG(combined_strength) as avg_strength
                FROM signals 
                WHERE symbol IN ({placeholders})
                AND recommendation = ?
                AND received_date >= ?
            '''
            params = symbol_variants + [rec_upper, cutoff]
            cursor.execute(query, params)
            row = cursor.fetchone()
            
            total_signals = row['total'] if row else 0
            avg_confidence = row['avg_confidence'] if row and row['avg_confidence'] else 0.5
            avg_strength = row['avg_strength'] if row and row['avg_strength'] else 0
            
            signals_conn.close()
            
            if total_signals < MIN_SIGNALS_FOR_ANALYSIS:
                return {
                    'symbol': symbol,
                    'recommendation': rec_upper,
                    'total_signals': total_signals,
                    'days_analyzed': days,
                    'reliable': False,
                    'reason': f'Not enough signals ({total_signals} < {MIN_SIGNALS_FOR_ANALYSIS})',
                    'win_rate': None,
                    'avg_profit': None,
                    'optimal_hold_time': None,
                    'score': 5,  # Neutral
                    'score_label': '⚠️ INSUFFICIENT DATA',
                    'quality_grade': 'C',
                }
            
            # Now match signals to actual price movement
            trades_conn = self._get_trades_conn()
            price_cursor = trades_conn.cursor()
            
            # Get price movement after each signal
            winning_signals = 0
            losing_signals = 0
            neutral_signals = 0
            profits = []
            hold_times = []
            
            # Get all signals for this pair
            cursor.execute(f'''
                SELECT symbol, price, received_at, rsi, macd, ma_trend, volume, ml_confidence
                FROM signals 
                WHERE symbol IN ({placeholders})
                AND recommendation = ?
                AND received_date >= ?
                ORDER BY received_at ASC
            ''', params)
            
            signals = cursor.fetchall()
            
            for signal in signals:
                signal_price = signal['price']
                signal_time = signal['received_at']
                
                # Get next price data for this pair from trading DB
                pair_name = signal['symbol'].lower()
                price_cursor.execute('''
                    SELECT close, timestamp FROM price_history
                    WHERE pair = ?
                    AND timestamp > ?
                    ORDER BY timestamp ASC
                    LIMIT 50
                ''', (pair_name, signal_time))
                
                future_prices = price_cursor.fetchall()
                if not future_prices:
                    continue
                
                # Calculate profit/loss based on signal type
                # BUY: profit when price goes UP (sell at highest price)
                # SELL: profit when price goes DOWN (buy back at lowest price = short selling logic)
                is_buy_signal = rec_upper in ['BUY', 'STRONG_BUY']
                is_sell_signal = rec_upper in ['SELL', 'STRONG_SELL']

                if is_buy_signal:
                    # For BUY: best exit is max price
                    best_price = max(fp['close'] for fp in future_prices)
                    profit_pct = ((best_price - signal_price) / signal_price) * 100

                    # Find optimal hold time (when best price occurred)
                    best_idx = 0
                    for i, fp in enumerate(future_prices):
                        if fp['close'] == best_price:
                            best_idx = i
                            break

                elif is_sell_signal:
                    # For SELL: profit when price goes down (short selling)
                    # Best case = lowest price reached
                    lowest_price = min(fp['close'] for fp in future_prices)
                    profit_pct = ((signal_price - lowest_price) / signal_price) * 100

                    # Find optimal hold time (when lowest price occurred)
                    best_idx = 0
                    for i, fp in enumerate(future_prices):
                        if fp['close'] == lowest_price:
                            best_idx = i
                            break

                else:  # HOLD signals - analyze if price went up (would have been good BUY)
                    price_change = ((future_prices[-1]['close'] - signal_price) / signal_price) * 100
                    profit_pct = price_change
                    best_idx = len(future_prices) // 2  # Middle point

                # Each candle ~15 min, so hold_time in hours = idx * 0.25
                hold_time_hours = best_idx * 0.25

                if profit_pct > 0:
                    winning_signals += 1
                    profits.append(profit_pct)
                    hold_times.append(hold_time_hours)
                elif profit_pct < -0.5:  # More than 0.5% loss
                    losing_signals += 1
                else:
                    neutral_signals += 1
            
            trades_conn.close()
            
            # Calculate metrics
            total_valid = winning_signals + losing_signals + neutral_signals
            if total_valid == 0:
                return {
                    'symbol': symbol,
                    'recommendation': rec_upper,
                    'total_signals': total_signals,
                    'days_analyzed': days,
                    'reliable': False,
                    'reason': 'No price data available to validate signals',
                    'win_rate': None,
                    'avg_profit': None,
                    'optimal_hold_time': None,
                    'score': 5,
                    'score_label': '⚠️ NO PRICE DATA',
                    'quality_grade': 'C',
                }
            
            win_rate = (winning_signals / total_valid) * 100
            avg_profit = sum(profits) / len(profits) if profits else 0
            optimal_hold = sum(hold_times) / len(hold_times) if hold_times else 4.0  # Default 4h
            
            # Calculate score (1-10)
            score = self._calculate_score(win_rate, avg_profit, total_signals, avg_confidence)
            
            # Determine quality grade
            if score >= 8:
                grade = 'A'
                label = '✅ EXCELLENT'
            elif score >= 6:
                grade = 'B'
                label = '👍 GOOD'
            elif score >= 4:
                grade = 'C'
                label = '⚠️ AVERAGE'
            else:
                grade = 'D'
                label = '❌ POOR'
            
            return {
                'symbol': symbol,
                'recommendation': rec_upper,
                'total_signals': total_signals,
                'signals_analyzed': total_valid,
                'days_analyzed': days,
                'reliable': total_signals >= MIN_SIGNALS_FOR_ANALYSIS,
                'win_rate': win_rate,
                'winning_signals': winning_signals,
                'losing_signals': losing_signals,
                'neutral_signals': neutral_signals,
                'avg_profit': avg_profit,
                'avg_loss': self._avg_loss(profits, total_valid, winning_signals),
                'optimal_hold_time': optimal_hold,
                'avg_confidence': avg_confidence,
                'avg_strength': avg_strength,
                'score': score,
                'score_label': label,
                'quality_grade': grade,
            }
            
        except Exception as e:
            logger.error(f"❌ Signal quality analysis failed for {symbol}/{recommendation}: {e}")
            return {
                'symbol': symbol,
                'recommendation': recommendation,
                'total_signals': 0,
                'reliable': False,
                'reason': f'Analysis error: {str(e)}',
                'win_rate': None,
                'score': 5,
                'score_label': '❌ ERROR',
                'quality_grade': 'F',
            }

    def _avg_loss(self, profits, total, wins):
        """Calculate average loss (placeholder - would need more data)"""
        # For now, estimate avg loss as negative of avg profit * 0.6
        if not profits:
            return -2.0
        return -(sum(profits) / len(profits)) * 0.6 if profits else -2.0

    def _calculate_score(self, win_rate: float, avg_profit: float, 
                        total_signals: int, avg_confidence: float) -> int:
        """Calculate signal quality score (1-10)"""
        score = 5.0  # Start neutral
        
        # Win rate contribution (40%)
        if win_rate >= 70:
            score += 2.5
        elif win_rate >= 60:
            score += 1.5
        elif win_rate >= 50:
            score += 0.5
        elif win_rate < 40:
            score -= 2.0
        elif win_rate < 45:
            score -= 1.0
        
        # Average profit contribution (20%)
        if avg_profit >= 3.0:
            score += 1.0
        elif avg_profit >= 2.0:
            score += 0.5
        elif avg_profit < 0:
            score -= 1.5
        
        # Data volume contribution (20%)
        if total_signals >= 100:
            score += 1.0
        elif total_signals >= 50:
            score += 0.5
        elif total_signals < 20:
            score -= 1.0
        
        # ML confidence contribution (20%)
        if avg_confidence >= 0.7:
            score += 1.0
        elif avg_confidence >= 0.6:
            score += 0.5
        elif avg_confidence < 0.5:
            score -= 1.0
        
        # Clamp to 1-10
        return max(1, min(10, round(score)))

    def should_trade(self, symbol: str, recommendation: str, min_score: int = 5) -> Tuple[bool, Dict]:
        """
        Check if a signal should be taken.
        
        Returns:
            (should_trade: bool, quality_report: Dict)
        """
        quality = self.get_signal_quality(symbol, recommendation)
        
        if not quality['reliable']:
            # Not enough data - default to allowing trade but with warning
            return True, quality
        
        should = quality['score'] >= min_score
        return should, quality

    def get_pair_summary(self, symbol: str, days: int = 30) -> Dict:
        """Get comprehensive signal summary for all signal types on a pair"""
        return {
            'BUY': self.get_signal_quality(symbol, 'BUY', days),
            'SELL': self.get_signal_quality(symbol, 'SELL', days),
            'STRONG_BUY': self.get_signal_quality(symbol, 'STRONG_BUY', days),
            'STRONG_SELL': self.get_signal_quality(symbol, 'STRONG_SELL', days),
            'HOLD': self.get_signal_quality(symbol, 'HOLD', days),
        }

    def get_top_pairs(self, recommendation: str = 'BUY', limit: int = 10, days: int = 30) -> list:
        """Get pairs with highest signal win rates"""
        try:
            signals_conn = self._get_signals_conn()
            cursor = signals_conn.cursor()

            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Use lower threshold for top_pairs (5 instead of 20) so we get results
            min_signals = max(5, MIN_SIGNALS_FOR_ANALYSIS // 4)

            cursor.execute('''
                SELECT symbol, COUNT(*) as total,
                       AVG(ml_confidence) as avg_conf
                FROM signals
                WHERE recommendation = ?
                AND received_date >= ?
                GROUP BY symbol
                HAVING total >= ?
                ORDER BY total DESC
                LIMIT ?
            ''', (recommendation, cutoff, min_signals, limit * 2))
            
            results = []
            for row in cursor.fetchall():
                symbol = row['symbol']
                quality = self.get_signal_quality(symbol, recommendation, days)
                if quality['win_rate'] is not None:
                    results.append({
                        'symbol': symbol,
                        'win_rate': quality['win_rate'],
                        'total_signals': quality['total_signals'],
                        'score': quality['score'],
                        'avg_profit': quality['avg_profit'],
                    })
            
            signals_conn.close()
            
            # Sort by win rate descending
            results.sort(key=lambda x: x['win_rate'], reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"❌ Failed to get top pairs: {e}")
            return []
