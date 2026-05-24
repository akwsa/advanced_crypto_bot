# Tujuan: Engine analisis signal, sizing, dan eksekusi order.
# Caller: bot.py, autotrade runtime, manual trade commands.
# Dependensi: Database, ML model, Indodax API, TechnicalAnalysis.
# Main Functions: class TradingEngine.
# Side Effects: DB read/write, HTTP order call, trade state mutation.
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
        # - prediction: True (BUY), False (SELL), or None (HOLD)
        # - confidence: probability of predicted direction
        # - signal_class: 'STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL'
        #
        # FIX BUG #5: Prioritize signal_class over prediction to handle
        # edge case where signal_class='HOLD' but prediction=False
        # =====================================================================
        if ml_signal_class and ml_signal_class in ['BUY', 'STRONG_BUY', 'SELL', 'STRONG_SELL']:
            # Use signal_class untuk direction (prioritas utama)
            if ml_signal_class in ['STRONG_BUY', 'BUY']:
                ml_direction = 1.0
                ml_strength = ml_direction * ml_confidence
            elif ml_signal_class in ['STRONG_SELL', 'SELL']:
                ml_direction = -1.0
                ml_strength = -ml_confidence
            else:
                ml_direction = 0.0
                ml_strength = 0.0
        elif ml_prediction is True:
            # Fallback ke binary prediction jika signal_class tidak tersedia
            ml_strength = ml_confidence  # confidence is prob of BUY
        elif ml_prediction is False:
            ml_strength = -ml_confidence  # confidence is prob of SELL
        else:
            # No ML prediction or HOLD - use neutral
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
        pair = Config.get_pair_symbol(signal.get('pair', 'UNKNOWN'))

        try:
            open_trades = self.db.get_open_trades(user_id) if hasattr(self.db, 'get_open_trades') else []
        except Exception as e:
            logger.error(f"Error loading open trades for user {user_id}: {e}")
            return False, "Error checking open positions"

        # Check if signal is strong enough
        valid_signals = ['STRONG_BUY', 'BUY', 'STRONG_SELL', 'SELL']
        if recommendation not in valid_signals:
            return False, f"Signal {recommendation} not strong enough"

        try:
            # Check daily trade limit (count trades opened today, not open positions)
            daily_trade_count = self.db.count_trades_today(user_id) if hasattr(self.db, 'count_trades_today') else len(open_trades)
            if daily_trade_count >= Config.MAX_DAILY_TRADES:
                return False, f"Daily trade limit reached: {daily_trade_count}/{Config.MAX_DAILY_TRADES}"
        except Exception as e:
            logger.error(f"Error checking daily trades for user {user_id}: {e}")
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
            existing_trades = [t for t in open_trades if Config.get_pair_symbol(t['pair']) == pair]
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

                # Use unified threshold from Config (same as signal pipeline)
                if rr_ratio < Config.SR_MIN_RR_RATIO:
                    return False, f"Risk-reward ratio too low: {rr_ratio:.2f} < {Config.SR_MIN_RR_RATIO}"
            except Exception as e:
                logger.error(f"Error calculating risk-reward ratio for {pair}: {e}")
                return False, "Error calculating risk metrics"

        # Check trading hours
        allowed, hours_reason = self.check_trading_hours()
        if not allowed:
            return False, hours_reason
            
        # Check correlation cooldown
        allowed, corr_reason = self.check_correlation_cooldown(pair, self.db)
        if not allowed:
            return False, corr_reason

        # ── VaR/CVaR hard gate (Integrasi #5) ────────────────────────────
        # FIX #5: Threshold disesuaikan ke skala per-candle yang realistis.
        # VaR candle crypto biasanya -0.5% s/d -3%. Threshold -3% / -5%
        # akan aktif saat volatilitas ekstrem (crash, pump besar).
        # Hanya untuk BUY signals — SELL tidak diblokir oleh VaR gate.
        if recommendation in ['BUY', 'STRONG_BUY']:
            try:
                var_hist = signal.get("var_historical")
                cvar_hist = signal.get("cvar_historical")
                if var_hist is not None and cvar_hist is not None:
                    if var_hist < -3.0:   # FIX: was -5.0 (tidak pernah aktif)
                        return False, (
                            f"VaR gate: VaR95={var_hist:.2f}% < -3.0% — volatilitas candle ekstrem"
                        )
                    if cvar_hist < -5.0:  # FIX: was -8.0 (tidak pernah aktif)
                        return False, (
                            f"CVaR gate: CVaR95={cvar_hist:.2f}% < -5.0% — tail risk candle ekstrem"
                        )
            except Exception as _ve:
                logger.debug(f"[VAR GATE] {pair}: skipped — {_ve}")
        # ── End VaR/CVaR gate ─────────────────────────────────────────────

        # NEW: Break-even check for existing positions
        # If price moved up enough, adjust stop to breakeven
        try:
            for trade in open_trades:
                trade_pair = Config.get_pair_symbol(trade['pair'])
                trade_type = trade['type']
                if trade_pair == pair and trade_type == 'BUY':
                    entry = trade['price']
                    trade_id = trade['id']
                    if entry > 0:
                        profit_pct = ((current_price - entry) / entry) * 100
                        # If profit > breakeven threshold, stop_loss should be at entry (plus fees)
                        if profit_pct >= Config.BREAK_EVEN_AFTER_PCT:
                            breakeven_price = entry * (1 + 2 * Config.TRADING_FEE_RATE)
                            # Persist breakeven stop to database
                            if hasattr(self.db, 'update_trade_stop_loss'):
                                self.db.update_trade_stop_loss(trade_id, breakeven_price)
                            logger.info(
                                f"🛡️ [{pair}] Break-even activated: profit {profit_pct:.1f}% >= {Config.BREAK_EVEN_AFTER_PCT}%, "
                                f"SL moved to {breakeven_price:,.0f} (includes fees)"
                            )
        except Exception as e:
            logger.warning(f"⚠️ Break-even check error for {pair}: {e}")  # Log instead of silent pass

        return True, "All checks passed"
    
    def check_trading_hours(self):
        """Check if current time is within allowed trading hours.
        
        Returns:
            tuple: (allowed: bool, reason: str)
        """
        if not Config.TRADING_HOURS_ENABLED:
            return True, "Trading hours check disabled"
        
        from datetime import datetime, timezone, timedelta

        tz_offset = getattr(Config, 'TRADING_TIMEZONE_OFFSET', 7)
        tz_label = getattr(Config, 'TRADING_TIMEZONE_LABEL', 'WIB')
        now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=tz_offset)))
        current_hour = now.hour
        
        if current_hour < Config.TRADING_HOURS_START or current_hour >= Config.TRADING_HOURS_END:
            return False, f"Outside trading hours ({current_hour}:00 {tz_label}). Allowed: {Config.TRADING_HOURS_START}:00-{Config.TRADING_HOURS_END}:00 {tz_label}"
        
        return True, f"Within trading hours ({current_hour}:00 {tz_label})"
    
    def check_correlation_cooldown(self, pair, db):
        """Check if recently traded a correlated pair.
        
        Args:
            pair: Trading pair (e.g., 'btcidr')
            db: Database instance
            
        Returns:
            tuple: (allowed: bool, reason: str)
        """
        if not Config.CORRELATION_AVOIDANCE_ENABLED:
            return True, "Correlation check disabled"
        
        # Find which group this pair belongs to
        pair_group = None
        for group_name, pairs in Config.CORRELATION_GROUPS.items():
            if pair.lower() in pairs:
                pair_group = group_name
                break
        
        if not pair_group:
            return True, "No correlation group found"
        
        # Check recent trades
        cooldown_minutes = Config.CORRELATION_COOLDOWN_MINUTES
        recent_trades = db.get_trade_history(user_id=1, limit=50)  # Get recent trades
        
        if recent_trades:
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(minutes=cooldown_minutes)
            
            for trade in recent_trades:
                trade_time = trade['closed_at']
                if trade_time and isinstance(trade_time, str):
                    try:
                        trade_time = datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
                        if trade_time > cutoff:
                            # Check if this trade was in a correlated pair
                            traded_pair = trade['pair'].lower()
                            for group_name, pairs in Config.CORRELATION_GROUPS.items():
                                if traded_pair in pairs and group_name == pair_group:
                                    return False, f"Correlated pair {traded_pair} traded {cooldown_minutes} min ago. Wait for cooldown."
                    except:
                        pass
        
        return True, "No correlated trades in cooldown period"
    
    def calculate_position_size(self, user_id, price, kelly_win_rate=None):
        """Calculate optimal position size using fixed max size or Kelly criterion.

        Args:
            user_id: User ID
            price: Current price per unit
            kelly_win_rate: Optional historical win rate (0.0 to 1.0) to use Kelly criterion

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

            if kelly_win_rate and kelly_win_rate > 0:
                avg_win_pct = Config.PARTIAL_TAKE_PROFIT_1 / 100 if hasattr(Config, 'PARTIAL_TAKE_PROFIT_1') else 0.03
                avg_loss_pct = Config.STOP_LOSS_PCT / 100 if hasattr(Config, 'STOP_LOSS_PCT') else 0.02
                amount, max_position, kelly_pct, _ = self.calculate_kelly_position_size(
                    balance, price, kelly_win_rate, avg_win_pct, avg_loss_pct
                )
                if max_position > 0 and kelly_pct > 0:
                    # FIX #2: Apply GARCH scaling ke Kelly path juga
                    garch_regime = getattr(self, '_last_garch_regime', 'MEDIUM')
                    garch_scale = {"LOW": 1.0, "MEDIUM": 1.0, "HIGH": 0.6, "EXTREME": 0.35}.get(garch_regime, 1.0)
                    if garch_scale < 1.0:
                        max_position *= garch_scale
                        amount = max_position / price
                        logger.info(f"📊 [GARCH SIZING/KELLY] regime={garch_regime} → scale={garch_scale:.2f}")
                    return amount, max_position

            # Fallback to fixed size
            # Max 25% of balance per trade
            max_position = balance * Config.MAX_POSITION_SIZE

            # Ensure max_position is reasonable
            if max_position < Config.MIN_TRADE_AMOUNT:
                logger.warning(f"Max position {max_position:,.0f} below minimum trade amount")
                return 0, 0

            # ── GARCH regime scaling ──────────────────────────────────────
            # Perkecil posisi saat volatilitas tinggi, tanpa memblokir trade.
            # Scaling factor: LOW=1.0, MEDIUM=1.0, HIGH=0.6, EXTREME=0.35
            garch_regime = getattr(self, '_last_garch_regime', 'MEDIUM')
            garch_scale = {"LOW": 1.0, "MEDIUM": 1.0, "HIGH": 0.6, "EXTREME": 0.35}.get(garch_regime, 1.0)
            if garch_scale < 1.0:
                max_position *= garch_scale
                logger.info(
                    f"📊 [GARCH SIZING] regime={garch_regime} → scale={garch_scale:.2f} "
                    f"→ max_position={max_position:,.0f}"
                )
            # ── End GARCH scaling ─────────────────────────────────────────

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
                **signal,
                'recommendation': 'HOLD',
                'reason': f"Volatility too high: {vol_info['reason']}",
            }, f"BLOCKED: {vol_info['reason']}"
        
        if recommendation in ['BUY', 'STRONG_BUY']:
            if trend_info.get('trend') == 'DOWN':
                logger.info(f"🚫 Blocked BUY for {signal['pair']}: Against trend")
                return {
                    **signal,
                    'recommendation': 'HOLD',
                    'reason': f"Against trend: {trend_info['sma_alignment']}",
                }, "BLOCKED: Against higher timeframe trend"
        
        if recommendation in ['SELL', 'STRONG_SELL']:
            if trend_info.get('trend') == 'UP':
                logger.info(f"🚫 Blocked SELL for {signal['pair']}: Against trend")
                return {
                    **signal,
                    'recommendation': 'HOLD',
                    'reason': f"Against trend: {trend_info['sma_alignment']}",
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
