#!/usr/bin/env python3
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

logger = logging.getLogger('crypto_bot')

# ============================================================================
# CONFIGURATION
# ============================================================================

# Cooldown period antar signal (menit) - OPTIMIZED for more signals
MINIMUM_SIGNAL_INTERVAL_MINUTES = 15

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

# Thresholds - OPTIMIZED for maximum profitability
# Strategy: Lower thresholds, let risk manager filter trades
STRONG_BUY_ML_CONFIDENCE = 0.30  
STRONG_BUY_COMBINED_STRENGTH = 0.03
BUY_ML_CONFIDENCE = 0.20         
BUY_COMBINED_STRENGTH = 0.005     

STRONG_SELL_ML_CONFIDENCE = 0.30  
STRONG_SELL_COMBINED_STRENGTH = -0.03
SELL_ML_CONFIDENCE = 0.20        
SELL_COMBINED_STRENGTH = -0.005

# Confidence threshold minimum - VERY LOW
MIN_ML_CONFIDENCE = 0.20  # Very low (was 0.65)

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
                    return 'VOLATILE', 0.0
                    
        except Exception as e:
            logger.debug(f"Regime detection error: {e}")
            return 'UNKNOWN', 1.0
    
    def check_volatility_filter(self, df) -> Tuple[bool, str]:
        """
        Check if volatility is too high for trading.
        
        Returns:
            (is_safe, reason) - True if safe to trade
        """
        if not VOLATILITY_CHECK_ENABLED:
            return True, "Volatility check disabled"
        
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
                except:
                    pass
            
            avg_atr = sum(atr_values) / len(atr_values) if atr_values else 0
            avg_atr_pct = (avg_atr / current_price) * 100 if current_price > 0 else 0
            
            if avg_atr_pct > 0 and atr_pct > avg_atr_pct * VOLATILITY_ATR_MULTIPLIER:
                reason = f"High volatility: ATR {atr_pct:.2f}% > {VOLATILITY_ATR_MULTIPLIER}x avg {avg_atr_pct:.2f}%"
                logger.warning(f"🛡️ [VOLATILITY FILTER] {pair}: {reason}")
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
        combined_strength: float = 0.0
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
        # CHECK 6: Confluence Scoring
        # =====================================================================
        # Determine signal direction for proper confluence calculation
        signal_direction = 'BUY' if ml_signal_class in ['BUY', 'STRONG_BUY'] else 'SELL'

        confluence_score = self._calculate_confluence_score(
            rsi, macd, ma_trend, bollinger, volume, ml_confidence, ta_strength,
            signal_direction=signal_direction
        )

        logger.info(
            f"📊 [CONFLUENCE] {pair}: Score={confluence_score}, "
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
        signal_direction: str = 'BUY'  # 'BUY' or 'SELL'
    ) -> int:
        """
        Hitung confluence score (0-8 poin).
        BUY dan SELL punya kriteria berbeda dan saling berlawanan.
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
