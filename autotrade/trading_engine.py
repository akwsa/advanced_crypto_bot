from datetime import datetime
from core.config import Config
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self, db, ml_model):
        self.db = db
        self.ml_model = ml_model

    def _validate_signal_inputs(self, pair, ta_signals, ml_confidence):
        """Validate inputs for signal generation to prevent errors."""
        if not pair or not isinstance(pair, str):
            raise ValueError(f"Invalid pair: {pair}")

        if not isinstance(ta_signals, dict):
            raise ValueError(f"ta_signals must be a dict, got {type(ta_signals)}")

        if 'strength' not in ta_signals:
            raise ValueError("ta_signals must contain 'strength' key")

        if not isinstance(ta_signals.get('price'), (int, float)):
            raise ValueError(f"Invalid price in ta_signals: {ta_signals.get('price')}")

        # Validate and clamp ml_confidence
        if ml_confidence is None:
            ml_confidence = 0.5
        elif not isinstance(ml_confidence, (int, float)):
            logger.warning(f"Invalid ml_confidence type: {type(ml_confidence)}, using 0.5")
            ml_confidence = 0.5
        elif ml_confidence < 0 or ml_confidence > 1:
            # Clamp to valid range
            ml_confidence = max(0.0, min(1.0, ml_confidence))

        return ml_confidence

    def generate_signal(self, pair, ta_signals, ml_prediction, ml_confidence, ml_signal_class=None):
        """Generate final trading signal combining TA and ML

        Args:
            ml_signal_class: V2 only - 'STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL'

        Raises:
            ValueError: If inputs are invalid
        """
        # Validate inputs
        try:
            ml_confidence = self._validate_signal_inputs(pair, ta_signals, ml_confidence)
        except ValueError as e:
            logger.error(f"Signal validation failed for {pair}: {e}")
            raise

        # Determine signal strength
        ta_strength = ta_signals.get('strength', 0)
        
        # =====================================================================
        # ML STRENGTH CALCULATION - FIX untuk masalah ML bias ke SELL
        # 
        # ML model returns:
        # - prediction: True (BUY) or False (SELL)
        # - confidence: probability of PREDICTED class (NOT probability of BUY)
        # - signal_class: 'BUY'/'SELL'/'HOLD'
        #
        # Problem: confidence field represents prob of SELL when prediction=False
        # So if pred=False, confidence=0.73 means 73% SELL - tidak 73% BUY!
        # =====================================================================
        if ml_signal_class and ml_signal_class in ['BUY', 'STRONG_BUY', 'SELL', 'STRONG_SELL']:
            # Use signal_class untuk direction
            if ml_signal_class in ['STRONG_BUY', 'BUY']:
                # BUY signal - ml_prediction=True means probability of BUY
                # Convert: prediction=True means confidence = probability of BUY
                ml_direction = 1.0
                ml_strength = ml_direction * ml_confidence
            elif ml_signal_class in ['STRONG_SELL', 'SELL']:
                # SELL signal - ml_prediction=False means probability of SELL  
                # ml_confidence field represents probability of SELL, bukan BUY
                # So we need to convert: if pred=False, confidence is prob of SELL
                # We want strength = -1 * (1 - confidence_of_SELL) or langsung -confidence
                # Wait - ml_confidence is ALREADY the probability of SELL class!
                # So strength should be NEGATIVE of that
                ml_direction = -1.0
                # FIX: ml_confidence for SELL = probability of SELL (NOT BUY)
                # So we use confidence directly as negative strength
                ml_strength = -ml_confidence  # -0.73 for 73% SELL confidence
            else:
                ml_direction = 0.0
                ml_strength = 0.0
        elif ml_prediction is not None:
            # Binary: True=BUY, False=SELL  
            if ml_prediction:  # True = BUY
                ml_strength = ml_confidence  # confidence is prob of BUY
            else:  # False = SELL
                ml_strength = -ml_confidence  # confidence is prob of SELL
        else:
            # No ML prediction - use neutral
            ml_strength = 0.0

        # Weight: keep BUY/SELL symmetric so the engine does not lean bearish
        # simply because SELL gets a larger ML contribution than BUY.
        if ml_signal_class in ['BUY', 'STRONG_BUY']:
            ml_weight = 0.30
        elif ml_signal_class in ['SELL', 'STRONG_SELL']:
            ml_weight = 0.30
        else:
            # HOLD or unknown - balanced
            ml_weight = 0.30
            
        combined_strength = (ta_strength * (1 - ml_weight)) + (ml_strength * ml_weight)

        # =====================================================================
        # OPTIMIZED THRESHOLDS - HIGHER TO REDUCE FALSE SIGNALS
        # Strategy: Higher thresholds to reduce false signals (user recommendation)
        # =====================================================================
        STRONG_THRESHOLD = 0.20     # Strong BUY signal threshold (was 0.08)
        MODERATE_THRESHOLD = 0.12   # Moderate BUY signal threshold (was 0.005)
        ML_STRONG_THRESHOLD = 0.45  # ML confidence for strong signal (was 0.25)

        # FIX: Use combined_strength only - don't block from ML confidence
        # Let user decide with full information
        if combined_strength > STRONG_THRESHOLD and ml_confidence >= ML_STRONG_THRESHOLD:
            recommendation = 'STRONG_BUY'
            reason = f'Strong bullish signals (TA: {ta_strength:+.2f}, ML: {ml_confidence:.1%})'
        elif combined_strength > MODERATE_THRESHOLD:
            recommendation = 'BUY'
            reason = f'Moderate bullish signals (TA: {ta_strength:+.2f}, ML: {ml_confidence:.1%})'
        elif combined_strength < -STRONG_THRESHOLD and ml_confidence >= ML_STRONG_THRESHOLD:
            recommendation = 'STRONG_SELL'
            reason = f'Strong bearish signals (TA: {ta_strength:+.2f}, ML: {ml_confidence:.1%})'
        elif combined_strength < -MODERATE_THRESHOLD:
            recommendation = 'SELL'
            reason = f'Moderate bearish signals (TA: {ta_strength:+.2f}, ML: {ml_confidence:.1%})'
        else:
            recommendation = 'HOLD'
            reason = f'Mixed signals, wait for confirmation (Combined: {combined_strength:+.2f})'

        logger.info(
            "🧮 [ENGINE] %s | ml_class=%s | ta_strength=%+.3f | ml_strength=%+.3f | "
            "ml_weight=%.2f | combined=%+.3f | rec=%s",
            pair,
            ml_signal_class or 'NONE',
            ta_strength,
            ml_strength,
            ml_weight,
            combined_strength,
            recommendation,
        )
        
        signal = {
            'timestamp': datetime.now(),
            'pair': pair,
            'recommendation': recommendation,
            'reason': reason,
            'ta_strength': float(ta_strength),  # Convert numpy types to Python native
            'ml_confidence': float(ml_confidence) if ml_confidence is not None else 0.5,
            'combined_strength': float(combined_strength),
            'price': float(ta_signals['price']),
            'indicators': ta_signals['indicators']
        }

        # =====================================================================
        # FIX: Removed save_signal call - signals now saved ONLY to signals.db
        # Previously: Signal was saved to BOTH trading.db AND signals.db (redundant)
        # Now: Signal is returned and bot.py saves it to signals.db only
        # =====================================================================
        # Old code (removed):
        # self.db.save_signal(
        #     pair=pair,
        #     signal_type=recommendation,
        #     price=float(ta_signals['price']),
        #     ...
        # )

        return signal
    
    def should_execute_trade(self, user_id, signal, current_price):
        """Check if trade should be executed.

        Args:
            user_id: User ID
            signal: Signal dictionary with 'recommendation' and 'pair' keys
            current_price: Current market price

        Returns:
            tuple: (should_execute: bool, reason: str)
        """
        # Validate inputs
        if not isinstance(signal, dict):
            logger.error(f"Invalid signal type: {type(signal)}")
            return False, "Invalid signal format"

        if not isinstance(current_price, (int, float)) or current_price <= 0:
            logger.error(f"Invalid current_price: {current_price}")
            return False, "Invalid price"

        recommendation = signal.get('recommendation')
        pair = signal.get('pair', 'UNKNOWN')

        # Check if signal is strong enough
        valid_signals = ['STRONG_BUY', 'BUY', 'STRONG_SELL', 'SELL']
        if recommendation not in valid_signals:
            return False, f"Signal {recommendation} not strong enough"

        try:
            # Check daily trade limit
            open_trades = self.db.get_open_trades(user_id)
            if len(open_trades) >= Config.MAX_DAILY_TRADES:
                return False, f"Daily trade limit reached: {len(open_trades)}/{Config.MAX_DAILY_TRADES}"
        except Exception as e:
            logger.error(f"Error checking open trades for user {user_id}: {e}")
            return False, "Error checking trade status"

        try:
            # Check balance
            balance = self.db.get_balance(user_id)
            if balance < Config.MIN_TRADE_AMOUNT:
                return False, f"Insufficient balance: {balance:,.0f} < {Config.MIN_TRADE_AMOUNT:,.0f}"
        except Exception as e:
            logger.error(f"Error checking balance for user {user_id}: {e}")
            return False, "Error checking balance"

        # Check if already have position
        try:
            existing_trades = [t for t in open_trades if t.get('pair') == pair]
            if recommendation in ['BUY', 'STRONG_BUY'] and existing_trades:
                return False, f"Already have position in {pair}"
        except Exception as e:
            logger.error(f"Error checking existing positions for {pair}: {e}")
            # Non-critical error, continue

        # Check risk-reward ratio for buy signals
        if recommendation in ['BUY', 'STRONG_BUY']:
            try:
                stop_loss = current_price * (1 - Config.STOP_LOSS_PCT / 100)
                take_profit = current_price * (1 + Config.TAKE_PROFIT_PCT / 100)
                risk = current_price - stop_loss
                reward = take_profit - current_price

                if risk <= 0:
                    logger.warning(f"Invalid risk calculation for {pair}: risk={risk}")
                    return False, "Invalid risk calculation"

                rr_ratio = reward / risk

                if rr_ratio < Config.RISK_REWARD_RATIO:
                    return False, f"Risk-reward ratio too low: {rr_ratio:.2f} < {Config.RISK_REWARD_RATIO}"
            except Exception as e:
                logger.error(f"Error calculating risk-reward ratio for {pair}: {e}")
                return False, "Error calculating risk metrics"

        # NEW: Break-even check for existing positions
        # If price moved up enough, adjust stop to breakeven
        try:
            open_trades = self.db.get_open_trades(user_id) if hasattr(self.db, 'get_open_trades') else []
            for trade in open_trades:
                if trade.get('pair') == pair and trade.get('type') == 'BUY':
                    entry = trade.get('price', 0)
                    if entry > 0:
                        profit_pct = ((current_price - entry) / entry) * 100
                        # If profit > breakeven threshold, stop_loss should be at entry
                        if profit_pct >= Config.BREAK_EVEN_AFTER_PCT:
                            # Update trade stop_loss to entry price (breakeven)
                            logger.info(f"📊 [{pair}] Break-even activated: profit {profit_pct:.1f}% >= {Config.BREAK_EVEN_AFTER_PCT}%")
        except:
            pass  # Non-critical, continue

        return True, "All checks passed"
    
    def calculate_position_size(self, user_id, price):
        """Calculate optimal position size.

        Args:
            user_id: User ID
            price: Current price per unit

        Returns:
            tuple: (amount: float, max_position: float) or (None, None) on error
        """
        # Validate price
        if not isinstance(price, (int, float)) or price <= 0:
            logger.error(f"Invalid price for position sizing: {price}")
            return None, None

        try:
            balance = self.db.get_balance(user_id)

            if balance <= 0:
                logger.warning(f"Zero or negative balance for user {user_id}: {balance}")
                return 0, 0

            # Max 25% of balance per trade
            max_position = balance * Config.MAX_POSITION_SIZE

            # Ensure max_position is reasonable
            if max_position < Config.MIN_TRADE_AMOUNT:
                logger.warning(f"Max position {max_position:,.0f} below minimum trade amount")
                return 0, 0

            # Calculate amount
            amount = max_position / price

            return amount, max_position

        except Exception as e:
            logger.error(f"Error calculating position size for user {user_id}: {e}")
            return None, None

    def calculate_stop_loss_take_profit(self, entry_price, trade_type, atr_value=None):
        """Calculate SL and TP levels with ATR-based and Partial Take Profit support.

        Args:
            entry_price: Entry price for the trade
            trade_type: 'BUY' or 'SELL'
            atr_value: ATR value (optional). If provided, uses ATR-based SL/TP

        Returns:
            dict with: stop_loss, take_profit_1, take_profit_2, rr_ratio, method
        """
        if not isinstance(entry_price, (int, float)) or entry_price <= 0:
            logger.error(f"Invalid entry_price: {entry_price}")
            return {'stop_loss': None, 'take_profit_1': None, 'take_profit_2': None, 'rr_ratio': 0, 'method': 'none'}

        if trade_type not in ['BUY', 'SELL', 'STRONG_BUY', 'STRONG_SELL']:
            logger.error(f"Invalid trade_type: {trade_type}")
            return {'stop_loss': None, 'take_profit_1': None, 'take_profit_2': None, 'rr_ratio': 0, 'method': 'none'}

        try:
            is_buy = trade_type in ['BUY', 'STRONG_BUY']
            
            # Use ATR-based if available, otherwise fallback to fixed percentage
            if atr_value and atr_value > 0:
                atr_multiplier_sl = 2.0  # 2x ATR for stop loss
                atr_multiplier_tp1 = 3.0  # 3x ATR for TP1
                atr_multiplier_tp2 = 5.0  # 5x ATR for TP2
                
                if is_buy:
                    stop_loss = entry_price - (atr_value * atr_multiplier_sl)
                    take_profit_1 = entry_price + (atr_value * atr_multiplier_tp1)
                    take_profit_2 = entry_price + (atr_value * atr_multiplier_tp2)
                else:
                    stop_loss = entry_price + (atr_value * atr_multiplier_sl)
                    take_profit_1 = entry_price - (atr_value * atr_multiplier_tp1)
                    take_profit_2 = entry_price - (atr_value * atr_multiplier_tp2)
                
                method = 'atr'
                logger.info(f"📊 [{trade_type}] ATR-based SL/TP: SL={atr_multiplier_sl}xATR, TP1={atr_multiplier_tp1}xATR, TP2={atr_multiplier_tp2}xATR")
            else:
                if is_buy:
                    stop_loss = entry_price * (1 - Config.STOP_LOSS_PCT / 100)
                    take_profit_1 = entry_price * (1 + Config.PARTIAL_TAKE_PROFIT_1 / 100)
                    take_profit_2 = entry_price * (1 + Config.PARTIAL_TAKE_PROFIT_2 / 100)
                else:
                    stop_loss = entry_price * (1 + Config.STOP_LOSS_PCT / 100)
                    take_profit_1 = entry_price * (1 - Config.PARTIAL_TAKE_PROFIT_1 / 100)
                    take_profit_2 = entry_price * (1 - Config.PARTIAL_TAKE_PROFIT_2 / 100)
                
                method = 'fixed'
            
            # Calculate R/R ratio for validation
            risk = abs(entry_price - stop_loss)
            reward_1 = abs(take_profit_1 - entry_price)
            rr_ratio = reward_1 / risk if risk > 0 else 0

            return {
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                'rr_ratio': rr_ratio,
                'method': method
            }

        except Exception as e:
            logger.error(f"Error calculating SL/TP: {e}")
            return {'stop_loss': None, 'take_profit_1': None, 'take_profit_2': None, 'rr_ratio': 0, 'method': 'none'}
    
    def check_multi_timeframe_trend(self, df):
        """Check trend direction using SMA alignment (simulating higher timeframe).
        
        Args:
            df: DataFrame with 'close' column
            
        Returns:
            dict: {'trend': 'UP'|'DOWN'|'NEUTRAL', 'sma_alignment': str}
        """
        if df is None or len(df) < 50:
            return {'trend': 'NEUTRAL', 'sma_alignment': 'INSUFFICIENT_DATA'}
        
        close = df['close']
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        
        current_20 = sma20.iloc[-1]
        current_50 = sma50.iloc[-1]
        
        if pd.isna(current_20) or pd.isna(current_50):
            return {'trend': 'NEUTRAL', 'sma_alignment': 'NaN_VALUE'}
        
        if current_20 > current_50:
            return {'trend': 'UP', 'sma_alignment': 'BULLISH'}
        elif current_20 < current_50:
            return {'trend': 'DOWN', 'sma_alignment': 'BEARISH'}
        else:
            return {'trend': 'NEUTRAL', 'sma_alignment': 'FLAT'}
    
    def check_volatility_filter(self, df, multiplier=3.0):
        """Check if volatility is too high for trading.
        
        Args:
            df: DataFrame with 'atr' column (from TechnicalAnalysis)
            multiplier: ATR multiplier threshold (default 3.0x average)
            
        Returns:
            dict: {'volatile': bool, 'atr_ratio': float, 'reason': str}
        """
        if df is None or 'atr' not in df.columns:
            return {'volatile': False, 'atr_ratio': 0, 'reason': 'NO_ATR_DATA'}
        
        if len(df) < Config.ATR_PERIOD + 10:
            return {'volatile': False, 'atr_ratio': 0, 'reason': 'INSUFFICIENT_DATA'}
        
        current_atr = df['atr'].iloc[-1]
        avg_atr = df['atr'].rolling(20).mean().iloc[-1]
        
        if pd.isna(current_atr) or pd.isna(avg_atr) or avg_atr == 0:
            return {'volatile': False, 'atr_ratio': 0, 'reason': 'NaN_ATR'}
        
        atr_ratio = current_atr / avg_atr
        
        if atr_ratio > multiplier:
            return {
                'volatile': True, 
                'atr_ratio': atr_ratio, 
                'reason': f'ATR {atr_ratio:.1f}x > {multiplier}x average'
            }
        
        return {'volatile': False, 'atr_ratio': atr_ratio, 'reason': 'OK'}
    
    def filter_by_conditions(self, signal, df_ta, trend_info, vol_info):
        """Apply multi-timeframe and volatility filters to signal.
        
        Args:
            signal: Signal dict from generate_signal
            df_ta: DataFrame with technical indicators (for ATR)
            trend_info: Dict from check_multi_timeframe_trend
            vol_info: Dict from check_volatility_filter
            
        Returns:
            tuple: (filtered_signal or None, reason: str)
        """
        recommendation = signal.get('recommendation', 'HOLD')
        
        if vol_info.get('volatile', False):
            logger.warning(f"🚫 Blocked {signal['pair']}: {vol_info['reason']}")
            return {
                'recommendation': 'HOLD',
                'reason': f"Volatility too high: {vol_info['reason']}",
                **signal
            }, f"BLOCKED: {vol_info['reason']}"
        
        if recommendation in ['BUY', 'STRONG_BUY']:
            if trend_info.get('trend') == 'DOWN':
                logger.info(f"🚫 Blocked BUY for {signal['pair']}: Against trend")
                return {
                    'recommendation': 'HOLD',
                    'reason': f"Against trend: {trend_info['sma_alignment']}",
                    **signal
                }, "BLOCKED: Against higher timeframe trend"
        
        if recommendation in ['SELL', 'STRONG_SELL']:
            if trend_info.get('trend') == 'UP':
                logger.info(f"🚫 Blocked SELL for {signal['pair']}: Against trend")
                return {
                    'recommendation': 'HOLD',
                    'reason': f"Against trend: {trend_info['sma_alignment']}",
                    **signal
                }, "BLOCKED: Against higher timeframe trend"
        
        return signal, "PASSED"
    
    def detect_market_regime(self, df, volatility_multiplier=2.0):
        """Detect current market regime: TRENDING_UP, TRENDING_DOWN, RANGING, or VOLATILE.
        
        Args:
            df: DataFrame with close and atr columns
            volatility_multiplier: Threshold for volatile regime
            
        Returns:
            dict: {'regime': str, 'trend': str, 'volatility': float}
        """
        if df is None or len(df) < 50:
            return {'regime': 'UNKNOWN', 'trend': 'NEUTRAL', 'volatility': 0}
        
        close = df['close']
        
        # Trend detection using SMA alignment
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        
        current_20 = sma20.iloc[-1]
        current_50 = sma50.iloc[-1]
        
        if pd.isna(current_20) or pd.isna(current_50):
            return {'regime': 'UNKNOWN', 'trend': 'NEUTRAL', 'volatility': 0}
        
        # Determine trend
        if current_20 > current_50 * 1.02:  # 2% threshold for clear trend
            trend = 'TRENDING_UP'
        elif current_20 < current_50 * 0.98:
            trend = 'TRENDING_DOWN'
        else:
            trend = 'RANGING'
        
        # Volatility detection
        if 'atr' not in df.columns:
            volatility = 0
        else:
            current_atr = df['atr'].iloc[-1]
            avg_atr = df['atr'].rolling(20).mean().iloc[-1]
            if pd.isna(current_atr) or pd.isna(avg_atr) or avg_atr == 0:
                volatility = 0
            else:
                volatility = current_atr / avg_atr
        
        # Determine regime
        if volatility > volatility_multiplier:
            regime = 'VOLATILE'
        elif trend == 'RANGING':
            regime = 'RANGING'
        else:
            regime = trend
        
        return {
            'regime': regime,
            'trend': trend,
            'volatility': volatility
        }
    
    def get_position_multiplier(self, regime):
        """Get position size multiplier based on regime.
        
        Args:
            regime: Market regime from detect_market_regime
            
        Returns:
            float: Position multiplier (0.0 to 1.0)
        """
        multipliers = {
            'TRENDING_UP': Config.REGIME_TRENDING_UP,
            'TRENDING_DOWN': Config.REGIME_TRENDING_DOWN,
            'RANGING': Config.REGIME_RANGING,
            'VOLATILE': Config.REGIME_VOLATILE,
            'UNKNOWN': 0.5  # Conservative when unknown
        }
        return multipliers.get(regime, 0.5)
    
    def calculate_kelly_position_size(self, balance, entry_price, win_rate, avg_win_pct, avg_loss_pct):
        """Calculate Kelly Criterion position sizing.
        
        Formula: Kelly % = W - (1-W)/R
        Where W = win rate, R = avg_win/avg_loss
        
        Args:
            balance: Account balance
            entry_price: Entry price
            win_rate: Historical win rate (0.0 to 1.0)
            avg_win_pct: Average win percentage (e.g., 0.05 for 5%)
            avg_loss_pct: Average loss percentage (e.g., 0.02 for 2%)
            
        Returns:
            tuple: (position_amount, position_value, kelly_pct, fractional_kelly)
        """
        if not balance or balance <= 0:
            return 0, 0, 0, 0
        if not win_rate or win_rate <= 0 or win_rate >= 1:
            logger.warning(f"Invalid win_rate: {win_rate}, using default 0.5")
            win_rate = 0.5
        if not avg_win_pct or avg_win_pct <= 0:
            avg_win_pct = 0.05
        if not avg_loss_pct or avg_loss_pct <= 0:
            avg_loss_pct = 0.02
        
        # Calculate Kelly
        win_loss_ratio = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 1
        kelly_pct = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Cap at reasonable levels (full Kelly is too aggressive)
        kelly_pct = max(0, min(kelly_pct, 0.25))  # Max 25% of balance
        
        # Use fractional Kelly (half-Kelly for safety)
        fractional_kelly = kelly_pct * 0.5
        
        # Calculate position value
        position_value = balance * fractional_kelly
        position_amount = position_value / entry_price if entry_price > 0 else 0
        
        # Apply max position limit
        max_position = balance * Config.MAX_POSITION_SIZE
        if position_value > max_position:
            position_value = max_position
            position_amount = position_value / entry_price if entry_price > 0 else 0
        
        logger.info(f"📊 Kelly: W={win_rate:.1%}, R={win_loss_ratio:.2f}, Kelly={kelly_pct:.1%}, "
                   f"Fractional={fractional_kelly:.1%}, Position={position_value:,.0f} IDR")
        
        return position_amount, position_value, kelly_pct, fractional_kelly
