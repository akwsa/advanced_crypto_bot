#!/usr/bin/env python3
"""
Scalper Module - Manual Trading with TP/SL
Extracted from scalper_hybrid.py for integration into main bot
"""

import time
import json
import os
import requests
import asyncio
import threading
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
import logging
import pandas as pd
import numpy as np

# Local modules
from cache.price_cache import price_cache
from cache.redis_state_manager import state_manager
from core.utils import Utils

logger = logging.getLogger('scalper_module')

# ============================================================
# CONFIG
# ============================================================
def load_scalper_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    token = admin = indodax_key = indodax_secret = ''
    dry_run = 'true'
    cancel_enabled = 'true'
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('SCALPER_BOT_TOKEN'): token = line.split('=', 1)[1].strip()
                if line.startswith('ADMIN_IDS'): admin = line.split('=', 1)[1].strip()
                if line.startswith('INDODAX_API_KEY'): indodax_key = line.split('=', 1)[1].strip()
                if line.startswith('INDODAX_SECRET_KEY'): indodax_secret = line.split('=', 1)[1].strip()
                if line.startswith('AUTO_TRADE_DRY_RUN'): dry_run = line.split('=', 1)[1].strip().lower()
                if line.startswith('CANCEL_TRADE_ENABLED'): cancel_enabled = line.split('=', 1)[1].strip().lower()
    return token, admin, indodax_key, indodax_secret, dry_run == 'true', cancel_enabled == 'true'

SCALPER_TOKEN, ADMIN_IDS_RAW, INDODAX_KEY, INDODAX_SECRET, DRY_RUN_ENABLED, CANCEL_ENABLED = load_scalper_env()
try:
    ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(',') if x.strip()]
except Exception as e:
    logger.error(f"Failed to parse ADMIN_IDS: {e}")
    ADMIN_IDS = []

class ScalperConfig:
    PAIRS_DEFAULT = ['pippinidr', 'bridr', 'stoidr', 'drxidr']
    PAIRS_FILE = 'scalper_pairs.txt'
    BASE_URL = "https://indodax.com/api/ticker/"
    
    # FIX: Load from .env directly to avoid import issues
    INITIAL_BALANCE = float(os.getenv('INITIAL_BALANCE', 50000000))  # Default 50 juta dari .env
    TRADING_FEE_PCT = 0.003
    DEFAULT_TRADE_PCT = 0.10
    PROFIT_ALERT_THRESHOLD = 3.0
    DROP_ALERT_THRESHOLDS = [3, 5, 10, 15, 20, 25, 30]  # Tiered drop alerts (loss)
    PROFIT_ALERT_THRESHOLDS = [3, 5, 8, 10, 15, 20, 25, 30]  # Tiered profit alerts (sell suggestions)

    @staticmethod
    def load_pairs():
        """Load pairs from all users' watchlist in database (priority), .env, and file."""
        pairs = set()
        
        # Load from database - all users' watchlist - PRIORITY
        try:
            from core.database import Database
            db = Database()
            with db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT DISTINCT pair FROM watchlist WHERE is_active = 1"
                )
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        pair = row['pair'].lower().strip()
                        if pair:
                            pairs.add(pair)
                    logger.info(f"📋 Loaded {len(pairs)} pairs from ALL users' watchlist in DB")
        except Exception as e:
            logger.debug(f"Failed to load from database: {e}")
        
        # Load from .env WATCH_PAIRS - fallback if DB empty
        if not pairs:
            watch_pairs_env = os.getenv('WATCH_PAIRS', '')
            if watch_pairs_env:
                for p in watch_pairs_env.split(','):
                    p = p.strip()
                    if p:
                        pairs.add(p.lower())
                logger.info(f"📋 Loaded {len(pairs)} pairs from .env WATCH_PAIRS")
        
        # Load from file (scalper custom pairs) - if still not in pairs
        try:
            if os.path.exists(ScalperConfig.PAIRS_FILE):
                with open(ScalperConfig.PAIRS_FILE, 'r') as f:
                    for line in f:
                        line = line.strip().lower()
                        if line and line not in pairs:
                            pairs.add(line)
        except Exception as e:
            logger.debug(f"Failed to load pairs file: {e}")
        
        # If still empty, use default pairs
        if not pairs:
            pairs = set(ScalperConfig.PAIRS_DEFAULT)
            logger.warning(f"⚠️ Using default pairs: {pairs}")
        
        return sorted(list(pairs))

    @staticmethod
    def save_pairs(pairs):
        with open(ScalperConfig.PAIRS_FILE, 'w') as f:
            f.write('\n'.join(p.lower() for p in pairs))

class ScalperModule:
    """Scalper trading module - integrates with main bot"""

    def __init__(self, app, admin_ids=None, is_standalone=False, use_main_bot_config=False, main_bot_config=None, main_bot_token=None, main_bot=None):
        self.app = app
        self.admin_ids = admin_ids or ADMIN_IDS

        # NEW: Use Redis state manager for active_positions
        self.state_manager = state_manager
        self._positions_file = 'scalper_positions.json'
        self.balance = ScalperConfig.INITIAL_BALANCE
        self.positions_file = 'scalper_positions.json'
        self.alerted_positions = set()
        self.notified_drops = {}  # {pair: set(thresholds)} to avoid duplicate drop alerts
        self.last_alert_time = None
        self.pairs = ScalperConfig.load_pairs()
        self.indodax_key = INDODAX_KEY
        self.indodax_secret = INDODAX_SECRET
        self.cancel_enabled = CANCEL_ENABLED
        self.is_standalone = is_standalone  # True if running as standalone bot
        self.main_bot = main_bot  # Reference to main bot for signal generation

        # Use main bot's config if integrating with main bot
        if use_main_bot_config and main_bot_config:
            self.dry_run = main_bot_config.AUTO_TRADE_DRY_RUN
            logger.info(f"🔗 Using main bot config: DRY_RUN={self.dry_run}")
            
            # FIX: Load balance from main bot's database
            try:
                from core.database import Database
                main_db = Database()
                # Get first user's balance (usually admin)
                with main_db.get_connection() as conn:
                    cursor = conn.execute('SELECT user_id, balance FROM users ORDER BY user_id ASC LIMIT 1')
                    first_user = cursor.fetchone()
                    if first_user:
                        self.balance = first_user['balance']
                        logger.info(f"💰 Scalper balance synced from main DB: {self.balance:,.0f} IDR")
                    else:
                        self.balance = ScalperConfig.INITIAL_BALANCE
                        logger.info(f"💰 Scalper balance using initial: {self.balance:,.0f} IDR")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load balance from main DB, using initial: {e}")
                self.balance = ScalperConfig.INITIAL_BALANCE
        else:
            self.dry_run = DRY_RUN_ENABLED
            logger.info(f"🔗 Using scalper's own config: DRY_RUN={self.dry_run}")
            self.balance = ScalperConfig.INITIAL_BALANCE

        self.is_real_trading = not self.dry_run and bool(self.indodax_key and self.indodax_secret)

        # Use main bot's token for sending messages via HTTP requests
        # This avoids asyncio event loop conflicts
        self.main_bot_token = main_bot_token
        self.use_main_bot = use_main_bot_config and main_bot_token

        if self.use_main_bot:
            logger.info("🔗 Using main bot's token for Telegram messages (single bot mode)")
        else:
            logger.warning("⚠️ Using separate SCALPER_BOT_TOKEN (legacy mode)")

        # Load Indodax API if real trading
        self.indodax = None
        if self.is_real_trading:
            try:
                from api.indodax_api import IndodaxAPI
                self.indodax = IndodaxAPI(self.indodax_key, self.indodax_secret)
            except Exception as e:
                logger.error(f"Failed to load Indodax API: {e}")

        # Load positions from Redis (with file fallback)
        self._load_positions()
        
        self._init_csv()
        self._register_handlers()
        self._start_monitor()

        mode_str = "🔴 REAL TRADING" if self.is_real_trading else "🟡 DRY RUN MODE"
        active_positions = self.state_manager.get_all_positions()
        logger.info(f"ScalperModule initialized: {mode_str} | {len(active_positions)} positions | Balance: {self.balance:,.0f}")

        # Log position summary at startup (once only, to console/log NOT Telegram)
        if active_positions:
            logger.info("📦 **Active Positions:**")
            for pair, pos in active_positions.items():
                entry = pos.get('entry', 0)
                capital = pos.get('capital', 0)
                logger.info(f"  • {pair.upper()}: Entry={entry:,.0f} | Capital={capital:,.0f}")
        else:
            logger.info("📦 No active positions")

        logger.info("💡 Use /s_menu or /s_info in Telegram to view positions and trade")

    @property
    def active_positions(self):
        """Property wrapper - get active positions from Redis"""
        return self.state_manager.get_all_positions()
    
    @active_positions.setter
    def active_positions(self, value):
        """Property wrapper - set active positions to Redis"""
        if isinstance(value, dict):
            # Clear old positions
            self.state_manager.clear_positions()
            # Set new positions
            for pair, pos in value.items():
                self.state_manager.set_position(pair, pos)

    # =====================================================================
    # Position Persistence (support manual trades from /trade command)
    # =====================================================================
    def add_manual_position(self, pair: str, entry_price: float, amount: float, capital: float, trade_id: int):
        """Add a position from manual trade (/trade command)"""
        pair_lower = pair.lower()
        self.active_positions[pair_lower] = {
            'entry': entry_price,
            'amount': amount,
            'capital': capital,
            'trade_id': trade_id,
            'source': 'manual',
            'timestamp': datetime.now().isoformat()
        }
        self._save_positions()
        logger.info(f"✅ Manual position added: {pair_lower} @ {entry_price} ({capital:,.0f} IDR)")

    def remove_manual_position(self, pair: str):
        """Remove a position (after sell or cancel)"""
        pair_lower = pair.lower()
        if pair_lower in self.active_positions:
            del self.active_positions[pair_lower]
            self._save_positions()
            logger.info(f"🗑️ Position removed: {pair_lower}")

    def _init_csv(self):
        history_file = 'scalper_manual_history.csv'
        if not os.path.exists(history_file):
            with open(history_file, 'w', newline='', encoding='utf-8') as f:
                import csv
                csv.writer(f).writerow(['Waktu', 'Pair', 'Type', 'Price', 'P/L %', 'Profit IDR', 'Saldo'])

    def _save_positions(self):
        try:
            # Convert sets to lists for JSON serialization
            alerted_list = list(self.alerted_positions)
            notified_drops_serializable = {k: list(v) for k, v in self.notified_drops.items()}

            data = {
                'balance': self.balance,
                'positions': self.active_positions,
                'alerted_positions': alerted_list,
                'notified_drops': notified_drops_serializable,
                'last_alert_time': self.last_alert_time,
                'saved_at': datetime.now().isoformat()
            }
            with open(self.positions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save positions: {e}")

    def _load_positions(self):
        try:
            if not os.path.exists(self.positions_file):
                return
            with open(self.positions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.balance = data.get('balance', ScalperConfig.INITIAL_BALANCE)
            self.active_positions = data.get('positions', {})
            self.alerted_positions = set(data.get('alerted_positions', []))
            self.last_alert_time = data.get('last_alert_time')

            # Load notified_drops (convert lists back to sets)
            raw_drops = data.get('notified_drops', {})
            self.notified_drops = {k: set(v) for k, v in raw_drops.items()}

            # SAFETY: In DRY RUN, never allow balance to be 0 or unrealistic
            if self.dry_run and self.balance < 100000:
                logger.warning(f"⚠️ Balance too low ({self.balance:,.0f}), resetting to default")
                self.balance = ScalperConfig.INITIAL_BALANCE
                self._save_positions()
        except Exception as e:
            logger.error(f"Failed to load positions: {e}")

    def _get_price_sync(self, pair, retries=2):
        """Get price — Redis cache first, fallback to API"""
        # Phase 2: Check Redis cache first (price_poller updates every 15s)
        try:
            from cache.redis_price_cache import price_cache as redis_cache
            cached = redis_cache.get_price_sync(pair)
            if cached is not None and cached > 0:
                # Check age — if < 60s old, use cached price
                pair_clean = pair.lower().replace('/', '')
                if not pair_clean.endswith('idr'):
                    pair_clean += 'idr'
                if pair_clean in redis_cache._local_cache:
                    _, ts = redis_cache._local_cache[pair_clean]
                    if (time.time() - ts) < 60:
                        return cached
        except Exception:
            pass  # Fallback to API if Redis check fails

        # Cache miss or expired — fetch from API
        last_error = None
        
        for attempt in range(retries):
            try:
                # Shorter timeout (3s instead of 5s) to fail faster
                res = requests.get(
                    f"{ScalperConfig.BASE_URL}{pair}",
                    timeout=3,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                res.raise_for_status()
                data = res.json()
                
                if 'ticker' not in data:
                    raise ValueError(f"Pair '{pair}' tidak ditemukan di Indodax")
                
                return float(data['ticker']['last'])
                
            except requests.exceptions.Timeout:
                last_error = f"Timeout (attempt {attempt + 1}/{retries})"
                if attempt < retries - 1:
                    time.sleep(0.5)  # Brief pause before retry
                continue
            except requests.exceptions.ConnectionError:
                last_error = "Connection error"
                if attempt < retries - 1:
                    time.sleep(0.5)
                continue
            except ValueError:
                raise  # Don't retry for invalid pair
            except Exception as e:
                last_error = str(e)
                if attempt < retries - 1:
                    time.sleep(0.5)
                continue
        
        # All retries exhausted
        logger.warning(f"Price fetch failed for {pair} after {retries} attempts: {last_error}")
        raise Exception(f"Failed to get price for {pair}: {last_error}")

    def validate_pair(self, pair):
        try:
            self._get_price_sync(pair)
            return True
        except ValueError as e:
            return "tidak ditemukan" not in str(e)
        except Exception as e:
            logger.error(f"validate_pair error for {pair}: {e}")
            return True

    def add_scalper_pair(self, pair):
        """Add a pair to scalper list if not already present"""
        pair = pair.lower().strip()
        if not pair.endswith('idr'):
            pair += 'idr'
        
        if pair in self.pairs:
            logger.info(f"📊 Pair {pair.upper()} already in scalper list")
            return False
        
        # Validate pair exists on Indodax before adding
        if not self.validate_pair(pair):
            logger.warning(f"⚠️ Pair {pair.upper()} not found on Indodax, skipping scalper add")
            return False
        
        self.pairs.append(pair)
        ScalperConfig.save_pairs(self.pairs)
        logger.info(f"✅ Auto-added {pair.upper()} to scalper list")
        return True

    def add_scalper_pairs_batch(self, pairs_list):
        """Add multiple pairs to scalper list from /watch command"""
        if not pairs_list:
            return
        
        added_count = 0
        skipped_count = 0
        invalid_count = 0
        
        for pair in pairs_list:
            pair_lower = pair.lower().strip()
            if not pair_lower.endswith('idr'):
                pair_lower += 'idr'
            
            # Check if already in list
            if pair_lower in self.pairs:
                skipped_count += 1
                continue
            
            # Try to add
            if self.add_scalper_pair(pair_lower):
                added_count += 1
            else:
                invalid_count += 1
        
        if added_count > 0:
            logger.info(f"📈 Scalper auto-add: {added_count} pair(s) added, {skipped_count} skipped, {invalid_count} invalid")
        
        return {
            'added': added_count,
            'skipped': skipped_count,
            'invalid': invalid_count
        }

    def _send_telegram_message(self, chat_id: int, text: str, reply_markup=None, max_retries=3):
        """Send message via main bot's token using HTTP requests (thread-safe) with retries"""
        token = self.main_bot_token or SCALPER_TOKEN
        if not token:
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(url, json=payload, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                if response.status_code == 200:
                    return  # Success
                elif response.status_code == 429:
                    # Rate limited - wait longer
                    wait_time = 5
                    logger.warning(f"⏳ Telegram rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Telegram API returned {response.status_code}: {response.text}")
                    return  # Don't retry on other errors
            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    wait_time = attempt * 3  # 3s, 6s, 9s
                    logger.warning(f"⏳ Telegram timeout (attempt {attempt}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Failed to send Telegram message after {max_retries} attempts: timeout")
            except Exception as e:
                logger.error(f"❌ Failed to send Telegram message: {e}")
                return  # Don't retry on other errors

    # ============================================================
    # HANDLER REGISTRATION
    # ============================================================
    def _start_monitor(self):
        """Start background monitor thread for TP/SL + profit/drop alerts (works in BOTH real & dry run)"""
        self._last_balance_sync = 0

        def monitor_loop():
            import time as time_mod
            logger.info("🔄 Scalper Monitor Thread Started (TP/SL + profit/drop alerts)")
            while True:
                try:
                    # Sync balance from Indodax every 5 minutes (real trading only)
                    if self.is_real_trading and self.indodax:
                        current_time = time_mod.time()
                        if (current_time - self._last_balance_sync) >= 300:
                            self._sync_balance_from_indodax()
                            self._last_balance_sync = current_time

                    # Check TP/SL + profit/drop alerts for ALL active positions
                    # Works in BOTH real trading AND dry run mode
                    if self.active_positions:
                        live_prices = {}
                        for p in list(self.active_positions.keys()):
                            try:
                                live_prices[p] = self._get_price_sync(p)
                            except Exception:
                                live_prices[p] = None

                        self._check_tp_sl_real(live_prices)

                    time_mod.sleep(5)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                    time_mod.sleep(5)

        threading.Thread(target=monitor_loop, daemon=True).start()

    def _sync_balance_from_indodax(self):
        """Sync local balance with Indodax real balance"""
        try:
            info = self.indodax.get_balance()
            if info and 'balance' in info:
                idr_balance_str = info['balance'].get('idr', '0')
                # Handle if idr is a dict with 'available' and 'on_order'
                if isinstance(idr_balance_str, dict):
                    idr_balance = float(idr_balance_str.get('available', 0))
                else:
                    idr_balance = float(idr_balance_str)

                if idr_balance > 0:
                    old_balance = self.balance
                    self.balance = idr_balance
                    self._save_positions()
                    if abs(old_balance - idr_balance) > 1000:
                        logger.info(f"💰 Balance synced: {old_balance:,.0f} → {idr_balance:,.0f} IDR")
                        print(f"💰 Balance synced: {old_balance:,.0f} → {idr_balance:,.0f} IDR", flush=True)
        except Exception as e:
            logger.debug(f"Balance sync skipped (DRY RUN or API error): {e}")

    def _verify_position_exists(self, pair):
        """Verify that a position actually exists in Indodax account"""
        if not self.is_real_trading or not self.indodax:
            # DRY RUN mode: Check if position is too old (stale)
            pos = self.active_positions.get(pair, {})
            position_age_hours = (time.time() - pos.get('time', time.time())) / 3600
            
            # If position is older than 7 days and has profit alerts sent, it's likely stale
            if position_age_hours > 168:  # 7 days
                profit_alerted = any(k.startswith('profit_') for k in self.notified_drops.get(pair, set()))
                if profit_alerted:
                    logger.warning(f"⚠️ Stale DRY RUN position: {pair.upper()} ({position_age_hours:.1f}h old) - will skip alerts")
                    return False
            
            return True  # Skip further verification in DRY RUN

        try:
            # Get balance from Indodax
            balance_info = self.indodax.get_balance()
            if not balance_info or 'funds' not in balance_info:
                logger.warning(f"⚠️ Could not fetch balance to verify position {pair.upper()}")
                return True  # Assume valid if we can't verify

            funds = balance_info['funds']

            # Extract coin name from pair (e.g., 'arcidr' -> 'arc')
            coin = pair.lower().replace('idr', '').strip()

            # Check if coin balance exists and is > 0
            coin_balance_str = funds.get(coin, '0')
            if isinstance(coin_balance_str, dict):
                # Handle if balance is dict with 'available' and 'on_order'
                available = float(coin_balance_str.get('available', 0))
                on_order = float(coin_balance_str.get('on_order', 0))
                coin_balance = available + on_order
            else:
                coin_balance = float(coin_balance_str)

            if coin_balance <= 0:
                logger.info(f"❌ Position verification failed: {pair.upper()} - No {coin.upper()} balance (0 coins)")
                return False

            logger.debug(f"✅ Position verified: {pair.upper()} - Balance: {coin_balance:.6f}")
            return True

        except Exception as e:
            logger.error(f"⚠️ Error verifying position {pair.upper()}: {e}")
            return True  # Assume valid on error to avoid false deletions

    def _check_tp_sl_real(self, live_prices):
        """Auto-execute TP/SL on Indodax + check profit/drop alerts for ALL positions"""
        snapshot = dict(self.active_positions)
        
        # First pass: Verify all positions exist in Indodax
        verified_positions = {}
        for pair, pos in snapshot.items():
            if self._verify_position_exists(pair):
                verified_positions[pair] = pos
            else:
                logger.warning(f"🗑️ Removing stale position: {pair.upper()} (not found in Indodax)")
                # Remove stale position from active_positions
                if pair in self.active_positions:
                    del self.active_positions[pair]
                    self._save_positions()
        
        # Second pass: Check alerts only for verified positions
        for pair, pos in verified_positions.items():
            has_tp = 'tp' in pos
            has_sl = 'sl' in pos

            price = live_prices.get(pair)
            if price is None:
                try:
                    price = self._get_price_sync(pair)
                except Exception as e:
                    logger.error(f"Failed to get price for {pair}: {e}")
                    continue

            # Check profit alerts for VERIFIED positions only
            self._check_profit_alerts(pair, pos, price)

            # Check drop alerts for VERIFIED positions only
            self._check_drop_alerts(pair, pos, price)

            # Only auto-execute TP/SL if they are actually set
            if not has_tp and not has_sl:
                continue

            tp = pos.get('tp')
            sl = pos.get('sl')

            # Check SL first (higher priority)
            if sl and price <= sl:
                logger.warning(f"🛑 STOP LOSS HIT: {pair.upper()} @ {price:,.0f}")
                self._execute_real_sell(pair, price, "STOP LOSS")
                continue

            # Check TP
            if tp and price >= tp:
                logger.info(f"🎯 TAKE PROFIT HIT: {pair.upper()} @ {price:,.0f}")
                self._execute_real_sell(pair, price, "TAKE PROFIT")

    def _check_profit_alerts(self, pair, pos, current_price):
        """Check if position is in profit and send tiered SELL suggestions"""
        entry_price = pos.get('entry', 0)
        if entry_price <= 0:
            return

        # Calculate P/L percentage (including fees)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # Only alert if position is in profit
        if pnl_pct <= 0:
            return

        # Initialize profit alerts tracking for this pair if needed
        if pair not in self.notified_drops:
            self.notified_drops[pair] = set()

        # Check each profit threshold
        for threshold in ScalperConfig.PROFIT_ALERT_THRESHOLDS:
            profit_key = f"profit_{threshold}"  # Use unique key for profit vs drop
            if pnl_pct >= threshold and profit_key not in self.notified_drops[pair]:
                # Mark as notified so we don't spam
                self.notified_drops[pair].add(profit_key)
                self._save_positions()

                # Calculate actual profit/loss
                current_value = current_price * pos.get('amount', 0)
                entry_value = entry_price * pos.get('amount', 0)
                profit_idr = current_value - entry_value

                # Severity-based emoji
                if threshold >= 20:
                    severity_emoji = "🎆"
                    severity_text = "MEGA PROFIT"
                elif threshold >= 15:
                    severity_emoji = "🚀"
                    severity_text = "BIG PROFIT"
                elif threshold >= 10:
                    severity_emoji = "🔥"
                    severity_text = "STRONG PROFIT"
                elif threshold >= 8:
                    severity_emoji = "💰"
                    severity_text = "GOOD PROFIT"
                elif threshold >= 5:
                    severity_emoji = "💵"
                    severity_text = "PROFIT"
                elif threshold >= 3:
                    severity_emoji = "📈"
                    severity_text = "MINOR PROFIT"
                else:
                    severity_emoji = "💹"
                    severity_text = "BREAK EVEN"

                tp_str = f"🎯 TP: `{pos.get('tp', 0):,.0f}`" if 'tp' in pos else "🎯 TP: _not set_ (manual sell recommended)"
                sl_str = f"🛑 SL: `{pos.get('sl', 0):,.0f}`" if 'sl' in pos else "🛑 SL: _not set_"

                action_msg = "💡 **Consider selling now to lock profit!**" if threshold >= 5 else "📊 Monitor for higher targets"

                msg = (
                    f"{severity_emoji} **SCALPER PROFIT ALERT {severity_text} +{threshold:.0f}%**\n\n"
                    f"🟢 Pair: {pair.upper()}\n"
                    f"💰 Entry: `{entry_price:,.0f}` IDR\n"
                    f"📈 Current: `{current_price:,.0f}` IDR\n"
                    f"📈 Profit: `+{pnl_pct:.1f}%` (+`{profit_idr:,.0f}` IDR)\n\n"
                    f"⚡ **Action:**\n"
                    f"• {action_msg}\n"
                    f"• {sl_str}\n"
                    f"• {tp_str}\n\n"
                    f"💬 Use `/s_sell {pair}` to execute sell"
                )

                # Send to all admins
                for admin_id in self.admin_ids:
                    self._send_telegram_message(admin_id, msg)

                logger.info(
                    f"📈 Scalper profit alert +{threshold}% for {pair.upper()}: "
                    f"Entry={entry_price:,.0f}, Current={current_price:,.0f}, Profit=+{pnl_pct:.1f}%"
                )

    def _check_drop_alerts(self, pair, pos, current_price):
        """Check if price has dropped by tiered percentages and send warnings"""
        entry_price = pos.get('entry', 0)
        if entry_price <= 0:
            return

        drop_pct = ((entry_price - current_price) / entry_price) * 100

        # Only alert if price is below entry (actual loss)
        if drop_pct <= 0:
            return

        # Initialize notified_drops for this pair if needed
        if pair not in self.notified_drops:
            self.notified_drops[pair] = set()

        # Check each threshold
        for threshold in ScalperConfig.DROP_ALERT_THRESHOLDS:
            if drop_pct >= threshold and threshold not in self.notified_drops[pair]:
                # Mark as notified so we don't spam
                self.notified_drops[pair].add(threshold)
                self._save_positions()  # Persist so alerts survive restart

                # Build alert message
                drop_amount = entry_price - current_price

                # Severity-based emoji
                if threshold >= 20:
                    severity_emoji = "🚨"
                    severity_text = "CRITICAL"
                elif threshold >= 15:
                    severity_emoji = "⚠️"
                    severity_text = "WARNING"
                elif threshold >= 10:
                    severity_emoji = "📉"
                    severity_text = "ALERT"
                elif threshold >= 5:
                    severity_emoji = "📊"
                    severity_text = "NOTICE"
                else:
                    severity_emoji = "🔔"
                    severity_text = "INFO"

                tp_str = f"TP: `{pos.get('tp', 0):,.0f}`" if 'tp' in pos else "TP: _not set_"
                sl_str = f"SL: `{pos.get('sl', 0):,.0f}`" if 'sl' in pos else "SL: _not set_"

                msg = (
                    f"{severity_emoji} **SCALPER PRICE DROP {severity_text} - {threshold:.0f}%**\n\n"
                    f"🔴 Pair: {pair.upper()}\n"
                    f"💰 Entry: `{entry_price:,.0f}` IDR\n"
                    f"📉 Current: `{current_price:,.0f}` IDR\n"
                    f"📉 Drop: `-{drop_pct:.1f}%` (-`{drop_amount:,.0f}` IDR)\n\n"
                    f"⚡ _Consider your strategy:_\n"
                    f"• {'🚨 Major drop! Review position carefully' if threshold >= 20 else '• Monitor closely'}\n"
                    f"• {sl_str}\n"
                    f"• {tp_str}"
                )

                # Send to all admins
                for admin_id in self.admin_ids:
                    self._send_telegram_message(admin_id, msg)

                logger.warning(
                    f"📉 Scalper drop alert {threshold}% for {pair.upper()}: "
                    f"Entry={entry_price:,.0f}, Current={current_price:,.0f}, Drop=-{drop_pct:.1f}%"
                )

    def _execute_real_sell(self, pair, price, reason):
        """Execute real sell on Indodax"""
        if pair not in self.active_positions:
            return

        pos = self.active_positions[pair]
        amount = pos['amount']

        try:
            # Call Indodax API to sell
            result = self.indodax.create_order(pair, 'sell', price, amount)

            if result and result.get('success'):
                # Calculate P/L
                revenue = (price * amount) * (1 - ScalperConfig.TRADING_FEE_PCT)
                profit_idr = revenue - pos['capital']
                pnl_pct = (profit_idr / pos['capital']) * 100

                del self.active_positions[pair]
                self._save_positions()

                # Notify admins via REST API
                emoji = "🎯" if reason == "TAKE PROFIT" else "🛑"
                msg = (
                    f"{emoji} **{reason}**\n\n"
                    f"🔴 **{pair.upper()}**\n"
                    f"💰 Sell Price: {price:,.0f}\n"
                    f"📦 Amount: {amount:,.2f}\n"
                    f"📈 P/L: **{pnl_pct:+.2f}%**\n"
                    f"💸 Profit: {profit_idr:+,.0f} IDR"
                )
                for admin_id in self.admin_ids:
                    self._send_telegram_message(admin_id, msg)

                print(f"{emoji} {reason}: {pair.upper()} @ {price:,.0f} | P/L: {pnl_pct:+.2f}%", flush=True)
            else:
                logger.error(f"Failed to sell {pair}: {result}")
        except Exception as e:
            logger.error(f"Real sell error for {pair}: {e}")

    def _send_position_summary_to_telegram(self):
        """Send position summary to all admins via Telegram REST API (thread-safe)"""
        if not self.active_positions:
            return

        try:
            snapshot = dict(self.active_positions)
            msg = "📊 **Update Posisi**\n\n"
            msg += f"💰 Saldo: {self.balance:,.0f} IDR\n\n"

            total_pnl = 0
            for pair, pos in snapshot.items():
                try:
                    price = self._get_price_sync(pair)
                    pnl = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                    profit = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
                    total_pnl += profit

                    ind = "🟢" if pnl >= 0 else "🔴"
                    alert = "🚨 PROFIT!" if pnl >= ScalperConfig.PROFIT_ALERT_THRESHOLD else ""
                    tp = f" | TP: {Utils.format_price(pos.get('tp', 0))}" if 'tp' in pos else ""
                    sl = f" | SL: {Utils.format_price(pos.get('sl', 0))}" if 'sl' in pos else ""

                    msg += f"{ind} *{pair.upper()}* {alert}\n"
                    msg += f"   Entry: {Utils.format_price(pos['entry'])} → Current: {Utils.format_price(price)}{tp}{sl}\n"
                    msg += f"   P/L: *{pnl:+.2f}%* ({profit:+,.0f} IDR)\n\n"
                except Exception as e:
                    logger.error(f"Error building summary for {pair}: {e}")
                    msg += f"⚠️ *{pair.upper()}*: Error\n\n"

            msg += "━━━━━━━━━━━━━━\n"
            msg += f"📈 *Total P/L: {total_pnl:+,.0f} IDR*"

            for admin_id in self.admin_ids:
                self._send_telegram_message(admin_id, msg)

        except Exception as e:
            logger.error(f"Telegram summary error: {e}")

    def _register_handlers(self):
        # Primary scalper commands
        self.app.add_handler(CommandHandler("s_buy", self.cmd_buy))
        self.app.add_handler(CommandHandler("s_sell", self.cmd_sell))
        self.app.add_handler(CommandHandler("s_sltp", self.cmd_sltp))
        self.app.add_handler(CommandHandler("s_cancel", self.cmd_cancel))
        self.app.add_handler(CommandHandler("s_info", self.cmd_info))
        self.app.add_handler(CommandHandler("s_pair", self.cmd_pair))
        self.app.add_handler(CommandHandler("s_posisi", self.cmd_posisi))
        self.app.add_handler(CommandHandler("s_reset", self.cmd_reset))
        self.app.add_handler(CommandHandler("s_analisa", self.cmd_analisa))
        self.app.add_handler(CommandHandler("s_menu", self.cmd_menu))
        self.app.add_handler(CommandHandler("s_sync", self.cmd_sync))
        self.app.add_handler(CommandHandler("s_portfolio", self.cmd_portfolio))
        self.app.add_handler(CommandHandler("s_riwayat", self.cmd_riwayat))
        
        # Aliases for convenience (no 's_' prefix needed)
        # Note: Skip 'menu' as it conflicts with main bot's /menu command
        self.app.add_handler(CommandHandler("buy", self.cmd_buy))
        self.app.add_handler(CommandHandler("sell", self.cmd_sell))
        self.app.add_handler(CommandHandler("sltp", self.cmd_sltp))
        self.app.add_handler(CommandHandler("posisi", self.cmd_posisi))
        self.app.add_handler(CommandHandler("analisa", self.cmd_analisa))

        # Callback handlers - register with patterns for priority
        # Note: Some callbacks are handled by menu_callback instead of separate handlers
        # Pattern handlers are for callbacks that need dedicated methods
        self.app.add_handler(CallbackQueryHandler(self.refresh_posisi_callback, pattern="^s_refresh_posisi$"))
        self.app.add_handler(CallbackQueryHandler(self.refresh_riwayat_callback, pattern="^s_refresh_riwayat$"))
        self.app.add_handler(CallbackQueryHandler(self.info_posisi_callback, pattern="^s_info:"))
        self.app.add_handler(CallbackQueryHandler(self.ignore_alert_callback, pattern="^s_ignore_alert:"))
        
        # General callback handler (catches all unhandled callbacks)
        self.app.add_handler(CallbackQueryHandler(self.menu_callback))
        
        # Also register some callbacks as text commands for convenience
        # This allows users to type commands directly in chat
        self.app.add_handler(CommandHandler("s_close_all", self.cmd_close_all))
        self.app.add_handler(CommandHandler("s_refresh", self.cmd_refresh_portfolio))

        # AUTO-SYNC saat startup (hanya di real trading mode)
        if self.is_real_trading:
            logger.info("🔄 Auto-syncing positions with Indodax at startup...")
            # Run sync in background thread to not block startup
            threading.Thread(target=self._auto_sync_on_startup, daemon=True).start()

    def _auto_sync_on_startup(self):
        """Auto sync posisi saat bot dimulai (real trading only)"""
        try:
            time.sleep(3)  # Wait untuk bot fully initialized
            
            if not self.indodax:
                logger.warning("⚠️ Indodax API not initialized, skipping auto-sync")
                return
            
            open_orders = self.indodax.get_open_orders()
            
            if not open_orders:
                logger.info("✅ No open orders at Indodax - clean start")
                return
            
            # Parse dan sync posisi
            synced_count = 0
            for order in open_orders:
                pair = order.get('pair', '').lower()
                if not pair.endswith('idr'):
                    pair += 'idr'
                
                order_type = order.get('type', 'buy').lower()
                price = float(order.get('price', 0))
                amount_remaining = float(order.get('amount_remain', 0))
                order_id = order.get('order', 0)
                
                if order_type == 'buy' and amount_remaining > 0:
                    if pair not in self.active_positions:
                        self.active_positions[pair] = {
                            'entry': price,
                            'amount': amount_remaining,
                            'capital': price * amount_remaining,
                            'time': int(time.time()),
                            'order_id': order_id,
                            'synced_from': 'indodax_startup'
                        }
                        synced_count += 1
                        logger.info(f"✅ Auto-synced {pair.upper()}: {amount_remaining} @ {price:,.0f}")
            
            if synced_count > 0:
                self._save_positions()
                logger.info(f"✅ Auto-synced {synced_count} positions from Indodax")
                
                # Notify admin
                msg = f"🔄 **AUTO-SYNC SELESAI**\n\nDitemukan {synced_count} posisi dari Indodax:\n"
                for pair, pos in self.active_positions.items():
                    if pos.get('synced_from', '').startswith('indodax'):
                        msg += f"\n• **{pair.upper()}**: {pos['amount']:.2f} @ {pos['entry']:,.0f}"
                msg += f"\n\n💡 Gunakan `/s_posisi` untuk detail"
                
                # Send to first admin
                if self.admin_ids:
                    self._send_telegram_message(self.admin_ids[0], msg)
            
        except Exception as e:
            logger.error(f"Auto-sync error: {e}")

    # ============================================================
    # CHECK ADMIN
    # ============================================================
    def _is_admin(self, user_id):
        return user_id in self.admin_ids

    # ============================================================
    # COMMANDS
    # ============================================================
    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return

        # FIX: Always use .env value directly (no fallback issues)
        # Get directly from .env, not from database (which might be empty)
        self.balance = float(os.getenv('INITIAL_BALANCE', 50000000))
        logger.debug(f"💰 Scalper balance from .env: {self.balance:,.0f} IDR")

        if not self.pairs:
            await update.effective_message.reply_text(
                "📋 **SCALPER MENU**\n\n"
                "⚠️ Belum ada pair aktif.\n\n"
                "Tambahkan pair:\n"
                "`/s_pair add <pair>`\n\n"
                "Contoh: `/s_pair add btcidr`",
                parse_mode='Markdown'
            )
            return

        # 🚀 Fetch live prices CONCURRENTLY (tidak sequential lagi!)
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Use price cache for fast concurrent fetch
        price_map = await price_cache.get_prices_batch(self.pairs)
        
        # 🔍 Check signals for each pair (to color buttons)
        signal_map = {}
        for pair in self.pairs:
            try:
                price = price_map.get(pair)
                if price and price > 0:
                    signal = self._get_signal_for_pair(pair)
                    if signal:
                        signal_map[pair] = signal.get('recommendation', 'HOLD')
                    else:
                        signal_map[pair] = 'HOLD'
            except:
                signal_map[pair] = 'HOLD'
        
        # Build price lines - plain text format
        price_lines = []
        for p in self.pairs:
            try:
                price = price_map.get(p)
                if price is None:
                    price_lines.append(f"{p.upper()}: Error")
                    continue
                    
                # Check if we have an active position
                has_position = p in self.active_positions
                pos_marker = " (posisi)" if has_position else ""
                price_lines.append(f"{p.upper()}: {price:,.0f}{pos_marker}")
            except Exception:
                price_lines.append(f"{p.upper()}: Error")

        # Build status message - plain text
        status_text = (
            f"🕐 {timestamp}\n"
            f"💰 Saldo: {self.balance:,.0f} IDR\n\n"
            f"📊 Daftar Pair:\n"
            + '\n'.join(f"• {line}" for line in price_lines)
        )

        # Add active positions summary
        if self.active_positions:
            status_text += f"\n\n📦 Posisi Aktif ({len(self.active_positions)}):"
            for pair, pos in self.active_positions.items():
                try:
                    entry = pos.get('entry', 0)
                    capital = pos.get('capital', 0)
                    # Use cached price
                    try:
                        current = price_map.get(pair)
                        if current is None:
                            status_text += f"\n⏳ {pair.upper()}: Entry {entry:,.0f}"
                            continue
                            
                        pnl = ((current * (1-ScalperConfig.TRADING_FEE_PCT) - entry * (1+ScalperConfig.TRADING_FEE_PCT)) / (entry * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                        emoji = "🟢" if pnl >= 0 else "🔴"
                        status_text += f"\n{emoji} {pair.upper()}: Entry {Utils.format_price(entry)} -> {Utils.format_price(current)} | P/L: {pnl:+.1f}%"
                    except Exception:
                        status_text += f"\n⏳ {pair.upper()}: Entry {Utils.format_price(entry)}"
                except Exception:
                    status_text += f"\n⚠️ {pair.upper()}: Error"
        
        status_text += "\n\n🎯 Klik tombol untuk trading:"

        # Build keyboard — use BOTH self.pairs AND active_positions
        # Color buttons based on signals (BUY = green)
        all_pairs = list(set(list(self.pairs) + list(self.active_positions.keys())))
        keyboard = []
        for p in all_pairs:
            pn = p.upper()
            has_position = p in self.active_positions
            signal = signal_map.get(p, 'HOLD')

            if has_position:
                # Check if position is profitable
                pos = self.active_positions[p]
                entry = pos.get('entry', 0)
                try:
                    current_price = price_map.get(p)
                    is_profit = False
                    if current_price and entry > 0:
                        pnl_pct = ((current_price * (1 - ScalperConfig.TRADING_FEE_PCT) - entry * (1 + ScalperConfig.TRADING_FEE_PCT)) / (entry * (1 + ScalperConfig.TRADING_FEE_PCT))) * 100
                        is_profit = pnl_pct > 0
                except Exception as e:
                    logger.error(f"Error checking profit for {p}: {e}")
                    is_profit = False

                if is_profit:
                    sell_label = f"💰 SELL {pn} (PROFIT)"
                else:
                    sell_label = f"⬆️ SELL {pn}"

                keyboard.append([
                    InlineKeyboardButton(f"⬇️ BUY {pn}", callback_data=f"s_buy:{p}"),
                    InlineKeyboardButton(sell_label, callback_data=f"s_sell:{p}")
                ])
            else:
                # No position — color BUY and SELL buttons based on signal
                if signal in ['BUY', 'STRONG_BUY']:
                    buy_label = f"🟢 BUY {pn}"
                    sell_label = f"⬆️ SELL {pn}"  # Default (not profitable to sell)
                elif signal in ['SELL', 'STRONG_SELL']:
                    buy_label = f"🔴 BUY {pn}"
                    sell_label = f"🔴 SELL {pn}"  # Good to sell!
                else:
                    buy_label = f"⬇️ BUY {pn}"
                    sell_label = f"⬆️ SELL {pn}"
                
                keyboard.append([
                    InlineKeyboardButton(buy_label, callback_data=f"s_buy:{p}"),
                    InlineKeyboardButton(sell_label, callback_data=f"s_sell:{p}")
                ])

        keyboard.append([
            InlineKeyboardButton("📦 Posisi", callback_data="s_refresh_posisi"),
            InlineKeyboardButton("➕ Tambah Pair", callback_data="s_add_pair_hint")
        ])
        keyboard.append([
            InlineKeyboardButton("🔄 Refresh Harga", callback_data="s_refresh_prices")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send as plain text to ensure keyboard is always shown
        try:
            await update.effective_message.reply_text(
                status_text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error sending menu: {e}")
            # Try without keyboard if first attempt fails
            await update.effective_message.reply_text(status_text)

    async def menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            logger.warning("⚠️ menu_callback: No callback_query in update")
            return
        
        user_id = query.from_user.id
        callback_data = query.data
        
        logger.info(f"🔍 menu_callback triggered: data='{callback_data}', user={user_id}")
        
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"⚠️ query.answer() failed: {e}")

        if not self._is_admin(user_id):
            logger.warning(f"⚠️ Non-admin user {user_id} tried callback")
            await query.edit_message_text("❌ Akses Ditolak")
            return

        if callback_data == 's_cancel_action':
            logger.info("✅ Handling s_cancel_action")
            await query.edit_message_text("✅ Dibatalkan.")
            return

        if callback_data == 's_sell_no_pos':
            await query.answer("⚠️ Tidak ada posisi untuk dijual. BUY dulu!", show_alert=True)
            return

        if callback_data == 's_add_pair_hint':
            logger.info("✅ Handling s_add_pair_hint")
            await query.edit_message_text(
                "➕ **Tambah Pair**\n\n"
                "Ketik: `/s_pair add <pair>`\n"
                "Contoh: `/s_pair add btcidr`\n\n"
                "Lalu `/s_menu` untuk refresh menu.",
                parse_mode='Markdown'
            )
            return

        if callback_data == 's_analisa_hint':
            logger.info("✅ Handling s_analisa_hint")
            try:
                await query.edit_message_text(
                    "📈 **Analisa Pair**\n\n"
                    "Ketik: `/s_analisa <pair>`\n"
                    "Contoh: `/s_analisa btcidr`\n\n"
                    "Menampilkan:\n"
                    "• RSI, MACD, Moving Average\n"
                    "• Bollinger Bands\n"
                    "• Volume analysis\n"
                    "• Support & Resistance\n\n"
                    "💡 Gunakan sebelum entry untuk analisa teknikal lengkap!",
                    parse_mode='Markdown'
                )
                logger.info("✅ s_analisa_hint sent successfully")
            except Exception as e:
                logger.error(f"❌ s_analisa_hint failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        if callback_data == 's_close_all_confirm':
            logger.info(f"✅ Handling s_close_all_confirm (positions: {len(self.active_positions)})")
            try:
                keyboard = [
                    [InlineKeyboardButton("⚠️ YES, Close ALL Positions", callback_data="s_confirm_close_all")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")]
                ]
                await query.edit_message_text(
                    "⚠️ **CONFIRMATION**\n\n"
                    "Tutup SEMUA posisi aktif?\n\n"
                    f"Jumlah posisi: {len(self.active_positions)}\n\n"
                    "Tindakan ini tidak bisa dibatalkan!",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                logger.info("✅ s_close_all_confirm dialog sent")
            except Exception as e:
                logger.error(f"❌ s_close_all_confirm failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        if callback_data == 's_confirm_close_all':
            logger.info("✅ Handling s_confirm_close_all")
            try:
                await self._execute_close_all_positions(query)
            except Exception as e:
                logger.error(f"❌ s_confirm_close_all execution failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        if callback_data == 's_refresh_portfolio':
            logger.info("✅ Handling s_refresh_portfolio")
            try:
                await self.refresh_portfolio_callback(update, context)
            except Exception as e:
                logger.error(f"❌ s_refresh_portfolio failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        if callback_data == 's_refresh_posisi':
            logger.info("✅ Handling s_refresh_posisi")
            try:
                await self.refresh_posisi_callback(update, context)
            except Exception as e:
                logger.error(f"❌ s_refresh_posisi failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        if callback_data == 's_refresh_prices':
            logger.info("✅ Handling s_refresh_prices")
            try:
                await self.refresh_prices_callback(update, context)
            except Exception as e:
                logger.error(f"❌ s_refresh_prices failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        # Handle s_menu button (return to main menu)
        if callback_data == 's_menu':
            logger.info("✅ Handling s_menu")
            try:
                await self.cmd_menu(update, context)
            except Exception as e:
                logger.error(f"❌ s_menu failed: {e}")
            return

        # Handle s_buy:{pair} - initiate buy process
        if query.data.startswith('s_buy:'):
            _, pair = query.data.split(':', 1)
            logger.info(f"✅ Handling s_buy:{pair}")
            try:
                await self._initiate_buy(query, pair)
            except Exception as e:
                logger.error(f"❌ s_buy failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        # Handle s_sell:{pair} - initiate sell process
        if query.data.startswith('s_sell:'):
            _, pair = query.data.split(':', 1)
            logger.info(f"✅ Handling s_sell:{pair}")
            try:
                await self._initiate_sell(query, pair)
            except Exception as e:
                logger.error(f"❌ s_sell failed: {e}")
                await query.answer(f"Error: {e}", show_alert=True)
            return

        if query.data.startswith('s_confirm_buy:'):
            parts = query.data.split(':')
            # New format: s_confirm_buy:pair:price:idr_amount:tp:sl
            if len(parts) == 6:
                pair = parts[1]
                price = float(parts[2])
                idr_amount = float(parts[3])
                tp = float(parts[4]) if parts[4] != '0' else 0
                sl = float(parts[5]) if parts[5] != '0' else 0
                await self._execute_confirmed_buy(query, pair, price, idr_amount, tp, sl)
            else:
                # Old format: s_confirm_buy:pair:capital
                pair, capital = parts[1], float(parts[2])
                await self._execute_confirmed_buy_old(query, pair, capital)
            return

        if query.data.startswith('s_confirm_sell:'):
            parts = query.data.split(':')
            pair, price = parts[1], float(parts[2])
            await self._execute_confirmed_sell(query, pair, price)
            return

        if ":" in query.data:
            action, pair = query.data.split(':', 1)
            # Strip s_ prefix
            action = action.replace('s_', '')
            
            if action == 'buy':
                await self._execute_buy(query, pair)
            elif action == 'sell':
                await self._execute_sell(query, pair)
            elif action == 'ignore_alert':
                await query.edit_message_text("⏸️ Alert diabaikan.")

    async def _execute_buy(self, query, pair):
        capital = self.balance * ScalperConfig.DEFAULT_TRADE_PCT
        if capital > self.balance:
            await query.message.reply_text(f"❌ Saldo tidak cukup ({self.balance:,.0f})")
            return

        if self.is_real_trading:
            keyboard = [[
                InlineKeyboardButton("✅ YES, Execute Real Buy", callback_data=f"s_confirm_buy:{pair}:{capital:.0f}")
            ], [
                InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")
            ]]
            await query.message.reply_text(
                f"⚠️ **REAL TRADING MODE**\nExecute BUY {pair.upper()}?\nModal: {capital:,.0f} IDR",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
            return

        try:
            loop = asyncio.get_running_loop()
            price = await loop.run_in_executor(None, lambda: self._get_price_sync(pair))
            amount = (capital * (1 - ScalperConfig.TRADING_FEE_PCT)) / price
            self.balance -= capital

            if pair in self.active_positions:
                old = self.active_positions[pair]
                total_capital = old['capital'] + capital
                total_amount = old['amount'] + amount
                avg_entry = total_capital / total_amount
                self.active_positions[pair] = {
                    'entry': avg_entry, 'time': old['time'],
                    'amount': total_amount, 'capital': total_capital
                }
                if 'tp' in old: self.active_positions[pair]['tp'] = old['tp']
                if 'sl' in old: self.active_positions[pair]['sl'] = old['sl']
            else:
                self.active_positions[pair] = {
                    'entry': price, 'time': time.time(), 'amount': amount, 'capital': capital
                }
            self._save_positions()
            if pair not in self.pairs:
                self.pairs.append(pair)
                ScalperConfig.save_pairs(self.pairs)

            await query.message.reply_text(f"✅ **BUY {pair.upper()}**\nPrice: {price:,.0f}\nModal: {capital:,.0f}", parse_mode='Markdown')
        except Exception as e:
            await query.message.reply_text(f"❌ Gagal Buy: {e}")

    async def _execute_confirmed_buy_old(self, query, pair, capital):
        """Old buy confirmation - used by legacy callback"""
        try:
            loop = asyncio.get_running_loop()
            price = await loop.run_in_executor(None, lambda: self._get_price_sync(pair))
            amount = (capital * (1 - ScalperConfig.TRADING_FEE_PCT)) / price

            if self.is_real_trading and self.indodax:
                # REAL: Call Indodax API
                result = self.indodax.create_order(pair, 'buy', price, amount)
                if result and result.get('success'):
                    order_id = result.get('return', {}).get('order_id', 'unknown')
                    self.balance -= capital
                    self.active_positions[pair] = {
                        'entry': price, 'time': time.time(), 'amount': amount, 'capital': capital,
                        'order_id': order_id
                    }
                    self._save_positions()
                    await query.edit_message_text(
                        f"✅ **BUY {pair.upper()}** (REAL)\n"
                        f"Price: {price:,.0f}\nModal: {capital:,.0f}\n"
                        f"Order ID: {order_id}\nSaldo: {self.balance:,.0f}",
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text(f"❌ Order gagal: {result}")
                    return
            else:
                # DRY RUN
                self.balance -= capital
                self.active_positions[pair] = {
                    'entry': price, 'time': time.time(), 'amount': amount, 'capital': capital
                }
                self._save_positions()
                await query.edit_message_text(
                    f"✅ **BUY {pair.upper()}** (DRY RUN)\n"
                    f"Price: {price:,.0f}\nModal: {capital:,.0f}\nSaldo: {self.balance:,.0f}",
                    parse_mode='Markdown'
                )
        except Exception as e:
            await query.message.reply_text(f"❌ Gagal Buy: {e}")

    async def _execute_sell(self, query, pair):
        if pair not in self.active_positions:
            await query.message.reply_text(f"⚠️ Tidak ada posisi di {pair.upper()}.")
            return
        pos = self.active_positions[pair]
        try:
            loop = asyncio.get_running_loop()
            price = await loop.run_in_executor(None, lambda: self._get_price_sync(pair))
        except Exception as e:
            await query.message.reply_text(f"❌ Gagal ambil harga: {e}")
            return

        if self.is_real_trading:
            revenue = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT)
            profit_idr = revenue - pos['capital']
            pnl_pct = (profit_idr / pos['capital']) * 100
            keyboard = [[
                InlineKeyboardButton(f"✅ YES, SELL at {price:,.0f}", callback_data=f"s_confirm_sell:{pair}:{price:.0f}")
            ], [InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")]]
            await query.message.reply_text(
                f"⚠️ **REAL TRADING MODE**\nSell {pair.upper()}?\nPrice: {price:,.0f}\nP/L: {pnl_pct:+.2f}%",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
            return

        revenue = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT)
        profit_idr = revenue - pos['capital']
        pnl_pct = (profit_idr / pos['capital']) * 100
        self.balance += revenue
        del self.active_positions[pair]
        self._save_positions()
        await query.message.reply_text(
            f"🔴 **SELL {pair.upper()}**\n"
            f"📦 Qty: {pos['amount']:,.2f}\n"
            f"💰 Price: {price:,.0f}\n"
            f"📊 P/L: {pnl_pct:+.2f}%\n"
            f"💸 Profit: {profit_idr:+,.0f} IDR",
            parse_mode='Markdown'
        )

    async def _execute_confirmed_sell(self, query, pair, price):
        if pair not in self.active_positions:
            await query.edit_message_text("⚠️ Posisi tidak ditemukan.")
            return
        pos = self.active_positions[pair]
        amount = pos['amount']
        revenue = (price * amount) * (1 - ScalperConfig.TRADING_FEE_PCT)
        profit_idr = revenue - pos['capital']
        pnl_pct = (profit_idr / pos['capital']) * 100

        if self.is_real_trading and self.indodax:
            # REAL: Call Indodax API
            result = self.indodax.create_order(pair, 'sell', price, amount)
            if result and result.get('success'):
                order_id = result.get('return', {}).get('order_id', 'unknown')
                self.balance += revenue
                del self.active_positions[pair]
                self._save_positions()
                await query.edit_message_text(
                    f"🔴 **SELL {pair.upper()}** (REAL)\n"
                    f"📦 Qty: `{amount:,.2f}`\n"
                    f"💰 Price: `{price:,.0f}` IDR\n"
                    f"📊 P/L: `{pnl_pct:+.2f}%`\n"
                    f"💸 Profit: `{profit_idr:+,.0f}` IDR\n"
                    f"🔗 Order ID: `{order_id}`\n"
                    f"💰 Saldo: `{self.balance:,.0f}` IDR",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(f"❌ Sell gagal: {result}")
                return
        else:
            # DRY RUN
            self.balance += revenue
            del self.active_positions[pair]
            self._save_positions()
            await query.edit_message_text(
                f"🔴 **SELL {pair.upper()}** (DRY RUN)\n"
                f"📦 Qty: `{amount:,.2f}`\n"
                f"💰 Price: `{price:,.0f}` IDR\n"
                f"📊 P/L: `{pnl_pct:+.2f}%`\n"
                f"💸 Profit: `{profit_idr:+,.0f}` IDR\n"
                f"💰 Saldo: `{self.balance:,.0f}` IDR",
                parse_mode='Markdown'
            )

    async def _execute_close_all_positions(self, query):
        """Close all active positions at current market price"""
        if not self.active_positions:
            await query.edit_message_text("ℹ️ Tidak ada posisi aktif untuk ditutup")
            return

        total_positions = len(self.active_positions)
        closed_count = 0
        failed_count = 0
        total_pnl = 0
        
        summary_msg = f"🔄 Menutup {total_positions} posisi...\n\n"
        
        # Create a copy to avoid modification during iteration
        positions_to_close = list(self.active_positions.items())
        
        for pair, pos in positions_to_close:
            try:
                # Get current price
                loop = asyncio.get_running_loop()
                price = await loop.run_in_executor(None, lambda p=pair: self._get_price_sync(p))
                
                # Calculate P/L
                pnl_pct = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                profit_idr = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
                total_pnl += profit_idr
                
                if self.is_real_trading and self.indodax:
                    # REAL: Execute sell via Indodax API
                    amount = pos['amount']
                    result = self.indodax.create_order(pair, 'sell', price, amount)
                    if result and result.get('success'):
                        self.balance += profit_idr + pos['capital']
                        del self.active_positions[pair]
                        closed_count += 1
                        emoji = "🟢" if profit_idr >= 0 else "🔴"
                        summary_msg += f"{emoji} **{pair.upper()}**: `{profit_idr:+,.0f} IDR` (`{pnl_pct:+.1f}%`)\n"
                    else:
                        failed_count += 1
                        summary_msg += f"❌ **{pair.upper()}**: Gagal sell\n"
                else:
                    # DRY RUN
                    self.balance += profit_idr + pos['capital']
                    del self.active_positions[pair]
                    closed_count += 1
                    emoji = "🟢" if profit_idr >= 0 else "🔴"
                    summary_msg += f"{emoji} **{pair.upper()}**: `{profit_idr:+,.0f} IDR` (`{pnl_pct:+.1f}%`)\n"
                    
            except Exception as e:
                failed_count += 1
                summary_msg += f"❌ **{pair.upper()}**: Error - {str(e)[:50]}\n"
        
        # Save updated positions
        self._save_positions()
        
        # Add summary
        mode_str = "REAL" if self.is_real_trading else "DRY RUN"
        summary_msg += f"\n✅ **CLOSE ALL COMPLETE** ({mode_str})"
        summary_msg += f"\n• Closed: {closed_count}"
        if failed_count > 0:
            summary_msg += f"\n• Failed: {failed_count}"
        summary_msg += f"\n• Total P/L: `{total_pnl:+,.0f} IDR`"
        summary_msg += f"\n• Saldo: `{self.balance:,.0f} IDR`"
        
        await query.edit_message_text(summary_msg, parse_mode='Markdown')

    async def cmd_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Buy position for scalper pair with optional TP/SL"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        if not context.args or len(context.args) < 3:
            await update.effective_message.reply_text("⚠️ Format: `/s_buy <pair> <price> <idr> [tp] [sl]`\nContoh: `/s_buy l3idr 375 1000000 400 350`", parse_mode='Markdown')
            return
        pair = context.args[0].lower().strip()
        try:
            price = float(context.args[1])
            idr_amount = float(context.args[2])
        except ValueError:
            await update.effective_message.reply_text("⚠️ Harga dan IDR harus angka!")
            return
        tp = float(context.args[3]) if len(context.args) > 3 and context.args[3] not in ['-', '0'] else None
        sl = float(context.args[4]) if len(context.args) > 4 and context.args[4] not in ['-', '0'] else None
        if tp and tp <= price:
            await update.effective_message.reply_text("⚠️ TP harus lebih tinggi dari entry!")
            return
        if sl and sl >= price:
            await update.effective_message.reply_text("⚠️ SL harus lebih rendah dari entry!")
            return
        if idr_amount > self.balance:
            await update.effective_message.reply_text(f"❌ Saldo tidak cukup!\nSaldo: {self.balance:,.0f} IDR")
            return

        # Calculate coin amount
        amount = (idr_amount * (1 - ScalperConfig.TRADING_FEE_PCT)) / price

        # ============================================================
        # REAL TRADING MODE - Execute buy on Indodax
        # ============================================================
        if self.is_real_trading and self.indodax:
            try:
                # Show confirmation before executing real buy
                keyboard = [[
                    InlineKeyboardButton(f"✅ YES, BUY {pair.upper()} at {price:,.0f}", callback_data=f"s_confirm_buy:{pair}:{price:.0f}:{idr_amount:.0f}:{tp or 0}:{sl or 0}")
                ], [InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")]]
                await update.effective_message.reply_text(
                    f"⚠️ **REAL TRADING MODE**\n\n"
                    f"🟢 **BUY {pair.upper()}**\n"
                    f"💰 Price: `{price:,.0f}` IDR\n"
                    f"💵 Modal: `{idr_amount:,.0f}` IDR\n"
                    f"📦 Est. Amount: `{amount:,.2f}`\n\n"
                    f"Order will be executed on **Indodax**!",
                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
                )
                return
            except Exception as e:
                await update.effective_message.reply_text(f"❌ Error preparing buy order: {e}")
                return

        # ============================================================
        # DRY RUN MODE - Local simulation only
        # ============================================================
        self.balance -= idr_amount

        if pair in self.active_positions:
            old = self.active_positions[pair]
            total_capital = old['capital'] + idr_amount
            total_amount = old['amount'] + amount
            avg_entry = total_capital / total_amount
            self.active_positions[pair] = {
                'entry': avg_entry, 'time': old['time'],
                'amount': total_amount, 'capital': total_capital
            }
            if 'tp' in old: self.active_positions[pair]['tp'] = old['tp']
            if 'sl' in old: self.active_positions[pair]['sl'] = old['sl']
            action_text = f"📊 **AVERAGE DOWN {pair.upper()}**"
            detail = f"Entry Lama: {old['entry']:,.0f} → Avg: {avg_entry:,.0f}\n"
        else:
            position = {'entry': price, 'time': time.time(), 'amount': amount, 'capital': idr_amount}
            if tp: position['tp'] = tp
            if sl: position['sl'] = sl
            self.active_positions[pair] = position
            action_text = f"✅ **BUY {pair.upper()}**"
            detail = ""

        self._save_positions()
        if pair not in self.pairs:
            self.pairs.append(pair)
            ScalperConfig.save_pairs(self.pairs)

        tp_info = f"\n🎯 TP: {tp:,.0f}" if tp else ""
        sl_info = f"\n🛑 SL: {sl:,.0f}" if sl else ""
        await update.effective_message.reply_text(f"{action_text}\n\n📊 Price: {price:,.0f}\n💵 Modal: {idr_amount:,.0f} IDR\n📦 Amount: {amount:,.2f}{tp_info}{sl_info}\n{detail}💰 Saldo: {self.balance:,.0f} IDR")

    async def _initiate_buy(self, query, pair: str):
        """Initiate buy process - get price and show confirmation"""
        await query.answer(f"💰 Buying {pair.upper()}...")

        try:
            import concurrent.futures
            loop = asyncio.get_running_loop()
            price = await loop.run_in_executor(None, lambda: self._get_price_sync(pair))

            has_position = pair in self.active_positions
            pos_info = ""
            if has_position:
                pos = self.active_positions[pair]
                pnl = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                pos_info = f"\n📦 Existing position: Entry `{Utils.format_price(pos['entry'])}` | P/L: `{pnl:+.2f}%`"

            # Default buy amount (10% of balance or 100k, whichever is smaller)
            default_amount = min(self.balance * 0.1, 500000)
            default_amount = max(default_amount, 50000)  # Minimum 50k

            mode_str = "🔴 REAL" if self.is_real_trading else "🧪 DRY RUN"

            text = (
                f"💰 **BUY {pair.upper()}** {mode_str}\n\n"
                f"📊 Current Price: `{Utils.format_price(price)}` IDR\n"
                f"💰 Saldo: `{self.balance:,.0f}` IDR{pos_info}\n\n"
                f"💡 **Quick Buy:**\n"
                f"• Use `/s_buy {pair} <amount_idr>` untuk langsung beli\n"
                f"• Contoh: `/s_buy {pair} 100000`\n\n"
                f"⚡ **Quick Actions:**\n"
                f"• Buy 50k → `/s_buy {pair} 50000`\n"
                f"• Buy 100k → `/s_buy {pair} 100000`\n"
                f"• Buy 500k → `/s_buy {pair} 500000`"
            )

            keyboard = [
                [
                    InlineKeyboardButton(f"💰 Buy 50k", callback_data=f"s_confirm_buy:{pair}:{price:.0f}:50000:0:0"),
                    InlineKeyboardButton(f"💰 Buy 100k", callback_data=f"s_confirm_buy:{pair}:{price:.0f}:100000:0:0")
                ],
                [
                    InlineKeyboardButton(f"💰 Buy 500k", callback_data=f"s_confirm_buy:{pair}:{price:.0f}:500000:0:0"),
                    InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")
                ],
                [
                    InlineKeyboardButton("📦 Posisi", callback_data="s_refresh_posisi"),
                    InlineKeyboardButton("📊 Menu", callback_data="s_menu")
                ]
            ]

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        except Exception as e:
            logger.error(f"❌ Initiate buy error for {pair}: {e}")
            await query.edit_message_text(f"❌ Gagal mendapatkan harga {pair.upper()}:\n`{str(e)}`", parse_mode='Markdown')

    async def _initiate_sell(self, query, pair: str):
        """Initiate sell process - get price and show confirmation"""
        await query.answer(f"💰 Selling {pair.upper()}...")

        if pair not in self.active_positions:
            await query.edit_message_text(
                f"⚠️ **Tidak ada posisi di {pair.upper()}**\n\n"
                f"Gunakan `/s_posisi` untuk melihat posisi aktif.",
                parse_mode='Markdown'
            )
            return

        try:
            import concurrent.futures
            loop = asyncio.get_running_loop()
            price = await loop.run_in_executor(None, lambda: self._get_price_sync(pair))

            pos = self.active_positions[pair]
            pnl = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
            profit_idr = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']

            emoji = "🟢" if pnl >= 0 else "🔴"
            mode_str = "🔴 REAL" if self.is_real_trading else "🧪 DRY RUN"

            text = (
                f"{emoji} **SELL {pair.upper()}** {mode_str}\n\n"
                f"📊 Current Price: `{Utils.format_price(price)}` IDR\n"
                f"📦 Entry: `{Utils.format_price(pos['entry'])}` IDR\n"
                f"💰 Amount: `{pos['amount']:.2f}` | Capital: `{pos['capital']:,.0f}` IDR\n\n"
                f"📈 P/L: `{pnl:+.2f}%` (`{profit_idr:+,.0f}` IDR)\n"
                f"💰 Saldo saat ini: `{self.balance:,.0f}` IDR\n\n"
                f"⚠️ **Yakin mau sell?**\n"
                f"Klik tombol di bawah untuk konfirmasi."
            )

            keyboard = [
                [
                    InlineKeyboardButton(f"✅ SELL ALL at {price:,.0f}", callback_data=f"s_confirm_sell:{pair}:{price:.0f}")
                ],
                [
                    InlineKeyboardButton("📊 Info Detail", callback_data=f"s_info:{pair}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")
                ],
                [
                    InlineKeyboardButton("📦 Posisi", callback_data="s_refresh_posisi"),
                    InlineKeyboardButton("📊 Menu", callback_data="s_menu")
                ]
            ]

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

        except Exception as e:
            logger.error(f"❌ Initiate sell error for {pair}: {e}")
            await query.edit_message_text(f"❌ Gagal mendapatkan harga {pair.upper()}:\n`{str(e)}`", parse_mode='Markdown')

    async def _execute_confirmed_buy(self, query, pair, price, idr_amount, tp, sl):
        """Execute confirmed buy order on Indodax (real trading)"""
        amount = (idr_amount * (1 - ScalperConfig.TRADING_FEE_PCT)) / price

        try:
            # Execute buy on Indodax
            result = self.indodax.create_order(pair, 'buy', price, amount)

            if result and result.get('success'):
                order_id = result.get('return', {}).get('order_id', 'N/A')

                # Get actual executed amount from response
                received_amount = result.get('return', {}).get('received_credit', amount)
                actual_amount = float(received_amount) if received_amount else amount

                # Update local position
                if pair in self.active_positions:
                    old = self.active_positions[pair]
                    total_capital = old['capital'] + idr_amount
                    total_amount = old['amount'] + actual_amount
                    avg_entry = total_capital / total_amount
                    self.active_positions[pair] = {
                        'entry': avg_entry, 'time': old['time'],
                        'amount': total_amount, 'capital': total_capital,
                        'order_id': order_id
                    }
                    if 'tp' in old: self.active_positions[pair]['tp'] = old['tp']
                    if 'sl' in old: self.active_positions[pair]['sl'] = old['sl']
                    action_text = f"📊 **AVERAGE DOWN {pair.upper()}**"
                else:
                    self.active_positions[pair] = {
                        'entry': price, 'time': time.time(),
                        'amount': actual_amount, 'capital': idr_amount,
                        'order_id': order_id
                    }
                    if tp and tp > 0: self.active_positions[pair]['tp'] = tp
                    if sl and sl > 0: self.active_positions[pair]['sl'] = sl
                    action_text = f"✅ **BUY {pair.upper()}**"

                # Deduct balance
                self.balance -= idr_amount
                self._save_positions()

                # Add to pairs list if not already
                if pair not in self.pairs:
                    self.pairs.append(pair)
                    ScalperConfig.save_pairs(self.pairs)

                tp_info = f"\n🎯 TP: {tp:,.0f}" if tp and tp > 0 else ""
                sl_info = f"\n🛑 SL: {sl:,.0f}" if sl and sl > 0 else ""

                await query.edit_message_text(
                    f"{action_text}\n\n"
                    f"📊 Price: `{price:,.0f}` IDR\n"
                    f"💵 Modal: `{idr_amount:,.0f}` IDR\n"
                    f"📦 Amount: `{actual_amount:,.2f}`\n"
                    f"🔗 Order ID: `{order_id}`{tp_info}{sl_info}\n"
                    f"💰 Saldo: `{self.balance:,.0f}` IDR\n\n"
                    f"✅ **Order executed on Indodax!**",
                    parse_mode='Markdown'
                )
            else:
                # Order failed
                error_msg = result.get('error', 'Unknown error') if result else 'No response'
                await query.edit_message_text(
                    f"❌ **BUY FAILED**\n\n"
                    f"🟢 {pair.upper()}\n"
                    f"💰 Price: `{price:,.0f}` IDR\n"
                    f"💵 Modal: `{idr_amount:,.0f}` IDR\n\n"
                    f"⚠️ Error: `{error_msg}`\n\n"
                    f"Balance NOT deducted. Check Indodax for details.",
                    parse_mode='Markdown'
                )
                logger.error(f"Real buy failed for {pair}: {result}")
        except Exception as e:
            await query.edit_message_text(
                f"❌ **BUY ERROR**\n\n"
                f"🟢 {pair.upper()}\n"
                f"💰 Price: `{price:,.0f}` IDR\n"
                f"⚠️ Error: `{str(e)}`\n\n"
                f"Balance NOT deducted.",
                parse_mode='Markdown'
            )
            logger.error(f"Real buy exception for {pair}: {e}")

    async def cmd_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sell scalper position at market or limit price"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        if not context.args:
            await update.effective_message.reply_text("⚠️ Format: `/s_sell <pair> [price]`", parse_mode='Markdown')
            return
        pair = context.args[0].lower().strip()
        if pair not in self.active_positions:
            await update.effective_message.reply_text(f"⚠️ Tidak ada posisi di {pair.upper()}.")
            return
        pos = self.active_positions[pair]
        if len(context.args) >= 2:
            try:
                price = float(context.args[1])
            except ValueError:
                await update.effective_message.reply_text("⚠️ Harga harus angka!")
                return
        else:
            try:
                price = self._get_price_sync(pair)
            except Exception as e:
                await update.effective_message.reply_text(f"❌ Gagal ambil harga: {e}")
                return

        if self.is_real_trading:
            revenue = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT)
            profit_idr = revenue - pos['capital']
            pnl_pct = (profit_idr / pos['capital']) * 100
            keyboard = [[
                InlineKeyboardButton("✅ YES, SELL", callback_data=f"s_confirm_sell:{pair}:{price:.0f}")
            ], [InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")]]
            await update.effective_message.reply_text(
                f"⚠️ **REAL TRADING MODE**\n\n"
                f"🔴 **SELL {pair.upper()}**\n"
                f"📦 Qty: `{pos['amount']:,.2f}`\n"
                f"💰 Price: `{price:,.0f}` IDR\n"
                f"📊 P/L: `{pnl_pct:+.2f}%`\n"
                f"💸 Est. Profit: `{profit_idr:+,.0f}` IDR\n\n"
                f"Order will be executed on **Indodax**!",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
            return

        revenue = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT)
        profit_idr = revenue - pos['capital']
        pnl_pct = (profit_idr / pos['capital']) * 100
        self.balance += revenue
        del self.active_positions[pair]
        self._save_positions()
        await update.effective_message.reply_text(
            f"🔴 **SELL {pair.upper()}**\n"
            f"📦 Qty: {pos['amount']:,.2f}\n"
            f"💰 Price: {price:,.0f}\n"
            f"📊 P/L: {pnl_pct:+.2f}%\n"
            f"💸 Profit: {profit_idr:+,.0f} IDR\n"
            f"💰 Saldo: {self.balance:,.0f}",
            parse_mode='Markdown'
        )

    async def cmd_sltp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set or update Take Profit / Stop Loss for scalper position"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        if not context.args or len(context.args) < 3:
            await update.effective_message.reply_text("⚠️ Format: `/s_sltp <pair> <tp> <sl>`\nGunakan `-` untuk skip.", parse_mode='Markdown')
            return
        pair = context.args[0].lower().strip()
        if pair not in self.active_positions:
            await update.effective_message.reply_text(f"⚠️ Tidak ada posisi di {pair.upper()}.")
            return
        tp = float(context.args[1]) if context.args[1] != '-' else None
        sl = float(context.args[2]) if context.args[2] != '-' else None
        pos = self.active_positions[pair]
        if tp and tp <= pos['entry']:
            await update.effective_message.reply_text("⚠️ TP harus lebih tinggi dari entry!")
            return
        if sl and sl >= pos['entry']:
            await update.effective_message.reply_text("⚠️ SL harus lebih rendah dari entry!")
            return
        if tp: pos['tp'] = tp
        elif 'tp' in pos: del pos['tp']
        if sl: pos['sl'] = sl
        elif 'sl' in pos: del pos['sl']
        self.active_positions[pair] = pos
        self._save_positions()
        tp_info = f"🎯 TP: {tp:,.0f}" if tp else "🎯 TP: Tidak ada"
        sl_info = f"🛑 SL: {sl:,.0f}" if sl else "🛑 SL: Tidak ada"
        await update.effective_message.reply_text(f"✅ **TP/SL {pair.upper()}**\n\n📊 Entry: {pos['entry']:,.0f}\n{tp_info}\n{sl_info}")

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel TP, SL, or pending order for scalper position"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        if not context.args:
            await update.effective_message.reply_text("⚠️ Format: `/s_cancel <pair> [tp|sl|all]`", parse_mode='Markdown')
            return
        pair = context.args[0].lower().strip()
        cancel_type = context.args[1].lower() if len(context.args) > 1 else 'all'
        if pair not in self.active_positions:
            await update.effective_message.reply_text(f"⚠️ Tidak ada posisi di {pair.upper()}.")
            return
        pos = self.active_positions[pair]
        removed = []

        # Cancel pending order on Indodax if exists
        if self.is_real_trading and self.indodax and 'order_id' in pos:
            order_id = pos['order_id']
            try:
                result = self.indodax.cancel_order(pair, order_id)
                if result and result.get('success'):
                    removed.append(f"📋 Indodax Order #{order_id}")
                else:
                    removed.append("⚠️ Gagal cancel order")
            except Exception as e:
                removed.append(f"❌ Error: {e}")
            finally:
                if 'order_id' in pos:
                    del pos['order_id']

        if cancel_type in ('sl', 'all'):
            if 'sl' in pos: del pos['sl']; removed.append('🛑 Stop Loss')
        if cancel_type in ('tp', 'all'):
            if 'tp' in pos: del pos['tp']; removed.append('🎯 Take Profit')
        self.active_positions[pair] = pos
        self._save_positions()
        if removed:
            await update.effective_message.reply_text(f"✅ **DIBATALKAN: {pair.upper()}**\n❌ {' + '.join(removed)}\n📊 Entry: {pos['entry']:,.0f}")
        else:
            await update.effective_message.reply_text(f"✅ Tidak ada TP/SL untuk {pair.upper()}.")

    async def cmd_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed info for specific scalper position"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        if not context.args:
            await update.effective_message.reply_text("⚠️ Format: `/s_info <pair>`", parse_mode='Markdown')
            return
        pair = context.args[0].lower().strip()
        if pair not in self.active_positions:
            await update.effective_message.reply_text(f"⚠️ Tidak ada posisi di {pair.upper()}.")
            return
        pos = self.active_positions[pair]
        try:
            price = self._get_price_sync(pair)
            pnl_pct = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
            profit_idr = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
            indicator = "🟢" if pnl_pct >= 0 else "🔴"
            tp_info = f"\n🎯 TP: {pos.get('tp', 0):,.0f}" if 'tp' in pos else ""
            sl_info = f"\n🛑 SL: {pos.get('sl', 0):,.0f}" if 'sl' in pos else ""
            info = (f"📊 **{pair.upper()}**\n\n{indicator} {'PROFIT' if pnl_pct >= 0 else 'LOSS'}\n"
                    f"📈 Entry: {pos['entry']:,.0f}\n💰 Current: {price:,.0f}\n"
                    f"📦 Amount: {pos['amount']:,.2f}\n💵 Modal: {pos['capital']:,.0f}\n"
                    f"📊 P/L: **{pnl_pct:+.2f}%** ({profit_idr:+,.0f} IDR)\n"
                    f"⏱️ Hold: {int(time.time() - pos['time'])}s{tp_info}{sl_info}")
            await update.effective_message.reply_text(info, parse_mode='Markdown')
        except Exception as e:
            await update.effective_message.reply_text(f"❌ Error: {e}")

    async def cmd_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        if not context.args:
            await update.effective_message.reply_text(
                "📊 **Pair Management**\n"
                "/s_pair add <pair>\n"
                "/s_pair remove <pair>\n"
                "/s_pair list\n"
                "/s_pair reset\n\n"
                "📈 **Analisa Pair:**\n"
                "/s_analisa <pair> - Analisa teknikal lengkap",
                parse_mode='Markdown'
            )
            return
        action = context.args[0].lower()
        if action == 'list':
            await update.effective_message.reply_text(f"📈 **Pairs** ({len(self.pairs)}):\n" + '\n'.join(f"• {p.upper()}" for p in self.pairs))
        elif action == 'add':
            if len(context.args) < 2:
                await update.effective_message.reply_text("⚠️ Format: `/s_pair add <pair>`")
                return
            new_pair = context.args[1].lower().strip()
            if not new_pair.endswith('idr'):
                new_pair += 'idr'
            if new_pair in self.pairs:
                await update.effective_message.reply_text(f"⚠️ {new_pair.upper()} sudah ada.")
                return
            await update.effective_message.reply_text(f"⏳ Validasi {new_pair.upper()}...")
            if not self.validate_pair(new_pair):
                await update.effective_message.reply_text(f"❌ {new_pair.upper()} tidak ditemukan di Indodax!")
                return
            self.pairs.append(new_pair)
            ScalperConfig.save_pairs(self.pairs)
            await update.effective_message.reply_text(f"✅ **{new_pair.upper()}** ditambahkan!")
        elif action == 'remove':
            if len(context.args) < 2:
                await update.effective_message.reply_text("⚠️ Format: `/s_pair remove <pair>`")
                return
            pair = context.args[1].lower().strip()
            if pair not in self.pairs:
                await update.effective_message.reply_text(f"⚠️ {pair.upper()} tidak ada.")
                return
            self.pairs.remove(pair)
            ScalperConfig.save_pairs(self.pairs)
            await update.effective_message.reply_text(f"🗑️ **{pair.upper()}** dihapus!")
        elif action == 'reset':
            # Reset pairs list to default
            self.pairs = ScalperConfig.PAIRS_DEFAULT
            ScalperConfig.save_pairs(self.pairs)
            
            # Clear ALL active positions (especially important for DRY RUN)
            positions_cleared = len(self.active_positions)
            if positions_cleared > 0:
                self.active_positions.clear()
                self.alerted_positions.clear()
                self.notified_drops.clear()
                self.last_alert_time = None
            
            # Reset balance to initial value (especially important for DRY RUN)
            old_balance = self.balance
            self.balance = ScalperConfig.INITIAL_BALANCE
            
            # Save all changes to file
            self._save_positions()
            logger.info(f"🗑️ Pair reset: {positions_cleared} positions cleared, balance {old_balance:,.0f} → {self.balance:,.0f} IDR")
            
            position_note = ""
            if positions_cleared > 0:
                position_note = f"\n\n🗑️ **Dihapus {positions_cleared} posisi aktif**\n• Semua posisi, alert & notifikasi direset"
            else:
                position_note = "\n\n✅ Tidak ada posisi aktif untuk dihapus"
            
            balance_note = f"\n\n💰 **Saldo direset:** `{old_balance:,.0f}` → `{ScalperConfig.INITIAL_BALANCE:,.0f}` IDR"
            
            # NOTE: Watchlist di main bot harus di-reset terpisah dengan /clear_watchlist
            watchlist_note = "\n\n💡 **Note:** Gunakan `/clear_watchlist` di main bot untuk hapus semua pair dari watchlist database"
            
            await update.effective_message.reply_text(
                f"✅ **Pair direset ke default ({len(self.pairs)}):**\n"
                + '\n'.join(f"• {p.upper()}" for p in self.pairs)
                + position_note
                + balance_note
                + watchlist_note,
                parse_mode='Markdown'
            )

    async def cmd_posisi(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return

        # FIX: Use .env value directly (no DB dependency)
        self.balance = float(os.getenv('INITIAL_BALANCE', 50000000))
        logger.debug(f"💰 Scalper balance from .env: {self.balance:,.0f} IDR")

        # Phase 2: Pre-fetch ALL position prices in parallel, cache to Redis
        price_cache_map = {}
        if self.active_positions:
            from cache.redis_price_cache import price_cache as redis_cache
            try:
                # Check Redis first for all pairs
                pairs_to_fetch = []
                for pair in self.active_positions.keys():
                    cached = redis_cache.get_price_sync(pair)
                    if cached is not None and cached > 0:
                        price_cache_map[pair] = cached
                    else:
                        pairs_to_fetch.append(pair)

                # Fetch missing pairs from API (parallel via ThreadPoolExecutor)
                if pairs_to_fetch:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(pairs_to_fetch))) as executor:
                        future_to_pair = {
                            executor.submit(self._get_price_from_api_only, p): p
                            for p in pairs_to_fetch
                        }
                        for future in concurrent.futures.as_completed(future_to_pair, timeout=30):
                            pair = future_to_pair[future]
                            try:
                                price = future.result()
                                price_cache_map[pair] = price
                                # Write to Redis for next time
                                redis_cache.set_price(pair, price)
                            except Exception as e:
                                logger.debug(f"Failed to fetch {pair}: {e}")
            except Exception as e:
                logger.debug(f"Batch price fetch error: {e}")

        # Build header message
        msg = f"📦 **POSISI AKTIF**\n\n💰 Saldo: {self.balance:,.0f}\n📈 P/L: {self.balance - ScalperConfig.INITIAL_BALANCE:+,.0f}\n📊 Open: {len(self.active_positions)}"

        keyboard = []
        if self.active_positions:
            for pair, pos in dict(self.active_positions).items():
                try:
                    # Use pre-fetched price, fallback to _get_price_sync
                    price = price_cache_map.get(pair)
                    if price is None:
                        price = self._get_price_sync(pair)

                    pnl = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                    profit = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
                    is_profit = pnl >= 0

                    # Format: 🟢/🔴 PAIR Entry → Current | P/L% (amount) | TP/SL
                    entry_str = Utils.format_price(pos['entry'])
                    current_str = Utils.format_price(price)
                    pnl_str = f"{pnl:+.2f}% ({profit:+,.0f})"
                    emoji = "🟢" if is_profit else "🔴"
                    
                    # Get TP/SL values
                    tp_val = pos.get('tp')
                    sl_val = pos.get('sl')
                    tp_str = f"TP:{Utils.format_price(tp_val)}" if tp_val else "TP:-"
                    sl_str = f"SL:{Utils.format_price(sl_val)}" if sl_val else "SL:-"

                    btn_label = f"{emoji} {pair.upper()} | {pnl_str} | {tp_str} / {sl_str}"

                    # Button bar: Info + Quick Sell
                    sell_emoji = "💰" if is_profit else "📉"
                    keyboard.append([
                        InlineKeyboardButton(btn_label, callback_data=f"s_info:{pair}"),
                        InlineKeyboardButton(f"{sell_emoji} SELL", callback_data=f"s_sell:{pair}")
                    ])
                except Exception as e:
                    logger.error(f"Error building position button for {pair}: {e}")
                    keyboard.append([
                        InlineKeyboardButton(f"⚠️ {pair.upper()} | Error", callback_data=f"s_info:{pair}")
                    ])

        keyboard.append([
            InlineKeyboardButton("🔄 Refresh", callback_data="s_refresh_posisi"),
            InlineKeyboardButton("📊 Menu", callback_data="s_menu")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Add "no positions" note if empty
        if not self.active_positions:
            msg += "\n\n_Tidak ada posisi_"

        await update.effective_message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    def _get_price_from_api_only(self, pair):
        """Fetch price from API only — used by batch fetcher"""
        res = requests.get(
            f"{ScalperConfig.BASE_URL}{pair}",
            timeout=3,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        res.raise_for_status()
        data = res.json()
        if 'ticker' not in data:
            raise ValueError(f"Pair '{pair}' tidak ditemukan")
        return float(data['ticker']['last'])

    def _get_signal_for_pair(self, pair):
        """Get signal for a pair from database (latest signal)"""
        try:
            from core.database import Database
            db = Database()
            
            # Get latest signal from signals table
            with db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT recommendation, ml_confidence FROM signals WHERE pair = ? ORDER BY timestamp DESC LIMIT 1",
                    (pair,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        'recommendation': row['recommendation'],
                        'ml_confidence': row['ml_confidence']
                    }
            
            # Fallback: If no signal in DB, try to generate using main bot
            if hasattr(self, 'main_bot') and self.main_bot:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    signal = loop.run_until_complete(
                        self.main_bot._generate_signal_for_pair(pair)
                    )
                    if signal:
                        return {
                            'recommendation': signal.get('recommendation', 'HOLD'),
                            'ml_confidence': signal.get('ml_confidence', 0)
                        }
                finally:
                    loop.close()
            
            return {'recommendation': 'HOLD', 'ml_confidence': 0}
        except Exception as e:
            logger.debug(f"Signal check failed for {pair}: {e}")
            return {'recommendation': 'HOLD', 'ml_confidence': 0}

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        
        # SAFETY CHECK: Warn user about actual positions at Indodax
        count = len(self.active_positions)
        
        # Check if there are actual open orders at Indodax (only in real trading)
        indodax_orders = []
        if self.is_real_trading and self.indodax:
            try:
                indodax_orders = self.indodax.get_open_orders()
                if indodax_orders:
                    warning_msg = (
                        f"⚠️ **PERINGATAN: ADA POSISI DI INDODAX!**\n\n"
                        f"Ditemukan **{len(indodax_orders)} open order** di akun Indodax Anda.\n\n"
                        f"Jika Anda reset:\n"
                        f"• ✅ Bot akan lupa semua posisi lokal\n"
                        f"• ❌ Order di Indodax TETAP ADA\n"
                        f"• ⚠️ Bot tidak akan monitor TP/SL lagi\n\n"
                        f"**Rekomendasi:**\n"
                        f"• Gunakan `/s_sync` dulu untuk sync posisi\n"
                        f"• Atau cancel manual order di Indodax\n\n"
                        f"Ketik `/s_reset confirm` untuk lanjutkan reset."
                    )
                    await update.effective_message.reply_text(warning_msg, parse_mode='Markdown')
                    return
            except Exception as e:
                logger.error(f"Error checking Indodax orders: {e}")
        
        # Check if confirm is required
        if count > 0 and not (context.args and context.args[0].lower() == 'confirm'):
            confirm_msg = (
                f"⚠️ **KONFIRMASI RESET**\n\n"
                f"Ada **{count} posisi aktif** yang akan dihapus:\n"
                f"{' | '.join(list(self.active_positions.keys())[:5])}\n\n"
                f"Reset akan:\n"
                f"• 🗑️ Hapus semua posisi\n"
                f"• 💰 Reset balance ke {ScalperConfig.INITIAL_BALANCE:,.0f}\n"
                f"• 📊 Clear alert history\n\n"
                f"Ketik `/s_reset confirm` untuk lanjutkan."
            )
            await update.effective_message.reply_text(confirm_msg, parse_mode='Markdown')
            return
        
        # Execute reset
        self.active_positions.clear()
        self.alerted_positions.clear()
        self.notified_drops.clear()  # Clear drop notification history too
        self.balance = ScalperConfig.INITIAL_BALANCE
        self._save_positions()
        
        reset_msg = f"⚠️ **RESET SELESAI**\n\n🗑️ {count} posisi dihapus\n💰 Saldo: {self.balance:,.0f}"
        
        if indodax_orders:
            reset_msg += f"\n\n⚠️ **PERHATIAN:** {len(indodax_orders)} order masih ada di Indodax!\nGunakan `/s_sync` untuk sync ulang."
        
        await update.effective_message.reply_text(reset_msg, parse_mode='Markdown')

    async def cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lihat SEMUA pair scalper: yang ada posisi + yang hanya di-monitor"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        
        msg = await update.effective_message.reply_text("🔄 **Loading portfolio...**", parse_mode='Markdown')
        
        try:
            # Fetch semua harga pair
            price_data = {}
            for pair in self.pairs:
                try:
                    price = self._get_price_sync(pair)
                    price_data[pair] = price
                except Exception as e:
                    logger.error(f"Error fetching price for {pair}: {e}")
                    price_data[pair] = None
            
            # Hitung total P/L dari posisi aktif
            total_profit = 0
            total_profit_pct = 0
            active_count = len(self.active_positions)
            
            for pair, pos in self.active_positions.items():
                if pair in price_data and price_data[pair]:
                    price = price_data[pair]
                    pnl_pct = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                    profit = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
                    total_profit += profit
                    total_profit_pct += pnl_pct
            
            # Build message
            portfolio_msg = f"📊 **SCALPER PORTFOLIO**\n\n"
            portfolio_msg += f"💰 **Saldo:** {self.balance:,.0f} IDR\n"
            portfolio_msg += f"📈 **P/L Total:** {total_profit:+,.0f} IDR ({total_profit_pct:+.2f}%)\n"
            portfolio_msg += f"📦 **Posisi Aktif:** {active_count}\n"
            portfolio_msg += f"👀 **Total Pair:** {len(self.pairs)}\n\n"
            
            # Section 1: Posisi Aktif (yang ada trading)
            if self.active_positions:
                portfolio_msg += f"━━━ 📦 **POSISI AKTIF** ━━━\n\n"
                for pair, pos in self.active_positions.items():
                    price = price_data.get(pair)
                    if price:
                        pnl_pct = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                        profit = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
                        ind = "🟢" if pnl_pct >= 0 else "🔴"
                        tp = f"🎯 {Utils.format_price(pos.get('tp', 0))}" if 'tp' in pos else "-"
                        sl = f"🛑 {Utils.format_price(pos.get('sl', 0))}" if 'sl' in pos else "-"
                        
                        portfolio_msg += f"{ind} **{pair.upper()}**\n"
                        portfolio_msg += f"   Entry: {Utils.format_price(pos['entry'])} → Current: {Utils.format_price(price)}\n"
                        portfolio_msg += f"   P/L: **{pnl_pct:+.2f}%** ({profit:+,.0f})\n"
                        portfolio_msg += f"   TP: {tp} | SL: {sl}\n"
                        portfolio_msg += f"   Hold: {int(time.time() - pos['time'])}s\n\n"
                    else:
                        portfolio_msg += f"⚠️ **{pair.upper()}**: Error fetch price\n\n"
            
            # Section 2: Pair yang Di-Monitor (tanpa posisi)
            monitored_pairs = [p for p in self.pairs if p not in self.active_positions]
            if monitored_pairs:
                portfolio_msg += f"━━━ 👀 **PAIR DI-MONITOR** ━━━\n\n"
                for pair in monitored_pairs:
                    price = price_data.get(pair)
                    if price:
                        portfolio_msg += f"• **{pair.upper()}**: `{price:,.0f}` IDR\n"
                    else:
                        portfolio_msg += f"• **{pair.upper()}**: ❌ Error\n"
            
            if not self.active_positions and not monitored_pairs:
                portfolio_msg += "_Tidak ada pair yang di-monitor_"
            
            # Add action buttons
            keyboard = []
            if self.active_positions:
                keyboard.append([
                    InlineKeyboardButton("💰 Close All", callback_data="s_close_all_confirm"),
                    InlineKeyboardButton("🔄 Refresh", callback_data="s_refresh_portfolio")
                ])
            else:
                keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="s_refresh_portfolio")])
            
            keyboard.append([
                InlineKeyboardButton("📊 Lihat Posisi", callback_data="s_refresh_posisi"),
                InlineKeyboardButton("📈 Analisa Pair", callback_data="s_analisa_hint")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await msg.edit_text(portfolio_msg, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Portfolio error: {e}")
            await msg.edit_text(f"❌ Error loading portfolio: `{str(e)}`", parse_mode='Markdown')

    async def cmd_close_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Close all active scalper positions at market price"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        
        if not self.active_positions:
            await update.effective_message.reply_text("ℹ️ Tidak ada posisi aktif untuk ditutup")
            return
        
        # Send confirmation request
        keyboard = [
            [InlineKeyboardButton("⚠️ YES, Close ALL Positions", callback_data="s_confirm_close_all")],
            [InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")]
        ]
        
        await update.effective_message.reply_text(
            f"⚠️ **CONFIRMATION**\n\n"
            f"Tutup SEMUA posisi aktif?\n\n"
            f"Jumlah posisi: {len(self.active_positions)}\n\n"
            f"⚠️ Tindakan ini tidak bisa dibatalkan!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def cmd_refresh_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Refresh portfolio view with live prices"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        
        # Reuse the callback handler logic
        await self.refresh_portfolio_callback(update, context)

    async def cmd_riwayat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lihat SEMUA pair yang PERNAH di-trade beserta harga dan P/L"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        
        msg = await update.effective_message.reply_text(
            "📜 **Loading riwayat trading...**\n\n⏳ Mengambil data dari Indodax...",
            parse_mode='Markdown'
        )
        
        # Check if real trading mode
        if not self.is_real_trading or not self.indodax:
            await msg.edit_text(
                "ℹ️ **DRY RUN MODE**\n\n"
                "Riwayat trading hanya tersedia di mode REAL TRADING.\n\n"
                "Di mode dry run, data trading bersifat simulasi dan tidak tersimpan permanen."
            )
            return
        
        try:
            # 1. Get trade history from Indodax (all pairs)
            trade_history = self.indodax.get_trade_history(limit=500)
            
            if not trade_history:
                await msg.edit_text(
                    "📜 **TIDAK ADA RIWAYAT TRADING**\n\n"
                    "Belum ada riwayat trading di akun Indodax Anda.\n\n"
                    "Riwayat akan muncul setelah Anda melakukan trading."
                )
                return
            
            # 2. Parse trade history dan group by pair
            pair_stats = {}
            total_fee = 0
            
            for trade in trade_history:
                pair = trade.get('pair', '').lower()
                if not pair:
                    continue
                
                # Normalize pair
                if not pair.endswith('idr'):
                    pair += 'idr'
                
                # Extract trade data
                trade_type = trade.get('type', 'buy').lower()  # buy or sell
                price = float(trade.get('price', 0))
                amount = float(trade.get('amount', 0))
                total = float(trade.get('total', 0))
                fee = float(trade.get('fee', 0))
                trade_time = trade.get('timestamp', trade.get('trade_date', 0))
                
                total_fee += fee
                
                # Initialize pair stats if new
                if pair not in pair_stats:
                    pair_stats[pair] = {
                        'buy_count': 0,
                        'sell_count': 0,
                        'total_buy': 0,
                        'total_sell': 0,
                        'total_amount_bought': 0,
                        'total_amount_sold': 0,
                        'total_fee': 0,
                        'last_price': price,
                        'last_trade_time': trade_time,
                        'first_trade_time': trade_time
                    }
                
                stats = pair_stats[pair]
                
                # Update stats based on trade type
                if trade_type == 'buy':
                    stats['buy_count'] += 1
                    stats['total_buy'] += total
                    stats['total_amount_bought'] += amount
                elif trade_type == 'sell':
                    stats['sell_count'] += 1
                    stats['total_sell'] += total
                    stats['total_amount_sold'] += amount
                
                stats['total_fee'] += fee
                stats['last_price'] = price
                stats['last_trade_time'] = max(stats['last_trade_time'], trade_time)
                stats['first_trade_time'] = min(stats['first_trade_time'], trade_time)
            
            # 3. Get current prices for all pairs
            current_prices = {}
            for pair in pair_stats.keys():
                try:
                    price = self._get_price_sync(pair)
                    current_prices[pair] = price
                except Exception as e:
                    logger.error(f"Error fetching price for {pair}: {e}")
                    current_prices[pair] = None
            
            # 4. Calculate P/L for each pair
            pair_summaries = []
            total_invested = 0
            total_current_value = 0
            total_realized_pnl = 0
            
            for pair, stats in pair_stats.items():
                current_price = current_prices.get(pair)
                
                # Calculate average buy/sell prices
                avg_buy_price = stats['total_buy'] / stats['total_amount_bought'] if stats['total_amount_bought'] > 0 else 0
                avg_sell_price = stats['total_sell'] / stats['total_amount_sold'] if stats['total_amount_sold'] > 0 else 0
                
                # Realized P/L (from completed trades)
                realized_pnl = stats['total_sell'] - stats['total_buy']
                realized_pnl_pct = ((realized_pnl / stats['total_buy']) * 100) if stats['total_buy'] > 0 else 0
                
                # Current holding (amount bought - amount sold)
                current_holding = stats['total_amount_bought'] - stats['total_amount_sold']
                current_value = current_holding * current_price if current_price else 0
                holding_pnl = (current_price - avg_buy_price) * current_holding if current_price and avg_buy_price > 0 else 0
                holding_pnl_pct = ((holding_pnl / (avg_buy_price * current_holding)) * 100) if avg_buy_price > 0 and current_holding > 0 else 0
                
                total_invested += stats['total_buy']
                total_current_value += current_value
                total_realized_pnl += realized_pnl
                
                # Determine status
                if current_holding > 0.01:
                    status = f"📦 HOLDING: {current_holding:,.2f}"
                    pnl_text = f"Unrealized: {holding_pnl:+,.0f} ({holding_pnl_pct:+.2f}%)"
                elif current_holding <= 0.01:
                    status = "✅ CLOSED"
                    pnl_text = f"Realized: {realized_pnl:+,.0f} ({realized_pnl_pct:+.2f}%)"
                else:
                    status = "MIXED"
                    pnl_text = f"Net: {realized_pnl + holding_pnl:+,.0f}"
                
                # Icon based on P/L
                net_pnl = realized_pnl + holding_pnl
                icon = "🟢" if net_pnl >= 0 else "🔴"
                
                pair_summaries.append({
                    'pair': pair.upper(),
                    'stats': stats,
                    'current_price': current_price,
                    'avg_buy': avg_buy_price,
                    'avg_sell': avg_sell_price,
                    'holding': current_holding,
                    'realized_pnl': realized_pnl,
                    'realized_pnl_pct': realized_pnl_pct,
                    'holding_pnl': holding_pnl,
                    'holding_pnl_pct': holding_pnl_pct,
                    'status': status,
                    'pnl_text': pnl_text,
                    'icon': icon
                })
            
            # Sort by total trade value (most active first)
            pair_summaries.sort(key=lambda x: x['stats']['total_buy'] + x['stats']['total_sell'], reverse=True)
            
            # 5. Build message
            riwayat_msg = f"📜 **RIWAYAT TRADING SCALPER**\n\n"
            riwayat_msg += f"📊 **Total Pair Ditrade:** {len(pair_stats)}\n"
            riwayat_msg += f"💰 **Total Investasi:** {total_invested:,.0f} IDR\n"
            riwayat_msg += f"📈 **Realized P/L:** {total_realized_pnl:+,.0f} IDR\n"
            riwayat_msg += f"💵 **Total Fee:** {total_fee:,.0f} IDR\n"
            riwayat_msg += f"🕐 **Dari:** {datetime.fromtimestamp(min(s['first_trade_time'] for s in pair_stats.values())).strftime('%d/%m/%Y')}\n\n"
            
            # Pair summaries
            for i, summary in enumerate(pair_summaries[:20], 1):  # Limit to 20 pairs
                stats = summary['stats']
                current_price = summary['current_price']
                
                riwayat_msg += f"**{i}. {summary['pair']}**\n"
                riwayat_msg += f"   {summary['icon']} {summary['status']}\n"
                
                if summary['avg_buy'] > 0:
                    riwayat_msg += f"   Avg Buy: {summary['avg_buy']:,.0f}"
                    if summary['current_price']:
                        riwayat_msg += f" → Current: {current_price:,.0f}"
                    riwayat_msg += f"\n"
                
                if summary['avg_sell'] > 0:
                    riwayat_msg += f"   Avg Sell: {summary['avg_sell']:,.0f}\n"
                
                # P/L
                if summary['holding'] > 0.01:
                    # Has holding - show unrealized P/L
                    pnl_icon = "🟢" if summary['holding_pnl'] >= 0 else "🔴"
                    riwayat_msg += f"   {pnl_icon} P/L: {summary['holding_pnl']:+,.0f} ({summary['holding_pnl_pct']:+.2f}%)\n"
                else:
                    # Closed position - show realized P/L
                    pnl_icon = "🟢" if summary['realized_pnl'] >= 0 else "🔴"
                    riwayat_msg += f"   {pnl_icon} P/L: {summary['realized_pnl']:+,.0f} ({summary['realized_pnl_pct']:+.2f}%)\n"
                
                # Trade count
                riwayat_msg += f"   📊 {stats['buy_count']}x Buy | {stats['sell_count']}x Sell\n"
                
                # Last trade time
                if stats['last_trade_time'] > 0:
                    last_trade = datetime.fromtimestamp(stats['last_trade_time'])
                    riwayat_msg += f"   ⏰ Last: {last_trade.strftime('%d/%m %H:%M')}\n"
                
                riwayat_msg += "\n"
            
            if len(pair_stats) > 20:
                riwayat_msg += f"... dan {len(pair_stats) - 20} pair lainnya\n\n"
            
            # Add refresh button
            keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="s_refresh_riwayat")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await msg.edit_text(riwayat_msg, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Riwayat error: {e}")
            import traceback
            await msg.edit_text(
                f"❌ **ERROR LOADING RIWAYAT**\n\n"
                f"`{str(e)}`\n\n"
                f"Pastikan:\n"
                f"• API Key & Secret sudah benar\n"
                f"• Ada riwayat trading di Indodax\n"
                f"• Koneksi internet lancar",
                parse_mode='Markdown'
            )

    async def cmd_analisa(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Analisa pair dengan technical indicators seperti bot utama"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        
        if not context.args:
            await update.effective_message.reply_text(
                "📊 **Pair Analysis**\n"
                "Format: `/s_analisa <pair>`\n"
                "Contoh: `/s_analisa bridr`",
                parse_mode='Markdown'
            )
            return
        
        pair = context.args[0].lower().strip()
        if not pair.endswith('idr'):
            pair += 'idr'
        
        # Tampilkan pesan loading
        msg = await update.effective_message.reply_text(f"⏳ Menganalisa **{pair.upper()}**...", parse_mode='Markdown')
        
        try:
            # Fetch historical data dari Indodax
            df = await self._fetch_historical_data(pair)
            
            if df is None or df.empty:
                await msg.edit_text(f"❌ Gagal mengambil data historis untuk **{pair.upper()}**", parse_mode='Markdown')
                return
            
            if len(df) < 60:
                await msg.edit_text(
                    f"⚠️ Data tidak cukup untuk **{pair.upper()}**\n"
                    f"Diperlukan minimal 60 candle, tersedia: {len(df)}",
                    parse_mode='Markdown'
                )
                return
            
            # Calculate technical indicators
            analysis = self._calculate_technical_indicators(df)
            
            # Get current price
            current_price = self._get_price_sync(pair)
            if current_price is None:
                current_price = df['close'].iloc[-1]
            
            # Format message
            message = self._format_analysis_message(pair, current_price, analysis)
            
            await msg.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error analyzing {pair}: {e}")
            await msg.edit_text(
                f"❌ Error saat analisa **{pair.upper()}**:\n"
                f"`{str(e)}`",
                parse_mode='Markdown'
            )

    async def cmd_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sync posisi scalper dengan Indodax - IMPORTAN untuk live trading!"""
        if not self._is_admin(update.effective_user.id):
            await update.effective_message.reply_text("❌ Akses Ditolak")
            return
        
        msg = await update.effective_message.reply_text("🔄 **Syncing dengan Indodax...**\n\n⏳ Mengecek open orders...", parse_mode='Markdown')
        
        if not self.is_real_trading:
            await msg.edit_text(
                "ℹ️ **DRY RUN MODE**\n\n"
                "Tidak ada sync dengan Indodax di mode simulasi.\n"
                "Sync hanya tersedia saat `AUTO_TRADE_DRY_RUN=false`"
            )
            return
        
        try:
            # 1. Get open orders dari Indodax
            open_orders = self.indodax.get_open_orders()
            
            if not open_orders:
                await msg.edit_text(
                    "✅ **TIDAK ADA OPEN ORDER**\n\n"
                    "Tidak ada posisi terbuka di Indodax.\n"
                    "Bot scalper siap digunakan!"
                )
                return
            
            # 2. Parse open orders dan sync ke active_positions
            synced_positions = {}
            sync_details = []
            
            for order in open_orders:
                pair = order.get('pair', '').lower()
                if not pair:
                    continue
                
                # Normalize pair name
                if not pair.endswith('idr'):
                    pair += 'idr'
                
                order_type = order.get('type', 'buy').lower()
                price = float(order.get('price', 0))
                amount_remaining = float(order.get('amount_remain', 0))
                order_id = order.get('order', 0)
                
                # Hanya sync BUY orders (posisi yang masih terbuka)
                if order_type == 'buy' and amount_remaining > 0:
                    # Cek apakah sudah ada di active_positions
                    if pair in self.active_positions:
                        # Update existing position
                        pos = self.active_positions[pair]
                        pos['order_id'] = order_id
                        sync_details.append(f"🔄 **{pair.upper()}** - Updated order ID")
                    else:
                        # Add new position (hanya info, tanpa entry price pasti)
                        synced_positions[pair] = {
                            'entry': price,  # Asumsi filled di price ini
                            'amount': amount_remaining,
                            'capital': price * amount_remaining,
                            'time': int(time.time()),
                            'order_id': order_id,
                            'synced_from': 'indodax'
                        }
                        sync_details.append(f"✅ **{pair.upper()}** - Added from Indodax\nEntry: ~{price:,.0f}")
            
            # 3. Merge dengan existing positions
            self.active_positions.update(synced_positions)
            self._save_positions()
            
            # 4. Get balance dari Indodax
            try:
                balance_info = self.indodax.get_balance()
                if balance_info and 'balance' in balance_info:
                    idr_balance = float(balance_info['balance'].get('idr', 0))
                    self.balance = idr_balance
                    self._save_positions()
                    balance_info_text = f"\n💰 **Balance Indodax:** {idr_balance:,.0f} IDR"
                else:
                    balance_info_text = "\n⚠️ Gagal ambil balance"
            except Exception as e:
                logger.error(f"Failed to fetch balance from Indodax: {e}")
                balance_info_text = "\n⚠️ Gagal ambil balance"
            
            # 5. Send summary
            if synced_positions:
                details_text = '\n\n'.join(sync_details)
                summary = (
                    f"✅ **SYNC SELESAI!**\n\n"
                    f"📊 **Ditemukan {len(synced_positions)} posisi di Indodax:**\n\n"
                    f"{details_text}"
                    f"\n\n{balance_info_text}"
                    f"\n\n💡 **Tips:**\n"
                    f"• Gunakan `/s_posisi` untuk lihat detail\n"
                    f"• Gunakan `/s_sltp` untuk set TP/SL\n"
                    f"• Pair monitoring aktif: {len(self.pairs)}"
                )
            else:
                summary = (
                    f"ℹ️ **TIDAK ADA POSISI BARU**\n\n"
                    f"Open orders di Indodax: {len(open_orders)}\n"
                    f"(Mungkin SELL orders atau belum filled)"
                    f"\n\n{balance_info_text}"
                )
            
            await msg.edit_text(summary, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error syncing with Indodax: {e}")
            await msg.edit_text(
                f"❌ **ERROR SAAT SYNC**\n\n"
                f"`{str(e)}`\n\n"
                f"Pastikan:\n"
                f"• API Key & Secret sudah di-set\n"
                f"• Koneksi internet lancar",
                parse_mode='Markdown'
            )

    async def _fetch_historical_data(self, pair):
        """Fetch historical data dari Indodax"""
        try:
            # Ambil data trade history dari Indodax API
            url = f"https://indodax.com/api/trades/{pair}"
            response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            
            if response.status_code != 200:
                return None
            
            trades = response.json()
            if not trades:
                return None
            
            # Convert ke DataFrame
            df = pd.DataFrame(trades)
            df['timestamp'] = pd.to_datetime(df['date'], unit='s')
            df = df.rename(columns={'price': 'close', 'amount': 'volume'})
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            # Resample ke candle 1 menit (group by menit)
            df = df.set_index('timestamp')
            df = df.resample('1T').agg({
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            # Tambahkan high, low, open (gunakan close sebagai placeholder)
            df['high'] = df['close']
            df['low'] = df['close']
            df['open'] = df['close'].shift(1).fillna(df['close'])
            
            # Reorder columns
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {pair}: {e}")
            return None

    def _calculate_technical_indicators(self, df):
        """Hitung semua technical indicators"""
        analysis = {}
        
        # RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        analysis['rsi'] = rsi.iloc[-1]
        
        if rsi.iloc[-1] < 30:
            analysis['rsi_signal'] = 'OVERSOLD'
        elif rsi.iloc[-1] > 70:
            analysis['rsi_signal'] = 'OVERBOUGHT'
        else:
            analysis['rsi_signal'] = 'NEUTRAL'
        
        # MACD
        ema_fast = df['close'].ewm(span=12, adjust=False).mean()
        ema_slow = df['close'].ewm(span=26, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        analysis['macd'] = macd.iloc[-1]
        analysis['macd_signal'] = macd_signal.iloc[-1]
        analysis['macd_hist'] = macd_hist.iloc[-1]
        
        if macd.iloc[-1] > macd_signal.iloc[-1]:
            analysis['macd_trend'] = 'BULLISH'
        else:
            analysis['macd_trend'] = 'BEARISH'
        
        # Moving Averages
        sma_20 = df['close'].rolling(window=20).mean()
        sma_50 = df['close'].rolling(window=50).mean()
        
        if df['close'].iloc[-1] > sma_20.iloc[-1] and df['close'].iloc[-1] > sma_50.iloc[-1]:
            analysis['ma_trend'] = 'BULLISH'
        elif df['close'].iloc[-1] < sma_20.iloc[-1] and df['close'].iloc[-1] < sma_50.iloc[-1]:
            analysis['ma_trend'] = 'BEARISH'
        else:
            analysis['ma_trend'] = 'NEUTRAL'
        
        # Bollinger Bands
        bb_middle = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        bb_upper = bb_middle + (bb_std * 2)
        bb_lower = bb_middle - (bb_std * 2)
        
        bb_position = (df['close'].iloc[-1] - bb_middle.iloc[-1]) / bb_std.iloc[-1]
        analysis['bb_position'] = bb_position
        
        if bb_position > 2:
            analysis['bb_signal'] = 'OVERBOUGHT'
        elif bb_position < -2:
            analysis['bb_signal'] = 'OVERSOLD'
        else:
            analysis['bb_signal'] = 'NEUTRAL'
        
        # Volume Analysis
        volume_sma = df['volume'].rolling(window=20).mean()
        volume_ratio = df['volume'].iloc[-1] / volume_sma.iloc[-1] if volume_sma.iloc[-1] > 0 else 1
        
        analysis['volume_ratio'] = volume_ratio
        
        if volume_ratio > 2:
            analysis['volume_signal'] = 'HIGH'
        elif volume_ratio < 0.5:
            analysis['volume_signal'] = 'LOW'
        else:
            analysis['volume_signal'] = 'NORMAL'
        
        # Simple ML-like prediction (mock)
        # Count bullish vs bearish signals
        bullish_count = 0
        bearish_count = 0
        
        if analysis['rsi_signal'] == 'OVERSOLD':
            bullish_count += 1
        elif analysis['rsi_signal'] == 'OVERBOUGHT':
            bearish_count += 1
        
        if analysis['macd_trend'] == 'BULLISH':
            bullish_count += 1
        else:
            bearish_count += 1
        
        if analysis['ma_trend'] == 'BULLISH':
            bullish_count += 1
        else:
            bearish_count += 1
        
        if analysis['bb_signal'] == 'OVERSOLD':
            bullish_count += 1
        elif analysis['bb_signal'] == 'OVERBOUGHT':
            bearish_count += 1
        
        total_signals = bullish_count + bearish_count
        if total_signals > 0:
            confidence = max(bullish_count, bearish_count) / total_signals
        else:
            confidence = 0.5
        
        # Combined strength: -1 to 1
        strength = (bullish_count - bearish_count) / max(total_signals, 1)
        
        analysis['ml_confidence'] = confidence
        analysis['ml_strength'] = strength
        
        # Generate recommendation
        if confidence < 0.6:
            analysis['recommendation'] = 'HOLD'
            analysis['reason'] = 'ML confidence too low'
        elif strength > 0.3:
            analysis['recommendation'] = 'BUY'
            analysis['reason'] = 'Strong bullish signals detected'
        elif strength < -0.3:
            analysis['recommendation'] = 'SELL'
            analysis['reason'] = 'Strong bearish signals detected'
        else:
            analysis['recommendation'] = 'HOLD'
            analysis['reason'] = 'Mixed signals, wait for clearer trend'
        
        return analysis

    def _format_analysis_message(self, pair, price, analysis):
        """Format analisa menjadi message yang readable"""
        # Emoji untuk recommendation
        rec_emoji = {
            'STRONG_BUY': '🚀',
            'BUY': '📈',
            'HOLD': '⏸️',
            'SELL': '📉',
            'STRONG_SELL': '🔻'
        }.get(analysis['recommendation'], '❓')
        
        message = f"""
{rec_emoji} **{pair.upper()} - Trading Signal**

💰 **Price:** `{price:,.0f}` IDR

🎯 **Recommendation:** **{analysis['recommendation']}**

📈 **Technical Indicators:**
• RSI (14): {analysis['rsi_signal']} ({analysis['rsi']:.1f})
• MACD: {analysis['macd_trend']}
• MA Trend: {analysis['ma_trend']}
• Bollinger: {analysis['bb_signal']}
• Volume: {analysis['volume_signal']}

🤖 **ML Prediction:**
• Confidence: {analysis['ml_confidence']:.1%}
• Combined Strength: {analysis['ml_strength']:.2f}

💡 **Analysis:** {analysis['reason']}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return message

    async def refresh_prices_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Refresh menu dengan harga terbaru + posisi aktif"""
        query = update.callback_query
        if not query or not self._is_admin(query.from_user.id):
            return
        
        # Answer callback FIRST (before any heavy work)
        try:
            await query.answer("🔄 Refresh harga...")
        except Exception as e:
            logger.warning(f"Callback answer failed (non-critical): {e}")

        try:
            # Fetch live prices with timeout protection
            timestamp = datetime.now().strftime('%H:%M:%S')
            price_lines = []
            for p in self.pairs:
                try:
                    price = self._get_price_sync(p)
                    # Check if we have an active position
                    has_position = p in self.active_positions
                    pos_marker = " 📦" if has_position else ""
                    price_lines.append(f"**{p.upper()}:** `{price:,.0f}`{pos_marker}")
                except Exception as e:
                    logger.warning(f"Price fetch error for {p}: {e}")
                    price_lines.append(f"**{p.upper()}:** ❌ Error")

            # Build status message
            status_text = (
                f"🕐 **{timestamp}**\n"
                f"💰 **Saldo:** `{self.balance:,.0f}` IDR\n\n"
                f"📊 **Daftar Pair:**\n"
                + '\n'.join(f"• {line}" for line in price_lines)
            )

            # Add active positions summary (same as cmd_menu)
            if self.active_positions:
                status_text += f"\n\n📦 **Posisi Aktif ({len(self.active_positions)}):**"
                for pair, pos in self.active_positions.items():
                    try:
                        entry = pos.get('entry', 0)
                        # Get current price
                        try:
                            current = self._get_price_sync(pair)
                            pnl = ((current * (1-ScalperConfig.TRADING_FEE_PCT) - entry * (1+ScalperConfig.TRADING_FEE_PCT)) / (entry * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                            emoji = "🟢" if pnl >= 0 else "🔴"
                            status_text += f"\n{emoji} `{pair.upper()}`: Entry `{Utils.format_price(entry)}` → `{Utils.format_price(current)}` | P/L: `{pnl:+.1f}%`"
                        except Exception:
                            status_text += f"\n⏳ `{pair.upper()}`: Entry `{Utils.format_price(entry)}`"
                    except Exception:
                        status_text += f"\n⚠️ `{pair.upper()}`: Error"

            status_text += "\n\n🎯 **Klik tombol untuk trading:**"

            # Rebuild keyboard — use BOTH self.pairs AND active_positions
            all_pairs = list(set(list(self.pairs) + list(self.active_positions.keys())))

            keyboard = []
            for p in all_pairs:
                pn = p.upper()
                has_position = p in self.active_positions

                if has_position:
                    # Check if position is profitable
                    pos = self.active_positions[p]
                    entry = pos.get('entry', 0)
                    try:
                        current = self._get_price_sync(p)
                        is_profit = False
                        if current and entry > 0:
                            pnl_pct = ((current * (1 - ScalperConfig.TRADING_FEE_PCT) - entry * (1 + ScalperConfig.TRADING_FEE_PCT)) / (entry * (1 + ScalperConfig.TRADING_FEE_PCT))) * 100
                            is_profit = pnl_pct > 0
                    except Exception as e:
                        logger.error(f"Error checking profit for {p}: {e}")
                        is_profit = False

                    if is_profit:
                        sell_label = f"💰 SELL {pn} (PROFIT)"
                    else:
                        sell_label = f"⬆️ SELL {pn}"

                    keyboard.append([
                        InlineKeyboardButton(f"⬇️ BUY {pn}", callback_data=f"s_buy:{p}"),
                        InlineKeyboardButton(sell_label, callback_data=f"s_sell:{p}")
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton(f"⬇️ BUY {pn}", callback_data=f"s_buy:{p}"),
                        InlineKeyboardButton(f"⬆️ SELL {pn} (tidak ada posisi)", callback_data="s_sell_no_pos")
                    ])

            keyboard.append([
                InlineKeyboardButton("📦 Posisi", callback_data="s_refresh_posisi"),
                InlineKeyboardButton("➕ Tambah Pair", callback_data="s_add_pair_hint")
            ])
            keyboard.append([
                InlineKeyboardButton("🔄 Refresh Harga", callback_data="s_refresh_prices")
            ])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"refresh_prices_callback error: {e}")
            try:
                await query.edit_message_text(f"❌ Error refresh harga:\n`{str(e)}`\n\nCoba lagi dalam beberapa detik.", parse_mode='Markdown')
            except Exception as e2:
                logger.error(f"Failed to show error message: {e2}")

    async def refresh_posisi_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self._is_admin(query.from_user.id):
            return
        await query.answer("🔄 Refreshing...")

        # Phase 2: Pre-fetch ALL position prices in parallel, cache to Redis
        price_cache_map = {}
        if self.active_positions:
            from cache.redis_price_cache import price_cache as redis_cache
            try:
                pairs_to_fetch = []
                for pair in self.active_positions.keys():
                    cached = redis_cache.get_price_sync(pair)
                    if cached is not None and cached > 0:
                        price_cache_map[pair] = cached
                    else:
                        pairs_to_fetch.append(pair)

                if pairs_to_fetch:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(pairs_to_fetch))) as executor:
                        future_to_pair = {
                            executor.submit(self._get_price_from_api_only, p): p
                            for p in pairs_to_fetch
                        }
                        for future in concurrent.futures.as_completed(future_to_pair, timeout=30):
                            pair = future_to_pair[future]
                            try:
                                price = future.result()
                                price_cache_map[pair] = price
                                redis_cache.set_price(pair, price)
                            except Exception as e:
                                logger.debug(f"Failed to fetch {pair}: {e}")
            except Exception as e:
                logger.debug(f"Batch price fetch error: {e}")

        # Build header message
        msg = f"📦 **POSISI AKTIF** [{datetime.now().strftime('%H:%M:%S')}]\n\n💰 Saldo: {self.balance:,.0f}\n📈 P/L: {self.balance - ScalperConfig.INITIAL_BALANCE:+,.0f}\n📊 Open: {len(self.active_positions)}"

        keyboard = []
        if self.active_positions:
            for pair, pos in dict(self.active_positions).items():
                try:
                    price = price_cache_map.get(pair)
                    if price is None:
                        price = self._get_price_sync(pair)

                    pnl = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                    profit = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
                    is_profit = pnl >= 0
                    entry_str = Utils.format_price(pos['entry'])
                    current_str = Utils.format_price(price)
                    pnl_str = f"{pnl:+.2f}% ({profit:+,.0f})"
                    emoji = "🟢" if is_profit else "🔴"
                    
                    # Get TP/SL values
                    tp_val = pos.get('tp')
                    sl_val = pos.get('sl')
                    tp_str = f"TP:{Utils.format_price(tp_val)}" if tp_val else "TP:-"
                    sl_str = f"SL:{Utils.format_price(sl_val)}" if sl_val else "SL:-"
                    
                    btn_label = f"{emoji} {pair.upper()} | {pnl_str} | {tp_str} / {sl_str}"
                    keyboard.append([
                        InlineKeyboardButton(btn_label, callback_data=f"s_info:{pair}")
                    ])
                except Exception as e:
                    logger.error(f"Error building position button for {pair}: {e}")
                    keyboard.append([
                        InlineKeyboardButton(f"⚠️ {pair.upper()} | Error", callback_data=f"s_info:{pair}")
                    ])

        keyboard.append([
            InlineKeyboardButton("🔄 Refresh", callback_data="s_refresh_posisi"),
            InlineKeyboardButton("📊 Menu", callback_data="s_menu")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)

        if not self.active_positions:
            msg += "\n\n_Tidak ada posisi_"

        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def refresh_portfolio_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self._is_admin(query.from_user.id):
            return
        await query.answer("🔄 Refreshing portfolio...")
        # Call cmd_portfolio logic
        await self.cmd_portfolio(update, context)

    async def refresh_riwayat_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self._is_admin(query.from_user.id):
            return
        await query.answer("🔄 Refreshing riwayat...")
        # Call cmd_riwayat logic
        await self.cmd_riwayat(update, context)

    async def info_posisi_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self._is_admin(query.from_user.id):
            return
        if ":" in query.data:
            _, pair = query.data.split(':', 1)
            if pair in self.active_positions:
                pos = self.active_positions[pair]
                try:
                    price = self._get_price_sync(pair)
                    pnl = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
                    profit = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
                    ind = "🟢" if pnl >= 0 else "🔴"
                    tp = f"\n🎯 TP: {pos.get('tp', 0):,.0f}" if 'tp' in pos else ""
                    sl = f"\n🛑 SL: {pos.get('sl', 0):,.0f}" if 'sl' in pos else ""
                    info = f"📊 **{pair.upper()}**\n\n{ind} {'PROFIT' if pnl >= 0 else 'LOSS'}\nEntry: {pos['entry']:,.0f}\nCurrent: {price:,.0f}\nP/L: {pnl:+.2f}% ({profit:+,.0f}){tp}{sl}\nHold: {int(time.time() - pos['time'])}s"
                    await query.answer(f"{pair.upper()}: {pnl:+.2f}%")
                    await query.edit_message_text(info, parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"Error showing position info for {pair}: {e}")
                    await query.answer("Error fetching price")
            else:
                await query.edit_message_text("⚠️ Posisi tidak ditemukan.")

    async def ignore_alert_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer("✅ Alert diabaikan")
