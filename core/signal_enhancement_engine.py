"""
Signal Enhancement Engine
==========================
5 fitur untuk meningkatkan kualitas signal:
1. Volume Check - Validates signal based on 24h trading volume
2. VWAP - Volume Weighted Average Price
3. Ichimoku Cloud - Comprehensive trend analysis
4. Divergence Detection - RSI/MACD divergence from price
5. Candlestick Patterns - Price action patterns
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class SignalEnhancementEngine:
    """Engine untuk enhanced signal analysis"""
    
    def __init__(self, config=None):
        self.config = config
        if config is None:
            from core.signal_enhancement_config import signal_enhancement_config
            self.config = signal_enhancement_config
    
    # =========================================================================
    # FEATURE 1: VOLUME CHECK
    # =========================================================================
    
    def check_volume(self, volume_24h: float) -> Dict[str, Any]:
        """
        Validate signal based on 24h trading volume.
        
        Args:
            volume_24h: Volume dalam IDR
            
        Returns:
            Dict dengan:
            - confidence: float (0.0 - 1.0)
            - is_valid: bool
            - reason: str
        """
        if not self.config.is_enabled("volume_check"):
            return {"confidence": 1.0, "is_valid": True, "reason": "disabled"}
        
        min_volume = self.config.get_config("volume_check").get("min_volume_idr", 100_000_000)
        
        if volume_24h <= 0:
            return {
                "confidence": 0.0,
                "is_valid": False,
                "reason": "No volume data available"
            }
        
        if volume_24h < min_volume * 0.5:
            return {
                "confidence": 0.0,
                "is_valid": False,
                "reason": f"Volume too low: {volume_24h:,.0f} IDR (min: {min_volume:,.0f})"
            }
        elif volume_24h < min_volume:
            ratio = volume_24h / min_volume
            confidence = 0.3 + (ratio * 0.4)
            return {
                "confidence": confidence,
                "is_valid": confidence >= 0.3,
                "reason": f"Low volume: {volume_24h:,.0f} IDR"
            }
        elif volume_24h < min_volume * 3:
            ratio = volume_24h / (min_volume * 3)
            confidence = 0.8 + (ratio * 0.2)
            return {
                "confidence": confidence,
                "is_valid": True,
                "reason": f"Good volume: {volume_24h:,.0f} IDR"
            }
        else:
            return {
                "confidence": 1.0,
                "is_valid": True,
                "reason": f"Excellent volume: {volume_24h:,.0f} IDR"
            }
    
    # =========================================================================
    # FEATURE 2: VWAP (Volume Weighted Average Price)
    # =========================================================================
    
    def calculate_vwap(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """
        Calculate VWAP untuk periode yang ditentukan.
        
        Args:
            df: DataFrame dengan 'high', 'low', 'close', 'volume'
            period: Jumlah candle untuk perhitungan
            
        Returns:
            VWAP value atau None jika tidak bisa dihitung
        """
        if not self.config.is_enabled("vwap"):
            return None
        
        if df is None or len(df) < period:
            return None
        
        try:
            # Typical Price = (High + Low + Close) / 3
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            
            # TP * Volume
            tpv = typical_price * df['volume']
            
            # Cumulative untuk period
            cum_tpv = tpv.rolling(window=period, min_periods=1).sum()
            cum_vol = df['volume'].rolling(window=period, min_periods=1).sum()
            
            # VWAP
            vwap = cum_tpv / cum_vol
            
            return float(vwap.iloc[-1])
        except Exception as e:
            logger.debug(f"VWAP calculation error: {e}")
            return None
    
    def get_vwap_signal(self, current_price: float, vwap: float) -> str:
        """
        Get signal direction dari VWAP.
        
        Returns:
            'bullish', 'bearish', atau 'neutral'
        """
        if vwap is None or vwap <= 0:
            return 'neutral'
        
        distance_pct = (current_price - vwap) / vwap * 100
        
        if distance_pct > 0.5:  # 0.5% above VWAP
            return 'bullish'
        elif distance_pct < -0.5:  # 0.5% below VWAP
            return 'bearish'
        else:
            return 'neutral'
    
    # =========================================================================
    # FEATURE 3: ICHIMOKU CLOUD
    # =========================================================================
    
    def calculate_ichimoku(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Calculate Ichimoku Cloud indicators.
        
        Returns:
            Dict dengan tenkan_sen, kijun_sen, cloud_top, cloud_bottom, signal
        """
        if not self.config.is_enabled("ichimoku"):
            return None
        
        cfg = self.config.get_config("ichimoku")
        conv = cfg.get("conversion_period", 9)
        base = cfg.get("base_period", 26)
        span_b = cfg.get("span_b_period", 52)
        delay = cfg.get("delay_period", 26)
        
        if df is None or len(df) < span_b + delay:
            return None
        
        try:
            # Tenkan-sen (Conversion Line)
            high_conv = df['high'].rolling(window=conv).max()
            low_conv = df['low'].rolling(window=conv).min()
            tenkan_sen = (high_conv + low_conv) / 2
            
            # Kijun-sen (Base Line)
            high_base = df['high'].rolling(window=base).max()
            low_base = df['low'].rolling(window=base).min()
            kijun_sen = (high_base + low_base) / 2
            
            # Senkou Span A (Leading Span A)
            senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(delay)
            
            # Senkou Span B (Leading Span B)
            high_span = df['high'].rolling(window=span_b).max()
            low_span = df['low'].rolling(window=span_b).min()
            senkou_b = ((high_span + low_span) / 2).shift(delay)
            
            # Cloud
            cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
            cloud_bottom = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
            
            # Latest values
            latest_idx = -1
            current_price = df['close'].iloc[latest_idx]
            tenkan_val = tenkan_sen.iloc[latest_idx]
            kijun_val = kijun_sen.iloc[latest_idx]
            cloud_top_val = cloud_top.iloc[latest_idx]
            cloud_bottom_val = cloud_bottom.iloc[latest_idx]
            
            # Determine signal
            above_cloud = current_price > cloud_top_val
            below_cloud = current_price < cloud_bottom_val
            tenkan_above_kijun = tenkan_val > kijun_val
            
            if above_cloud and tenkan_above_kijun:
                signal = 'bullish'
            elif below_cloud and not tenkan_above_kijun:
                signal = 'bearish'
            else:
                signal = 'neutral'
            
            return {
                "tenkan_sen": float(tenkan_val),
                "kijun_sen": float(kijun_val),
                "cloud_top": float(cloud_top_val),
                "cloud_bottom": float(cloud_bottom_val),
                "signal": signal
            }
        except Exception as e:
            logger.debug(f"Ichimoku calculation error: {e}")
            return None
    
    # =========================================================================
    # FEATURE 4: DIVERGENCE DETECTION
    # =========================================================================
    
    def _find_pivots(self, data: np.ndarray, threshold: float = 0.03) -> List[Dict]:
        """Find pivot points dalam data."""
        pivots = []
        if len(data) < 5:
            return pivots
        
        for i in range(2, len(data) - 2):
            # Check for local high
            if (data[i] > data[i-1] and data[i] > data[i-2] and
                data[i] > data[i+1] and data[i] > data[i+2]):
                pivots.append({'type': 'high', 'index': i, 'value': data[i]})
            # Check for local low
            elif (data[i] < data[i-1] and data[i] < data[i-2] and
                  data[i] < data[i+1] and data[i] < data[i+2]):
                pivots.append({'type': 'low', 'index': i, 'value': data[i]})
        
        return pivots
    
    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate RSI."""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.convolve(gains, np.ones(period)/period, mode='full')[:len(prices)]
        avg_loss = np.convolve(losses, np.ones(period)/period, mode='full')[:len(prices)]
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(self, prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate MACD line."""
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)
        macd_line = ema_fast - ema_slow
        signal_line = self._ema(macd_line, signal)
        return macd_line, signal_line
    
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        ema = np.zeros_like(data, dtype=float)
        ema[0] = data[0]
        multiplier = 2 / (period + 1)
        for i in range(1, len(data)):
            ema[i] = (data[i] - ema[i-1]) * multiplier + ema[i-1]
        return ema
    
    def detect_divergence(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect RSI dan MACD divergence dari price action.
        
        Returns:
            Dict dengan rsi_divergence, macd_divergence, signal
        """
        if not self.config.is_enabled("divergence"):
            return {
                "rsi_divergence": "none",
                "macd_divergence": "none",
                "signal": "neutral"
            }
        
        cfg = self.config.get_config("divergence")
        lookback = cfg.get("lookback", 20)
        rsi_period = cfg.get("rsi_period", 14)
        
        if df is None or len(df) < lookback + 5:
            return {
                "rsi_divergence": "none",
                "macd_divergence": "none",
                "signal": "neutral"
            }
        
        try:
            # Get recent data
            recent_df = df.tail(lookback).copy()
            prices = recent_df['close'].values
            
            # RSI divergence
            rsi = self._calculate_rsi(prices, rsi_period)
            price_pivots = self._find_pivots(prices, 0.03)
            rsi_pivots = self._find_pivots(rsi, 0.05)
            
            rsi_div = "none"
            if len(price_pivots) >= 2 and len(rsi_pivots) >= 2:
                last_price = price_pivots[-1]
                prev_price = price_pivots[-2]
                last_rsi = rsi_pivots[-1]
                prev_rsi = rsi_pivots[-2]
                
                # Bullish: price lower low, RSI higher low
                if (last_price['type'] == 'low' and prev_price['type'] == 'low' and
                    last_rsi['type'] == 'low' and prev_rsi['type'] == 'low'):
                    if (last_price['value'] < prev_price['value'] and 
                        last_rsi['value'] > prev_rsi['value']):
                        rsi_div = "bullish"
                
                # Bearish: price higher high, RSI lower high
                elif (last_price['type'] == 'high' and prev_price['type'] == 'high' and
                      last_rsi['type'] == 'high' and prev_rsi['type'] == 'high'):
                    if (last_price['value'] > prev_price['value'] and 
                        last_rsi['value'] < prev_rsi['value']):
                        rsi_div = "bearish"
            
            # MACD divergence (simplified - use histogram direction)
            macd_line, signal_line = self._calculate_macd(
                prices,
                cfg.get("macd_fast", 12),
                cfg.get("macd_slow", 26),
                cfg.get("macd_signal", 9)
            )
            macd_hist = macd_line - signal_line
            
            macd_div = "none"
            if len(macd_hist) >= 5:
                # Check if MACD turning while price continuing
                price_trend = prices[-1] - prices[-5]
                macd_trend = macd_hist[-1] - macd_hist[-5]
                
                if price_trend > 0 and macd_trend < 0:
                    macd_div = "bearish"  # Price up, MACD down
                elif price_trend < 0 and macd_trend > 0:
                    macd_div = "bullish"  # Price down, MACD up
            
            # Combined signal
            if rsi_div in ["bullish", "bearish"]:
                signal = rsi_div
            elif macd_div in ["bullish", "bearish"]:
                signal = macd_div
            else:
                signal = "neutral"
            
            return {
                "rsi_divergence": rsi_div,
                "macd_divergence": macd_div,
                "signal": signal
            }
        except Exception as e:
            logger.debug(f"Divergence detection error: {e}")
            return {
                "rsi_divergence": "none",
                "macd_divergence": "none",
                "signal": "neutral"
            }
    
    # =========================================================================
    # FEATURE 5: CANDLESTICK PATTERNS
    # =========================================================================
    
    def detect_candlestick_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect common candlestick patterns.
        
        Returns:
            Dict dengan patterns detected, signal
        """
        if not self.config.is_enabled("candlestick_patterns"):
            return {
                "patterns": [],
                "signal": "neutral"
            }
        
        if df is None or len(df) < 3:
            return {
                "patterns": [],
                "signal": "neutral"
            }
        
        patterns = []
        latest = df.iloc[-1]
        prev1 = df.iloc[-2] if len(df) > 1 else None
        prev2 = df.iloc[-3] if len(df) > 2 else None
        
        # Body calculations
        latest_body = latest['close'] - latest['open']
        latest_body_size = abs(latest_body)
        latest_range = latest['high'] - latest['low']
        
        if latest_range > 0:
            upper_shadow = latest['high'] - max(latest['close'], latest['open'])
            lower_shadow = min(latest['close'], latest['open']) - latest['low']
            body_to_range = latest_body_size / latest_range
        
        # HAMMER: Small body, long lower shadow
        if latest_range > 0 and body_to_range < 0.3 and lower_shadow > latest_body_size * 2:
            patterns.append('hammer')
        
        # SHOOTING STAR: Small body, long upper shadow
        if latest_range > 0 and body_to_range < 0.3 and upper_shadow > latest_body_size * 2:
            patterns.append('shooting_star')
        
        # BULLISH ENGULFING
        if prev1 is not None:
            prev1_body = prev1['close'] - prev1['open']
            if (latest_body > 0 and prev1_body < 0 and  # Current green, prev red
                latest['open'] < prev1['close'] and latest['close'] > prev1['open']):
                patterns.append('bullish_engulfing')
            
            # BEARISH ENGULFING
            if (latest_body < 0 and prev1_body > 0 and  # Current red, prev green
                latest['open'] > prev1['close'] and latest['close'] < prev1['open']):
                patterns.append('bearish_engulfing')
        
        # MORNING STAR (3-candle pattern)
        if prev1 is not None and prev2 is not None:
            prev2_body = prev2['close'] - prev2['open']
            prev1_body = prev1['close'] - prev1['open']
            
            if (prev2_body < 0 and  # First candle red
                abs(prev1_body) < abs(prev2_body) * 0.5 and  # Second candle small
                latest_body > 0 and  # Third candle green
                latest['close'] > (prev2['open'] + prev2['close']) / 2):  # Close into first
                patterns.append('morning_star')
            
            # EVENING STAR (opposite)
            elif (prev2_body > 0 and
                  abs(prev1_body) < abs(prev2_body) * 0.5 and
                  latest_body < 0 and
                  latest['close'] < (prev2['open'] + prev2['close']) / 2):
                patterns.append('evening_star')
        
        # DOJI
        if latest_range > 0 and body_to_range < 0.1:
            patterns.append('doji')
        
        # Determine signal
        bullish_patterns = ['hammer', 'bullish_engulfing', 'morning_star', 'inverted_hammer']
        bearish_patterns = ['shooting_star', 'bearish_engulfing', 'evening_star', 'hanging_man']
        
        bullish_count = sum(1 for p in patterns if p in bullish_patterns)
        bearish_count = sum(1 for p in patterns if p in bearish_patterns)
        
        if bullish_count > bearish_count:
            signal = 'bullish'
        elif bearish_count > bullish_count:
            signal = 'bearish'
        else:
            signal = 'neutral'
        
        return {
            "patterns": patterns,
            "signal": signal,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count
        }
    
    # =========================================================================
    # COMBINED ANALYSIS
    # =========================================================================
    
    def analyze(self, df: pd.DataFrame, current_price: float, 
                volume_24h: float = None, base_recommendation: str = 'HOLD') -> Dict[str, Any]:
        """
        Combined analysis dari semua feature.
        
        Args:
            df: Historical price data
            current_price: Current price
            volume_24h: 24h volume (optional)
            base_recommendation: Base recommendation dari existing logic
            
        Returns:
            Dict dengan semua hasil dan adjustment
        """
        results = {
            "enabled_features": [],
            "adjustments": [],
            "final_confidence_adjustment": 0.0,
            "should_override": False,
            "override_reason": ""
        }
        
        # 1. Volume Check
        if volume_24h is not None and volume_24h > 0:
            vol_result = self.check_volume(volume_24h)
            results['volume'] = vol_result
            if self.config.is_enabled("volume_check"):
                results["enabled_features"].append("volume_check")
                weight = self.config.get_weight("volume_check")
                if not vol_result['is_valid']:
                    results['should_override'] = True
                    results['override_reason'] = f"Volume: {vol_result['reason']}"
                else:
                    results['adjustments'].append(('volume', vol_result['confidence'], weight))
                    results['final_confidence_adjustment'] += vol_result['confidence'] * weight
        
        # 2. VWAP
        if self.config.is_enabled("vwap"):
            vwap = self.calculate_vwap(df)
            vwap_signal = self.get_vwap_signal(current_price, vwap) if vwap else 'neutral'
            results['vwap'] = {'value': vwap, 'signal': vwap_signal}
            results["enabled_features"].append("vwap")
            weight = self.config.get_weight("vwap")
            if vwap_signal == 'bullish':
                results['adjustments'].append(('bullish', weight))
                results['final_confidence_adjustment'] += weight
            elif vwap_signal == 'bearish':
                results['adjustments'].append(('bearish', -weight))
                results['final_confidence_adjustment'] -= weight
        
        # 3. Ichimoku
        if self.config.is_enabled("ichimoku"):
            ichimoku = self.calculate_ichimoku(df)
            results['ichimoku'] = ichimoku
            if ichimoku:
                results["enabled_features"].append("ichimoku")
                weight = self.config.get_weight("ichimoku")
                if ichimoku['signal'] == 'bullish':
                    results['adjustments'].append(('bullish', weight))
                    results['final_confidence_adjustment'] += weight
                elif ichimoku['signal'] == 'bearish':
                    results['adjustments'].append(('bearish', -weight))
                    results['final_confidence_adjustment'] -= weight
        
        # 4. Divergence
        if self.config.is_enabled("divergence"):
            divergence = self.detect_divergence(df)
            results['divergence'] = divergence
            if divergence['signal'] != 'neutral':
                results["enabled_features"].append("divergence")
                weight = self.config.get_weight("divergence")
                if divergence['signal'] == 'bullish':
                    results['adjustments'].append(('bullish', weight))
                    results['final_confidence_adjustment'] += weight
                elif divergence['signal'] == 'bearish':
                    results['adjustments'].append(('bearish', -weight))
                    results['final_confidence_adjustment'] -= weight
        
        # 5. Candlestick Patterns
        if self.config.is_enabled("candlestick_patterns"):
            candle = self.detect_candlestick_patterns(df)
            results['candlestick'] = candle
            if candle['signal'] != 'neutral':
                results["enabled_features"].append("candlestick_patterns")
                weight = self.config.get_weight("candlestick_patterns")
                if candle['signal'] == 'bullish':
                    results['adjustments'].append(('bullish', weight))
                    results['final_confidence_adjustment'] += weight
                elif candle['signal'] == 'bearish':
                    results['adjustments'].append(('bearish', -weight))
                    results['final_confidence_adjustment'] -= weight
        
        # Check for conflicting signals (reduce confidence)
        bullish_count = sum(1 for a in results['adjustments'] if a[0] == 'bullish')
        bearish_count = sum(1 for a in results['adjustments'] if a[0] == 'bearish')
        
        if bullish_count > 0 and bearish_count > 0:
            # Conflicting signals - reduce adjustment
            results['final_confidence_adjustment'] *= 0.5
            logger.debug(f"Conflicting signals detected: {bullish_count} bullish, {bearish_count} bearish")
        
        return results


# Global instance
signal_enhancement_engine = SignalEnhancementEngine()