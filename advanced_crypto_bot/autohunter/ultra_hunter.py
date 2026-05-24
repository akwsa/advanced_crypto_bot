#!/usr/bin/env python3
"""
Ultra Conservative Hunter — Integrated version with DB persistence.
Based on deprecated.archived/ultra_hunter.py, refactored to run inside
the main bot process and persist trades to trading.db.
"""

import os
import requests
import logging
import time
import asyncio
from datetime import datetime, timedelta
from telegram import Bot

from core.config import Config

logger = logging.getLogger('crypto_bot')

# Ultra Conservative Settings
MIN_VOLUME_IDR = 2_000_000_000
MAX_POSITION_SIZE = 100_000
MAX_DAILY_LOSS = 100_000
MAX_TRADES_PER_DAY = 2
COOLDOWN_AFTER_LOSS = 3600
MIN_RSI = 30
MAX_RSI = 45
MIN_VOLUME_RATIO = 2.0
TAKE_PROFIT = 4.0
STOP_LOSS = -2.0
TRAILING_STOP = True
TRAILING_PERCENT = 1.5
MIN_RISK_REWARD = 2.0
INDODAX_API_URL = "https://indodax.com"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("ADMIN_IDS", "").split(",")[0].strip() if os.getenv("ADMIN_IDS") else ""


class UltraConservativeHunter:
    """Ultra conservative trading strategy with DB persistence."""

    def __init__(self, dry_run=True, db=None):
        self.session = requests.Session()
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.active_trades = {}
        self.daily_trades = 0
        self.daily_pnl = 0
        self.balance_idr = 0
        self.last_loss_time = None
        self.dry_run = dry_run
        self.db = db

        if dry_run:
            logger.info("🧪 Ultra Hunter initialized in DRY RUN mode")
        else:
            logger.warning("🔴 Ultra Hunter initialized in REAL TRADING mode")

    def _get_db(self):
        if getattr(self, 'db', None):
            return self.db
        if getattr(self, 'main_bot', None) and getattr(self.main_bot, 'db', None):
            return self.main_bot.db
        return None

    def _get_user_id(self):
        main_bot = getattr(self, 'main_bot', None)
        if main_bot and hasattr(main_bot, 'subscribers') and main_bot.subscribers:
            return list(main_bot.subscribers.keys())[0]
        return 1

    def get_balance(self):
        if self.dry_run:
            self.balance_idr = 10_000_000
            return True
        # Real balance fetch omitted for brevity; same as smart_profit_hunter
        return True

    def get_candles(self, pair_id, limit=50):
        try:
            r = self.session.get(f"{INDODAX_API_URL}/api/trades/{pair_id}", timeout=10)
            if r.status_code == 200:
                trades = r.json()
                if isinstance(trades, list):
                    return [{'price': float(t.get('price', 0)), 'volume': float(t.get('amount', 0))}
                            for t in trades[:limit]]
        except Exception as e:
            logger.debug(f"Failed to fetch trades for {pair_id}: {e}")
        return []

    def calc_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50
        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            gains.append(max(diff, 0))
            losses.append(abs(min(diff, 0)))
        avg_g = sum(gains[-period:]) / period
        avg_l = sum(losses[-period:]) / period
        if avg_l == 0:
            return 100
        return round(100 - (100 / (1 + avg_g / avg_l)), 2)

    def calc_ema(self, prices, period):
        if len(prices) < period:
            return None
        mult = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for p in prices[period:]:
            ema = (p - ema) * mult + ema
        return round(ema, 2)

    def calc_macd(self, prices):
        if len(prices) < 35:
            return {'bullish': False, 'macd': 0, 'hist': 0, 'fresh': False}
        ema12 = self.calc_ema(prices, 12)
        ema26 = self.calc_ema(prices, 26)
        if ema12 is None or ema26 is None:
            return {'bullish': False, 'macd': 0, 'hist': 0, 'fresh': False}
        macd = ema12 - ema26
        prev_macd = self.calc_ema(prices[:-5], 12) - self.calc_ema(prices[:-5], 26) if len(prices) > 35 else 0
        fresh = macd > 0 and prev_macd <= 0
        return {'bullish': macd > 0, 'macd': round(macd, 4), 'hist': round(macd * 0.1, 4), 'fresh': fresh}

    def calc_ma(self, prices):
        if len(prices) < 25:
            return {'bullish': False}
        ma9 = sum(prices[-9:]) / 9
        ma25 = sum(prices[-25:]) / 25
        return {'bullish': ma9 > ma25, 'ma9': ma9, 'ma25': ma25}

    def calc_bb(self, prices):
        if len(prices) < 20:
            return {'status': 'NEUTRAL', 'pos': 0.5}
        mid = sum(prices[-20:]) / 20
        std = (sum((p - mid) ** 2 for p in prices[-20:]) / 20) ** 0.5
        upper, lower = mid + 2 * std, mid - 2 * std
        if upper == lower:
            return {'status': 'NEUTRAL', 'pos': 0.5}
        pos = (prices[-1] - lower) / (upper - lower)
        status = 'LOWER' if pos < 0.2 else 'UPPER' if pos > 0.8 else 'MID'
        return {'status': status, 'pos': pos, 'lower': lower, 'upper': upper}

    def calc_vol_ratio(self, candles):
        if len(candles) < 20:
            return 1.0
        avg_vol = sum(c['volume'] for c in candles[-20:]) / 20
        recent_vol = sum(c['volume'] for c in candles[-5:]) / 5
        return round(recent_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    def analyze(self, pair_id, tickers):
        ticker = tickers.get(pair_id, {})
        vol_idr = float(ticker.get('vol_idr', 0))
        if vol_idr < MIN_VOLUME_IDR:
            return None

        candles = self.get_candles(pair_id)
        if len(candles) < 35:
            return None

        prices = [c['price'] for c in candles]
        rsi = self.calc_rsi(prices)
        macd = self.calc_macd(prices)
        ma = self.calc_ma(prices)
        bb = self.calc_bb(prices)
        vol_ratio = self.calc_vol_ratio(candles)

        checks = {
            'rsi_ok': MIN_RSI <= rsi <= MAX_RSI,
            'macd_bullish': macd['bullish'],
            'macd_fresh': macd['fresh'],
            'ma_bullish': ma['bullish'],
            'bb_lower': bb['status'] == 'LOWER',
            'volume_ok': vol_ratio >= MIN_VOLUME_RATIO
        }

        score = sum(checks.values()) * 15 + 10
        all_pass = all(checks.values())

        return {
            'pair': pair_id.replace('_', '').upper(),
            'pair_id': pair_id,
            'price': prices[-1],
            'rsi': rsi,
            'macd': macd,
            'ma': ma,
            'bb': bb,
            'vol_ratio': vol_ratio,
            'score': score,
            'checks': checks,
            'all_pass': all_pass
        }

    def buy(self, pair_id, price, coin_amount):
        if self.dry_run:
            logger.info(f"🧪 [DRY RUN] Simulating BUY {pair_id}: {coin_amount:.4f} @ {price:,.0f}")
            return f"DRY_BUY_{int(time.time() * 1000)}"
        # Real trading omitted; same pattern as smart_profit_hunter
        return None

    def sell(self, pair_id, price, coin_amount):
        if self.dry_run:
            logger.info(f"🧪 [DRY RUN] Simulating SELL {pair_id}: {coin_amount:.4f} @ {price:,.0f}")
            return f"DRY_SELL_{int(time.time() * 1000)}"
        # Real trading omitted
        return None

    async def notify(self, msg):
        try:
            await self.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def scan_and_trade(self, tickers):
        opportunities = []
        for pair_id in tickers.keys():
            analysis = self.analyze(pair_id, tickers)
            if analysis and analysis['all_pass']:
                opportunities.append(analysis)

        opportunities.sort(key=lambda x: x['score'], reverse=True)

        if opportunities and self.balance_idr > MAX_POSITION_SIZE and not self.active_trades:
            if self.last_loss_time and (datetime.now() - self.last_loss_time).seconds < COOLDOWN_AFTER_LOSS:
                logger.info("⏳ Cooldown after loss, skipping...")
                return
            if self.daily_trades >= MAX_TRADES_PER_DAY:
                logger.warning(f"⚠️ Daily trade limit reached ({MAX_TRADES_PER_DAY})")
                return
            if self.daily_pnl <= -MAX_DAILY_LOSS:
                logger.warning(f"⚠️ Daily loss limit reached: {self.daily_pnl:,.0f} IDR")
                return
            await self.execute_trade(opportunities[0])

    async def execute_trade(self, opp):
        position_size = MAX_POSITION_SIZE * 0.9
        coin_amt = round(position_size / opp['price'], 8)
        if coin_amt <= 0:
            return

        dry_indicator = "🧪 [DRY RUN] " if self.dry_run else ""
        logger.info(f"{dry_indicator}ULTRA BUY {opp['pair']} @ {opp['price']:,.0f}")

        msg = f"""
{dry_indicator}🟢 **ULTRA CONSERVATIVE BUY**

📊 Pair: `{opp['pair']}`
💰 Entry: `{opp['price']:,.0f}` IDR
💵 Amount: `{position_size:,.0f}` IDR
📦 Coins: `{coin_amt:.2f}`

✅ **ALL Criteria Met:**
• RSI: `{opp['rsi']}` (Oversold: 30-45) ✅
• MACD: BULLISH ✅
• MA: BULLISH ✅
• Bollinger: `{opp['bb']['status']}` (At lower band) ✅
• Volume: `{opp['vol_ratio']:.1f}x` average ✅
• Score: `{opp['score']}/100`

🎯 Target: `{opp['price'] * 1.04:,.0f}` IDR (+4%)
🛑 Stop: `{opp['price'] * 0.98:,.0f}` IDR (-2%)

⏰ {datetime.now().strftime('%H:%M:%S')}
        """
        await self.notify(msg)

        order_id = self.buy(opp['pair_id'], opp['price'], coin_amt)

        if order_id:
            self.active_trades[opp['pair']] = {
                'entry_price': opp['price'],
                'coin_amount': coin_amt,
                'pair_id': opp['pair_id'],
                'order_id': order_id,
                'timestamp': datetime.now(),
                'highest_price': opp['price']
            }

            # Persist BUY to database
            db = self._get_db()
            if db:
                try:
                    trade_id = db.add_trade(
                        user_id=self._get_user_id(),
                        pair=opp['pair'],
                        trade_type='BUY',
                        price=opp['price'],
                        amount=coin_amt,
                        total=position_size,
                        fee=0,
                        signal_source='ultra_hunter',
                        ml_confidence=0,
                        notes=f"Score:{opp['score']}, RSI:{opp['rsi']}, Vol:{opp['vol_ratio']:.1f}x",
                    )
                    self.active_trades[opp['pair']]['db_trade_id'] = trade_id
                    logger.info(f"📝 Ultra Hunter trade persisted to DB: id={trade_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to persist ultra hunter trade: {e}")

            self.daily_trades += 1
            if self.dry_run:
                self.balance_idr -= position_size
            logger.info(f"✅ Ultra trade active: {opp['pair']} (Order: {order_id})")

    async def monitor_positions(self, tickers):
        if not self.active_trades:
            return

        for pair, trade in list(self.active_trades.items()):
            pair_id = trade['pair_id']
            if pair_id not in tickers:
                continue

            current_price = float(tickers[pair_id].get('last', 0))
            entry_price = trade['entry_price']
            coin_amount = trade['coin_amount']

            if current_price > trade['highest_price']:
                trade['highest_price'] = current_price

            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            pnl_idr = (current_price - entry_price) * coin_amount

            # Trailing stop
            if TRAILING_STOP:
                highest = trade['highest_price']
                trail_price = highest * (1 - TRAILING_PERCENT / 100)
                if current_price <= trail_price and pnl_pct > 0:
                    await self.close_position(pair, trade, current_price, f"Trailing Stop (+{pnl_pct:.1f}%)")
                    continue

            # Hard stop loss
            if pnl_pct <= STOP_LOSS:
                await self.close_position(pair, trade, current_price, "Stop Loss (-2%)")
                self.last_loss_time = datetime.now()
                self.daily_pnl += pnl_idr
                continue

            # Take profit
            if pnl_pct >= TAKE_PROFIT:
                await self.close_position(pair, trade, current_price, f"Take Profit (+{pnl_pct:.1f}%)")

    async def close_position(self, pair, trade, price, reason):
        coin_amount = trade['coin_amount']
        pair_id = trade['pair_id']

        sell_order_id = self.sell(pair_id, price, coin_amount)

        if sell_order_id:
            entry_price = trade['entry_price']
            pnl_pct = ((price - entry_price) / entry_price) * 100
            pnl_idr = (price - entry_price) * coin_amount

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
                    logger.info(f"📝 Ultra Hunter trade closed in DB: id={db_trade_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to close ultra hunter trade in DB: {e}")

            del self.active_trades[pair]
            self.daily_pnl += pnl_idr
            if self.dry_run:
                self.balance_idr += price * coin_amount

            dry_indicator = "🧪 [DRY RUN] " if self.dry_run else ""
            emoji = "🎯" if pnl_idr > 0 else "🛑"
            pnl_emoji = "✅" if pnl_idr > 0 else "❌"

            msg = f"""
{dry_indicator}{emoji} **POSITION CLOSED** - {reason}

📊 Pair: `{pair}`
💰 Entry: `{entry_price:,.0f}` IDR
💰 Exit: `{price:,.0f}` IDR
📈 P&L: {pnl_emoji} `{pnl_idr:,.0f}` IDR (`{pnl_pct:+.1f}%`)

💰 **Daily P&L:** `{self.daily_pnl:,.0f}` IDR
            """
            await self.notify(msg)
            logger.info(f"✅ Closed {pair}: {pnl_idr:,.0f} IDR ({reason})")

    async def run(self):
        logger.info("[START] Ultra Conservative Hunter started")
        self.get_balance()
        await asyncio.sleep(5)

        while True:
            try:
                if datetime.now().date() != getattr(self, '_last_reset', datetime.now().date()):
                    self.daily_trades = 0
                    self.daily_pnl = 0
                    self._last_reset = datetime.now().date()
                    logger.info("[INFO] Daily reset")

                try:
                    url = f"{INDODAX_API_URL}/api/tickers"
                    response = self.session.get(url, timeout=10)
                    tickers = response.json().get('tickers', {}) if response.status_code == 200 else {}
                except Exception as e:
                    logger.warning(f"Failed to fetch tickers: {e}")
                    tickers = {}

                await self.scan_and_trade(tickers)
                await self.monitor_positions(tickers)
                await asyncio.sleep(30)

            except KeyboardInterrupt:
                logger.info("[STOP] Stopped by user")
                break
            except Exception as e:
                logger.error(f"[ERROR] {e}")
                await asyncio.sleep(30)
