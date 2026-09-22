#!/usr/bin/env python3
# Tujuan: Quality gate signal berbasis confluence, volume, dan cooldown.
# Caller: bot.py dan signal_pipeline.
# Dependensi: Config, pandas/numpy signal features.
# Main Functions: class SignalQualityEngine.
# Side Effects: In-memory cooldown/counters; no direct DB/HTTP.
"""
Signal Quality Engine V3
========================
Advanced signal generation dengan:
- Multi-timeframe analysis (15m primary, 4h trend filter)
- Volume confirmation requirement
- Confluence scoring system
- Cooldown period antar signal (30 menit)
- RSI overbought/oversold protection
- ML vs TA conflict detection

Usage:
    from signal_quality_engine import SignalQualityEngine
    
    engine = SignalQualityEngine()
    signal = engine.generate_signal(
        pair='BTCIDR',
        ta_signals={...},
        ml_prediction=True,
        ml_confidence=0.75,
        ml_signal_class='BUY',
        last_signal_time=datetime.now(),
        last_recommendation='HOLD'
    )
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger('crypto_bot')

# ============================================================================
# CONFIGURATION
# ============================================================================

# Cooldown period antar signal (menit) - OPTIMIZED for more signals
# Prioritas 1 2026-05-22: turun 15 → 10 supaya pipeline tidak menahan signal terlalu lama untuk crypto intraday
MINIMUM_SIGNAL_INTERVAL_MINUTES = 10

# Timeframe settings
PRIMARY_TIMEFRAME = '15m'  # Signal utama
TREND_TIMEFRAME = '4h'     # Trend filter

# Volume confirmation (lebih lenient - HIGH/NORMAL cukup)
VOLUME_CONFIRMATION_REQUIRED = False  # Changed: Jadi warning only, bukan reject

# Confluence scoring - VERY RELAXED untuk dapat signals
CONFLUENCE_MINIMUM_BUY = 1    # Sangat rendah
CONFLUENCE_MINIMUM_SELL = 1   # Sangat rendah
CONFLUENCE_STRONG_BUY = 2     # Sangat rendah
CONFLUENCE_STRONG_SELL = 2    # Sangat rendah

# Asymmetric thresholds (Opsi B - RELAXED):
# Both sides relaxed to allow more signals through pipeline.
# Enhancement layer may reduce confidence, so base thresholds must be lower.
STRONG_BUY_ML_CONFIDENCE = 0.50  # 2026-06-29: 0.64→0.50
STRONG_BUY_COMBINED_STRENGTH = -0.05
BUY_ML_CONFIDENCE = 0.40  # 2026-06-29: 0.50→0.40
BUY_COMBINED_STRENGTH = -0.10

STRONG_SELL_ML_CONFIDENCE = 0.70
STRONG_SELL_COMBINED_STRENGTH = -0.04
SELL_ML_CONFIDENCE = 0.58
SELL_COMBINED_STRENGTH = -0.02

# Confidence threshold minimum (lowered to allow more signals)
MIN_ML_CONFIDENCE = 0.55

# NEW: Volatility filter - HIGH volatility can cause false signals
VOLATILITY_ATR_MULTIPLIER = 3.0  # Don't trade if ATR > 3x average
VOLATILITY_CHECK_ENABLED = True  # Enable volatility filter

# NEW: Market Regime Detection
REGIME_SMA_FAST = 20    # Fast MA period
REGIME_SMA_SLOW = 50   # Slow MA period


class SignalQualityEngine:
    """
    Advanced signal generation dengan quality filters.
    """

    def __init__(self):
        self.signal_history: Dict[str, Dict] = {}  # {pair: {time, recommendation}}
        self.rejection_stats: Dict[str, int] = {}

        # NEW: Quant Mean Reversion Engine
        try:
            from quant.mean_reversion import MeanReversionEngine
            self.mean_reversion_engine = MeanReversionEngine()
            logger.info("✅ Quant Mean Reversion Engine loaded into Quality Engine")
        except Exception as e:
            self.mean_reversion_engine = None
            logger.warning(f"⚠️ Mean Reversion Engine not available: {e}")

        logger.info("✅ Signal Quality Engine V3 initialized")

    def _record_rejection(self, pair: str, reason_key: str, detail: str):
        """Track and log quality-engine rejection reasons without changing signal strategy."""
        count = self.rejection_stats.get(reason_key, 0) + 1
        self.rejection_stats[reason_key] = count
        logger.warning(
            f"🛡️ [SQE REJECT] {pair}: {reason_key} | {detail} | total={count}"
        )
    
    def detect_market_regime(self, df) -> Tuple[str, float]:
        """
        Detect market regime using MA alignment.
        
        Returns:
            (regime, position_multiplier)
            - 'TRENDING_UP': Full position (1.0)
            - 'TRENDING_DOWN': Full position (1.0)
            - 'RANGING': Half position (0.5)
            - 'VOLATILE': No trading (0.0)
        """
        try:
            close = df['close']
            sma_fast = close.rolling(REGIME_SMA_FAST).mean()
            sma_slow = close.rolling(REGIME_SMA_SLOW).mean()
            
            if len(sma_fast) < 2 or len(sma_slow) < 2:
                return 'UNKNOWN', 1.0
            
            fast = sma_fast.iloc[-1]
            slow = sma_slow.iloc[-1]
            
            if pd.isna(fast) or pd.isna(slow):
                return 'UNKNOWN', 1.0
            
            # Trend detection
            if fast > slow * 1.02:  # 2% above = uptrend
                return 'TRENDING_UP', 1.0
            elif fast < slow * 0.98:  # 2% below = downtrend
                return 'TRENDING_DOWN', 1.0
            else:
                # Check if close is within narrow range = ranging
                price_range = (close.max() - close.min()) / close.mean()
                if price_range < 0.02:  # <2% range = ranging
                    return 'RANGING', 0.5
                else:
                    return 'VOLATILE', 0.5
                    
        except Exception as e:
            logger.debug(f"Regime detection error: {e}")
            return 'UNKNOWN', 1.0

    # ========================================================================
    # NEW 2026-06-12: Higher-Timeframe (HTF) Trend Filter
    # ========================================================================
    # Konteks: data di `price_history` adalah TICK (polling 3-5 menit) bukan
    # candle 15m. open=high=low=close=last_price untuk tiap row, jadi indikator
    # range-based (ATR, BB width, candle pattern) degenerate di TF native.
    #
    # Solusi: resample ticks ke 1h aggregation. Ini menghasilkan OHLC real
    # (high=max tick dalam jam itu, low=min tick, dst). Sekaligus melebarkan
    # horizon — 200 ticks ≈ 10-16h jadi 10-16 candle 1h, cukup buat SMA pendek.
    # ========================================================================

    def compute_higher_tf_trend(
        self,
        df: pd.DataFrame,
        target_minutes: int = 60,
        sma_fast: int = 5,
        sma_slow: int = 10,
        trend_threshold_pct: float = 1.0,
    ) -> Dict:
        """Hitung trend direction di higher timeframe via resample tick → OHLC.

        Args:
            df: DataFrame tick dengan kolom timestamp + OHLCV (open=high=low=close
                untuk tick mode, tapi method ini juga jalan untuk candle real).
            target_minutes: Target candle size hasil resample. Default 60 (1h).
            sma_fast: Period SMA cepat di HTF. Default 5 candle (= 5 jam @ 1h).
            sma_slow: Period SMA lambat di HTF. Default 10 candle (= 10 jam @ 1h).
            trend_threshold_pct: Selisih SMA fast vs slow (%) untuk vonis trend.
                Default 1.0 (1%) — di bawah ini = SIDEWAYS.

        Returns:
            Dict {
                'trend': 'UP' | 'DOWN' | 'SIDEWAYS' | 'INSUFFICIENT_DATA',
                'sma_fast': float | None,
                'sma_slow': float | None,
                'spread_pct': float | None,   # (fast-slow)/slow * 100
                'htf_candles': int,           # jumlah candle hasil resample
                'tf': str,                    # label e.g. '1h'
            }
        """
        result = {
            'trend': 'INSUFFICIENT_DATA',
            'sma_fast': None,
            'sma_slow': None,
            'spread_pct': None,
            'htf_candles': 0,
            'tf': f'{target_minutes}min' if target_minutes < 60 else f'{target_minutes // 60}h',
        }

        if df is None or len(df) == 0:
            return result

        try:
            work = df.copy()
            # Pastikan timestamp sebagai index untuk resample.
            if 'timestamp' in work.columns:
                work['timestamp'] = pd.to_datetime(work['timestamp'], errors='coerce')
                work = work.dropna(subset=['timestamp']).set_index('timestamp')
            elif not isinstance(work.index, pd.DatetimeIndex):
                # Tidak bisa resample tanpa timestamp valid.
                return result

            # Resample. Kalau tick mode (high=low=close), OHLC tetap benar
            # (max/min lintas tick = high/low real); kalau candle real, hasil
            # tetap valid.
            agg = {}
            if 'open' in work.columns:
                agg['open'] = 'first'
            if 'high' in work.columns:
                agg['high'] = 'max'
            if 'low' in work.columns:
                agg['low'] = 'min'
            if 'close' in work.columns:
                agg['close'] = 'last'
            if 'volume' in work.columns:
                agg['volume'] = 'sum'

            if 'close' not in agg:
                return result

            rule = f'{target_minutes}min'
            htf = work.resample(rule).agg(agg).dropna(subset=['close'])
            result['htf_candles'] = len(htf)

            min_candles = max(sma_slow, sma_fast) + 1
            if len(htf) < min_candles:
                return result  # insufficient

            close = htf['close']
            fast = float(close.rolling(sma_fast).mean().iloc[-1])
            slow = float(close.rolling(sma_slow).mean().iloc[-1])

            if pd.isna(fast) or pd.isna(slow) or slow <= 0:
                return result

            spread_pct = (fast - slow) / slow * 100
            result['sma_fast'] = fast
            result['sma_slow'] = slow
            result['spread_pct'] = spread_pct

            if spread_pct > trend_threshold_pct:
                result['trend'] = 'UP'
            elif spread_pct < -trend_threshold_pct:
                result['trend'] = 'DOWN'
            else:
                result['trend'] = 'SIDEWAYS'

            return result

        except Exception as e:
            logger.debug(f"[HTF TREND] Resample/compute failed: {e}")
            return result

    def htf_alignment_score(self, signal_direction: str, htf_trend: str) -> int:
        """Confluence bonus/penalty dari alignment HTF trend dengan signal direction.

        Skema (kontribusi ke confluence_score):
            - BUY  + HTF UP        → +1  (aligned)
            - BUY  + HTF SIDEWAYS  →  0  (neutral)
            - BUY  + HTF DOWN      → -1  (counter-trend, hati-hati)
            - SELL + HTF DOWN      → +1  (aligned)
            - SELL + HTF SIDEWAYS  →  0
            - SELL + HTF UP        → -1
            - INSUFFICIENT_DATA    →  0  (jangan menghukum kalau data kurang)

        Sengaja tidak BLOCK signal — hanya nge-rank. Threshold `actionable`
        downstream akan reject signal yang skornya jatuh di bawah minimum
        confluence (CONFLUENCE_MINIMUM_BUY/SELL).
        """
        if htf_trend == 'INSUFFICIENT_DATA':
            return 0
        if signal_direction == 'BUY':
            if htf_trend == 'UP':
                return 1
            if htf_trend == 'DOWN':
                return -1
            return 0
        # SELL
        if htf_trend == 'DOWN':
            return 1
        if htf_trend == 'UP':
            return -1
        return 0
    
    def check_volatility_filter(self, df, pair: Optional[str] = None) -> Tuple[bool, str]:
        """
        Check if volatility is too high for trading.
        
        Returns:
            (is_safe, reason) - True if safe to trade
        """
        if not VOLATILITY_CHECK_ENABLED:
            return True, "Volatility check disabled"
        
        pair_label = pair or "UNKNOWN_PAIR"
        try:
            from analysis.technical_analysis import TechnicalAnalysis
            
            ta = TechnicalAnalysis(df)
            indicators = ta.get_indicators()
            
            # Get ATR
            atr = indicators.get('atr', 0)
            if atr <= 0:
                return True, "No ATR data"
            
            # Calculate ATR as percentage of price
            current_price = df['close'].iloc[-1] if len(df) > 0 else 0
            if current_price <= 0:
                return True, "No price data"
            
            atr_pct = (atr / current_price) * 100
            
            # Get average ATR from last 20 candles
            atr_values = []
            for i in range(max(0, len(df)-20), len(df)):
                try:
                    h = df['high'].iloc[i]
                    l = df['low'].iloc[i]
                    c = df['close'].iloc[i-1] if i > 0 else df['close'].iloc[i]
                    tr = max(
                        h - l,
                        abs(h - c),
                        abs(l - c)
                    )
                    atr_values.append(tr)
                except Exception as e:
                    logger.debug(f"[VOLATILITY FILTER] {pair_label}: skip ATR sample at idx={i}: {e}")
            
            avg_atr = sum(atr_values) / len(atr_values) if atr_values else 0
            avg_atr_pct = (avg_atr / current_price) * 100 if current_price > 0 else 0
            
            if avg_atr_pct > 0 and atr_pct > avg_atr_pct * VOLATILITY_ATR_MULTIPLIER:
                reason = f"High volatility: ATR {atr_pct:.2f}% > {VOLATILITY_ATR_MULTIPLIER}x avg {avg_atr_pct:.2f}%"
                logger.warning(f"🛡️ [VOLATILITY FILTER] {pair_label}: {reason}")
                return False, reason
            
            return True, "Volatility OK"
            
        except Exception as e:
            logger.debug(f"Volatility check error: {e}")
            return True, "Volatility check error"

    def generate_signal(
        self,
        pair: str,
        ta_signals: Dict,
        ml_prediction: bool,
        ml_confidence: float,
        ml_signal_class: str,
        last_signal_time: Optional[datetime] = None,
        last_recommendation: str = 'HOLD',
        combined_strength: float = 0.0,
        df: Optional[pd.DataFrame] = None,  # NEW: price data for quant analysis
        market_regime: str = 'UNKNOWN',     # NEW: current market regime
        current_price: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        Generate trading signal dengan quality filters.

        Returns:
            Signal dict atau None jika ditolak
        """

        # =====================================================================
        # CHECK 1: Cooldown period
        # =====================================================================
        if last_signal_time and last_recommendation != 'HOLD':
            minutes_elapsed = (datetime.now() - last_signal_time).total_seconds() / 60
            
            if minutes_elapsed < MINIMUM_SIGNAL_INTERVAL_MINUTES:
                # Check untuk flip signal (BUY → SELL atau sebaliknya)
                is_flip = (
                    (last_recommendation in ['BUY', 'STRONG_BUY'] and 
                     ml_signal_class in ['SELL', 'STRONG_SELL']) or
                    (last_recommendation in ['SELL', 'STRONG_SELL'] and 
                     ml_signal_class in ['BUY', 'STRONG_BUY'])
                )
                
                if is_flip:
                    detail = (
                        f"Skip signal flip ({last_recommendation} → {ml_signal_class}) setelah "
                        f"{minutes_elapsed:.0f} menit (min: {MINIMUM_SIGNAL_INTERVAL_MINUTES})"
                    )
                    logger.info(f"🛡️ [COOLDOWN] {pair}: {detail}")
                    self._record_rejection(pair, 'cooldown_flip', detail)
                    return None

        # =====================================================================
        # CHECK 2: Extract TA indicators
        # =====================================================================
        indicators = ta_signals.get('indicators', {})
        rsi = indicators.get('rsi', 'NEUTRAL')
        macd = indicators.get('macd', 'NEUTRAL')
        ma_trend = indicators.get('ma_trend', 'NEUTRAL')
        bollinger = indicators.get('bb', 'NEUTRAL')
        volume = indicators.get('volume', 'NORMAL')
        ta_strength = ta_signals.get('strength', 0)

        # =====================================================================
        # CHECK 3: RSI Overbought/Oversold Protection (DISABLED - terlalu strict, блокирует semua BUY)
        # =====================================================================
        # COMMENTED OUT: RSI OVERBOUGHT tidak berarti harga langsung turun
        # User harus decide sendiri, bot hanya kasih signal bukan block
        #
        # # BUY saat RSI OVERBOUGHT = jangan beli di pucuk
        # if ml_signal_class in ['BUY', 'STRONG_BUY'] and rsi == 'OVERBOUGHT':
        #     logger.warning(
        #         f"🚫 [RSI PROTECTION] {pair}: Reject BUY saat RSI OVERBOUGHT"
        #     )
        #     return self._create_hold_signal(
        #         pair, ta_signals, ml_confidence, ml_signal_class,
        #         reason="RSI OVERBOUGHT - harga sudah terlalu tinggi"
        #     )
        #
        # # SELL saat RSI+Bollinger OVERSOLD = jangan jual di bottom
        # if ml_signal_class in ['SELL', 'STRONG_SELL'] and rsi == 'OVERSOLD' and bollinger == 'OVERSOLD':
        #     logger.warning(
        #         f"🚫 [RSI PROTECTION] {pair}: Reject SELL saat RSI+Bollinger OVERSOLD"
        #     )
        #     return self._create_hold_signal(
        #         pair, ta_signals, ml_confidence, ml_signal_class,
        #         reason="RSI+Bollinger OVERSOLD - bahaya jual di bottom"
        #     )

        # INFO: Log RSI status but DO NOT BLOCK signal
        if rsi == 'OVERBOUGHT' and ml_signal_class in ['BUY', 'STRONG_BUY']:
            logger.info(
                f"ℹ️ [RSI INFO] {pair}: BUY signal dgn RSI OVERBOUGHT "
                f"(harga mungkin lanjut naik, tapi waspadai koreksi)"
            )
        elif rsi == 'OVERSOLD' and ml_signal_class in ['SELL', 'STRONG_SELL']:
            logger.info(
                f"ℹ️ [RSI INFO] {pair}: SELL signal dgn RSI OVERSOLD "
                f"(harga mungkin sudah bottom, waspadai rebound)"
            )

        # =====================================================================
        # CHECK 4: Volume Confirmation (INFO only - tidak reject signal)
        # =====================================================================
        # VOLUME_CONFIRMATION_REQUIRED = False, jadi hanya logging
        if ml_signal_class in ['BUY', 'STRONG_BUY'] and volume != 'HIGH':
            logger.info(
                f"ℹ️ [VOLUME INFO] {pair}: BUY dengan volume {volume} (ideal: HIGH)"
            )
        # Tidak reject signal karena volume, hanya info saja

        # =====================================================================
        # CHECK 5: ML vs TA Conflict Detection (DISABLED - terlalu strict, block too many BUY)
        # =====================================================================
        # COMMENTED OUT: ML dan TA sering disagree, tapi masih bisa useful
        # User harus decide sendiri dengan informasi lengkap
        #
        # # ML sangat yakin BUY tapi TA bearish = konflik
        # if ml_signal_class in ['BUY', 'STRONG_BUY'] and ta_strength < -0.30:
        #     return self._create_hold_signal(...)
        #
        # # ML sangat yakin SELL tapi TA bullish = konflik  
        # if ml_signal_class in ['SELL', 'STRONG_SELL'] and ta_strength > 0.30:
        #     return self._create_hold_signal(...)

        # INFO: Log conflict but DO NOT BLOCK
        if ml_signal_class in ['BUY', 'STRONG_BUY'] and ta_strength < -0.30:
            logger.info(
                f"⚠️ [CONFLICT INFO] {pair}: ML {ml_signal_class} tapi TA bearish "
                f"(ta_strength: {ta_strength:.2f}) - hati2 dgn entry"
            )
        elif ml_signal_class in ['SELL', 'STRONG_SELL'] and ta_strength > 0.30:
            logger.info(
                f"⚠️ [CONFLICT INFO] {pair}: ML {ml_signal_class} tapi TA bullish "
                f"(ta_strength: {ta_strength:.2f}) - hati2 dgn entry"
            )

        # =====================================================================
        # CHECK 6: Confluence Scoring (with Quant Mean Reversion)
        # =====================================================================
        # Determine signal direction for proper confluence calculation
        signal_direction = 'BUY' if ml_signal_class in ['BUY', 'STRONG_BUY'] else 'SELL'

        # NEW: Calculate mean reversion z-score bonus
        mean_reversion_bonus = 0
        mr_result = None
        if self.mean_reversion_engine is not None and df is not None:
            try:
                mr_current_price = current_price if current_price is not None else ta_signals.get('price')
                if mr_current_price is None and len(df) > 0 and 'close' in df.columns:
                    mr_current_price = float(df['close'].iloc[-1])
                mr_analysis = self.mean_reversion_engine.analyze(
                    df=df,
                    current_price=mr_current_price,
                    pair=pair,
                    market_regime=market_regime,
                )
                if mr_analysis is not None:
                    mr_result = mr_analysis
                    # Only add bonus if MR signal direction matches the trade direction
                    if (signal_direction == 'BUY' and mr_analysis.direction == 'BUY') or \
                       (signal_direction == 'SELL' and mr_analysis.direction == 'SELL'):
                        mean_reversion_bonus = mr_analysis.confluence_bonus
                        logger.info(
                            f"📈 [QUANT MR] {pair}: z={mr_analysis.z_score_composite:+.2f} | "
                            f"mr_signal={mr_analysis.signal} | bonus=+{mean_reversion_bonus} | "
                            f"direction_match=True"
                        )
                    elif mr_analysis.is_actionable:
                        logger.info(
                            f"📉 [QUANT MR] {pair}: z={mr_analysis.z_score_composite:+.2f} | "
                            f"mr_signal={mr_analysis.signal} | bonus=0 (direction mismatch: "
                            f"trade={signal_direction}, mr={mr_analysis.direction})"
                        )
            except Exception as e:
                logger.debug(f"[QUANT MR] {pair}: Analysis skipped: {e}")

        # NEW 2026-06-12: Higher-Timeframe trend filter (1h aggregation).
        # Tick data → resample → 1h candles → SMA fast/slow direction.
        htf_bonus = 0
        htf_info = None
        if df is not None and len(df) > 0:
            try:
                htf_info = self.compute_higher_tf_trend(
                    df,
                    target_minutes=60,
                    sma_fast=5,
                    sma_slow=10,
                    trend_threshold_pct=1.0,
                )
                htf_bonus = self.htf_alignment_score(signal_direction, htf_info['trend'])
                logger.info(
                    f"📈 [HTF TREND] {pair}: tf={htf_info['tf']} trend={htf_info['trend']} "
                    f"spread={htf_info['spread_pct']:+.2f}%" if htf_info['spread_pct'] is not None
                    else f"📈 [HTF TREND] {pair}: tf={htf_info['tf']} trend={htf_info['trend']} "
                    f"(htf_candles={htf_info['htf_candles']})"
                )
                if htf_bonus != 0:
                    logger.info(
                        f"📈 [HTF ALIGN] {pair}: signal={signal_direction} vs htf={htf_info['trend']} "
                        f"→ score{'+' if htf_bonus > 0 else ''}{htf_bonus}"
                    )
            except Exception as e:
                logger.debug(f"[HTF TREND] {pair}: skipped: {e}")

        confluence_score = self._calculate_confluence_score(
            rsi, macd, ma_trend, bollinger, volume, ml_confidence, ta_strength,
            signal_direction=signal_direction,
            mean_reversion_bonus=mean_reversion_bonus,
            htf_alignment_bonus=htf_bonus,
        )

        logger.info(
            f"📊 [CONFLUENCE] {pair}: Score={confluence_score} "
            f"(MR=+{mean_reversion_bonus}, HTF={'+' if htf_bonus >= 0 else ''}{htf_bonus}), "
            f"ML={ml_signal_class}, TA={ta_strength:.2f}"
        )

        # =====================================================================
        # CHECK 7: Determine Final Signal
        # =====================================================================
        final_signal = self._determine_final_signal(
            pair, ml_signal_class, confluence_score, ml_confidence, ta_strength, combined_strength
        )

        # Save to history
        self.signal_history[pair] = {
            'time': datetime.now(),
            'recommendation': final_signal['recommendation'],
            'confluence_score': confluence_score
        }

        return final_signal

    def _calculate_confluence_score(
        self,
        rsi: str,
        macd: str,
        ma_trend: str,
        bollinger: str,
        volume: str,
        ml_confidence: float,
        ta_strength: float,
        signal_direction: str = 'BUY',  # 'BUY' or 'SELL'
        mean_reversion_bonus: int = 0,  # NEW: bonus from z-score analysis
        htf_alignment_bonus: int = 0,   # NEW 2026-06-12: HTF trend alignment
    ) -> int:
        """
        Hitung confluence score (0-10 poin).
        BUY dan SELL punya kriteria berbeda dan saling berlawanan.
        Now includes mean reversion z-score bonus.
        """
        score = 0

        if signal_direction == 'BUY':
            # ==================================================================
            # BUY SIGNAL CONFLUENCE
            # ==================================================================
            # RSI: OVERSOLD = potential reversal up (+2)
            if rsi == 'OVERSOLD':
                score += 2
            elif rsi == 'NEUTRAL':
                score += 1
            # RSI OVERBOUGHT = bad for BUY (don't add points)

            # MACD: BULLISH = good (+2)
            if macd in ['BULLISH', 'BULLISH_CROSS']:
                score += 2

            # MA: BULLISH trend = good (+1)
            if ma_trend == 'BULLISH':
                score += 1

            # Bollinger: OVERSOLD/LOWER_BAND = potential bounce up (+1)
            if bollinger in ['OVERSOLD', 'LOWER_BAND']:
                score += 1

        else:  # SELL direction
            # ==================================================================
            # SELL SIGNAL CONFLUENCE
            # ==================================================================
            # RSI: OVERBOUGHT = potential reversal down (+2)
            if rsi == 'OVERBOUGHT':
                score += 2
            elif rsi == 'NEUTRAL':
                score += 1
            # RSI OVERSOLD = bad for SELL (don't add points)

            # MACD: BEARISH = good (+2)
            if macd in ['BEARISH', 'BEARISH_CROSS']:
                score += 2

            # MA: BEARISH trend = good (+1)
            if ma_trend == 'BEARISH':
                score += 1

            # Bollinger: OVERBOUGHT/UPPER_BAND = potential bounce down (+1)
            if bollinger in ['OVERBOUGHT', 'UPPER_BAND']:
                score += 1

        # Volume: HIGH = confirmation for both BUY and SELL (+1)
        if volume == 'HIGH':
            score += 1

        # ML Confidence: >= 70% = good for any signal direction (+1)
        if ml_confidence >= 0.70:
            score += 1

        # NEW: Mean Reversion Z-Score bonus (+0 to +2)
        score += mean_reversion_bonus

        # NEW 2026-06-12: Higher-Timeframe trend alignment (-1 to +1)
        # Aligned: +1, sideways/insufficient: 0, counter-trend: -1.
        # Floor at 0 supaya counter-trend tidak bisa bikin negative score
        # (downstream confluence comparisons asumsi non-negative).
        score += htf_alignment_bonus
        if score < 0:
            score = 0

        return score

    def _determine_final_signal(
        self,
        pair: str,
        ml_signal_class: str,
        confluence_score: int,
        ml_confidence: float,
        ta_strength: float,
        combined_strength: float
    ) -> Dict:
        """
        Determine final signal berdasarkan confluence score dan thresholds.
        """
        
        # HOLD signal - pass through directly (no validation needed)
        if ml_signal_class == 'HOLD' or ml_signal_class is None:
            return {'type': 'HOLD', 'recommendation': 'HOLD', 'confluence': confluence_score}

        # STRONG_BUY validation
        if ml_signal_class == 'STRONG_BUY':
            if (confluence_score >= CONFLUENCE_STRONG_BUY and
                ml_confidence >= STRONG_BUY_ML_CONFIDENCE and
                combined_strength >= STRONG_BUY_COMBINED_STRENGTH):
                return {'type': 'STRONG_BUY', 'recommendation': 'STRONG_BUY', 'confluence': confluence_score}
            elif (confluence_score >= CONFLUENCE_MINIMUM_BUY and
                  ml_confidence >= BUY_ML_CONFIDENCE and
                  combined_strength >= BUY_COMBINED_STRENGTH):
                logger.info(
                    f"⬇️ [QUALITY ENGINE] {pair}: STRONG_BUY downgraded to BUY "
                    f"(conf={ml_confidence:.2f}, combined={combined_strength:.4f}, confluence={confluence_score})"
                )
                return {'type': 'BUY', 'recommendation': 'BUY', 'confluence': confluence_score,
                       'reason': 'STRONG_BUY downgraded to BUY'}
            else:
                self._record_rejection(
                    pair=pair,
                    reason_key='strong_buy_requirements',
                    detail=(
                        f"confluence={confluence_score}, ml_confidence={ml_confidence:.2f}, "
                        f"combined_strength={combined_strength:.4f}"
                    )
                )
                return {'type': 'HOLD', 'recommendation': 'HOLD', 'confluence': confluence_score,
                       'reason': 'STRONG_BUY requirements not met'}

        # BUY validation
        elif ml_signal_class == 'BUY':
            if (confluence_score >= CONFLUENCE_MINIMUM_BUY and
                ml_confidence >= BUY_ML_CONFIDENCE and
                combined_strength >= BUY_COMBINED_STRENGTH):
                return {'type': 'BUY', 'recommendation': 'BUY', 'confluence': confluence_score}
            else:
                self._record_rejection(
                    pair=pair,
                    reason_key='buy_requirements',
                    detail=(
                        f"confluence={confluence_score}, ml_confidence={ml_confidence:.2f}, "
                        f"combined_strength={combined_strength:.4f}"
                    )
                )
                return {'type': 'HOLD', 'recommendation': 'HOLD', 'confluence': confluence_score,
                       'reason': 'BUY requirements not met'}

        # STRONG_SELL validation
        elif ml_signal_class == 'STRONG_SELL':
            if (confluence_score >= CONFLUENCE_STRONG_SELL and
                ml_confidence >= STRONG_SELL_ML_CONFIDENCE and
                combined_strength <= STRONG_SELL_COMBINED_STRENGTH):
                return {'type': 'STRONG_SELL', 'recommendation': 'STRONG_SELL', 'confluence': confluence_score}
            elif (confluence_score >= CONFLUENCE_MINIMUM_SELL and
                  ml_confidence >= SELL_ML_CONFIDENCE and
                  combined_strength <= SELL_COMBINED_STRENGTH):
                logger.info(
                    f"⬇️ [QUALITY ENGINE] {pair}: STRONG_SELL downgraded to SELL "
                    f"(conf={ml_confidence:.2f}, combined={combined_strength:.4f}, confluence={confluence_score})"
                )
                return {'type': 'SELL', 'recommendation': 'SELL', 'confluence': confluence_score,
                       'reason': 'STRONG_SELL downgraded to SELL'}
            else:
                self._record_rejection(
                    pair=pair,
                    reason_key='strong_sell_requirements',
                    detail=(
                        f"confluence={confluence_score}, ml_confidence={ml_confidence:.2f}, "
                        f"combined_strength={combined_strength:.4f}"
                    )
                )
                return {'type': 'HOLD', 'recommendation': 'HOLD', 'confluence': confluence_score,
                       'reason': 'STRONG_SELL requirements not met'}

        # SELL validation
        elif ml_signal_class == 'SELL':
            if (confluence_score >= CONFLUENCE_MINIMUM_SELL and
                ml_confidence >= SELL_ML_CONFIDENCE and
                combined_strength <= SELL_COMBINED_STRENGTH):
                return {'type': 'SELL', 'recommendation': 'SELL', 'confluence': confluence_score}
            else:
                self._record_rejection(
                    pair=pair,
                    reason_key='sell_requirements',
                    detail=(
                        f"confluence={confluence_score}, ml_confidence={ml_confidence:.2f}, "
                        f"combined_strength={combined_strength:.4f}"
                    )
                )
                return {'type': 'HOLD', 'recommendation': 'HOLD', 'confluence': confluence_score,
                       'reason': 'SELL requirements not met'}

        return {'type': 'HOLD', 'recommendation': 'HOLD', 'confluence': confluence_score}

    def _create_hold_signal(
        self,
        pair: str,
        ta_signals: Dict,
        ml_confidence: float,
        ml_signal_class: str,
        reason: str
    ) -> Dict:
        """Create HOLD signal dengan alasan penolakan."""
        return {
            'type': 'HOLD',
            'recommendation': 'HOLD',  # FIX: Add recommendation key for bot.py compatibility
            'pair': pair,
            'reason': reason,
            'ml_confidence': ml_confidence,
            'original_signal': ml_signal_class
        }

    def should_generate_signal(self, pair: str) -> bool:
        """Check apakah pair boleh generate signal (cooldown check)."""
        if pair not in self.signal_history:
            return True

        last_signal = self.signal_history[pair]
        minutes_elapsed = (datetime.now() - last_signal['time']).total_seconds() / 60

        return minutes_elapsed >= MINIMUM_SIGNAL_INTERVAL_MINUTES

    def analyze_mean_reversion(
        self,
        df: pd.DataFrame,
        pair: str = "UNKNOWN",
        market_regime: str = "UNKNOWN",
        current_price: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        Run mean reversion analysis and return result dict.

        This is the public interface for signal_pipeline to call and
        enrich the signal with z-score data.

        Returns:
            Dict with z-score data or None if engine unavailable/insufficient data
        """
        if self.mean_reversion_engine is None:
            return None

        result = self.mean_reversion_engine.analyze(
            df=df,
            current_price=current_price,
            pair=pair,
            market_regime=market_regime,
        )

        if result is None:
            return None

        return result.to_dict()
