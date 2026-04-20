#!/usr/bin/env python3
"""
Ultra Conservative Hunter
=========================
Target: +3-5% per trade, Cut Loss: -2%
Max 2 trades/day, Max 100k loss/day

Features:
- DRY RUN / REAL TRADE modes
- Strict entry criteria (RSI 30-45, MACD bullish, 2x volume)
- Trailing stop with 1.5% trail
- CSV trade logging
"""

import requests
import logging
import time
import asyncio
import csv
import os
import hmac
import hashlib
from datetime import datetime, timedelta
from telegram import Bot

# Settings
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
LOG_FILE = 'logs/ultra_hunter.csv'

logger = logging.getLogger(__name__)


class UltraConservativeHunter:
    """
    Ultra conservative trading strategy.

    Args:
        api_key: Indodax API key
        api_secret: Indodax API secret
        telegram_token: Bot token for notifications
        telegram_chat_id: Chat ID for notifications
        dry_run: If True, simulate trades. If False, execute real trades.
    """

    def __init__(self, api_key, api_secret, telegram_token, telegram_chat_id, dry_run=True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.dry_run = dry_run
        self.is_real_trading = not dry_run

        self.session = requests.Session()
        self.bot = Bot(token=telegram_token)
        self.active_trades = {}
        self.daily_trades = 0
        self.daily_pnl = 0
        self.balance_idr = 0
        self.last_loss_time = None

        self.indodax_url = "https://indodax.com"

        # Mode indicator
        mode_label = "🧪 DRY RUN" if dry_run else "🔴 REAL TRADING"
        logger.info(f"Ultra Hunter initialized: {mode_label}")

        if dry_run:
            logger.info("   Trades will be SIMULATED (no real orders)")
        else:
            logger.warning("   Real orders will be placed on Indodax!")

        self._init_log()

    def _init_log(self):
        """Initialize CSV trade log."""
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'pair', 'type', 'entry_price', 'exit_price',
                    'amount_idr', 'coin_amount', 'pnl_idr', 'pnl_pct', 'reason', 'mode'
                ])

    def _log_trade(self, pair, trade_type, entry, exit_price, amount_idr,
                   coin_amount, pnl_idr, pnl_pct, reason):
        """Log trade to CSV."""
        try:
            with open(LOG_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    pair,
                    trade_type,
                    entry,
                    exit_price,
                    amount_idr,
                    coin_amount,
                    pnl_idr,
                    f"{pnl_pct:+.2f}",
                    reason,
                    "DRY_RUN" if self.dry_run else "REAL"
                ])
        except Exception as e:
            logger.error(f"Failed to log trade: {e}")

    def _get_signature(self, params):
        """Generate HMAC signature."""
        data = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(self.api_secret.encode(), data.encode(), hashlib.sha512).hexdigest()

    def _get_headers(self, params):
        """Get authenticated headers."""
        return {
            'Key': self.api_key,
            'Sign': self._get_signature(params),
            'Timestamp': params.get('timestamp', str(int(time.time() * 1000)))
        }

    def get_balance(self):
        """Get Indodax balance."""
        if self.dry_run:
            # Use simulated balance in dry run
            self.balance_idr = 10000000  # 10M IDR default
            logger.info(f"🧪 [DRY RUN] Simulated balance: {self.balance_idr:,.0f} IDR")
            return True

        try:
            url = f"{self.indodax_url}/tapi"
            params = {'method': 'getInfo', 'timestamp': str(int(time.time() * 1000))}
            data = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            r = self.session.post(url, headers=self._get_headers(params), data=data)
            d = r.json()
            if d.get('success') == 1:
                self.balance_idr = float(d['return'].get('balance', {}).get('idr', 0))
                logger.info(f"💰 Balance: {self.balance_idr:,.0f} IDR")
                return True
        except Exception as e:
            logger.error(f"Balance error: {e}")
        return False

    def get_candles(self, pair_id, limit=50):
        """Get historical price data."""
        try:
            r = self.session.get(f"{self.indodax_url}/api/trades/{pair_id}", timeout=10)
            if r.status_code == 200:
                trades = r.json()
                if isinstance(trades, list):
                    return [{'price': float(t.get('price', 0)), 'volume': float(t.get('amount', 0))}
                            for t in trades[:limit]]
        except Exception as e:
            logger.debug(f"Failed to fetch recent trades for {pair_id}: {e}")
        return []

    def calc_rsi(self, prices, period=14):
        """Calculate RSI indicator."""
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
        return round(100 - (100 / (1 + avg_g/avg_l)), 2)

    def calc_ema(self, prices, period):
        """Calculate EMA."""
        if len(prices) < period:
            return None
        mult = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for p in prices[period:]:
            ema = (p - ema) * mult + ema
        return round(ema, 2)

    def calc_macd(self, prices):
        """Calculate MACD indicator."""
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
        """Calculate Moving Average trend."""
        if len(prices) < 25:
            return {'bullish': False}
        ma9 = sum(prices[-9:]) / 9
        ma25 = sum(prices[-25:]) / 25
        return {'bullish': ma9 > ma25, 'ma9': ma9, 'ma25': ma25}

    def calc_bb(self, prices):
        """Calculate Bollinger Bands."""
        if len(prices) < 20:
            return {'status': 'NEUTRAL', 'pos': 0.5}
        mid = sum(prices[-20:]) / 20
        std = (sum((p-mid)**2 for p in prices[-20:])/20) ** 0.5
        upper, lower = mid + 2*std, mid - 2*std
        if upper == lower:
            return {'status': 'NEUTRAL', 'pos': 0.5}
        pos = (prices[-1] - lower) / (upper - lower)
        status = 'LOWER' if pos < 0.2 else 'UPPER' if pos > 0.8 else 'MID'
        return {'status': status, 'pos': pos, 'lower': lower, 'upper': upper}

    def calc_vol_ratio(self, candles):
        """Calculate volume ratio."""
        if len(candles) < 20:
            return 1.0
        avg_vol = sum(c['volume'] for c in candles[-20:]) / 20
        recent_vol = sum(c['volume'] for c in candles[-5:]) / 5
        return round(recent_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    def analyze(self, pair_id, tickers):
        """Analyze a pair for trading opportunity."""
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

        # Ultra strict criteria
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

    def buy(self, pair_id, price, amount):
        """Execute BUY order or simulate."""
        # DRY RUN: Simulate
        if self.dry_run:
            logger.info(f"🧪 [DRY RUN] Simulating BUY {pair_id}: {amount:.4f} @ {price:,.0f}")
            return f"DRY_BUY_{int(time.time() * 1000)}"

        # REAL TRADING
        try:
            url = f"{self.indodax_url}/tapi"
            ts = str(int(time.time() * 1000))
            coin = pair_id.split('_')[0]
            params = {
                'method': 'trade',
                'pair': pair_id,
                'type': 'buy',
                'price': str(price),
                coin: str(amount),
                'timestamp': ts,
                'order_type': 'limit'
            }
            data = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            r = self.session.post(url, headers=self._get_headers(params), data=data)
            d = r.json()
            if d.get('success') == 1 and 'return' in d:
                return d['return'].get('order_id')
            logger.error(f"BUY failed: {d}")
        except Exception as e:
            logger.error(f"BUY error: {e}")
        return None

    def sell(self, pair_id, price, amount):
        """Execute SELL order or simulate."""
        # DRY RUN: Simulate
        if self.dry_run:
            logger.info(f"🧪 [DRY RUN] Simulating SELL {pair_id}: {amount:.4f} @ {price:,.0f}")
            return f"DRY_SELL_{int(time.time() * 1000)}"

        # REAL TRADING
        try:
            url = f"{self.indodax_url}/tapi"
            ts = str(int(time.time() * 1000))
            coin = pair_id.split('_')[0]
            params = {
                'method': 'trade',
                'pair': pair_id,
                'type': 'sell',
                'price': str(price),
                coin: str(amount),
                'timestamp': ts,
                'order_type': 'limit'
            }
            data = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            r = self.session.post(url, headers=self._get_headers(params), data=data)
            d = r.json()
            if d.get('success') == 1 and 'return' in d:
                return d['return'].get('order_id')
            logger.error(f"SELL failed: {d}")
        except Exception as e:
            logger.error(f"SELL error: {e}")
        return None

    async def notify(self, msg):
        """Send Telegram notification."""
        try:
            dry_indicator = "🧪 [DRY RUN] " if self.dry_run else ""
            await self.bot.send_message(
                chat_id=self.telegram_chat_id,
                text=f"{dry_indicator}{msg}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def scan_and_trade(self, tickers):
        """Scan for opportunities and execute trades."""
        opportunities = []
        for pair_id in tickers.keys():
            analysis = self.analyze(pair_id, tickers)
            if analysis and analysis['all_pass']:
                opportunities.append(analysis)

        opportunities.sort(key=lambda x: x['score'], reverse=True)

        if opportunities and self.balance_idr > MAX_POSITION_SIZE and not self.active_trades:
            if self.last_loss_time:
                if (datetime.now() - self.last_loss_time).seconds < COOLDOWN_AFTER_LOSS:
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
        """Execute a trade."""
        coin_amt = round((MAX_POSITION_SIZE * 0.9) / opp['price'], 8)
        if coin_amt <= 0:
            return

        dry_indicator = "🧪 [DRY RUN] " if self.dry_run else ""
        logger.info(f"{dry_indicator}ULTRA BUY {opp['pair']} @ {opp['price']:,.0f}")

        msg = f"""
{dry_indicator}🟢 **ULTRA CONSERVATIVE BUY**

📊 Pair: `{opp['pair']}`
💰 Entry: `{opp['price']:,.0f}` IDR
💵 Amount: `{MAX_POSITION_SIZE * 0.9:,.0f}` IDR
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
            self.daily_trades += 1
            if self.dry_run:
                self.balance_idr -= MAX_POSITION_SIZE * 0.9

            self._log_trade(
                opp['pair'], 'BUY', opp['price'], 0,
                MAX_POSITION_SIZE * 0.9, coin_amt, 0, 0, 'Entry'
            )

            logger.info(f"✅ Trade active: {opp['pair']} (Order: {order_id})")

    async def monitor_positions(self, tickers):
        """Monitor active positions for exits."""
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
                trail_price = highest * (1 - TRAILING_PERCENT/100)

                if current_price <= trail_price and pnl_pct > 0:
                    await self.close_position(pair, trade, current_price, f"Trailing Stop (+{pnl_pct:.1f}%)")
                    continue

            # Hard stop loss
            if pnl_pct <= STOP_LOSS:
                await self.close_position(pair, trade, current_price, "Stop Loss (-2%)")
                self.last_loss_time = datetime.now()
                self.daily_pnl += pnl_idr

            # Take profit
            if pnl_pct >= TAKE_PROFIT:
                await self.close_position(pair, trade, current_price, f"Take Profit (+{pnl_pct:.1f}%)")

    async def close_position(self, pair, trade, price, reason):
        """Close a position."""
        coin_amount = trade['coin_amount']
        pair_id = trade['pair_id']

        sell_order_id = self.sell(pair_id, price, coin_amount)

        if sell_order_id:
            entry_price = trade['entry_price']
            pnl_pct = ((price - entry_price) / entry_price) * 100
            pnl_idr = (price - entry_price) * coin_amount

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
📈 P&L: `{pnl_pct:+.1f}%` ({pnl_emoji} `{pnl_idr:,.0f}` IDR)
⏰ Duration: {datetime.now() - trade['timestamp']}

💰 **Daily P&L:** `{self.daily_pnl:,.0f}` IDR
            """

            await self.notify(msg)

            self._log_trade(
                pair, 'SELL', entry_price, price, 0,
                coin_amount, pnl_idr, pnl_pct, reason
            )

            logger.info(f"✅ Closed {pair}: {pnl_idr:,.0f} IDR ({reason})")

    async def run(self):
        """Main loop."""
        dry_indicator = "🧪 [DRY RUN] " if self.dry_run else ""
        logger.info(f"{dry_indicator}Ultra Hunter started")
        logger.info(f"   Max position: {MAX_POSITION_SIZE:,.0f} IDR")
        logger.info(f"   Max daily loss: {MAX_DAILY_LOSS:,.0f} IDR")
        logger.info(f"   Daily trade limit: {MAX_TRADES_PER_DAY}")

        self.get_balance()
        await asyncio.sleep(5)

        while True:
            try:
                # Reset daily counters
                if datetime.now().date() != datetime.now().date():
                    self.daily_trades = 0
                    self.daily_pnl = 0

                self.get_balance()

                # Get tickers
                r = self.session.get(f"{self.indodax_url}/api/tickers", timeout=10)
                tickers = r.json().get('tickers', {}) if r.status_code == 200 else {}

                if tickers:
                    await self.scan_and_trade(tickers)
                    await self.monitor_positions(tickers)

                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(30)


async def main():
    """Standalone entry point."""
    import sys

    # Load from environment or args
    dry_run = os.getenv('ULTRA_DRY_RUN', 'true').lower() == 'true'
    if '--real' in sys.argv:
        dry_run = False

    # Load credentials from environment
    api_key = os.getenv('INDODAX_API_KEY', '')
    api_secret = os.getenv('INDODAX_SECRET_KEY', '')
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')

    if not all([api_key, api_secret, telegram_token, telegram_chat_id]):
        print("❌ Missing credentials. Set environment variables:")
        print("   INDODAX_API_KEY, INDODAX_SECRET_KEY")
        print("   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        print("   ULTRA_DRY_RUN=true (default, safe)")
        sys.exit(1)

    # Safety check for real trading
    if not dry_run:
        print("⚠️  WARNING: REAL TRADING MODE!")
        print("   Real orders will be placed on Indodax!")
        confirm = input("   Type 'REAL' to confirm: ")
        if confirm != 'REAL':
            print("   Cancelled.")
            sys.exit(0)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/ultra_hunter.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    # Start hunter
    hunter = UltraConservativeHunter(
        api_key=api_key,
        api_secret=api_secret,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        dry_run=dry_run
    )

    await hunter.run()


if __name__ == '__main__':
    asyncio.run(main())
