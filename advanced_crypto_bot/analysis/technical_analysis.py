# Tujuan: Perhitungan indikator teknikal untuk signal trading.
# Caller: TradingEngine, signal pipeline, scalper analisa.
# Dependensi: pandas, numpy, price OHLCV data.
# Main Functions: class TechnicalAnalysis.
# Side Effects: Pure computation; no DB/HTTP.
import pandas as pd
import numpy as np
from datetime import datetime
from core.config import Config
import logging

logger = logging.getLogger(__name__)

class TechnicalAnalysis:
    def __init__(self, df):
        """Initialize TechnicalAnalysis with price data.

        Args:
            df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume']

        Raises:
            ValueError: If DataFrame is empty or missing required columns
        """
        # Validate input
        if df is None or df.empty:
            raise ValueError("DataFrame is empty or None")

        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # Check minimum data requirement (LOWER from 200 to 50 for more signals)
        # Bot uses 60 for ML, but TA was requiring 200 which is too strict
        min_periods = 50  # Was: max(Config.SMA_PERIODS...) = 200, now 50
        if len(df) < min_periods:
            raise ValueError(f"Insufficient data: {len(df)} rows, need at least {min_periods}")

        self.df = df.copy()
        self.calculate_all_indicators()

    def calculate_all_indicators(self):
        """Calculate all technical indicators with error handling."""
        df = self.df

        # Validate data quality
        if df['close'].isna().all():
            raise ValueError("All close prices are NaN")
        
        # Moving Averages
        for period in Config.SMA_PERIODS:
            df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
        
        for period in Config.EMA_PERIODS:
            df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        
        # RSI
        df['rsi'] = self._calculate_rsi(df['close'], Config.RSI_PERIOD)
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = self._calculate_macd(df['close'])
        
        # Bollinger Bands
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = self._calculate_bollinger(df['close'])
        
        # ATR
        df['atr'] = self._calculate_atr(df)
        
        # Stochastic
        df['stoch_k'], df['stoch_d'] = self._calculate_stochastic(df)
        
        # ADX
        df['adx'] = self._calculate_adx(df)
        
        # OBV
        df['obv'] = self._calculate_obv(df)
        
        # Volume SMA
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        
        # Price Change
        df['price_change'] = df['close'].pct_change() * 100
        df['price_change_5'] = df['close'].pct_change(periods=5) * 100
        df['price_change_10'] = df['close'].pct_change(periods=10) * 100
        
        # Volatility
        df['volatility'] = df['close'].rolling(window=20).std() / df['close'].rolling(window=20).mean() * 100
        
        self.df = df
    
    def _calculate_rsi(self, prices, period):
        """Calculate RSI with division by zero protection.

        Returns RSI values (0-100), handling edge cases where loss = 0.
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        # Handle division by zero: if loss is 0, RSI = 100 (all gains)
        rs = pd.Series(np.where(loss == 0, np.inf, gain / loss), index=prices.index)

        # Calculate RSI: 100 - (100 / (1 + RS))
        rsi = 100 - (100 / (1 + rs))

        # Handle extreme values
        rsi = rsi.replace([np.inf, -np.inf], np.nan)
        rsi = rsi.fillna(50)  # Neutral value for undefined RSI

        # Clamp to valid range
        return rsi.clip(0, 100)
    
    def _calculate_macd(self, prices):
        ema_fast = prices.ewm(span=Config.MACD_FAST, adjust=False).mean()
        ema_slow = prices.ewm(span=Config.MACD_SLOW, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=Config.MACD_SIGNAL, adjust=False).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist
    
    def _calculate_bollinger(self, prices):
        """Calculate Bollinger Bands with zero standard deviation handling."""
        middle = prices.rolling(window=Config.BB_PERIOD).mean()
        std = prices.rolling(window=Config.BB_PERIOD).std()

        # Handle zero std: use small epsilon to prevent identical upper/lower bands
        std = std.replace(0, 0.0001)

        upper = middle + (std * Config.BB_STD)
        lower = middle - (std * Config.BB_STD)

        return upper, middle, lower
    
    def _calculate_atr(self, df):
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=Config.ATR_PERIOD).mean()
    
    def _calculate_stochastic(self, df):
        """Calculate Stochastic Oscillator with division by zero handling."""
        low_14 = df['low'].rolling(window=14).min()
        high_14 = df['high'].rolling(window=14).max()

        # Handle case where high == low (no price movement)
        range_val = high_14 - low_14
        range_val = range_val.replace(0, 0.0001)  # Prevent division by zero

        k = 100 * ((df['close'] - low_14) / range_val)
        d = k.rolling(window=3).mean()

        # Clamp to valid range
        k = k.clip(0, 100)
        d = d.clip(0, 100)

        return k, d
    
    def _calculate_adx(self, df):
        """Calculate ADX with division by zero handling."""
        high = df['high']
        low = df['low']
        close = df['close']

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.clip(lower=0)
        minus_dm = minus_dm.clip(lower=0)

        tr = self._calculate_atr(df)

        # Handle division by zero for TR
        tr_safe = tr.replace(0, np.nan)

        plus_di = 100 * (plus_dm.rolling(window=14).mean() / tr_safe)
        minus_di = 100 * (minus_dm.rolling(window=14).mean() / tr_safe)

        # Handle case where plus_di + minus_di = 0
        di_sum = plus_di + minus_di
        di_sum_safe = di_sum.replace(0, np.nan)

        dx = 100 * abs(plus_di - minus_di) / di_sum_safe
        adx = dx.rolling(window=14).mean()

        # Fill NaN values with 0 (neutral trend strength)
        adx = adx.fillna(0)

        return adx
    
    def _calculate_obv(self, df):
        obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        return obv
    
    def get_signals(self):
        """Generate trading signals from indicators with validation."""
        df = self.df

        # Validate we have enough data
        if len(df) < 2:
            logger.warning("Insufficient data for signal generation")
            return {
                'timestamp': datetime.now(),
                'price': 0,
                'indicators': {},
                'strength': 0,
                'buy_signals': 0,
                'sell_signals': 0,
                'recommendation': 'HOLD',
                'reason': 'Insufficient data'
            }

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # Validate and fallback close price
        close_price = latest.get('close')
        if pd.isna(close_price) or close_price <= 0:
            # Fallback to open, high, or low if close is invalid
            fallback_price = latest.get('open')
            if pd.isna(fallback_price) or fallback_price <= 0:
                fallback_price = latest.get('high')
            if pd.isna(fallback_price) or fallback_price <= 0:
                fallback_price = latest.get('low')
            if pd.isna(fallback_price) or fallback_price <= 0:
                logger.warning(f"All price fields (close/open/high/low) are invalid: {latest.to_dict()}")
                return {
                    'timestamp': datetime.now(),
                    'price': 0,
                    'indicators': {},
                    'strength': 0,
                    'buy_signals': 0,
                    'sell_signals': 0,
                    'recommendation': 'HOLD',
                    'reason': 'Invalid price data'
                }
            logger.warning(f"Invalid close price {close_price}, using fallback: {fallback_price}")
            latest['close'] = fallback_price
            close_price = fallback_price

        # Ensure price is positive
        if close_price <= 0:
            logger.warning(f"Fallback price is still invalid: {close_price}")
            return {
                'timestamp': datetime.now(),
                'price': 0,
                'indicators': {},
                'strength': 0,
                'buy_signals': 0,
                'sell_signals': 0,
                'recommendation': 'HOLD',
                'reason': 'Invalid price data'
            }
        
        signals = {
            'timestamp': datetime.now(),
            'price': latest['close'],
            'indicators': {},
            'strength': 0,
            'buy_signals': 0,
            'sell_signals': 0
        }
        
        # RSI Signal
        if latest['rsi'] < Config.RSI_OVERSOLD:
            signals['indicators']['rsi'] = 'OVERSOLD'
            signals['buy_signals'] += 1
        elif latest['rsi'] > Config.RSI_OVERBOUGHT:
            signals['indicators']['rsi'] = 'OVERBOUGHT'
            signals['sell_signals'] += 1
        else:
            signals['indicators']['rsi'] = 'NEUTRAL'
        
        # MACD Signal
        if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            signals['indicators']['macd'] = 'BULLISH_CROSS'
            signals['buy_signals'] += 1
        elif latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            signals['indicators']['macd'] = 'BEARISH_CROSS'
            signals['sell_signals'] += 1
        elif latest['macd'] > latest['macd_signal']:
            signals['indicators']['macd'] = 'BULLISH'
            signals['buy_signals'] += 0.5
        else:
            signals['indicators']['macd'] = 'BEARISH'
            signals['sell_signals'] += 0.5
        
        # MA Signal
        if latest['close'] > latest['sma_20'] > latest['sma_50']:
            signals['indicators']['ma_trend'] = 'BULLISH'
            signals['buy_signals'] += 1
        elif latest['close'] < latest['sma_20'] < latest['sma_50']:
            signals['indicators']['ma_trend'] = 'BEARISH'
            signals['sell_signals'] += 1
        else:
            signals['indicators']['ma_trend'] = 'NEUTRAL'
        
        # Bollinger Bands
        if latest['close'] < latest['bb_lower']:
            signals['indicators']['bb'] = 'OVERSOLD'
            signals['buy_signals'] += 1
        elif latest['close'] > latest['bb_upper']:
            signals['indicators']['bb'] = 'OVERBOUGHT'
            signals['sell_signals'] += 1
        else:
            signals['indicators']['bb'] = 'NEUTRAL'
        
        # Volume
        if latest['volume'] > latest['volume_sma'] * 1.5:
            signals['indicators']['volume'] = 'HIGH'
            signals['buy_signals'] += 0.5 if latest['close'] > prev['close'] else 0
            signals['sell_signals'] += 0.5 if latest['close'] < prev['close'] else 0
        else:
            signals['indicators']['volume'] = 'NORMAL'

        # =====================================================================
        # FIX #1: TA Strength Calculation - Weighted Average (Bug Fix)
        # =====================================================================
        # OLD BUG: (buy - sell) / total → gave -1.0 when only 1 indicator bearish
        # NEW: Sum of weighted scores / number of indicators
        # Each indicator: -1 (strong bearish), -0.5 (bearish), 0 (neutral), +0.5 (bullish), +1 (strong bullish)
        # =====================================================================
        #
        # Bug HIGH #7 (audit 2026-06-07): TA Strength bias ±0.10
        # Root cause: MACD selalu BULLISH/BEARISH (±0.5) saat tidak ada cross, dan
        # 4 indikator lain biasanya NEUTRAL di pasar sideways → strength = ±0.5/5
        # = ±0.10 → 67% sample stuck di ±0.10. Decision layer & quality engine tidak
        # bisa membedakan setup bagus vs buruk.
        #
        # Fix: tambah komponen kontinu (tilt) untuk RSI/MACD/MA/BB/Volume sehingga
        # nilai TA Strength jadi continuous di rentang [-1, +1], bukan terkonsentrasi
        # di kelipatan 0.20 (=1/5).
        # =====================================================================
        indicator_scores = []

        # RSI: -1 (oversold→bullish), +1 (overbought→bearish), wait no...
        # RSI oversold = bullish opportunity → +1
        # RSI overbought = bearish risk → -1
        rsi_signal = signals['indicators'].get('rsi', 'NEUTRAL')
        rsi_value = float(latest.get('rsi', 50.0))
        if pd.isna(rsi_value):
            rsi_value = 50.0
        if rsi_signal == 'OVERSOLD':
            indicator_scores.append(1.0)    # Oversold → bullish
        elif rsi_signal == 'OVERBOUGHT':
            indicator_scores.append(-1.0)   # Overbought → bearish
        else:
            # Continuous tilt: RSI 50 = neutral, 30 = mild bullish, 70 = mild bearish.
            # Map [30, 70] linearly to [+0.5, -0.5] so the score reflects how close
            # we are to the threshold. Clamp to [-0.5, +0.5] for non-extreme region.
            tilt = (50.0 - rsi_value) / 40.0  # 30→+0.5, 70→-0.5, 50→0
            indicator_scores.append(max(-0.5, min(0.5, tilt)))

        # MACD: +1 (bullish), -1 (bearish), ±0.5 (cross)
        macd_signal = signals['indicators'].get('macd', 'NEUTRAL')
        macd_hist_val = float(latest.get('macd_hist', 0.0) or 0.0)
        close_val = float(latest['close'])
        # Histogram magnitude relative to price gives continuous strength
        # Use a scaling factor that maps typical hist magnitudes (~0.1% of price)
        # to the [0, 0.5] range so it's meaningful but doesn't dominate.
        macd_tilt = 0.0
        if close_val > 0 and not pd.isna(macd_hist_val):
            # Scale histogram by 1000/close so magnitude lives in a usable range.
            # Typical macd_hist for crypto IDR pairs: 0.01-1.0% of close.
            macd_tilt = max(-0.4, min(0.4, macd_hist_val / close_val * 200.0))

        if macd_signal == 'BULLISH_CROSS':
            indicator_scores.append(1.0)
        elif macd_signal == 'BEARISH_CROSS':
            indicator_scores.append(-1.0)
        elif macd_signal == 'BULLISH':
            # Base 0.3 + continuous histogram tilt → varies in [0.0, 0.7]
            indicator_scores.append(0.3 + max(0.0, macd_tilt))
        elif macd_signal == 'BEARISH':
            # Base -0.3 + continuous histogram tilt → varies in [-0.7, 0.0]
            indicator_scores.append(-0.3 + min(0.0, macd_tilt))
        else:
            indicator_scores.append(0.0)

        # MA Trend: +1 (bullish alignment), -1 (bearish alignment)
        ma_signal = signals['indicators'].get('ma_trend', 'NEUTRAL')
        sma_20 = float(latest.get('sma_20', close_val) or close_val)
        # Continuous: distance from SMA20 as percentage, clipped.
        ma_tilt = 0.0
        if sma_20 > 0 and not pd.isna(sma_20):
            ma_tilt = max(-0.5, min(0.5, (close_val - sma_20) / sma_20 * 25.0))
        if ma_signal == 'BULLISH':
            indicator_scores.append(1.0)
        elif ma_signal == 'BEARISH':
            indicator_scores.append(-1.0)
        else:
            # NEUTRAL: use proximity to SMA20 as soft tilt
            indicator_scores.append(ma_tilt)

        # Bollinger Bands: +1 (oversold at lower band), -1 (overbought at upper band)
        bb_signal = signals['indicators'].get('bb', 'NEUTRAL')
        bb_upper = float(latest.get('bb_upper', close_val) or close_val)
        bb_lower = float(latest.get('bb_lower', close_val) or close_val)
        bb_middle = float(latest.get('bb_middle', close_val) or close_val)
        # %B-style position within bands: -1 at lower, 0 at middle, +1 at upper
        bb_tilt = 0.0
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            # Position relative to middle, scaled into [-0.5, +0.5] for non-extreme cases.
            # Note inverted sign: closer to LOWER → bullish (+), closer to UPPER → bearish (-)
            pos = (close_val - bb_middle) / (bb_range / 2.0)
            bb_tilt = max(-0.5, min(0.5, -pos * 0.5))
        if bb_signal == 'OVERSOLD':
            indicator_scores.append(1.0)
        elif bb_signal == 'OVERBOUGHT':
            indicator_scores.append(-1.0)
        else:
            indicator_scores.append(bb_tilt)

        # Volume: directional confirmation
        vol_signal = signals['indicators'].get('volume', 'NORMAL')
        if vol_signal == 'HIGH':
            if latest['close'] > prev['close']:
                indicator_scores.append(0.5)   # High volume + price up = bullish
            else:
                indicator_scores.append(-0.5)  # High volume + price down = bearish
        else:
            # Continuous tilt from price change vs prev (small influence even at normal vol)
            try:
                pct = (close_val - float(prev['close'])) / float(prev['close']) if float(prev['close']) > 0 else 0
                indicator_scores.append(max(-0.2, min(0.2, pct * 5.0)))
            except (TypeError, ZeroDivisionError, ValueError):
                indicator_scores.append(0.0)

        # Calculate weighted average strength (-1.0 to +1.0)
        num_indicators = len(indicator_scores)
        signals['strength'] = sum(indicator_scores) / num_indicators if num_indicators > 0 else 0.0

        # Store individual scores for debugging
        signals['indicator_scores'] = indicator_scores
        signals['indicator_names'] = ['rsi', 'macd', 'ma_trend', 'bb', 'volume']

        # Determine TA recommendation (for standalone TA signal)
        # ✅ BALANCED thresholds for BUY and SELL - symmetric
        # FIX: SELL thresholds were too high, now balanced with BUY
        if signals['strength'] > 0.5:
            signals['recommendation'] = 'STRONG_BUY'
        elif signals['strength'] > 0.05:
            signals['recommendation'] = 'BUY'
        elif signals['strength'] < -0.5:
            signals['recommendation'] = 'STRONG_SELL'
        elif signals['strength'] < -0.05:  # FIX: Was -0.2, now -0.05 (symmetric with BUY)
            signals['recommendation'] = 'SELL'
        else:
            signals['recommendation'] = 'HOLD'

        # Log strength for debugging signals
        logger.debug(f"📈 TA Signal strength for {signals.get('pair', 'unknown')}: {signals['strength']:.3f} → {signals['recommendation']}")

        return signals
    
    def get_support_resistance(self, levels=3):
        """Find support and resistance levels"""
        df = self.df
        
        # Find local maxima and minima
        from scipy.signal import argrelextrema
        
        highs = argrelextrema(df['high'].values, np.greater, order=10)[0]
        lows = argrelextrema(df['low'].values, np.less, order=10)[0]
        
        resistance = sorted(df['high'].iloc[highs].nlargest(levels), reverse=True)
        support = sorted(df['low'].iloc[lows].nsmallest(levels))
        
        return {
            'resistance': resistance.tolist() if len(resistance) > 0 else [df['close'].iloc[-1] * 1.05],
            'support': support.tolist() if len(support) > 0 else [df['close'].iloc[-1] * 0.95]
        }