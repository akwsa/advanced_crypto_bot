#!/usr/bin/env python3
# Tujuan: Smart Hunter strategy loop for scanning, scoring, entering, and exiting high-edge spot trades.
# Caller: autohunter.smart_hunter_integration and standalone runtime usage.
# Dependensi: requests, telegram.Bot, core.config, core.profit_optimizer, Indodax HTTP API.
# Main Functions: SmartProfitHunter.get_balance, analyze_pair, find_best_opportunity, execute_smart_trade, monitor_positions_smart, close_position.
# Side Effects: HTTP calls to Indodax and Telegram, log file writes, in-memory trade state mutation.
"""
Smart Profit Hunter v2
Advanced Multi-Indicator Trading Strategy for Maximum Profit
"""

import os
import requests
import logging
import time
import asyncio
from datetime import datetime, timedelta
from telegram import Bot
import json

from core.config import Config
from core.profit_optimizer import evaluate_hunter_setup

# Configuration - loaded from .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("ADMIN_IDS", "").split(",")[0].strip() if os.getenv("ADMIN_IDS") else ""
INDODAX_API_URL = "https://indodax.com"
INDODAX_API_KEY = os.getenv("INDODAX_API_KEY", "")
INDODAX_SECRET_KEY = os.getenv("INDODAX_SECRET_KEY", "")

# Smart Trading Settings
MIN_VOLUME_IDR = 1_000_000_000  # Min 1B IDR volume (liquidity)
MAX_POSITION_SIZE = 100_000  # Max 100k per trade
MAX_DAILY_LOSS = 200_000  # Stop if lose 200k/day

# Entry Criteria (ALL must be BULLISH)
MIN_RSI = 30  # Oversold zone
MAX_RSI = 60  # Not overbought (stricter)
MIN_VOLUME_RATIO = 1.5  # Volume 1.5x average
MIN_MACD_SIGNAL = 0  # MACD must be bullish (positive)
MIN_MA_BULLISH = True  # MA must be bullish
BOLLINGER_MAX = 0.8  # Price must be below 80% of BB width (not at upper band)
MIN_ML_CONFIDENCE = 0.50  # ML confidence >50%
MIN_PRICE_CHANGE = 1.0  # Minimum intraday expansion to avoid dead pairs
MAX_PRICE_CHANGE = 12.0  # Avoid chasing already overextended moves

# Exit Strategy
TAKE_PROFIT_LEVELS = [
    (3.0, 0.5),   # Sell 50% at +3%
    (5.0, 0.3),   # Sell 30% at +5%
    (8.0, 0.2),   # Sell 20% at +8%
]
STOP_LOSS = -2.0  # Hard stop at -2%
TRAILING_STOP = True  # Enable trailing stop
TRAILING_PERCENT = 1.5  # Trail by 1.5%

# Risk Management
MIN_RISK_REWARD = 3.0  # Min 1:3 risk/reward
MAX_TRADES_PER_DAY = 5
COOLDOWN_AFTER_LOSS = 300  # Wait 5 min after loss

# Setup logging (use existing logger from bot.py, do NOT call basicConfig to avoid duplicate handlers)
logger = logging.getLogger(__name__)


class SmartProfitHunter:
    def __init__(self, dry_run=True, db=None):
        """
        Initialize SmartProfitHunter

        Args:
            dry_run: If True, simulate trades without executing real orders.
                    If False, execute real trades on Indodax.
            db: Optional database instance for persisting trades.
        """
        self.session = requests.Session()
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.active_trades = {}
        self.daily_trades = 0
        self.daily_pnl = 0
        self.last_reset = datetime.now().date()
        self.balance_idr = 0
        self.last_loss_time = None
        self.price_history = {}  # For RSI calculation
        self.db = db

        # DRY RUN mode - CRITICAL for safety
        self.dry_run = dry_run
        self.is_real_trading = not dry_run

        if dry_run:
            logger.info("🧪 SmartProfitHunter initialized in DRY RUN mode (simulation only)")
        else:
            logger.warning("🔴 SmartProfitHunter initialized in REAL TRADING mode!")
            logger.warning("   Real orders will be placed on Indodax!")

    def _get_db(self):
        """Safely get database instance from self or main_bot."""
        if getattr(self, 'db', None):
            return self.db
        if getattr(self, 'main_bot', None) and getattr(self.main_bot, 'db', None):
            return self.main_bot.db
        return None

    def _get_user_id(self):
        """Safely get user_id from main_bot subscribers or default to 1."""
        main_bot = getattr(self, 'main_bot', None)
        if main_bot and hasattr(main_bot, 'subscribers') and main_bot.subscribers:
            return list(main_bot.subscribers.keys())[0]
        return 1

    def _generate_signature(self, post_params):
        """Generate HMAC signature"""
        import hmac
        import hashlib
        post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
        signature = hmac.new(
            INDODAX_SECRET_KEY.encode(),
            post_data.encode(),
            hashlib.sha512
        ).hexdigest()
        return signature
    
    def _get_headers(self, post_params):
        """Get authenticated headers"""
        signature = self._generate_signature(post_params)
        timestamp = post_params.get('timestamp', str(int(time.time() * 1000)))
        return {
            'Key': INDODAX_API_KEY,
            'Sign': signature,
            'Timestamp': timestamp,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    
    def get_balance(self):
        """Get Indodax balance"""
        if self.dry_run:
            self.balance_idr = 10_000_000
            return True

        try:
            url = f"{INDODAX_API_URL}/tapi"
            timestamp = str(int(time.time() * 1000))
            post_params = {'method': 'getInfo', 'timestamp': timestamp}
            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            headers = self._get_headers(post_params)
            
            response = self.session.post(url, headers=headers, data=post_data)
            data = response.json()
            
            if data.get('success') == 1 and 'return' in data:
                self.balance_idr = float(data['return'].get('balance', {}).get('idr', 0))
                return True
            return False
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return False
    
    def get_candles(self, pair_id, limit=50):
        """Get historical price data for indicators"""
        try:
            # Use Indodax trades history - remove underscore for this specific endpoint
            clean_pair = pair_id.replace('_', '').lower()
            url = f"{INDODAX_API_URL}/api/trades/{clean_pair}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                trades = response.json()
                if isinstance(trades, list):
                    # Convert to candles (simplified)
                    candles = []
                    for trade in trades[:limit]:
                        candles.append({
                            'price': float(trade.get('price', 0)),
                            'volume': float(trade.get('amount', 0)),
                            'timestamp': trade.get('date', 0)
                        })
                    return candles
            return []
        except Exception as e:
            logger.error(f"Error getting candles: {e}")
            return []
    
    def calculate_rsi(self, prices, period=14):
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return 50  # Neutral
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            if diff > 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(diff))
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calculate MACD indicator"""
        if len(prices) < slow + signal:
            return {'macd': 0, 'signal': 0, 'histogram': 0, 'bullish': False}
        
        # Calculate EMAs
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        
        if ema_fast is None or ema_slow is None:
            return {'macd': 0, 'signal': 0, 'histogram': 0, 'bullish': False}
        
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line (simplified)
        recent_macds = []
        for i in range(signal):
            idx = len(prices) - signal + i
            if idx >= slow:
                fast_idx = len(prices) - signal + i - (slow - fast)
                if fast_idx >= 0:
                    ema_f = self.calculate_ema(prices[:len(prices)-signal+i+fast], fast)
                    ema_s = self.calculate_ema(prices[:len(prices)-signal+i+slow], slow)
                    if ema_f and ema_s:
                        recent_macds.append(ema_f - ema_s)
        
        if len(recent_macds) < signal:
            signal_line = macd_line * 0.9  # Approximation
        else:
            signal_line = sum(recent_macds[-signal:]) / signal
        
        histogram = macd_line - signal_line
        
        return {
            'macd': round(macd_line, 4),
            'signal': round(signal_line, 4),
            'histogram': round(histogram, 4),
            'bullish': macd_line > signal_line and macd_line > 0
        }
    
    def calculate_ema(self, prices, period):
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return round(ema, 2)
    
    def calculate_ma_trend(self, prices, short=9, long=25):
        """Calculate MA trend"""
        if len(prices) < long:
            return {'short_ma': 0, 'long_ma': 0, 'bullish': False}
        
        short_ma = sum(prices[-short:]) / short
        long_ma = sum(prices[-long:]) / long
        
        return {
            'short_ma': round(short_ma, 2),
            'long_ma': round(long_ma, 2),
            'bullish': short_ma > long_ma
        }
    
    def calculate_bollinger(self, prices, period=20, std_dev=2):
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return {'position': 0.5, 'status': 'NEUTRAL'}
        
        middle = sum(prices[-period:]) / period
        variance = sum((p - middle) ** 2 for p in prices[-period:]) / period
        std = variance ** 0.5
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        current_price = prices[-1]
        
        # Calculate position within bands (0 = lower, 1 = upper)
        if upper == lower:
            position = 0.5
        else:
            position = (current_price - lower) / (upper - lower)
        
        # Determine status
        if position < 0.3:
            status = 'BULLISH'  # Near lower band, potential bounce
        elif position < 0.7:
            status = 'NEUTRAL'  # Middle area
        else:
            status = 'BEARISH'  # Near upper band, potential reversal
        
        return {
            'upper': round(upper, 2),
            'middle': round(middle, 2),
            'lower': round(lower, 2),
            'position': round(position, 2),
            'status': status
        }
    
    def analyze_pair(self, pair_id, tickers_data):
        """Comprehensive pair analysis"""
        pair = pair_id.upper().replace('_', '/')
        if 'IDR' not in pair:
            pair += '/IDR'
        
        data = tickers_data.get(pair_id, {})
        current_price = float(data.get('last', 0))
        current_volume = float(data.get('vol', 0))
        high_24h = float(data.get('high', 0))
        low_24h = float(data.get('low', 0))
        
        # Skip if price too low
        if current_price < 100 or current_volume < MIN_VOLUME_IDR:
            return None
        
        # Get candles for indicators
        candles = self.get_candles(pair_id, limit=50)
        
        if len(candles) < 20:
            return None
        
        prices = [c['price'] for c in candles]
        
        # Calculate indicators
        rsi = self.calculate_rsi(prices)
        volume_ratio = self.calculate_volume_ratio(current_volume, candles)
        
        # Calculate price momentum
        if low_24h > 0:
            price_change = ((current_price - low_24h) / low_24h) * 100
        else:
            price_change = 0
        
        # Calculate trend (simple MA)
        ma_short = sum(prices[-7:]) / 7
        ma_long = sum(prices[-25:]) / 25
        trend = "BULLISH" if ma_short > ma_long else "BEARISH"
        
        # Calculate volatility
        if low_24h > 0:
            volatility = ((high_24h - low_24h) / low_24h) * 100
        else:
            volatility = 0
        
        # SMART SCORING (max 100)
        score = 0
        
        # RSI Score (30 points) - Buy in oversold zone
        if 30 <= rsi <= 50:
            score += 30  # Perfect entry
        elif 50 < rsi <= 60:
            score += 20  # Good
        elif rsi < 30:
            score += 15  # Very oversold (risky)
        elif 60 < rsi <= 70:
            score += 10  # Getting overbought
        
        # Volume Score (25 points)
        if volume_ratio >= 2.0:
            score += 25  # High volume
        elif volume_ratio >= 1.5:
            score += 20
        elif volume_ratio >= 1.2:
            score += 15
        
        # Price Momentum Score (25 points)
        if 2 <= price_change <= 8:
            score += 25  # Sweet spot
        elif 8 < price_change <= 12:
            score += 15  # Already pumped a bit
        elif price_change < 2:
            score += 10  # No momentum
        
        # Trend Score (20 points)
        if trend == "BULLISH":
            score += 20
        else:
            score += 5
        
        # Entry criteria check
        is_good_entry = (
            30 <= rsi <= 65 and  # Not overbought
            volume_ratio >= MIN_VOLUME_RATIO and
            MIN_PRICE_CHANGE <= price_change <= MAX_PRICE_CHANGE and
            score >= 60  # Minimum score
        )
        
        # Calculate risk/reward
        entry_price = current_price
        stop_loss = entry_price * (1 + STOP_LOSS/100)
        take_profit = entry_price * 1.05  # Target +5%
        
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
        risk_reward = reward / risk if risk > 0 else 0
        optimization = evaluate_hunter_setup(
            score=score,
            rsi=rsi,
            volume_ratio=volume_ratio,
            trend=trend,
            volatility=volatility,
            price_change=price_change,
            risk_reward=risk_reward,
        )
        is_good_entry = is_good_entry and not optimization.should_skip

        return {
            'pair': pair,
            'pair_id': pair_id,
            'price': current_price,
            'volume': current_volume,
            'rsi': rsi,
            'volume_ratio': volume_ratio,
            'price_change': price_change,
            'trend': trend,
            'volatility': volatility,
            'score': score,
            'is_good_entry': is_good_entry,
            'risk_reward': risk_reward,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'edge_score': optimization.edge_score,
            'position_multiplier': optimization.position_multiplier,
            'optimization_reason': optimization.reason,
        }
    
    def find_best_opportunity(self, tickers):
        """Find best trading opportunity with smart analysis"""
        opportunities = []
        
        for pair_id in tickers.keys():
            analysis = self.analyze_pair(pair_id, tickers)
            
            if analysis and analysis['is_good_entry']:
                opportunities.append(analysis)
        
        # Sort by combined quality so high-profit/high-liquidity setups rise first
        opportunities.sort(
            key=lambda x: (x.get('edge_score', 0), x['score'], x.get('volume_ratio', 0)),
            reverse=True,
        )
        
        return opportunities[:3]  # Top 3
    
    def create_buy_order(self, pair_id, price, coin_amount):
        """Execute BUY order (or simulate in DRY RUN mode)"""
        # DRY RUN: Simulate trade without executing
        if self.dry_run:
            logger.info(f"🧪 [DRY RUN] Simulating BUY {pair_id}: {coin_amount:.4f} @ {price:,.0f} IDR")
            # Return a simulated order ID
            return f"DRY_{int(time.time() * 1000)}"

        # REAL TRADING: Execute actual order
        try:
            url = f"{INDODAX_API_URL}/tapi"
            timestamp = str(int(time.time() * 1000))
            coin_name = pair_id.split('_')[0]

            post_params = {
                'method': 'trade',
                'pair': pair_id,
                'type': 'buy',
                'price': str(price),
                coin_name: str(coin_amount),
                'timestamp': timestamp,
                'order_type': 'limit'
            }

            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            headers = self._get_headers(post_params)

            response = self.session.post(url, headers=headers, data=post_data)
            data = response.json()

            if data.get('success') == 1 and 'return' in data:
                return data['return'].get('order_id')
            else:
                logger.error(f"BUY failed: {data}")
                return None
        except Exception as e:
            logger.error(f"Error creating BUY: {e}")
            return None
    
    def create_sell_order(self, pair_id, price, coin_amount):
        """Execute SELL order (or simulate in DRY RUN mode)"""
        # DRY RUN: Simulate trade without executing
        if self.dry_run:
            logger.info(f"🧪 [DRY RUN] Simulating SELL {pair_id}: {coin_amount:.4f} @ {price:,.0f} IDR")
            # Return a simulated order ID
            return f"DRY_SELL_{int(time.time() * 1000)}"

        # REAL TRADING: Execute actual order
        try:
            url = f"{INDODAX_API_URL}/tapi"
            timestamp = str(int(time.time() * 1000))
            coin_name = pair_id.split('_')[0]

            post_params = {
                'method': 'trade',
                'pair': pair_id,
                'type': 'sell',
                'price': str(price),
                coin_name: str(coin_amount),
                'timestamp': timestamp,
                'order_type': 'limit'
            }

            post_data = '&'.join([f"{k}={v}" for k, v in sorted(post_params.items())])
            headers = self._get_headers(post_params)

            response = self.session.post(url, headers=headers, data=post_data)
            data = response.json()

            if data.get('success') == 1 and 'return' in data:
                return data['return'].get('order_id')
            else:
                logger.error(f"SELL failed: {data}")
                return None
        except Exception as e:
            logger.error(f"Error creating SELL: {e}")
            return None
    
    async def send_notification(self, message):
        """Send notification to Telegram"""
        try:
            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Telegram error: {e}")
    
    def _check_signal_before_entry(self, pair):
        """Tier 1: Check ML signal from signals.db + V4 outcome before hunter entry.
        Returns (allowed: bool, reason: str).
        """
        # Check V4 trade outcome prediction first (if available)
        try:
            if hasattr(self, 'main_bot') and self.main_bot:
                v4 = getattr(self.main_bot, 'ml_model_v4', None)
                if v4 and v4.is_fitted:
                    # Get latest signal info for V4 features
                    from signals.signal_db import SignalDatabase
                    sdb = SignalDatabase()
                    symbol = pair.upper().replace('/', '')
                    signals = sdb.get_signals(symbol=symbol, limit=1)
                    if signals:
                        latest = dict(signals[0])
                        v4_features = {
                            'signal_price': float(latest.get('price', 0)),
                            'ml_confidence': float(latest.get('ml_confidence', 0) or 0),
                            'recommendation': latest.get('recommendation', 'HOLD'),
                            'hour': datetime.now().hour,
                            'dayofweek': datetime.now().weekday(),
                            'symbol': symbol,
                        }
                        v4_pred, v4_conf = v4.predict(v4_features)
                        if v4_pred.startswith('BAD'):
                            return False, f"V4 predicts {v4_pred} ({v4_conf:.1%}) — skipping entry"
                        if v4_pred.startswith('GOOD') and v4_conf >= 0.65:
                            return True, f"V4 predicts {v4_pred} ({v4_conf:.1%}) — high confidence"
        except Exception as e:
            logger.debug(f"V4 check skipped for hunter {pair}: {e}")

        # Fallback: check latest signal recommendation
        try:
            from signals.signal_db import SignalDatabase
            sdb = SignalDatabase()
            symbol = pair.upper().replace('/', '')
            signals = sdb.get_signals(symbol=symbol, limit=1)
            if not signals:
                return True, "No recent ML signal in DB"
            latest = dict(signals[0])
            rec = latest.get('recommendation', 'HOLD')
            conf = latest.get('ml_confidence', 0) or 0
            if rec in ('SELL', 'STRONG_SELL'):
                return False, f"ML signal is {rec} (confidence {conf:.1%}) — skipping BUY"
            if rec == 'HOLD' and conf < 0.55:
                return False, f"ML signal HOLD with low confidence ({conf:.1%}) — skipping"
            if rec in ('BUY', 'STRONG_BUY') and conf >= 0.65:
                return True, f"ML signal {rec} (confidence {conf:.1%}) — aligned with hunter"
            return True, f"ML signal {rec} (confidence {conf:.1%}) — neutral, proceeding"
        except Exception as e:
            logger.debug(f"Signal check failed for hunter entry {pair}: {e}")
            return True, "Signal check error, proceeding"

    async def execute_smart_trade(self, opportunity):
        """Execute trade with smart risk management"""
        pair = opportunity['pair']
        pair_id = opportunity['pair_id']
        entry_price = opportunity['price']

        # Tier 1: Check ML signal before entry
        signal_allowed, signal_reason = self._check_signal_before_entry(pair)
        if not signal_allowed:
            logger.info(f"🚫 [SIGNAL_GATE] Hunter entry blocked for {pair}: {signal_reason}")
            return
        logger.info(f"✅ [SIGNAL_GATE] Hunter entry allowed for {pair}: {signal_reason}")
        
        # Pair performance filter
        try:
            if hasattr(self, 'main_bot') and self.main_bot:
                pp = self.main_bot.db.get_pair_performance(pair)
                if pp and pp['profit_factor'] is not None and pp['profit_factor'] < 1.0 and pp['total_trades'] >= 5:
                    logger.info(
                        f"🚫 [PAIR_FILTER] Hunter entry blocked for {pair}: "
                        f"profit_factor={pp['profit_factor']:.2f} (min 1.0) over {pp['total_trades']} trades"
                    )
                    return
        except Exception as e:
            logger.debug(f"⚠️ Pair performance check skipped for hunter {pair}: {e}")
        
        # Check daily loss limit
        if self.daily_pnl <= -MAX_DAILY_LOSS:
            logger.warning(f"⚠️ Daily loss limit reached: {self.daily_pnl:,.0f} IDR")
            return
        
        # Check cooldown after loss
        if self.last_loss_time:
            if (datetime.now() - self.last_loss_time).seconds < COOLDOWN_AFTER_LOSS:
                logger.info("⏳ Cooldown after loss, skipping...")
                return
        
        # Check trade limit
        if self.daily_trades >= MAX_TRADES_PER_DAY:
            logger.warning(f"⚠️ Daily trade limit reached")
            return
        
        # Calculate position size
        position_size_idr = min(MAX_POSITION_SIZE, self.balance_idr * 0.8)
        position_size_idr *= max(opportunity.get('position_multiplier', 1.0), 0.0)
        position_size_idr = min(position_size_idr, self.balance_idr * Config.MAX_POSITION_SIZE)
        if position_size_idr < Config.MIN_TRADE_AMOUNT:
            logger.info(
                f"⏭️ Position skipped for {pair}: optimized size {position_size_idr:,.0f} "
                f"below minimum {Config.MIN_TRADE_AMOUNT:,.0f}"
            )
            return
        coin_amount = round(position_size_idr / entry_price, 8)
        
        if coin_amount <= 0:
            return
        
        # Check risk/reward
        if opportunity['risk_reward'] < max(MIN_RISK_REWARD, Config.PROFIT_HUNTER_MIN_RR):
            logger.warning(f"⚠️ Risk/Reward too low: {opportunity['risk_reward']:.2f}")
            return
        
        # Execute BUY
        logger.info(f"🟢 SMART BUY: {pair} @ {entry_price:,.0f} IDR (RSI: {opportunity['rsi']}, Score: {opportunity['score']})")

        # DRY RUN indicator in message
        dry_run_indicator = "🧪 [DRY RUN] " if self.dry_run else ""

        buy_message = f"""
{dry_run_indicator}🟢 **SMART BUY EXECUTED**

📊 Pair: `{pair}`
💰 Entry: `{entry_price:,.0f}` IDR
💵 Amount: `{position_size_idr:,.0f}` IDR
📦 Coins: `{coin_amount:.2f}`

📈 **Analysis:**
• RSI: `{opportunity['rsi']}` ({'Oversold' if opportunity['rsi'] < 40 else 'Neutral'})
• Volume: `{opportunity['volume_ratio']:.1f}x` average
• Trend: `{opportunity['trend']}`
• Score: `{opportunity['score']}/100`
• Edge: `{opportunity.get('edge_score', 0):.1f}/100`

🎯 **Exit Plan:**
• Target Profit: `{entry_price * 1.08:,.0f}` (+8% max target)
• Stop Loss: `{entry_price * 0.98:,.0f}` (-2%)

💡 _Bot will auto-sell at highest profit reached_

⏰ {datetime.now().strftime('%H:%M:%S')}
        """
        
        await self.send_notification(buy_message)
        
        order_id = self.create_buy_order(pair_id, entry_price, coin_amount)
        
        # Dynamic trailing stop based on volatility
        volatility = opportunity.get('volatility', 0)
        if volatility <= Config.HUNTER_DYNAMIC_TRAILING_VOLATILITY_LOW:
            trailing_percent = Config.HUNTER_DYNAMIC_TRAILING_PCT_LOW_VOL
        elif volatility >= Config.HUNTER_DYNAMIC_TRAILING_VOLATILITY_HIGH:
            trailing_percent = Config.HUNTER_DYNAMIC_TRAILING_PCT_HIGH_VOL
        else:
            trailing_percent = Config.HUNTER_DYNAMIC_TRAILING_PCT_NORMAL

        if order_id:
            self.active_trades[pair] = {
                'entry_price': entry_price,
                'coin_amount': coin_amount,
                'pair_id': pair_id,
                'order_id': order_id,
                'timestamp': datetime.now(),
                'highest_price': entry_price,  # For trailing stop
                'sold_50': False,
                'sold_30': False,
                'sold_20': False,
                'breakeven_stop': None,
                'breakeven_activated': False,
                'edge_score': opportunity.get('edge_score', 0),
                'max_hold_until': datetime.now() + timedelta(hours=Config.HUNTER_MAX_HOLD_HOURS),
                'trailing_percent': trailing_percent,
            }

            # Persist BUY to database
            db = self._get_db()
            if db:
                try:
                    ml_conf = opportunity.get('ml_confidence', 0) or 0
                    if ml_conf > 1:
                        ml_conf = ml_conf / 100.0
                    trade_id = db.add_trade(
                        user_id=self._get_user_id(),
                        pair=pair,
                        trade_type='BUY',
                        price=entry_price,
                        amount=coin_amount,
                        total=position_size_idr,
                        fee=0,
                        signal_source='smart_hunter',
                        ml_confidence=ml_conf,
                        notes=f"Score:{opportunity['score']}, Edge:{opportunity.get('edge_score', 0):.1f}, RSI:{opportunity['rsi']}, R/R:{opportunity['risk_reward']:.2f}",
                    )
                    self.active_trades[pair]['db_trade_id'] = trade_id
                    logger.info(f"📝 Trade persisted to DB: id={trade_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to persist trade to DB: {e}")

            logger.info(
                f"📊 Trade setup for {pair}: max_hold={Config.HUNTER_MAX_HOLD_HOURS}h, "
                f"trail={trailing_percent}% (vol={volatility:.1f}%)"
            )
            self.daily_trades += 1
            self.balance_idr -= position_size_idr
            logger.info(f"✅ Trade active: {pair}")
        else:
            logger.error(f"❌ Failed to buy {pair}")
    
    async def monitor_positions_smart(self):
        """Monitor positions with trailing stop and partial sells"""
        if not self.active_trades:
            return

        tickers = {}
        try:
            url = f"{INDODAX_API_URL}/api/tickers"
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                tickers = response.json().get('tickers', {})
        except Exception as e:
            logger.warning(f"Failed to fetch tickers: {e}")
            return

        for pair, trade in list(self.active_trades.items()):
            pair_id = trade['pair_id']

            if pair_id not in tickers:
                continue

            current_price = float(tickers[pair_id].get('last', 0))
            entry_price = trade['entry_price']
            coin_amount = trade['coin_amount']

            # Update highest price for trailing stop
            if current_price > trade['highest_price']:
                self.active_trades[pair]['highest_price'] = current_price

            # Calculate P&L
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            pnl_idr = (current_price - entry_price) * coin_amount

            logger.info(f"📊 {pair}: {pnl_pct:+.2f}% | Highest: {trade['highest_price']:,.0f}")

            # Check for partial sells - execute silently without notification
            if pnl_pct >= 3.0 and not trade['sold_50']:
                await self._execute_partial_sell_silent(pair, trade, current_price, 0.5, "Take Profit 1 (+3%)")
            elif pnl_pct >= 5.0 and not trade['sold_30']:
                await self._execute_partial_sell_silent(pair, trade, current_price, 0.3, "Take Profit 2 (+5%)")
            elif pnl_pct >= 8.0 and not trade['sold_20']:
                await self._execute_partial_sell_silent(pair, trade, current_price, 0.2, "Take Profit 3 (+8%)")

            # Check time-based max hold exit
            max_hold_until = trade.get('max_hold_until')
            if max_hold_until and datetime.now() >= max_hold_until:
                await self.close_position(pair, trade, current_price, f"Time-Based Exit (held {Config.HUNTER_MAX_HOLD_HOURS}h)")
                # NOTE: daily_pnl updated inside close_position() — do NOT double-count
                continue

            # Check trailing stop (dynamic by volatility)
            if TRAILING_STOP:
                highest = trade['highest_price']
                trailing_pct = trade.get('trailing_percent', TRAILING_PERCENT)
                trailing_stop_price = highest * (1 - trailing_pct / 100)

                if current_price <= trailing_stop_price and pnl_pct > 0:
                    await self.close_position(pair, trade, current_price, f"Trailing Stop (+{pnl_pct:.1f}%, trail={trailing_pct}%)")
                    # NOTE: daily_pnl updated inside close_position() — do NOT double-count
                    continue

            # Check breakeven stop (after TP1 secured)
            if trade.get('breakeven_activated') and trade.get('breakeven_stop'):
                if current_price <= trade['breakeven_stop']:
                    await self.close_position(pair, trade, current_price, "Breakeven Stop (TP1 secured)")
                    # NOTE: daily_pnl updated inside close_position() — do NOT double-count
                    continue

            # Check hard stop loss
            if pnl_pct <= STOP_LOSS:
                await self.close_position(pair, trade, current_price, "Stop Loss (-2%)")
                self.last_loss_time = datetime.now()
                # NOTE: daily_pnl updated inside close_position() — do NOT double-count
    
    async def _execute_partial_sell_silent(self, pair, trade, price, percent, reason):
        """Execute partial sell WITHOUT sending notification (silent)"""
        coin_amount = trade['coin_amount']
        sell_amount = round(coin_amount * percent, 8)
        pair_id = trade['pair_id']

        sell_order_id = self.create_sell_order(pair_id, price, sell_amount)

        if sell_order_id:
            pnl = (price - trade['entry_price']) * sell_amount

            # FIX: Reduce remaining coin amount to prevent over-selling on close
            self.active_trades[pair]['coin_amount'] -= sell_amount

            if percent == 0.5:
                self.active_trades[pair]['sold_50'] = True
                # Activate breakeven stop after securing first partial profit
                self.active_trades[pair]['breakeven_activated'] = True
                # FIX: True breakeven includes round-trip fees (0.3% entry + 0.3% exit = 0.6%)
                breakeven_price = self.active_trades[pair]['entry_price'] * (1 + 2 * Config.TRADING_FEE_RATE)
                self.active_trades[pair]['breakeven_stop'] = breakeven_price
                logger.info(f"🛡️ Breakeven stop activated for {pair} at {breakeven_price:,.0f} (includes fees)")
            elif percent == 0.3:
                self.active_trades[pair]['sold_30'] = True
            elif percent == 0.2:
                self.active_trades[pair]['sold_20'] = True

            # FIX BUG #8: Update daily_pnl dengan profit dari partial sell
            self.daily_pnl += pnl
            self.balance_idr += (price * sell_amount)

            # Log silently without sending notification
            logger.info(f"✅ {reason} for {pair}: +{pnl:,.0f} IDR (silent, daily_pnl updated)")

    async def partial_sell(self, pair, trade, price, percent, reason):
        """Sell partial position"""
        coin_amount = trade['coin_amount']
        sell_amount = round(coin_amount * percent, 8)
        pair_id = trade['pair_id']

        sell_order_id = self.create_sell_order(pair_id, price, sell_amount)

        if sell_order_id:
            pnl = (price - trade['entry_price']) * sell_amount

            if percent == 0.5:
                self.active_trades[pair]['sold_50'] = True
            elif percent == 0.3:
                self.active_trades[pair]['sold_30'] = True
            elif percent == 0.2:
                self.active_trades[pair]['sold_20'] = True

            self.balance_idr += (price * sell_amount)

            message = f"""
✅ **PARTIAL SELL** - {reason}

📊 Pair: `{pair}`
💰 Sell Price: `{price:,.0f}` IDR
📦 Amount: `{sell_amount:.2f}` coins
💵 Received: `{price * sell_amount:,.0f}` IDR
📈 P&L: `{pnl:,.0f}` IDR

Remaining: `{coin_amount - sell_amount:.2f}` coins
            """

            await self.send_notification(message)
            logger.info(f"✅ {reason} for {pair}: +{pnl:,.0f} IDR")
    
    async def close_position(self, pair, trade, price, reason):
        """Close entire position with highest profit notification"""
        coin_amount = trade['coin_amount']
        pair_id = trade['pair_id']

        sell_order_id = self.create_sell_order(pair_id, price, coin_amount)

        if sell_order_id:
            pnl_pct = ((price - trade['entry_price']) / trade['entry_price']) * 100
            pnl_idr = (price - trade['entry_price']) * coin_amount

            # Close in database
            db = self._get_db()
            db_trade_id = trade.get('db_trade_id')
            if db and db_trade_id:
                try:
                    db.close_trade(
                        trade_id=db_trade_id,
                        close_price=price,
                        sell_price=price,
                        sell_amount=coin_amount,
                        order_id=sell_order_id,
                        reason=reason,
                    )
                    logger.info(f"📝 Trade closed in DB: id={db_trade_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to close trade in DB: {e}")

            # Calculate highest profit level that was reached during this trade
            highest_profit_pct = pnl_pct  # Current profit
            if trade.get('sold_50', False):
                highest_profit_pct = max(highest_profit_pct, 3.0)
            if trade.get('sold_30', False):
                highest_profit_pct = max(highest_profit_pct, 5.0)
            if trade.get('sold_20', False):
                highest_profit_pct = max(highest_profit_pct, 8.0)

            del self.active_trades[pair]
            self.balance_idr += (price * coin_amount)
            self.daily_pnl += pnl_idr

            emoji = "🎯" if pnl_idr > 0 else "🛑"
            pnl_emoji = "✅" if pnl_idr > 0 else "❌"

            # DRY RUN indicator in message
            dry_run_indicator = "🧪 [DRY RUN] " if self.dry_run else ""

            # Only show highest profit percentage reached, not all levels
            message = f"""
{dry_run_indicator}{emoji} **POSITION CLOSED** - {reason}

📊 Pair: `{pair}`
💰 Entry: `{trade['entry_price']:,.0f}` IDR
💰 Exit: `{price:,.0f}` IDR
📈 **Highest Profit Reached:** `+{highest_profit_pct:.1f}%` ({pnl_emoji} `{pnl_idr:,.0f}` IDR)
⏰ Duration: {datetime.now() - trade['timestamp']}

💰 **Daily P&L:** `{self.daily_pnl:,.0f}` IDR
            """

            await self.send_notification(message)
            logger.info(f"✅ Closed {pair}: {pnl_idr:,.0f} IDR (Highest: +{highest_profit_pct:.1f}%)")
    
    async def run(self):
        """Main loop"""
        logger.info("[START] Smart Profit Hunter v2 started")
        logger.info(f"[INFO] Min volume: {MIN_VOLUME_IDR/1_000_000_000:.1f}B IDR")
        logger.info(f"[INFO] Max position: {MAX_POSITION_SIZE/1_000:.0f}k IDR")
        logger.info(f"[INFO] Max daily loss: {MAX_DAILY_LOSS/1_000:.0f}k IDR")
        logger.info(f"[INFO] Min risk/reward: {MIN_RISK_REWARD}:1")
        logger.info(f"[INFO] Trailing stop: {TRAILING_PERCENT}%")
        
        self.get_balance()
        await asyncio.sleep(5)
        
        while True:
            try:
                # Reset daily
                if datetime.now().date() != self.last_reset:
                    self.daily_trades = 0
                    self.daily_pnl = 0
                    self.last_reset = datetime.now().date()
                    logger.info("[INFO] Daily reset")
                
                # Get tickers
                try:
                    url = f"{INDODAX_API_URL}/api/tickers"
                    response = self.session.get(url, timeout=10)
                    tickers = response.json().get('tickers', {}) if response.status_code == 200 else {}
                except Exception as e:
                    logger.warning(f"Failed to fetch tickers in scan loop: {e}")
                    tickers = {}
                
                # Find opportunities
                opportunities = self.find_best_opportunity(tickers)
                
                if opportunities:
                    logger.info(f"[FOUND] {len(opportunities)} opportunities")
                    top = opportunities[0]
                    logger.info(f"[TOP] {top['pair']}: RSI={top['rsi']}, Vol={top['volume_ratio']:.1f}x, Score={top['score']}")
                    
                    if self.balance_idr > MAX_POSITION_SIZE and not self.active_trades:
                        await self.execute_smart_trade(top)
                
                # Monitor positions
                await self.monitor_positions_smart()
                
                await asyncio.sleep(30)
                
            except KeyboardInterrupt:
                logger.info("[STOP] Stopped by user")
                break
            except Exception as e:
                logger.error(f"[ERROR] {e}")
                await asyncio.sleep(30)


async def main():
    hunter = SmartProfitHunter()
    await hunter.run()


if __name__ == "__main__":
    asyncio.run(main())
