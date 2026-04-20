#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Advanced Crypto Trading Bot
🔗 Indodax WebSocket + Telegram + Machine Learning
📊 Real-time signals, auto-trading, risk management
"""

import asyncio
import os
import threading
import time
import subprocess
import requests
from datetime import datetime, timedelta
from typing import Dict, List

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Data & ML
import pandas as pd

# Local modules - Core
from core.config import Config
from core.database import Database
from core.logger import CustomLogger
from core.utils import Utils
from core.signal_enhancement_engine import SignalEnhancementEngine
from core.signal_enhancement_config import SignalEnhancementConfig

# Local modules - API
from api.indodax_api import IndodaxAPI

# Local modules - Analysis
from analysis.technical_analysis import TechnicalAnalysis
from analysis.ml_model import MLTradingModel
from analysis.ml_model_v2 import MLTradingModelV2  # NEW: Improved ML model V2
from analysis.ml_model_v3 import MLTradingModelV3, create_model as create_ml_v3  # PRO: ML model V3 with backtesting
from analysis.signal_analyzer import SignalAnalyzer  # NEW: Signal Quality Analyzer
from analysis.support_resistance import SupportResistanceDetector  # NEW: S/R Level Detection
from analysis.analyze_signals import AnalyzeSignals  # NEW: Quick BUY/SELL analysis

# Local modules - Trading
from autotrade.trading_engine import TradingEngine
from autotrade.risk_manager import RiskManager
from autotrade.portfolio import Portfolio
from autotrade.price_monitor import PriceMonitor
from scalper.scalper_module import ScalperModule  # Scalper integration
from autohunter.smart_hunter_integration import SmartHunterBotIntegration  # Smart Hunter integration

# Local modules - Signals
from signals.signal_quality_engine import SignalQualityEngine  # NEW: Signal Quality Engine V3
from signals.signal_queue import signal_queue, scheduler  # Phase 4: Signal Queue + Scheduler

# Local modules - Cache
from cache.redis_price_cache import price_cache as redis_price_cache  # NEW: Redis-backed price cache

# Local modules - Workers
from workers.async_worker import BackgroundWorker  # Phase 3: Async workers
from workers.price_poller import PricePoller

from concurrent.futures import ThreadPoolExecutor

# Setup logging
logger = CustomLogger('crypto_bot').get_logger()


# =============================================================================
# MAIN BOT CLASS
# =============================================================================

from cache.redis_state_manager import state_manager

class AdvancedCryptoBot:
    """
    Advanced Crypto Trading Bot with:
    • Real-time WebSocket (Indodax)
    • Machine Learning predictions
    • Technical Analysis (15+ indicators)
    • Automated trading signals
    • Risk management & portfolio tracking
    • Telegram interface
    """

    def __init__(self):
        logger.info("🚀 Initializing Advanced Crypto Trading Bot...")

        # Initialize components
        self.db = Database()

        # FIX: Use ML Model V2 (improved) with fallback to V1
        try:
            self.ml_model = MLTradingModelV2()
            self.ml_version = 'V2'
            logger.info("✅ Using ML Model V2 (improved with multi-class target)")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load V2, falling back to V1: {e}")
            self.ml_model = MLTradingModel()
            self.ml_version = 'V1'
        
        # NEW: ML Model V3 (Pro version with backtesting)
        self.ml_model_v3 = None
        try:
            self.ml_model_v3 = create_ml_v3()
            logger.info("✅ ML Model V3 initialized (with backtesting & Kelly Criterion)")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load ML V3: {e}")

        self.trading_engine = TradingEngine(self.db, self.ml_model)
        self.risk_manager = RiskManager(self.db)
        self.portfolio = Portfolio(self.db)
        self.price_monitor = PriceMonitor(self.db)  # Initialize price monitor
        self.indodax = IndodaxAPI()  # Initialize Indodax API
        self.price_poller = PricePoller(self)  # Initialize REST API poller

        # NEW: Signal Quality Analyzer
        self.signal_analyzer = SignalAnalyzer()
        logger.info("✅ Signal Quality Analyzer initialized")

        # NEW: Signal Quality Engine V3 (confluence scoring, cooldown, volume confirmation)
        self.signal_quality_engine = SignalQualityEngine()
        logger.info("✅ Signal Quality Engine V3 initialized")

        # NEW: Support & Resistance Detector (auto-detect S/R levels)
        # Uses imported SupportResistanceDetector from support_resistance.py (line 55)
        self.sr_detector = SupportResistanceDetector()
        logger.info("✅ Support & Resistance Detector initialized")

        # NEW: Signal Enhancement Engine (Volume, VWAP, Ichimoku, Divergence, Candlestick)
        self.signal_enhancement = SignalEnhancementEngine()
        logger.info(f"✅ Signal Enhancement Engine initialized: {self.signal_enhancement.config}")

        # NEW: Redis State Manager
        self.state_manager = state_manager
        logger.info("✅ Redis State Manager initialized")

        # Separate executor for heavy DB operations (avoid conflict with Telegram's event loop)
        self._heavy_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="HeavyDB")
        logger.info("✅ Heavy DB executor initialized")

        # Telegram setup with increased timeouts for unreliable networks
        self.app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN) \
            .connect_timeout(30.0) \
            .read_timeout(30.0) \
            .write_timeout(30.0) \
            .pool_timeout(30.0) \
            .get_updates_connect_timeout(30.0) \
            .get_updates_read_timeout(30.0) \
            .get_updates_write_timeout(30.0) \
            .get_updates_pool_timeout(30.0) \
            .build()

        # Initialize Scalper Module (use main bot's dry-run config + token + admin IDs)
        self.scalper = ScalperModule(
            self.app,
            admin_ids=Config.ADMIN_IDS,  # Pass admin IDs from main config
            is_standalone=False,
            use_main_bot_config=True,
            main_bot_config=Config,
            main_bot_token=Config.TELEGRAM_BOT_TOKEN,  # Pass main bot's token
            main_bot=self  # Pass main bot reference for signal generation
        )

        # Initialize Smart Hunter Integration
        self.smart_hunter = SmartHunterBotIntegration(
            main_bot=self,
            db=self.db,
            indodax_api=self.indodax
        )

        self._setup_handlers()

        # WebSocket setup
        self.ws_handler = None
        
        # NEW: price_data dan historical_data tetap di-memory (karena sering diakses)
        # tapi akan di-sync ke Redis secara periodic untuk persistence
        self.price_data: Dict[str, Dict] = {}
        self.historical_data: Dict[str, pd.DataFrame] = {}
        logger.info("✅ Price & Historical data caches initialized (in-memory + Redis sync)")
        
        # FIX: Load watchlist from database (persistent storage)
        # Memory cache for fast access, synced with database
        self.subscribers: Dict[int, List[str]] = self._load_watchlist_from_db()
        
        self.ws_connected = False

        # Trading state
        self.is_trading = False
        self.start_time = time.time()
        self.last_ml_update: Dict[str, datetime] = {}
        self.last_price_update: Dict[str, datetime] = {}

        # Background task tracking (for async tasks)
        self.background_tasks = set()

        # Trailing stop tracking: {trade_id: {'highest_price': float, 'trailing_stop': float}}
        self.trailing_stops: Dict[int, Dict] = {}
        
        # Auto-trade check interval (minutes) - configurable via /set_interval
        self.auto_trade_interval_minutes = 5

        # Auto-trade pairs list (SEPARATE from watchlist/scalper)
        # Only pairs in this list will be auto-traded
        # Watchlist (/watch) is for monitoring + scalping
        # Auto-trade pairs is for automated trading
        self.auto_trade_pairs: Dict[int, List[str]] = {}  # {user_id: [pair1, pair2, ...]}

        # Reinforcement Learning: Q-table {state: {action: value}}
        self.rl_q_table: Dict[str, Dict[str, float]] = {}
        self.rl_actions = ['BUY', 'SELL', 'HOLD']
        
        # Spoofing detection: {pair: {price: {'vol': float, 'seen': int}}}
        self.spoof_tracker: Dict[str, Dict] = {}
        
        # Heatmap liquidity: {pair: [{'time': float, 'bids': [], 'asks': []}]}
        self.heatmap_data: Dict[str, list] = {}

        # Signal stabilization: {pair: {'recommendation': str, 'timestamp': datetime}}
        self.previous_signals: Dict[str, Dict] = {}

        # Load auto-trade mode from database (persistent setting)
        self._load_auto_trade_mode()

        # Phase 3: Initialize async worker
        self.async_worker = BackgroundWorker(bot_instance=self)

        # Phase 4: Initialize signal queue + scheduler
        self.signal_queue = signal_queue
        self.task_scheduler = scheduler

        # Initialize WebSocket
        self._init_websocket()

        # FIX: Preload historical data from DB (so signals work immediately after restart)
        self._preload_historical_data()

        logger.info(f"✅ Bot initialized successfully! Watchlist loaded from DB: {sum(len(p) for p in self.subscribers.values())} pairs across {len(self.subscribers)} users")

        # Initialize signal DB connection early and show status
        try:
            from signals.signal_db import SignalDatabase
            self._signal_db = SignalDatabase("data/signals.db")
            total_signals = self._signal_db.get_total_count()
            logger.info(f"📊 Signal DB ready: {total_signals} signals in database")
        except Exception as e:
            logger.warning(f"⚠️ Signal DB init failed: {e} - Signals will NOT be saved")
            self._signal_db = None

    def _load_watchlist_from_db(self) -> Dict[int, List[str]]:
        """Load watchlist from database on startup"""
        try:
            watchlists = self.db.get_all_watchlists()
            if watchlists:
                total_pairs = sum(len(pairs) for pairs in watchlists.values())
                logger.info(f"📋 Loaded watchlist from DB: {total_pairs} pairs across {len(watchlists)} users")
            else:
                logger.info("📋 No watchlist in DB (fresh start or all cleared)")
            return watchlists
        except Exception as e:
            logger.error(f"❌ Failed to load watchlist from DB: {e}")
            return {}

    def _preload_historical_data(self):
        """
        FIX: Load historical data from DB into memory at startup
        So signals work immediately without waiting for poller to accumulate 60+ candles
        """
        import threading

        def _preload():
            all_pairs = set()
            for user_pairs in self.subscribers.values():
                all_pairs.update(user_pairs)

            if not all_pairs:
                logger.info("📚 No pairs to preload")
                return

            logger.info(f"📚 Preloading historical data for {len(all_pairs)} pairs...")
            loaded_count = 0

            for pair in all_pairs:
                try:
                    # Load 200 candles from DB (enough for 60+ requirement)
                    df = self.db.get_price_history(pair, limit=200)
                    if not df.empty and len(df) >= 60:
                        self.historical_data[pair] = df
                        loaded_count += 1
                        logger.debug(f"  ✅ {pair}: {len(df)} candles loaded")
                    elif not df.empty:
                        self.historical_data[pair] = df
                        logger.debug(f"  ⚠️  {pair}: {len(df)} candles (need 60+, accumulating...)")
                    else:
                        logger.debug(f"  ❌ {pair}: No data in DB yet")
                except Exception as e:
                    logger.error(f"  ❌ {pair}: Error loading data: {e}")

            logger.info(f"📚 Preload complete: {loaded_count}/{len(all_pairs)} pairs ready (60+ candles)")

        # Run in background thread to not block bot startup
        preload_thread = threading.Thread(target=_preload, daemon=True, name="Preload-History")
        preload_thread.start()

    def _sync_watchlist_to_db(self, user_id: int, pair: str):
        """Sync single pair addition to database"""
        try:
            self.db.add_to_watchlist(user_id, pair)
        except Exception as e:
            logger.error(f"❌ Failed to sync watchlist to DB: {e}")

    def _remove_watchlist_from_db(self, user_id: int, pair: str):
        """Sync single pair removal from database"""
        try:
            self.db.remove_from_watchlist(user_id, pair)
        except Exception as e:
            logger.error(f"❌ Failed to remove watchlist from DB: {e}")

    def _clear_watchlist_in_db(self, user_id: int = None):
        """Clear watchlist in database (for specific user or all)"""
        try:
            if user_id:
                self.db.clear_watchlist(user_id)
            else:
                self.db.clear_all_watchlists()
        except Exception as e:
            logger.error(f"❌ Failed to clear watchlist in DB: {e}")
    
    def run(self):
        """Start the bot with graceful shutdown handling"""
        logger.info("🚀 Starting Advanced Crypto Trading Bot...")

        # Global flag for clean shutdown
        self.shutdown_event = threading.Event()
        
        # Track background threads for cleanup
        self.background_threads = []

        # Start REST API price poller in background thread
        def start_poller():
            import logging
            thread_logger = logging.getLogger('crypto_bot')

            try:
                import asyncio
                thread_logger.info("🔄 Creating asyncio event loop for poller...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                thread_logger.info("🔄 Starting poller with asyncio...")

                # Start the poller (creates the polling task)
                loop.run_until_complete(self.price_poller.start_polling())
                thread_logger.info("✅ Poller task created, starting event loop...")

                # Schedule a periodic check for shutdown signal
                async def check_shutdown():
                    while not self.shutdown_event.is_set():
                        await asyncio.sleep(1)
                    loop.stop()  # This will stop run_forever()

                # Start shutdown checker task
                asyncio.ensure_future(check_shutdown())

                # Keep the event loop RUNNING to process the polling task
                loop.run_forever()

                # Clean shutdown
                thread_logger.info("🛑 Stopping poller gracefully...")
                loop.run_until_complete(self.price_poller.stop_polling())
                loop.close()
                thread_logger.info("✅ Poller stopped successfully")
            except Exception as e:
                thread_logger.error(f"❌ FAILED to start price poller thread: {e}")
                import traceback
                thread_logger.error(f"Poller traceback: {traceback.format_exc()}")
                raise

        poller_thread = threading.Thread(target=start_poller, daemon=True)
        poller_thread.start()
        self.background_threads.append(poller_thread)
        logger.info("✅ Price poller thread started")

        # DISABLED: Background cache refresh (causes asyncio Semaphore event loop conflict)
        # The price poller already updates price_cache every 15s, so separate refresh is redundant
        # Having two event loops fighting over the same Semaphore causes errors
        logger.info("⚠️ Background cache refresh DISABLED (poller handles all caching)")

        # WebSocket DISABLED (Indodax public channels not working)
        # if self.ws_handler:
        #     self.ws_handler.connect()
        #     logger.info("📡 WebSocket thread started (optional)")
        logger.info("⚠️ WebSocket disabled (using REST API polling only)")

        # Pass bot app to price monitor for notifications
        if self.price_monitor:
            self.price_monitor.bot_app = self.app
            self.price_monitor.subscribers = self.subscribers

        # Initial ML training if needed - NOW IN BACKGROUND
        if self.ml_model.should_retrain():
            logger.info(f"🤖 ML model needs retrain (using {self.ml_version})...")
            # FIX: Run retrain in background thread (non-blocking)
            self._retrain_ml_model(background=True)
            logger.info("🔄 ML retrain started in background thread - bot continues startup")

        # Start auto ML retrain timer (runs every 24h when in real trading mode)
        self._start_auto_retrain_timer()

        # Phase 4: Setup scheduler tasks
        self._setup_scheduler_tasks()

        # Phase 3: Start async worker
        self.async_worker.start()
        logger.info("🔧 Async worker started (Phase 3)")

        # Start health monitor (auto-restart on crash)
        self._start_health_monitor()
        
        # NEW: Start Redis state syncer (background thread)
        self._start_redis_state_syncer()

        # Start Telegram bot polling with graceful shutdown
        logger.info("📱 Starting Telegram bot polling...")
        logger.info("💡 Press Ctrl+C to stop bot (graceful shutdown with 10s timeout)")
        
        try:
            self.app.run_polling(allowed_updates=Update.ALL_TYPES)
        except KeyboardInterrupt:
            logger.info("\n🛑 Ctrl+C detected - Starting graceful shutdown...")
            self._shutdown()
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._shutdown()
    
    def _shutdown(self, timeout=10):
        """
        Graceful shutdown with timeout
        Stops all background threads and saves state
        """
        import time
        
        logger.info(f"🛑 Shutting down bot (timeout: {timeout}s)...")
        
        # Step 1: Set shutdown event
        self.shutdown_event.set()
        logger.info("📴 Shutdown event set")
        
        # Step 2: Stop scheduler
        try:
            if hasattr(self, 'task_scheduler'):
                self.task_scheduler.stop()
                logger.info("📅 Scheduler stopped")
        except Exception as e:
            logger.warning(f"⚠️ Error stopping scheduler: {e}")
        
        # Step 3: Stop async worker
        try:
            if hasattr(self, 'async_worker'):
                self.async_worker.stop()
                logger.info("🔧 Async worker stopped")
        except Exception as e:
            logger.warning(f"⚠️ Error stopping async worker: {e}")
        
        # Step 4: Wait for background threads (with timeout)
        start_time = time.time()
        for thread in self.background_threads:
            if thread.is_alive():
                thread_name = thread.name or "unnamed"
                logger.info(f"⏳ Waiting for thread '{thread_name}'...")
                thread.join(timeout=3)  # 3 seconds per thread
                if thread.is_alive():
                    logger.warning(f"⚠️ Thread '{thread_name}' didn't stop in time, skipping")
        
        elapsed = time.time() - start_time
        logger.info(f"⏱️ Thread cleanup took {elapsed:.1f}s")
        
        # Step 5: Save final state
        try:
            if hasattr(self, 'db'):
                logger.info("💾 Database connection will be closed automatically")
        except Exception as e:
            logger.warning(f"⚠️ Error during final save: {e}")
        
        # Step 6: Final message
        total_elapsed = time.time() - start_time
        logger.info(f"✅ Bot shutdown complete ({total_elapsed:.1f}s)")
        logger.info("👋 Goodbye!")

        # Force exit (in case something is still hanging)
        import sys
        sys.exit(0)

    def _start_redis_state_syncer(self):
        """Start background thread to sync state to Redis periodically"""
        def redis_sync_loop():
            import time
            import logging
            thread_logger = logging.getLogger('crypto_bot')
            
            sync_interval = 60  # Sync every 60 seconds
            
            while True:
                time.sleep(sync_interval)
                
                # Check if shutdown event is set
                if hasattr(self, 'shutdown_event') and self.shutdown_event.is_set():
                    thread_logger.info("🛑 Redis syncer stopping...")
                    break
                
                try:
                    # Sync price_data to Redis
                    if self.price_data:
                        for pair, data in list(self.price_data.items()):
                            try:
                                self.state_manager.set_price_data(pair, data)
                            except Exception as e:
                                thread_logger.debug(f"⚠️ Failed to sync price_data for {pair}: {e}")
                    
                    # Sync historical_data metadata to Redis (not full DataFrame, too large)
                    # We only sync metadata, not the actual candle data
                    for pair in list(self.historical_data.keys()):
                        try:
                            df = self.historical_data[pair]
                            if not df.empty:
                                # Sync only metadata
                                meta = {
                                    'rows': len(df),
                                    'columns': list(df.columns),
                                    'first_timestamp': str(df.index[0]) if hasattr(df.index[0], '__str__') else str(df.index[0]),
                                    'last_timestamp': str(df.index[-1]) if hasattr(df.index[-1], '__str__') else str(df.index[-1]),
                                }
                                self.state_manager.set_historical(pair, meta)
                        except Exception as e:
                            thread_logger.debug(f"⚠️ Failed to sync historical metadata for {pair}: {e}")
                    
                    thread_logger.debug("✅ Redis state sync completed")
                except Exception as e:
                    thread_logger.error(f"❌ Redis sync failed: {e}")
        
        sync_thread = threading.Thread(target=redis_sync_loop, daemon=True, name="RedisStateSync")
        sync_thread.start()
        logger.info("✅ Redis state syncer started (60s interval)")

    def _start_health_monitor(self):
        """Start health monitor that auto-restarts bot on crash"""
        import psutil

        def health_monitor_loop():
            import time
            import logging
            thread_logger = logging.getLogger('crypto_bot')

            max_restarts = 5  # Max restarts before giving up
            restart_window = 3600  # 1 hour window
            restart_times = []

            while True:
                time.sleep(60)  # Check every minute

                # Clean old restart times
                now = time.time()
                restart_times = [t for t in restart_times if now - t < restart_window]

                # Check memory usage
                try:
                    process = psutil.Process()
                    mem_mb = process.memory_info().rss / 1024 / 1024

                    # Log memory every 5 minutes
                    if int(now) % 300 < 60:
                        thread_logger.info(f"💾 Memory usage: {mem_mb:.0f}MB")

                    # Auto-restart if memory > 2GB (VPS safety)
                    if mem_mb > 2048:
                        thread_logger.warning(f"🚨 Memory critical: {mem_mb:.0f}MB — triggering restart")
                        restart_times.append(now)
                        if len(restart_times) > max_restarts:
                            thread_logger.error("💀 Too many restarts, shutting down")
                            break
                        # Graceful restart via sys.exit (systemd/docker will restart)
                        thread_logger.info("🔄 Requesting graceful restart...")
                        self._shutdown(timeout=5)
                        import sys
                        sys.exit(3)  # Exit code 3 = restart requested

                except Exception as e:
                    thread_logger.error(f"❌ Health check error: {e}")

        health_thread = threading.Thread(target=health_monitor_loop, daemon=True)
        health_thread.start()
        logger.info("🏥 Health monitor started (memory watch + auto-restart)")

    def _setup_scheduler_tasks(self):
        """Register periodic tasks with the scheduler"""
        from signals.signal_queue import scheduler

        # Task 1: Market scanner (every 15 minutes - reduced from 5 min to avoid duplicates)
        scheduler.add_task(
            name="market_scan",
            interval_seconds=900,  # 15 minutes (was 5 min)
            func=self._scheduled_market_scan,
            description="Scan watched pairs for strong signals"
        )

        # Task 2: Database cleanup (every 6 hours)
        scheduler.add_task(
            name="db_cleanup",
            interval_seconds=21600,  # 6 hours
            func=self._scheduled_db_cleanup,
            description="Cleanup old price data (>30 days)"
        )

        # Task 3: Signal stats update (every 1 hour)
        scheduler.add_task(
            name="signal_stats",
            interval_seconds=3600,  # 1 hour
            func=self._scheduled_signal_stats,
            description="Update signal queue statistics"
        )

        # Task 4: Redis cache health check (every 30 minutes)
        scheduler.add_task(
            name="cache_health",
            interval_seconds=1800,  # 30 minutes
            func=self._scheduled_cache_health_check,
            description="Check Redis + cache health"
        )

        # Start scheduler
        scheduler.start()
        logger.info(f"📅 Scheduler started ({len(scheduler.tasks)} tasks)")

    # =============================================================================
    # SCHEDULED TASKS (Phase 4)
    # =============================================================================

    def _scheduled_market_scan(self):
        """Scan watched pairs for strong signals every 5 minutes"""
        # Always run market scan for signals (separate from auto-execution)
        # Auto-execution is controlled by Config.AUTO_TRADING_ENABLED elsewhere
        
        try:
            logger.info("🔍 Running market scan...")
            from signals.signal_queue import signal_queue
            import threading

            def scan_thread():
                try:
                    strong_signals = []

                    for pair in Config.WATCH_PAIRS:
                        try:
                            # Get latest price
                            price = redis_price_cache.get_price_sync(pair)
                            if price is None:
                                ticker = self.indodax.get_ticker(pair)
                                if ticker:
                                    price = ticker['last']
                                    redis_price_cache.set_price(pair, price)

                            if price is None:
                                continue

                            # Generate signal (lightweight - no ML, just TA)
                            hist = self.db.get_price_history(pair, limit=100)
                            if hist.empty or len(hist) < 50:
                                continue

                            # Quick TA analysis - use get_signals() for all indicators
                            from analysis.technical_analysis import TechnicalAnalysis
                            ta = TechnicalAnalysis(hist)
                            ta_signals = ta.get_signals()

                            # Get recommendation from TA signals
                            recommendation = ta_signals.get('recommendation', 'HOLD')
                            ta_strength = ta_signals.get('strength', 0)
                            indicators = ta_signals.get('indicators', {})

                            # Check for ALL signals (BUY, SELL, STRONG_BUY, STRONG_SELL)
                            # FILTER: Skip if price is 0 or None
                            if recommendation in ['STRONG_BUY', 'BUY', 'STRONG_SELL', 'SELL']:
                                if not price or price <= 0:
                                    logger.debug(f"Skipped {pair}: price is 0 or invalid")
                                elif abs(ta_strength) < 0.30:
                                    logger.debug(f"Skipped {pair}: TA strength too low ({ta_strength:.2f})")
                                else:
                                    strong_signals.append({
                                        'pair': pair,
                                        'type': recommendation,
                                        'confidence': abs(ta_strength),
                                        'price': price,
                                        'reason': ta_signals.get('reason', f'TA strength: {ta_strength:.2f}')
                                    })
                        except Exception as e:
                            logger.debug(f"Scan error for {pair}: {e}")

                    # DEDUPLICATION: Remove duplicates (same pair + same type within cooldown period)
                    # Also check against last sent signals (track per pair)
                    filtered_signals = []
                    current_time = time.time()
                    cooldown_seconds = 300  # 5 minutes cooldown between same signal
                    
                    # Initialize last signal time tracker if not exists
                    if not hasattr(self, '_last_scan_signals'):
                        self._last_scan_signals = {}  # {pair_type_key: timestamp}
                    
                    for sig in strong_signals:
                        key = f"{sig['pair']}_{sig['type']}"
                        last_sent = self._last_scan_signals.get(key, 0)
                        
                        if current_time - last_sent >= cooldown_seconds:
                            filtered_signals.append(sig)
                            self._last_scan_signals[key] = current_time
                            logger.info(f"✅ Market scan signal sent: {key}")
                        else:
                            logger.info(f"⏳ Market scan cooldown: {key} ({current_time - last_sent:.0f}s ago)")
                    
                    strong_signals = filtered_signals
                    
                    # MARKET SCAN NOTIFICATIONS ARE DISABLED - Use /signal command instead
                    # Reason: Duplicate notifications issue due to threading/concurrency
                    logger.info(f"📊 Market scan: {len(strong_signals)} signals found (notifications disabled)")
                    
                    # Queue strong signals (only filtered)
                    for sig in strong_signals:
                        signal_queue.push_signal(
                            pair=sig['pair'],
                            signal_type=sig['type'],
                            confidence=sig['confidence'],
                            price=sig['price'],
                            data={'reason': sig['reason']},
                            priority=10
                        )

                    # 📢 Market scan notifications are now disabled - use /signal command instead
                    # Keeping logic for signal collection but not sending to Telegram
                    if strong_signals:
                        logger.info(f"📊 Market scan: {len(strong_signals)} signals found (Telegram notifications disabled)")
                        for sig in strong_signals:
                            logger.info(f"   {sig['type']} {sig['pair']} @ {sig['price']:,.0f} (conf: {sig['confidence']:.0%})")
                    
                    # Queue strong signals for processing (if auto-execution is enabled)
                    # Not sending to Telegram to avoid duplicates

                except Exception as e:
                    logger.error(f"❌ Market scan error: {e}")

            # Run in background thread
            threading.Thread(target=scan_thread, daemon=True).start()

        except Exception as e:
            logger.error(f"❌ Market scan scheduler error: {e}")

    def _scheduled_db_cleanup(self):
        """Cleanup old data every 6 hours"""
        try:
            logger.info("⏰ Running scheduled DB cleanup...")
            self.db.cleanup_old_price_data(days=30)
            logger.info("✅ DB cleanup complete")
        except Exception as e:
            logger.error(f"❌ DB cleanup error: {e}")

    def _scheduled_signal_stats(self):
        """Update signal stats every hour"""
        try:
            if self.signal_queue.is_available():
                stats = self.signal_queue.get_stats()
                logger.info(f"📊 Signal Stats (24h): {stats}")
        except Exception as e:
            logger.error(f"❌ Signal stats error: {e}")

    def _scheduled_cache_health_check(self):
        """Check Redis + cache health every 30 minutes"""
        try:
            redis_ok = redis_price_cache.is_redis_available()
            cache_info = redis_price_cache.get_info()

            if redis_ok:
                logger.info(f"💾 Cache Health: Redis ✅ | Local: {cache_info['local_cache_size']} pairs | TTL: {cache_info['ttl_seconds']}s")
            else:
                logger.warning(f"⚠️ Cache Health: Redis ❌ | Fallback to dict | Local: {cache_info['local_cache_size']} pairs")
        except Exception as e:
            logger.error(f"❌ Cache health check error: {e}")

    def _retrain_ml_model(self, background=True):
        """
        Retrain ML model with latest data + cleanup old data to save storage

        FIX: Now runs in background thread by default to avoid blocking main thread
        FIX: Uses efficient pd.concat instead of loop
        FIX: Memory-safe training with n_jobs limit
        FIX: Sends results to Telegram admins when triggered from auto-retrain
        """
        def _do_retrain(send_to_telegram=False):
            """Actual retrain logic (runs in background thread)"""
            try:
                logger.info("🤖 Retraining ML model with latest data...")

                # Cleanup old data first (keep last 30 days to save storage)
                self.db.cleanup_old_price_data(days=30)

                # FIX: Collect DataFrames in list, concat once at end (memory efficient)
                data_frames = []
                pairs_with_data = []

                for pair in Config.WATCH_PAIRS:
                    # Load more data for better training (was limit=1000)
                    df = self.db.get_price_history(pair, limit=5000)
                    if not df.empty and len(df) >= 100:
                        data_frames.append(df)
                        pairs_with_data.append(f"• {pair}: {len(df)} candles")
                    elif not df.empty:
                        logger.warning(f"⚠️  {pair}: only {len(df)} candles (need 100+)")

                # FIX: Concat all data at once instead of in loop
                if data_frames:
                    all_data = pd.concat(data_frames, ignore_index=True)
                else:
                    all_data = pd.DataFrame()

                total_candles = len(all_data)
                pairs_count = len(pairs_with_data)

                if total_candles >= 200:
                    success = self.ml_model.train(all_data)
                    if success:
                        accuracy = getattr(self.ml_model, 'last_accuracy', 'N/A')
                        recall = getattr(self.ml_model, 'last_recall', 'N/A')
                        precision = getattr(self.ml_model, 'last_precision', 'N/A')
                        f1 = getattr(self.ml_model, 'last_f1', 'N/A')
                        
                        accuracy_str = f"{accuracy:.2%}" if isinstance(accuracy, (int, float)) else str(accuracy)
                        recall_str = f"{recall:.2%}" if isinstance(recall, (int, float)) else str(recall)
                        precision_str = f"{precision:.2%}" if isinstance(precision, (int, float)) else str(precision)
                        f1_str = f"{f1:.2%}" if isinstance(f1, (int, float)) else str(f1)
                        
                        logger.info(f"✅ ML model retrained: {total_candles} candles, "
                                  f"{pairs_count} pairs, Accuracy: {accuracy_str}")
                        
                        # Send to Telegram if requested
                        if send_to_telegram:
                            self._send_telegram_admins(
                                f"🤖 <b>ML Model Auto-Retrained</b>\n\n"
                                f"📊 Data: <code>{total_candles}</code> candles from {pairs_count} pairs\n\n"
                                f"🎯 Accuracy: <code>{accuracy_str}</code>\n"
                                f"🎯 Recall: <code>{recall_str}</code>\n"
                                f"🎯 Precision: <code>{precision_str}</code>\n"
                                f"🎯 F1 Score: <code>{f1_str}</code>\n\n"
                                f"💡 Signal quality improved!"
                            )
                    else:
                        logger.warning("❌ ML training failed")
                        if send_to_telegram:
                            self._send_telegram_admins(
                                f"🤖 <b>ML Auto-Retrain Failed</b>\n\n"
                                f"❌ Training returned False\n"
                                f"📊 Data: <code>{total_candles}</code> candles"
                            )
                elif total_candles >= 100:
                    logger.warning(f"⚠️  Only {total_candles} candles available — training with marginal data")
                    success = self.ml_model.train(all_data)
                    if success:
                        logger.info("✅ ML model trained (marginal data - retrain again when more data available)")
                        if send_to_telegram:
                            self._send_telegram_admins(
                                f"⚠️ <b>ML Model Trained (Marginal Data)</b>\n\n"
                                f"📊 Only <code>{total_candles}</code> candles (need 200+)\n"
                                f"💡 Retrain again when more data collected"
                            )
                else:
                    logger.warning(f"⚠️  Not enough data for ML training: {total_candles} candles "
                                 f"(need 100+ minimum, 200+ recommended)")
                    logger.info(f"💡 Bot is collecting data. Estimated time to ready: "
                              f"~{(200 - total_candles) * 15 // 60} minutes")
                    if send_to_telegram:
                        self._send_telegram_admins(
                            f"⚠️ <b>ML Auto-Retrain Skipped</b>\n\n"
                            f"📊 Only <code>{total_candles}</code> candles (need 100+)\n"
                            f"💡 Bot still collecting data"
                        )
            except Exception as e:
                logger.error(f"❌ Error retraining ML model: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                if send_to_telegram:
                    self._send_telegram_admins(
                        f"❌ <b>ML Auto-Retrain Error</b>\n\n"
                        f"Error: <code>{str(e)}</code>"
                    )

        # FIX: Run in background thread by default to avoid blocking main thread
        if background:
            logger.info("🔄 Starting ML retraining in background thread...")
            retrain_thread = threading.Thread(target=_do_retrain, args=(False,), daemon=True, name="ML-Retrain")
            retrain_thread.start()
            return retrain_thread
        else:
            # Synchronous mode (for manual /retrain command)
            _do_retrain(send_to_telegram=False)


    def _send_telegram_admins(self, message):
        """Send message to all admin Telegram IDs (thread-safe)"""
        import asyncio
        
        def _send():
            try:
                from telegram import Bot
                bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    async def _async_send():
                        for admin_id in Config.ADMIN_IDS:
                            try:
                                await bot.send_message(
                                    chat_id=admin_id,
                                    text=message,
                                    parse_mode='HTML'
                                )
                            except Exception as e:
                                logger.warning(f"⚠️ Failed to send to admin {admin_id}: {e}")
                    
                    loop.run_until_complete(_async_send())
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"❌ Error sending Telegram message: {e}")
        
        thread = threading.Thread(target=_send, daemon=True, name="Telegram-Send")
        thread.start()


    def _start_auto_retrain_timer(self):
        """Start periodic auto-retrain timer (24h interval, always runs for signal quality)"""
        def auto_retrain_loop():
            import time
            import logging
            thread_logger = logging.getLogger('crypto_bot')

            while True:
                time.sleep(24 * 3600)  # Wait 24 hours

                # Always retrain for signal quality improvement
                # (not just when trading - better signals needed for DRY RUN too)
                thread_logger.info("⏰ Auto-retrain timer triggered (24h)")
                # Run with send_to_telegram=True to notify admins
                self._retrain_ml_model_with_telegram()

        retrain_thread = threading.Thread(target=auto_retrain_loop, daemon=True)
        retrain_thread.start()
        logger.info("⏰ Auto ML retrain timer started (24h interval, always active)")

    def _retrain_ml_model_with_telegram(self):
        """Retrain ML model and send results to Telegram admins"""
        def _do_retrain_with_telegram():
            """Retrain with Telegram notification enabled"""
            try:
                logger.info("🤖 Auto-retraining ML model with latest data (with Telegram notification)...")

                # Cleanup old data first (keep last 30 days to save storage)
                self.db.cleanup_old_price_data(days=30)

                # Collect DataFrames in list, concat once at end (memory efficient)
                data_frames = []
                pairs_with_data = []

                for pair in Config.WATCH_PAIRS:
                    df = self.db.get_price_history(pair, limit=5000)
                    if not df.empty and len(df) >= 100:
                        data_frames.append(df)
                        pairs_with_data.append(f"• {pair}: {len(df)} candles")
                    elif not df.empty:
                        logger.warning(f"⚠️  {pair}: only {len(df)} candles (need 100+)")

                # Concat all data at once
                if data_frames:
                    all_data = pd.concat(data_frames, ignore_index=True)
                else:
                    all_data = pd.DataFrame()

                total_candles = len(all_data)
                pairs_count = len(pairs_with_data)

                if total_candles >= 200:
                    success = self.ml_model.train(all_data)
                    if success:
                        accuracy = getattr(self.ml_model, 'last_accuracy', 'N/A')
                        recall = getattr(self.ml_model, 'last_recall', 'N/A')
                        precision = getattr(self.ml_model, 'last_precision', 'N/A')
                        f1 = getattr(self.ml_model, 'last_f1', 'N/A')
                        
                        accuracy_str = f"{accuracy:.2%}" if isinstance(accuracy, (int, float)) else str(accuracy)
                        recall_str = f"{recall:.2%}" if isinstance(recall, (int, float)) else str(recall)
                        precision_str = f"{precision:.2%}" if isinstance(precision, (int, float)) else str(precision)
                        f1_str = f"{f1:.2%}" if isinstance(f1, (int, float)) else str(f1)
                        
                        logger.info(f"✅ ML model auto-retrained: {total_candles} candles, "
                                  f"{pairs_count} pairs, Accuracy: {accuracy_str}")
                        
                        # NEW: Get undersampling info
                        undersample_info = getattr(self.ml_model, 'last_undersample_info', None)
                        undersample_text = ""
                        if undersample_info and undersample_info.get('applied'):
                            undersample_text = (
                                f"\n📊 <b>Undersampling Applied:</b>\n"
                                f"<code>{undersample_info['before'].replace(chr(10), chr(10))}</code>\n\n"
                                f"<code>{undersample_info['after'].replace(chr(10), chr(10))}</code>\n"
                            )
                        elif undersample_info:
                            undersample_text = f"\n📊 <b>Class Balance:</b>\n<code>{undersample_info.get('message', 'Balanced')}</code>\n"

                        # Always send to Telegram for auto-retrain
                        message = (
                            f"🤖 <b>ML Model Auto-Retrained (24h)</b>\n\n"
                            f"📊 Data: <code>{total_candles}</code> candles from {pairs_count} pairs\n\n"
                            f"🎯 Accuracy: <code>{accuracy_str}</code>\n"
                            f"🎯 Recall: <code>{recall_str}</code>\n"
                            f"🎯 Precision: <code>{precision_str}</code>\n"
                            f"🎯 F1 Score: <code>{f1_str}</code>\n"
                            f"{undersample_text}\n"
                            f"💡 Signal quality improved!"
                        )
                        self._send_telegram_admins(message)
                    else:
                        logger.warning("❌ ML auto-training failed")
                        self._send_telegram_admins(
                            f"🤖 <b>ML Auto-Retrain Failed (24h)</b>\n\n"
                            f"❌ Training returned False\n"
                            f"📊 Data: <code>{total_candles}</code> candles from {pairs_count} pairs"
                        )
                elif total_candles >= 100:
                    logger.warning(f"⚠️  Only {total_candles} candles available — training with marginal data")
                    success = self.ml_model.train(all_data)
                    if success:
                        logger.info("✅ ML model trained (marginal data)")
                        self._send_telegram_admins(
                            f"⚠️ <b>ML Model Trained (Marginal Data)</b>\n\n"
                            f"📊 Only <code>{total_candles}</code> candles (need 200+)\n"
                            f"💡 Retrain again when more data collected"
                        )
                else:
                    logger.warning(f"⚠️  Not enough data for ML training: {total_candles} candles "
                                 f"(need 100+ minimum, 200+ recommended)")
                    self._send_telegram_admins(
                        f"⚠️ <b>ML Auto-Retrain Skipped (24h)</b>\n\n"
                        f"📊 Only <code>{total_candles}</code> candles (need 100+)\n"
                        f"💡 Bot still collecting data"
                    )
            except Exception as e:
                logger.error(f"❌ Error auto-retraining ML model: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                self._send_telegram_admins(
                    f"❌ <b>ML Auto-Retrain Error (24h)</b>\n\n"
                    f"Error: <code>{str(e)}</code>"
                )

        # Run in background thread
        thread = threading.Thread(target=_do_retrain_with_telegram, daemon=True, name="ML-AutoRetrain")
        thread.start()
    
    def _setup_handlers(self):
        """Register all Telegram command handlers"""
        # Basic commands
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("menu", self.menu))
        
        # Watchlist commands
        self.app.add_handler(CommandHandler("watch", self.watch))
        self.app.add_handler(CommandHandler("unwatch", self.unwatch))
        self.app.add_handler(CommandHandler("list", self.list_watch))
        self.app.add_handler(CommandHandler("clear_watchlist", self.clear_watchlist))  # NEW: Clear watchlist from DB
        self.app.add_handler(CommandHandler("cleanup_signals", self.cleanup_signals))  # NEW: Clean incomplete signals
        self.app.add_handler(CommandHandler("reset_skip", self.reset_skip))  # NEW: Reset skipped/invalid pairs
        
        # Price & signals
        self.app.add_handler(CommandHandler("price", self.price))
        self.app.add_handler(CommandHandler("signal", self.get_signal))
        self.app.add_handler(CommandHandler("signals", self.signals))
        self.app.add_handler(CommandHandler("signal_buy", self.signal_buy_only))
        self.app.add_handler(CommandHandler("signal_sell", self.signal_sell_only))
        self.app.add_handler(CommandHandler("signal_hold", self.signal_hold_only))
        self.app.add_handler(CommandHandler("signal_buysell", self.signal_buysell))
        self.app.add_handler(CommandHandler("notifications", self.notifications))
        
        # Portfolio & trades
        self.app.add_handler(CommandHandler("balance", self.balance))
        self.app.add_handler(CommandHandler("trades", self.trades))
        self.app.add_handler(CommandHandler("sync", self.sync_trades))
        self.app.add_handler(CommandHandler("performance", self.performance))
        self.app.add_handler(CommandHandler("position", self.position))
        
        # Admin commands
        self.app.add_handler(CommandHandler("status", self.status))
        self.app.add_handler(CommandHandler("start_trading", self.start_trading))
        self.app.add_handler(CommandHandler("stop_trading", self.stop_trading))
        self.app.add_handler(CommandHandler("emergency_stop", self.emergency_stop))  # HEDGE FUND: Kill switch
        self.app.add_handler(CommandHandler("metrics", self.metrics_cmd))  # HEDGE FUND: Prometheus-like metrics
        self.app.add_handler(CommandHandler("autotrade", self.autotrade))
        self.app.add_handler(CommandHandler("autotrade_status", self.autotrade_status))
        self.app.add_handler(CommandHandler("scheduler_status", self.scheduler_status))
        self.app.add_handler(CommandHandler("set_interval", self.set_interval))
        self.app.add_handler(CommandHandler("hunter_status", self.hunter_status))
        self.app.add_handler(CommandHandler("ultrahunter", self.ultra_hunter_cmd))
        self.app.add_handler(CommandHandler("retrain", self.retrain_ml))
        self.app.add_handler(CommandHandler("backtest", self.backtest_cmd))
        self.app.add_handler(CommandHandler("backtest_v3", self.backtest_v3_cmd))  # PRO backtest with ML V3
        self.app.add_handler(CommandHandler("dryrun", self.dryrun_cmd))  # Dry-run simulation
        self.app.add_handler(CommandHandler("regime", self.regime_cmd))  # Market regime detection
        self.app.add_handler(CommandHandler("kelly", self.kelly_cmd))  # Kelly Criterion position sizing
        self.app.add_handler(CommandHandler("compare", self.compare_cmd))  # Multi-pair comparison

        # Signal Quality Analysis commands
        self.app.add_handler(CommandHandler("signal_quality", self.signal_quality_cmd))
        self.app.add_handler(CommandHandler("signal_report", self.signal_report_cmd))

        # Auto-trade pairs management commands (SEPARATE from watchlist)
        self.app.add_handler(CommandHandler("add_autotrade", self.add_autotrade))
        self.app.add_handler(CommandHandler("remove_autotrade", self.remove_autotrade))
        self.app.add_handler(CommandHandler("list_autotrade", self.list_autotrade))
        
        # Price monitoring commands
        self.app.add_handler(CommandHandler("monitor", self.monitor))
        self.app.add_handler(CommandHandler("set_sl", self.set_stoploss))
        self.app.add_handler(CommandHandler("set_tp", self.set_takeprofit))

        # Manual S/R levels commands
        self.app.add_handler(CommandHandler("set_sr", self.set_manual_sr))
        self.app.add_handler(CommandHandler("view_sr", self.view_manual_sr))
        self.app.add_handler(CommandHandler("delete_sr", self.delete_manual_sr))
        
        # Smart Hunter commands
        self.app.add_handler(CommandHandler("smarthunter", self.smarthunter_cmd))
        self.app.add_handler(CommandHandler("smarthunter_status", self.smarthunter_status))

        # Manual trading command
        self.app.add_handler(CommandHandler("trade", self.trade))

        # Auto sell command
        self.app.add_handler(CommandHandler("trade_auto_sell", self.trade_auto_sell))

        # Cancel trade command
        self.app.add_handler(CommandHandler("cancel", self.cancel_trade))

        # Market scanner command
        self.app.add_handler(CommandHandler("scan", self.market_scan))
        
        # Top volume command
        self.app.add_handler(CommandHandler("topvolume", self.top_volume))

        # Analyze command - Quick BUY/SELL analysis
        self.app.add_handler(CommandHandler("analyze", self.analyze_signal))

        # Command helper - quick reference guide
        self.app.add_handler(CommandHandler("cmd", self.commands_helper))

        # =====================================================================
        # SCALPER MODULE COMMANDS
        # =====================================================================
        if self.scalper:
            self.app.add_handler(CommandHandler("s_menu", self.scalper.cmd_menu))
            self.app.add_handler(CommandHandler("s_posisi", self.scalper.cmd_posisi))
            self.app.add_handler(CommandHandler("s_analisa", self.scalper.cmd_analisa))
            self.app.add_handler(CommandHandler("s_buy", self.scalper.cmd_buy))
            self.app.add_handler(CommandHandler("s_sell", self.scalper.cmd_sell))
            self.app.add_handler(CommandHandler("s_sltp", self.scalper.cmd_sltp))
            self.app.add_handler(CommandHandler("s_cancel", self.scalper.cmd_cancel))
            self.app.add_handler(CommandHandler("s_info", self.scalper.cmd_info))
            self.app.add_handler(CommandHandler("s_pair", self.scalper.cmd_pair))
            self.app.add_handler(CommandHandler("s_reset", self.scalper.cmd_reset))
            self.app.add_handler(CommandHandler("s_portfolio", self.scalper.cmd_portfolio))
            self.app.add_handler(CommandHandler("s_closeall", self.scalper.cmd_close_all))
            self.app.add_handler(CommandHandler("s_riwayat", self.scalper.cmd_riwayat))
            self.app.add_handler(CommandHandler("s_sync", self.scalper.cmd_sync))
            logger.info("✅ Scalper module commands registered")

        # Text handler for pair shortcuts
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_text_input
        ))

        # Handler untuk "/" atau command yang tidak dikenal - tampilkan help menu
        self.app.add_handler(MessageHandler(
            filters.TEXT & filters.Regex('^/'),
            self.handle_unknown_command
        ))
        
        # Callback handler for inline keyboards
        self.app.add_handler(CallbackQueryHandler(self.callback_handler))
        
        logger.info("📋 Registered all command handlers")
    
    def _init_websocket(self):
        """Initialize WebSocket connection to Indodax (DISABLED - Indodax public channels not working)"""
        # WebSocket DISABLED - using REST API polling only
        # Indodax public WebSocket channels are not reliable for this use case
        # self.ws_handler = None  # Already set to None in __init__
        logger.info("⚠️ WebSocket disabled (using REST API polling only)")

    def _load_auto_trade_mode(self):
        """Load auto-trade mode from database (persistent setting)"""
        try:
            is_dry_run = self.db.get_auto_trade_mode()
            Config.AUTO_TRADE_DRY_RUN = is_dry_run
            mode_label = "🧪 DRY RUN" if is_dry_run else "🔴 REAL"
            logger.info(f"📊 Auto-trade mode loaded from database: {mode_label}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load auto-trade mode from database: {e}")
            logger.info(f"Using default from .env: AUTO_TRADE_DRY_RUN={Config.AUTO_TRADE_DRY_RUN}")

    def _save_auto_trade_mode(self, is_dry_run):
        """Save auto-trade mode to database (persistent setting)"""
        try:
            self.db.set_auto_trade_mode(is_dry_run)
            Config.AUTO_TRADE_DRY_RUN = is_dry_run
            mode_label = "🧪 DRY RUN" if is_dry_run else "🔴 REAL"
            logger.info(f"💾 Auto-trade mode saved to database: {mode_label}")
        except Exception as e:
            logger.error(f"❌ Failed to save auto-trade mode to database: {e}")

    # =============================================================================
    # TELEGRAM COMMAND HANDLERS
    # =============================================================================
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message and menu"""
        user = update.effective_user
        self.db.add_user(user.id, user.username, user.first_name)

        is_admin = user.id in Config.ADMIN_IDS

        text = f"""
👋 <b>Welcome to Advanced Crypto Trading Bot!</b>

🤖 <b>Features:</b>
• Real-time WebSocket price updates
• Machine Learning predictions (RF+GB ensemble)
• Technical Analysis (RSI, MACD, BB, ADX, etc.)
• Automated trading signals with confidence scores
• Risk management (SL/TP, position sizing)
• Portfolio tracking & performance metrics

📊 <b>Quick Commands:</b>
• /watch &lt;PAIR&gt; atau /watch &lt;PAIR1&gt;, &lt;PAIR2&gt; - Subscribe to real-time updates
• /signal &lt;PAIR&gt; - Get detailed trading signal
• /price &lt;PAIR&gt; - Quick price check
• /position &lt;PAIR&gt; - Analyze your position with order book
• /balance - View portfolio balance
• /trades - View open/closed trades
• /status - Bot system status (admin)

🤖 <b>Auto Trading:</b>
• /autotrade - Toggle bot auto-trading ON/OFF
• /ultrahunter - Ultra Conservative Hunter control
• /hunter_status - Check hunter status & performance

🎯 <b>Current Status:</b>
• Trading: {'🟢 Active' if self.is_trading else '🔴 Paused'}
• WebSocket: {'🟢 Connected' if self.ws_connected else '🔴 Disconnected'}
• ML Model: {'✅ Loaded' if self.ml_model else '❌ Not Loaded'}
• Your Access: {'👑 Admin' if is_admin else '👤 User'}

💡 <b>Tip:</b> Type a pair like BTC/IDR to quickly analyze!
        """

        # Dynamic inline keyboard - watchlist starts empty (user must add pairs)
        keyboard = []
        user_id = update.effective_user.id
        user_watchlist = self.subscribers.get(user_id, [])
        user_autotrade = self.auto_trade_pairs.get(user_id, [])

        if user_watchlist:
            # Show user's personal watchlist (max 4 pairs)
            display_pairs = user_watchlist[:4]
            for i in range(0, len(display_pairs), 2):
                row = []
                pair1 = display_pairs[i].strip().upper()
                row.append(InlineKeyboardButton(f"📊 {pair1}", callback_data=f"watch_{pair1.lower()}"))
                if i + 1 < len(display_pairs):
                    pair2 = display_pairs[i + 1].strip().upper()
                    row.append(InlineKeyboardButton(f"📊 {pair2}", callback_data=f"watch_{pair2.lower()}"))
                keyboard.append(row)
        else:
            # No pairs yet — prompt to add for AUTO-TRADE (separate from scalping)
            keyboard.append([
                InlineKeyboardButton("🤖 Setup Auto-Trade Pairs", callback_data="autotrade_add_pair")
            ])

        # Show auto-trade pairs summary if any
        if user_autotrade:
            autotrade_label = f"🤖 Auto-Trade: {len(user_autotrade)} pair(s)"
            keyboard.append([
                InlineKeyboardButton(autotrade_label, callback_data="autotrade_add_pair")
            ])

        # Action buttons
        keyboard.append([
            InlineKeyboardButton("🔍 Quick Price", callback_data="price_quick"),
            InlineKeyboardButton("🤖 Quick Signal", callback_data="signal_quick")
        ])
        keyboard.append([InlineKeyboardButton("❓ Help & Guide", callback_data="help")])

        if is_admin:
            keyboard.append([
                InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")
            ])

        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"👤 User {user.id} started bot")
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Detailed help guide"""
        text = """
📚 <b>COMPLETE USER GUIDE</b>

💡 <b>QUICK REFERENCE:</b>
Gunakan <code>/cmd</code> untuk panduan lengkap semua command
• <code>/cmd bot</code> - Command Bot Utama
• <code>/cmd scalp</code> - Command Scalper Module
• <code>/cmd trade</code> - Command Trading
• <code>/cmd pair</code> - Manajemen Pair
• <code>/cmd status</code> - Status &amp; Monitoring

🔹 <b>WATCHING PAIRS (Real-time Updates):</b>
<code>/watch &lt;PAIR&gt;</code> atau <code>/watch &lt;PAIR1&gt;, &lt;PAIR2&gt;, ...</code> - Subscribe to live price updates
Examples: 
• <code>/watch btcidr</code>
• <code>/watch btcidr, ethidr, solidr</code> (multiple pairs)
• You'll receive instant notifications on price changes
• Use <code>/list</code> to see your watchlist
• Use <code>/unwatch &lt;PAIR&gt;</code> atau <code>/unwatch &lt;PAIR1&gt;, &lt;PAIR2&gt;</code> to stop receiving updates

🔹 <b>TRADING SIGNALS:</b>
<code>/signal &lt;PAIR&gt;</code> - Get comprehensive trading analysis
Shows:
• Current price &amp; 24h change
• Technical indicators (RSI, MACD, MA, Bollinger)
• ML prediction with confidence score
• Combined recommendation (BUY/SELL/HOLD)
• Support &amp; resistance levels

🔹 <b>FILTERED SIGNALS (Specific Type Only):</b>
<code>/signal_buy &lt;PAIR&gt;</code> - BUY/STRONG_BUY only (tidak tampil SELL/HOLD)
<code>/signal_sell &lt;PAIR&gt;</code> - SELL/STRONG_SELL only (tidak tampil BUY/HOLD)
<code>/signal_hold &lt;PAIR&gt;</code> - HOLD only (tidak tampil BUY/SELL)
<code>/signal_buysell &lt;PAIR&gt;</code> - BUY atau SELL only (tidak tampil HOLD)

🔹 <b>AUTO-TRADING (Admin Only):</b>
<code>/autotrade</code> - Toggle auto-trading (keeps current mode)
<code>/autotrade dryrun</code> - Enable SIMULATION mode (no real trades)
<code>/autotrade real</code> - Enable REAL trading (real money)
<code>/autotrade off</code> - Disable auto-trading
<code>/autotrade_status</code> - Check auto-trading status and history

When enabled, bot will:
• Analyze watched markets every 5 minutes
• Execute trades when signals meet confidence threshold
• Apply stop-loss (2%) and take-profit (5%) automatically
• Manage position sizing (max 25% per trade)
• Enforce daily loss limits (5%)

🧪 <b>DRY RUN MODE (Recommended for testing):</b>
• All trades are SIMULATED - no real money used
• Perfect for learning how the bot works
• Test strategies without any financial risk
• See exactly what trades would happen
• Virtual P&amp;L tracking for analysis

🔹 <b>PORTFOLIO MANAGEMENT:</b>
<code>/balance</code> - Check available balance &amp; positions
<code>/trades</code> - View open and historical trades
<code>/performance</code> - View win rate, P&amp;L, Sharpe ratio
<code>/position &lt;PAIR&gt;</code> - Deep position analysis with order book
<code>/sync</code> - Sync trades from Indodax API

🔹 <b>POSITION ANALYSIS:</b>
The <code>/position</code> command provides:
• Your open positions with P&amp;L
• Order book walls (buy/sell)
• Support &amp; resistance levels
• Strategy recommendations
• Stop loss &amp; take profit levels

🔹 <b>SYNC MANUAL TRADES:</b>
Use <code>/sync</code> to import your Indodax trade history
This allows bot to analyze trades you made manually on Indodax website

🔹 <b>ML MODEL:</b>
• <code>/retrain</code> - Manually retrain ML model (admin)
• Model auto-retrains every 24 hours

🔹 <b>SMART HUNTER (Auto Hunter):</b>
• <code>/smarthunter on</code> - Start Smart Hunter (scans market)
• <code>/smarthunter off</code> - Stop Smart Hunter
• <code>/smarthunter_status</code> - Check positions & status
• Strategy: RSI oversold + MACD bullish + Volume
• Exit: +3% (50%), +5% (30%), +8% (20%)
• Stop loss: -2% with trailing stop

🔹 <b>ULTRA HUNTER (Conservative):</b>
• <code>/ultrahunter on</code> - Start Ultra Hunter
• <code>/ultrahunter off</code> - Stop Ultra Hunter

⚠️ <b>RISK PARAMETERS:</b>
• Max position size: 25% of balance
• Stop-loss: 2% per trade
• Take-profit: 5% per trade
• Max trades/day: 10
• Daily loss limit: 5%
• Min risk-reward ratio: 2:1

🎯 <b>STRATEGY OVERVIEW:</b>
Bot combines:
• 60% Technical Analysis weight
• 40% Machine Learning prediction
• Strict risk management rules
• Real-time WebSocket data feed

📞 <b>Support:</b> Contact admin for issues
        """
        await update.message.reply_text(text, parse_mode='HTML')

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show quick menu with all available commands"""
        text = """
📋 **BOT MENU - Quick Commands**

📚 **PANDUAN CEPAT:**
`/cmd` - Lihat semua command lengkap
`/cmd bot` - Command Bot Utama
`/cmd scalp` - Command Scalper
`/cmd trade` - Command Trading

🔹 **WATCH & PRICE**
`/watch <PAIR>` atau `/watch <P1>, <P2>, ...` - Add pairs to watchlist
`/list` - View your watchlist
`/unwatch <PAIR>` atau `/unwatch <P1>, <P2>` - Remove from watchlist
`/price <PAIR>` - Quick price check

🔹 **SIGNALS & ANALYSIS**
/analyze <PAIR> - Quick BUY/SELL analysis (Recommended!)
/signal <PAIR> - Get trading signal (all types)
/signal_buy <PAIR> - BUY/STRONG_BUY only
/signal_sell <PAIR> - SELL/STRONG_SELL only
/signal_hold <PAIR> - HOLD only
/signal_buysell <PAIR> - BUY or SELL only (no HOLD)
/signals - Signals for all watched pairs
/scan - Market scanner for opportunities
/topvolume - Top volume pairs

🔹 **SMART HUNTER (Auto Hunter)**
/smarthunter on - Start Smart Hunter (auto scan)
/smarthunter off - Stop Smart Hunter
/smarthunter_status - Check positions & status
/topvolume - Top volume pairs
/signals - Signals for all watchlist pairs

💡 **Tips:**
• Start with `/watch btcidr, ethidr, solidr` for multiple pairs
• Use `/signal <PAIR>` for full analysis
• Enable `/autotrade dryrun` for testing (RECOMMENDED)
• Try `/smarthunter on` for automated hunting
"""
        await self._send_message(update, context, text, parse_mode='Markdown')

    async def commands_helper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show quick reference guide for all commands"""
        if not context.args:
            # Show main menu
            text = """
📋 **PANDUAN LENGKAP COMMAND BOT**

🔹 **CARA PAKAI:**
`/cmd` - Lihat panduan ini
`/cmd bot` - Command Bot Utama
`/cmd scalp` - Command Scalper Module
`/cmd pair` - Manajemen Pair
`/cmd trade` - Trading
`/cmd status` - Status & Monitoring

_Ketik `/cmd <kategori>` untuk detail_
"""
        else:
            kategori = context.args[0].lower()
            
            if kategori == 'bot':
                text = """
🤖 **COMMAND BOT UTAMA**

👀 **Watchlist & Monitoring**
• `/watch <pair>` atau `/watch <p1>, <p2>, ...` - Add pairs to watchlist + scalper
• `/unwatch <pair>` atau `/unwatch <p1>, <p2>, ...` - Remove from watchlist
• `/list` - Lihat watchlist Anda
• `/price <pair>` - Cek harga cepat
• `/monitor <pair>` - Set price monitoring

📊 **Analisa & Sinyal**
• `/analyze <pair>` - Analisa cepat BUY/SELL (Recomendation!)
• `/signal <pair>` - Signal lengkap
• `/signal_buy <pair>` - BUY/STRONG_BUY only
• `/signal_sell <pair>` - SELL/STRONG_SELL only
• `/signal_hold <pair>` - HOLD only
• `/signal_buysell <pair>` - BUY/SELL only
• `/signals` - Analisa semua pair di watchlist
• `/scan` - Scan market untuk peluang
• `/topvolume` - Top volume pairs

🤖 **Smart Hunter (Auto Hunter)**
• `/smarthunter on` - Start Smart Hunter
• `/smarthunter off` - Stop Smart Hunter
• `/smarthunter_status` - Check positions
• `/position <pair>` - Analisa mendalam

💼 **Portfolio & Trading**
• `/balance` - Saldo & posisi
• `/trades` - Riwayat trade
• `/performance` - Statistik win rate & P&L
• `/sync` - Sync trade dari Indodax

⚙️ **Auto Trading**
• `/autotrade` - Toggle auto-trade mode
• `/autotrade dryrun` - Mode simulasi (RECOMMENDED)
• `/autotrade real` - Trading sungguhan
• `/autotrade off` - Matikan auto-trade
• `/autotrade_status` - Cek status
• `/set_interval <menit>` - Set interval auto-trade
• `/scheduler_status` - Check scheduled tasks

🤖 **Smart Hunter**
• `/smarthunter on` - Start Smart Hunter
• `/smarthunter off` - Stop Smart Hunter
• `/smarthunter_status` - Check positions

🔧 **Admin & ML**
• `/status` - Status bot
• `/retrain` - Retrain model ML
• `/metrics` - Prometheus-like metrics
• `/emergency_stop` - Kill switch (STOP ALL)

🛠️ **Manual Trading**
• `/trade BUY/SELL <pair> <price> <amount>`
• `/cancel <order_id>` - Cancel order
• `/set_sl <pair> <price>` - Set stop loss
• `/set_tp <pair> <price>` - Set take profit
"""
            elif kategori == 'scalp':
                text = """
⚡ **COMMAND SCALPER MODULE**

📊 **Pair Management**
• `/s_pair list` - Lihat pair aktif
• `/s_pair add <pair>` - Tambah pair
• `/s_pair remove <pair>` - Hapus pair
• `/s_pair reset` - Reset ke default

🔍 **Analisa**
• `/s_analisa <pair>` - Analisa teknikal lengkap
  Contoh: `/s_analisa bridr`
  Menampilkan: RSI, MACD, MA, Bollinger, Volume

💰 **Trading Manual**
• `/s_buy <pair>` - Buy manual
• `/s_sell <pair>` - Sell manual
• `/s_sltp <pair> <tp> <sl>` - Set TP/SL
• `/s_cancel <pair>` - Cancel TP/SL
• `/s_info <pair>` - Info posisi

📋 **Monitoring**
• `/s_menu` - Menu utama scalper
• `/s_posisi` - Lihat posisi aktif
• `/s_reset` - Reset semua posisi

💡 **Tips Scalper:**
• Gunakan `/s_analisa` sebelum entry
• Set TP/SL untuk manage risk
• `/s_posisi` untuk pantau profit/loss
"""
            elif kategori == 'pair':
                text = """
📈 **MANAJEMEN PAIR**

**Bot Utama:**
• `/watch <pair>` atau `/watch <p1>, <p2>, ...` - Tambah ke watchlist
• `/unwatch <pair>` atau `/unwatch <p1>, <p2>, ...` - Hapus dari watchlist
• `/list` - Lihat semua pair Anda

_Default: btcidr, ethidr, bridr, pippinidr, solidr, dogeidr, xrpidr, adaidr_

**Scalper Module:**
• `/s_pair list` - Lihat pair scalper
• `/s_pair add <pair>` - Tambah pair
• `/s_pair remove <pair>` - Hapus pair
• `/s_pair reset` - Reset ke default

_Default: pippinidr, bridr, stoidr, drxidr_

**Contoh:**
```
/watch btcidr, ethidr, solidr
/s_pair add btcidr
/s_analisa btcidr
```
"""
            elif kategori == 'trade':
                text = """
💰 **COMMAND TRADING**

**Bot Utama - Manual:**
• `/trade BUY <pair> <price> <idr_amount>`
• `/trade SELL <pair> <price> <coin_amount>`
• `/cancel <order_id>`
• `/set_sl <pair> <price>`
• `/set_tp <pair> <price>`

**Bot Utama - Auto:**
• `/autotrade dryrun` - Simulasi (aman!)
• `/autotrade real` - Trading sungguhan
• `/autotrade off` - Matikan

**Scalper Module:**
• `/s_buy <pair>` - Buy
• `/s_sell <pair>` - Sell
• `/s_sltp <pair> <tp> <sl>` - Set TP/SL
• `/s_cancel <pair>` - Cancel TP/SL

**Risk Management:**
• Max 25% balance per trade
• Stop loss: 2%
• Take profit: 5%
• Max 10 trades/hari
• Daily loss limit: 5%
"""
            elif kategori == 'status':
                text = """
📊 **STATUS & MONITORING**

**Bot Status:**
• `/status` - Status keseluruhan bot
• `/autotrade_status` - Status auto-trade
• `/smarthunter_status` - Smart Hunter status
• `/scheduler_status` - Scheduled tasks

**Portfolio:**
• `/balance` - Saldo & posisi terbuka
• `/trades` - Riwayat trade
• `/performance` - Win rate, P&L, Sharpe ratio

**Market:**
• `/price <pair>` - Harga saat ini
• `/signal <pair>` - Sinyal trading
• `/signals` - Semua sinyal watchlist
• `/scan` - Market scanner
• `/topvolume` - Top volume pairs

**Smart Hunter:**
• `/smarthunter on` - Start Smart Hunter
• `/smarthunter off` - Stop Smart Hunter
• `/smarthunter_status` - Positions & status

**Scalper:**
• `/s_menu` - Menu scalper
• `/s_posisi` - Posisi aktif
• `/s_analisa <pair>` - Analisa pair

**Contoh Penggunaan:**
```
/status
/autotrade_status
/smarthunter_status
/balance
```
"""
            else:
                text = f"""
❌ Kategori tidak dikenal: `{kategori}`

**Kategori tersedia:**
• `/cmd bot` - Command Bot Utama
• `/cmd scalp` - Command Scalper
• `/cmd pair` - Manajemen Pair
• `/cmd trade` - Trading
• `/cmd status` - Status & Monitoring
"""

        await self._send_message(update, context, text, parse_mode='Markdown')

    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Subscribe to real-time updates for one or more pairs"""
        if not context.args:
            await update.message.reply_text(
                "❌ **Format:** `/watch <PAIR>` atau `/watch <PAIR1>, <PAIR2>, ...`\n\n"
                "✅ **Contoh yang valid:**\n"
                "• `/watch btcidr`\n"
                "• `/watch btcidr, ethidr, solidr`\n"
                "• `/watch BTCIDR, SOL/IDR, eth`\n"
                "• `/watch btc`\n\n"
                "💡 Bot akan otomatis menormalkan format pair!",
                parse_mode='Markdown'
            )
            return

        user_id = update.effective_user.id

        # Parse comma-separated pairs
        pairs_input = ' '.join(context.args)
        raw_pairs_list = [p.strip() for p in pairs_input.split(',') if p.strip()]
        
        if not raw_pairs_list:
            await update.message.reply_text(
                "❌ **Format:** `/watch <PAIR>` atau `/watch <PAIR1>, <PAIR2>, ...`\n\n"
                "✅ **Contoh:** `/watch btcidr, ethidr, solidr`",
                parse_mode='Markdown'
            )
            return

        # Normalize and validate all pairs
        normalized_pairs = []
        invalid_pairs = []
        norm_notes = []
        
        for original_input in raw_pairs_list:
            pair_raw = original_input.lower()
            
            # Remove accidental command prefixes
            prefixes_to_remove = ['watch ', 'watch/', '/watch ', 'signal ', '/signal ', 'price ', '/price ']
            for prefix in prefixes_to_remove:
                if pair_raw.startswith(prefix):
                    pair_raw = pair_raw[len(prefix):].strip()

            pair_raw = pair_raw.lstrip('/')

            # Normalize pair: remove slashes, ensure lowercase
            pair = pair_raw.replace('/', '').lower()
            if not pair.endswith('idr'):
                pair = pair + 'idr'

            # Validate pair format
            if not pair.endswith('idr') or len(pair) < 4:
                invalid_pairs.append(original_input)
                continue
            
            normalized_pairs.append(pair)
            
            # Track normalization notes
            if original_input.lower() != pair:
                norm_notes.append(f"`{original_input}` → `{pair}`")

        if not normalized_pairs:
            await self._send_message(update, context,
                "❌ **Semua pair tidak valid**\n\n"
                f"Input: `{self._escape_markdown(pairs_input)}`\n\n"
                "✅ **Format benar:** `btcidr`, `ethidr`, `solidr`\n\n"
                "💡 **Contoh:**\n"
                "`/watch btcidr, ethidr, solidr`",
                parse_mode='Markdown'
            )
            return

        # Initialize user subscription list
        if user_id not in self.subscribers:
            self.subscribers[user_id] = []

        # Process each valid pair
        added_pairs = []
        existing_pairs = []

        for pair in normalized_pairs:
            if pair not in self.subscribers[user_id]:
                # Add to memory
                self.subscribers[user_id].append(pair)
                added_pairs.append(pair)

                # FIX: Sync to database (persistent storage)
                self._sync_watchlist_to_db(user_id, pair)

                # Subscribe to WebSocket channel (sync function now)
                self._subscribe_pair(pair)

                logger.info(f"👤 User {user_id} subscribed to {pair} (saved to DB)")
            else:
                existing_pairs.append(pair)

        # Build response message
        messages = []

        if added_pairs:
            pairs_str = ', '.join([f"`{p.upper()}`" for p in added_pairs])
            messages.append(f"✅ **Mulai menonton:** {pairs_str}")
            messages.append("• Real-time updates: 🟢 Active")
            messages.append("• ML predictions: 🟢 Enabled")
            messages.append(f"• Auto-trading: {'🟢 On' if self.is_trading else '🔴 Off'}")

            if norm_notes:
                messages.append("\n🔄 **Normalisasi:**")
                messages.extend(norm_notes)

            # Auto-add to scalper list
            try:
                if hasattr(self, 'scalper') and self.scalper:
                    scalper_result = self.scalper.add_scalper_pairs_batch(added_pairs)
                    if scalper_result and scalper_result['added'] > 0:
                        messages.append(f"\n⚡ **Scalper:** {scalper_result['added']} pair(s) ditambahkan ke scalper list")
                        if scalper_result['skipped'] > 0:
                            messages.append(f"• {scalper_result['skipped']} pair sudah ada di scalper")
                        if scalper_result['invalid'] > 0:
                            messages.append(f"• {scalper_result['invalid']} pair invalid (tidak ada di Indodax)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to auto-add pairs to scalper: {e}")

            messages.append("\n💡 **Tips:**")
            messages.append("• Gunakan `/signal <pair>` untuk analisa")
            messages.append("• Gunakan `/unwatch <pair>` untuk stop")
            messages.append("• Gunakan `/list` untuk lihat watchlist")
            messages.append("• Gunakan `/s_menu` untuk scalper menu")

        if existing_pairs:
            existing_str = ', '.join([f"`{p.upper()}`" for p in existing_pairs])
            messages.append(f"\n⚠️ **Sudah menonton:** {existing_str}")

        final_message = '\n'.join(messages)

        await self._send_message(update, context, final_message, parse_mode='Markdown')

        # 🚀 BACKGROUND TASK: Load historical data PARALLEL (tidak blocking response!)
        if added_pairs:
            self._create_background_task(self._load_historical_background(added_pairs))
            # Send initial signals one-by-one as they complete
            for pair in added_pairs:
                self._create_background_task(self._send_initial_signal_background(pair, update, context))

    async def _send_initial_signal(self, pair, update, context):
        """Send initial trading signal after watching a pair"""
        try:
            # Always try to load from DB if memory cache is too small (<60)
            if pair not in self.historical_data or len(self.historical_data[pair]) < 60:
                await self._load_historical_data(pair)
            
            # Check if we have enough data in memory
            candle_count = len(self.historical_data.get(pair, []))
            logger.info(f"📊 Checking data for {pair}: {candle_count} candles available")

            if candle_count < 60:
                # Not enough data yet - show friendly message
                time_left = max(0, (60 - candle_count) * 5)  # 5s per candle
                text = f"""
⏳ <b>Collecting Data for {pair}</b>

📊 Candles: {candle_count}/60 needed for ML analysis
⏱️ Estimated time: ~{time_left//60}m {time_left%60}s

💡 <b>What's happening:</b>
• Bot polling prices every 5 seconds
• Building historical data for ML model
• Signals will appear when enough data collected

🔔 You'll receive signal automatically when ready!

💡 <b>Meanwhile:</b>
• Add more pairs: /watch btcidr
• Check status: /autotrade_status
• Manual price: /price {pair}
                """
                await self._send_message(update, context, text, parse_mode='HTML')
                return

            # Enough data - generate signal
            logger.info(f"📊 Generating signal for {pair} ({candle_count} candles)")
            signal = await self._generate_signal_for_pair(pair)

            if signal:
                # FILTER: Only send signal if it's useful (not weak HOLD)
                recommendation = signal.get('recommendation', 'HOLD')
                confidence = signal.get('ml_confidence', 0)
                
                # Skip if HOLD with low confidence (not useful)
                if recommendation == 'HOLD' and confidence < 0.5:
                    logger.debug(f"🔇 Skipping {pair} initial signal: HOLD with low confidence ({confidence:.1%})")
                    return  # Don't send useless HOLD signal
                
                text = self._format_signal_message_html(signal)
                await self._send_message(update, context, text, parse_mode='HTML')
            else:
                await self._send_message(update, context,
                    f"⚠️ <b>No clear signal for {pair}</b>\n\n"
                    f"Market conditions are unclear.\n"
                    f"Try again later.",
                    parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error sending initial signal: {e}")
            import traceback
            logger.error(f"Signal error traceback: {traceback.format_exc()}")

    async def _load_historical_background(self, pairs: list):
        """
        🚀 BACKGROUND TASK: Load historical data untuk multiple pairs PARALLEL
        Tidak blocking user command!
        """
        logger.info(f"🔄 Background loading historical data for {len(pairs)} pairs...")
        start = time.time()
        
        # Load semua pairs secara concurrent
        tasks = []
        for pair in pairs:
            if pair not in self.historical_data or len(self.historical_data[pair]) < 60:
                tasks.append(self._load_historical_data(pair))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success = sum(1 for r in results if not isinstance(r, Exception))
            failed = sum(1 for r in results if isinstance(r, Exception))
            
            elapsed = time.time() - start
            logger.info(f"✅ Background loaded {success}/{len(pairs)} pairs in {elapsed:.2f}s ({failed} failed)")
            
            # Notify user jika ada yang gagal
            if failed > 0:
                logger.warning(f"⚠️ {failed} pairs failed to load historical data")
        else:
            logger.info(f"✅ All {len(pairs)} pairs already have historical data")

    def _create_background_task(self, coro):
        """
        Create a background asyncio task with tracking for clean shutdown.
        Returns the task object.
        """
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        return task

    async def _send_initial_signal_background(self, pair, update, context):
        """
        🚀 BACKGROUND TASK: Send initial signal (tidak blocking command response)
        """
        try:
            logger.info(f"📊 Background generating signal for {pair}...")

            # Wait untuk data cukup (max 30 detik)
            waited = 0
            while waited < 30:
                # Check for shutdown
                if self.shutdown_event.is_set():
                    logger.info(f"🛑 Shutdown requested, canceling signal task for {pair}")
                    return
                    
                candle_count = len(self.historical_data.get(pair, []))
                if candle_count >= 60:
                    break
                try:
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    logger.info(f"⏹️ Task canceled while waiting for data: {pair}")
                    return
                waited += 2

            # Check if we have enough data
            candle_count = len(self.historical_data.get(pair, []))
            if candle_count < 60:
                time_left = max(0, (60 - candle_count) * 5)
                text = f"""
⏳ <b>Collecting Data for {pair}</b>

📊 Candles: {candle_count}/60 needed for ML analysis
⏱️ Estimated time: ~{time_left//60}m {time_left%60}s

💡 <b>What's happening:</b>
• Bot polling prices every 5 seconds
• Building historical data for ML model
• Signals will appear when enough data collected

🔔 You'll receive signal automatically when ready!
                """
                try:
                    await self._send_message(update, context, text, parse_mode='HTML')
                except Exception as e:
                    logger.warning(f"⚠️ Failed to send data collection message: {e}")
                return

            # Enough data - generate signal
            logger.info(f"📊 Generating signal for {pair} ({candle_count} candles)")
            signal = await self._generate_signal_for_pair(pair)

            if signal:
                # FILTER: Only send signal if it's useful (not weak HOLD)
                recommendation = signal.get('recommendation', 'HOLD')
                confidence = signal.get('ml_confidence', 0)

                # Skip if HOLD with low confidence (not useful)
                if recommendation == 'HOLD' and confidence < 0.5:
                    logger.debug(f"🔇 Skipping {pair} signal: HOLD with low confidence ({confidence:.1%})")
                    return  # Don't send useless HOLD signal

                text = self._format_signal_message_html(signal)
                try:
                    await self._send_message(update, context, text, parse_mode='HTML')
                except Exception as e:
                    logger.error(f"❌ Failed to send signal alert for {pair}: {e}")
            else:
                try:
                    await self._send_message(update, context,
                        f"⚠️ <b>No clear signal for {pair}</b>\n\n"
                        f"Market conditions are unclear.\n"
                        f"Try again later.",
                        parse_mode='HTML')
                except Exception as e:
                    logger.error(f"❌ Failed to send no-signal message for {pair}: {e}")

        except asyncio.CancelledError:
            logger.info(f"⏹️ Background signal task canceled for {pair}")
        except Exception as e:
            logger.error(f"❌ Background signal error for {pair}: {e}")

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape special Markdown characters to prevent parse errors"""
        # Escape characters that have special meaning in Markdown
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def _normalize_pair_for_indodax(self, pair: str) -> str:
        """
        Convert pair format for Indodax API.
        zenidr → zen_idr, btcidr → btc_idr, pippinidr → pippin_idr
        Handles both uppercase and lowercase.
        """
        pair_lower = pair.lower()

        # Already has underscore — return as-is
        if '_' in pair_lower:
            return pair_lower

        # Remove trailing 'idr' and insert '_idr'
        if pair_lower.endswith('idr') and len(pair_lower) > 3:
            base = pair_lower[:-3]
            return f"{base}_idr"

        # Unknown format — return as-is
        return pair_lower

    async def _send_message(self, update, context, text, **kwargs):
        """Helper to send message for both command and callback query"""
        try:
            # Try callback query first (inline button click)
            if update.callback_query:
                await update.callback_query.answer()
                try:
                    await update.callback_query.edit_message_text(text, **kwargs)
                    return
                except Exception:
                    # If edit fails, send new message
                    pass
        except Exception:
            pass
        
        # Fallback to regular message
        if update.message:
            await update.message.reply_text(text, **kwargs)
        elif update.effective_message:
            await update.effective_message.reply_text(text, **kwargs)
        elif update.callback_query:
            await update.callback_query.message.reply_text(text, **kwargs)
    
    async def unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unsubscribe from one or more pairs"""
        if not context.args:
            await self._send_message(update, context,
                "❌ **Format:** `/unwatch <PAIR>` atau `/unwatch <PAIR1>, <PAIR2>, ...`\n\n"
                "✅ **Contoh:**\n"
                "• `/unwatch btcidr, ethidr`\n"
                "• `/unwatch BTCIDR, SOL/IDR`\n\n"
                "💡 Format akan dinormalkan otomatis!",
                parse_mode='Markdown'
            )
            return

        user_id = update.effective_user.id
        
        # Parse comma-separated pairs
        pairs_input = ' '.join(context.args)
        raw_pairs_list = [p.strip() for p in pairs_input.split(',') if p.strip()]
        
        if not raw_pairs_list:
            await self._send_message(update, context,
                "❌ **Format:** `/unwatch <PAIR>` atau `/unwatch <PAIR1>, <PAIR2>, ...`\n\n"
                "✅ **Contoh:** `/unwatch btcidr, ethidr, solidr`",
                parse_mode='Markdown'
            )
            return

        # Normalize all pairs
        normalized_pairs = []
        norm_notes = []
        
        for pair_input in raw_pairs_list:
            # Normalize pair (same as /watch)
            pair = pair_input.replace('/', '').upper()
            if not pair.endswith('IDR'):
                pair = pair + 'IDR'
            
            normalized_pairs.append(pair)
            
            # Track normalization
            if pair_input.upper() != pair:
                norm_notes.append(f"`{pair_input}` → `{pair}`")

        if user_id not in self.subscribers:
            self.subscribers[user_id] = []

        # Process each pair
        removed_pairs = []
        not_watching = []
        
        for pair in normalized_pairs:
            if pair in self.subscribers[user_id]:
                # Remove from memory
                self.subscribers[user_id].remove(pair)
                removed_pairs.append(pair)
                
                # FIX: Remove from database (persistent storage)
                self._remove_watchlist_from_db(user_id, pair)
            else:
                not_watching.append(pair)

        # Build response
        messages = []
        
        if removed_pairs:
            pairs_str = ', '.join([f"`{p}`" for p in removed_pairs])
            messages.append(f"✅ **Berhenti menonton:** {pairs_str}")

            if norm_notes:
                messages.append("\n🔄 **Normalisasi:**")
                messages.extend(norm_notes)
        else:
            messages.append("⚠️ Tidak ada pair yang dihapus dari watchlist")

        if not_watching:
            not_watching_str = ', '.join([f"`{p}`" for p in not_watching])
            messages.append(f"\n❌ **Tidak ada di watchlist:** {not_watching_str}")

        if user_id in self.subscribers and len(self.subscribers[user_id]) == 0:
            messages.append("\n📋 Watchlist Anda sekarang kosong")
            messages.append("Gunakan `/watch <PAIR>` untuk menambahkan pair")
        elif user_id in self.subscribers:
            remaining = ', '.join([f"`{p}`" for p in self.subscribers[user_id]])
            messages.append(f"\n📋 **Watchlist tersisa:** {remaining}")

        final_message = '\n'.join(messages)
        
        await self._send_message(update, context, final_message, parse_mode='Markdown')
        
        if removed_pairs:
            logger.info(f"👤 User {user_id} unsubscribed from {removed_pairs}")

    async def list_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's watchlist"""
        user_id = update.effective_user.id

        if user_id in self.subscribers and self.subscribers[user_id]:
            pairs = '\n'.join([f"• `{self._escape_markdown(p)}`" for p in self.subscribers[user_id]])
            text = f"📋 **Your Watchlist ({len(self.subscribers[user_id])} pairs):**\n\n{pairs}"
            await self._send_message(update, context, text, parse_mode='Markdown')
        else:
            await self._send_message(update, context,
                "📋 Watchlist is empty!\n\nUse `/watch <PAIR>` to add pairs.",
                parse_mode='Markdown'
            )

    async def cleanup_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clean up incomplete signal records from database (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in Config.ADMIN_IDS:
            await update.effective_message.reply_text("❌ Admin only!")
            return
        
        msg = await update.effective_message.reply_text(
            "🔍 **Checking for incomplete signals...**\n\n⏳ Please wait...",
            parse_mode='Markdown'
        )
        
        try:
            # Initialize signal DB if not already done
            if not hasattr(self, '_signal_db'):
                from signals.signal_db import SignalDatabase
                self._signal_db = SignalDatabase("data/signals.db")
                logger.info("✅ Signal database initialized for cleanup")
            
            total_before = self._signal_db.get_total_count()
            deleted = self._signal_db.cleanup_incomplete_signals()
            total_after = self._signal_db.get_total_count()
            
            if deleted > 0:
                text = (
                    f"🗑️ **Signal Cleanup Complete!**\n\n"
                    f"• Records before: `{total_before}`\n"
                    f"• Incomplete deleted: `{deleted}`\n"
                    f"• Records after: `{total_after}`\n\n"
                    f"✅ Only signals with complete data remain"
                )
            else:
                text = (
                    f"✅ **No incomplete signals found!**\n\n"
                    f"• Total records: `{total_before}`\n"
                    f"• All signals have complete data"
                )
            
            await msg.edit_text(text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Signal cleanup error: {e}")
            try:
                await msg.edit_text(f"❌ Error during cleanup:\n\n`{str(e)}`", parse_mode='Markdown')
            except Exception:
                await update.effective_message.reply_text(f"❌ Error: {str(e)}")

    async def reset_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reset skipped/invalid pairs blacklist (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in Config.ADMIN_IDS:
            await update.effective_message.reply_text("❌ Admin only!")
            return
        
        if hasattr(self, 'price_poller') and self.price_poller:
            count = self.price_poller.reset_invalid_pairs()
            text = (
                f"🔄 **Skipped Pairs Reset!**\n\n"
                f"• `{count}` pairs removed from skip list\n"
                f"• Bot will retry polling these pairs\n\n"
                f"💡 Pairs will be re-tested on next poll cycle"
            )
        else:
            text = "⚠️ **Price poller not found**\n\nBot may need to be restarted."
        
        await update.effective_message.reply_text(text, parse_mode='Markdown')

    async def clear_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear ALL pairs from watchlist (from database)"""
        user_id = update.effective_user.id
        
        # Check if admin (only admins can clear all watchlists)
        is_admin = user_id in Config.ADMIN_IDS
        
        if not is_admin and not context.args:
            # Regular user: clear their own watchlist
            self._clear_watchlist_in_db(user_id)
            self.subscribers[user_id] = []
            
            await self._send_message(update, context,
                "🗑️ **Watchlist Cleared!**\n\n"
                "Semua pair telah dihapus dari watchlist Anda.\n"
                "Gunakan `/watch <PAIR>` untuk menambahkan pair baru.",
                parse_mode='Markdown'
            )
            return
        
        if is_admin and (not context.args or context.args[0].lower() != 'all'):
            # Admin without 'all' arg: clear their own watchlist
            self._clear_watchlist_in_db(user_id)
            self.subscribers[user_id] = []
            
            await self._send_message(update, context,
                "🗑️ **Watchlist Anda Cleared!**\n\n"
                "Gunakan `/clear_watchlist all` untuk hapus SEMUA watchlist semua user.",
                parse_mode='Markdown'
            )
            return
        
        if is_admin and context.args and context.args[0].lower() == 'all':
            # Admin with 'all' arg: clear ALL watchlists
            deleted_count = self.db.clear_all_watchlists()
            self.subscribers.clear()
            
            await self._send_message(update, context,
                f"🗑️ **SEMUA WATCHLIST CLEARED!**\n\n"
                f"• {deleted_count} records dihapus dari database\n"
                f"• Semua user watchlist dikosongkan\n"
                f"• Bot siap untuk fresh start",
                parse_mode='Markdown'
            )
            return

    async def price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Quick price check for a pair"""
        if not context.args:
            await self._send_message(update, context,
                "❌ **Format:** `/price <PAIR>`\nExample: `/price BTC/IDR`",
                parse_mode='Markdown'
            )
            return

        pair = context.args[0].upper()
        pair_escaped = self._escape_markdown(pair)
        await self._send_message(update, context, f"🔄 Fetching price for {pair_escaped}...")

        try:
            # ALWAYS fetch fresh price from API first
            from api.indodax_api import IndodaxAPI
            indodax = IndodaxAPI()
            ticker = indodax.get_ticker(pair)
            
            if ticker:
                change_pct = ticker.get('change_percent', 0)
                change_sign = '+' if change_pct >= 0 else ''

                text = f"""
💰 **{pair_escaped} - Current Price**

📊 Price: `{Utils.format_price(ticker['last'])}` IDR
📈 24h Change: `{change_sign}{change_pct:.2f}%`
💧 Volume: `{Utils.format_price(ticker['volume'])}`
🟢 Bid: `{Utils.format_price(ticker['bid'])}` IDR
🔴 Ask: `{Utils.format_price(ticker['ask'])}` IDR

⏰ Updated: {datetime.now().strftime('%H:%M:%S')}
                """
                await self._send_message(update, context, text, parse_mode='Markdown')
                
                # Update cache
                self.price_data[pair] = {
                    'last': ticker['last'],
                    'volume': ticker['volume'],
                    'change_percent': change_pct,
                    'timestamp': datetime.now()
                }

                # Also write to Redis cache
                try:
                    redis_price_cache.set_price(pair, ticker['last'])
                except Exception as e:
                    logger.debug(f"Redis cache write failed: {e}")

                # Show Redis status
                redis_status = "🔴 Dict" if not redis_price_cache.is_redis_available() else "🟢 Redis"
                text += f"\n💾 Cache: {redis_status}"

                await self._send_message(update, context, text, parse_mode='Markdown')
            else:
                await self._send_message(update, context,
                    f"❌ Failed to fetch price for {pair_escaped}")
        except Exception as e:
            logger.error(f"Error fetching price for {pair}: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}")
    
    async def get_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate and send trading signal for a pair"""
        if not context.args:
            await self._send_message(update, context,
                "❌ **Format:** `/signal <PAIR>`\nExample: `/signal BTC/IDR`",
                parse_mode='Markdown'
            )
            return

        # Get pair and sanitize
        pair_raw = context.args[0].strip().upper()
        
        # Remove accidental command prefixes
        prefixes_to_remove = [
            'WATCH ', 'WATCH/', 'WATCH', 
            '/WATCH ', 'WATCH ', 'W/',
            'SIGNAL ', 'SIGNAL/', 'SIGNAL',
            '/SIGNAL ', 'PRICE ', 'PRICE/',
            '/PRICE '
        ]
        
        pair_clean = pair_raw
        for prefix in prefixes_to_remove:
            if pair_clean.startswith(prefix):
                pair_clean = pair_clean[len(prefix):].strip()
        
        # Remove any remaining slashes at the start
        pair_clean = pair_clean.lstrip('/')
        
        pair = pair_clean

        await self._send_message(update, context, f"🔄 Analyzing {pair}...\n\n⏳ Loading data...", parse_mode='HTML')

        try:
            # Load data if not available
            if pair not in self.historical_data or self.historical_data[pair].empty:
                await self._load_historical_data(pair)

            # Check if we have data now
            if pair not in self.historical_data or self.historical_data[pair].empty:
                await self._send_message(update, context,
                    f"❌ <b>No data available for {pair}</b>\n\n"
                    f"⚠️ Bot needs historical data to analyze.\n\n"
                    f"💡 <b>Solution:</b>\n"
                    f"1. Use <code>/watch {pair}</code> first to subscribe\n"
                    f"2. Wait a few minutes for data collection\n"
                    f"3. Then try <code>/signal {pair}</code> again",
                    parse_mode='HTML')
                return

            signal = await self._generate_signal_for_pair(pair)

            if signal:
                text = self._format_signal_message_html(signal)
                await self._send_message(update, context, text, parse_mode='HTML')
            else:
                # Signal is None - data issue
                candle_count = len(self.historical_data.get(pair, []))
                await self._send_message(update, context,
                    f"⚠️ <b>Still collecting data for {pair}</b>\n\n"
                    f"📊 Candles: {candle_count}/60\n"
                    f"⏱️ Please wait a few more minutes.\n"
                    f"Bot will auto-generate signal when ready!",
                    parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error generating signal for {pair}: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}", parse_mode='HTML')

    async def analyze_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Quick BUY/SELL analysis for a pair using AnalyzeSignals"""
        if not context.args:
            await self._send_message(update, context,
                "❌ **Format:** `/analyze <PAIR>`\nExample: `/analyze BTC/IDR`",
                parse_mode='Markdown'
            )
            return

        pair = context.args[0].strip().upper()
        pair_clean = pair.lstrip('/')
        
        await self._send_message(update, context, f"🔄 Analyzing {pair_clean}...", parse_mode='HTML')

        try:
            analyzer = AnalyzeSignals()
            result = await analyzer.analyze(pair_clean)
            message = analyzer.format_message(result)
            await self._send_message(update, context, message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error in analyze_signal for {pair}: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}", parse_mode='HTML')

    async def position(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Analyze open position for a pair with order book analysis"""
        if not context.args:
            await self._send_message(update, context,
                "❌ **Format:** `/position <PAIR>`\nExample: `/position BTC/IDR`",
                parse_mode='Markdown'
            )
            return

        pair = context.args[0].upper().strip()
        pair_escaped = self._escape_markdown(pair)
        user_id = update.effective_user.id

        await self._send_message(update, context,
            f"🔍 **Analyzing Position for {pair_escaped}**\n\n⏳ Loading data...")

        try:
            # Get ALL trades for this pair (both OPEN and CLOSED)
            all_trades = self.db.get_trades_for_pair(user_id, pair)
            pair_trades = list(all_trades)  # Convert to list for indexing

            # Get current price — Redis cache first, then dict, then API
            current_price = None

            # Phase 2: Try Redis cache first
            try:
                redis_cached = redis_price_cache.get_price_sync(pair)
                if redis_cached is not None and redis_cached > 0:
                    current_price = redis_cached
                    logger.debug(f"💾 Position {pair}: Using Redis cache price")
            except Exception:
                pass

            # Fallback: local dict
            if current_price is None:
                if pair in self.price_data:
                    current_price = self.price_data[pair]['last']

            # Last resort: Fetch from API
            if current_price is None:
                ticker = self.indodax.get_ticker(pair)
                if ticker:
                    current_price = ticker['last']
                    self.price_data[pair] = ticker
                    # Also update Redis
                    try:
                        redis_price_cache.set_price(pair, current_price)
                    except Exception:
                        pass

            if not current_price:
                await self._send_message(update, context,
                    f"❌ **No price data for {pair_escaped}**\n\n"
                    f"Use `/watch {pair_escaped}` first to get real-time data.",
                    parse_mode='Markdown'
                )
                return

            # Get order book
            orderbook = None
            bids = []
            asks = []
            try:
                orderbook = self.indodax.get_orderbook(pair, limit=20)
                if orderbook:
                    bids = orderbook.get('bids', [])
                    asks = orderbook.get('asks', [])
            except Exception as e:
                logger.warning(f"Order book unavailable for {pair}: {e}")

            # Build analysis text
            text = f"📊 **POSITION ANALYSIS: {pair_escaped}**\n\n"
            text += f"🕐 Updated: {datetime.now().strftime('%H:%M:%S')}\n"
            text += "=" * 40 + "\n\n"

            # Section 1: Current Position
            text += "🔹 **1. YOUR POSITIONS**\n\n"

            if not pair_trades:
                text += "⚠️ **No open positions for this pair**\n\n"
                text += "You haven't bought this asset yet.\n\n"
                text += "💡 **To start trading:**\n"
                text += "`/trade BUY <PAIR> <PRICE> <AMOUNT_IDR>`\n\n"
            else:
                total_invested = 0
                total_amount = 0
                total_unrealized_pnl = 0
                has_open_position = False
                
                # Limit displayed trades to avoid Telegram message length limit (4096 chars)
                # Show max 3 OPEN trades + last 3 CLOSED trades
                open_trades = [t for t in pair_trades if t['status'] == 'OPEN'][:3]
                closed_trades = [t for t in pair_trades if t['status'] == 'CLOSED'][:3]
                displayed_trades = open_trades + closed_trades
                
                trades_skipped = len(pair_trades) - len(displayed_trades)

                # Database returns trades sorted: OPEN first, then CLOSED, all by date DESC
                for idx, trade in enumerate(displayed_trades):
                    entry_price = trade['price']
                    amount = trade['amount']
                    invested = trade['total']
                    opened_at = trade['opened_at']
                    trade_type = trade['type']
                    status = trade['status']
                    trade_id = trade['id']

                    # Check if trade is OPEN or CLOSED
                    is_open = status == 'OPEN'

                    if is_open:
                        has_open_position = True
                        # Calculate unrealized PnL for OPEN trades
                        if invested > 0 and amount > 0:
                            unrealized_pnl = (current_price - entry_price) * amount
                            unrealized_pnl_pct = (unrealized_pnl / invested) * 100
                            total_unrealized_pnl += unrealized_pnl
                            total_invested += invested
                            total_amount += amount

                            status_emoji = "🟢" if unrealized_pnl >= 0 else "🔴"
                            pnl_sign = "+" if unrealized_pnl >= 0 else ""
                            pnl_text = f"`{pnl_sign}{Utils.format_currency(unrealized_pnl)}` ({pnl_sign}{unrealized_pnl_pct:.2f}%)"
                            # current_price used implicitly in pnl calculation
                        else:
                            # Skip invalid trades
                            logger.warning(f"Skipping invalid trade {trade_id}: invested={invested}, amount={amount}")
                            continue
                    else:
                        # CLOSED trade - use realized PnL from database
                        realized_pnl = trade['profit_loss'] if trade['profit_loss'] else 0
                        realized_pnl_pct = trade['profit_loss_pct'] if trade['profit_loss_pct'] else 0
                        closed_at = trade['closed_at'] if trade['closed_at'] else ''
                        
                        status_emoji = "🟢" if realized_pnl >= 0 else "🔴"
                        pnl_sign = "+" if realized_pnl >= 0 else ""
                        pnl_text = f"`{pnl_sign}{Utils.format_currency(realized_pnl)}` ({pnl_sign}{realized_pnl_pct:.2f}%) ✅"

                        # Format opened_at - handle both string and datetime
                        if isinstance(opened_at, str):
                            try:
                                from datetime import datetime as dt
                                opened_at_dt = dt.strptime(opened_at, '%Y-%m-%d %H:%M:%S')
                                opened_at_str = opened_at_dt.strftime('%d/%m %H:%M')
                            except Exception:
                                opened_at_str = opened_at[:16].replace('-', '/').replace('T', ' ')
                        else:
                            opened_at_str = opened_at.strftime('%d/%m %H:%M')

                        # Format closed_at
                        if closed_at:
                            if isinstance(closed_at, str):
                                try:
                                    from datetime import datetime as dt
                                    closed_at_dt = dt.strptime(closed_at, '%Y-%m-%d %H:%M:%S')
                                    closed_at_str = closed_at_dt.strftime('%d/%m %H:%M')
                                except Exception:
                                    closed_at_str = closed_at[:16]
                            else:
                                closed_at_str = closed_at.strftime('%d/%m %H:%M')
                            opened_at_str = f"{opened_at_str} → {closed_at_str}"

                    # Display label based on status and position
                    if idx == 0 and is_open:
                        text += f"🔥 **Latest {trade_type}** (OPEN)\n"
                    elif idx == 0 and not is_open:
                        text += f"🔥 **Last {trade_type}** (CLOSED)\n"
                    elif is_open:
                        text += f"{status_emoji} **{trade_type}** (OPEN)\n"
                    else:
                        text += f"{status_emoji} **{trade_type}** (CLOSED)\n"
                    
                    text += f"`{Utils.format_price(entry_price)}` | `{amount:.0f}` | {pnl_text} | `{opened_at_str}` | ID:{trade_id}\n\n"

                # Summary - only for OPEN positions
                if has_open_position:
                    overall_pnl_pct = (total_unrealized_pnl / total_invested) * 100 if total_invested > 0 else 0
                    overall_emoji = "🟢" if total_unrealized_pnl >= 0 else "🔴"
                    pnl_sign = "+" if total_unrealized_pnl >= 0 else ""

                    text += f"{overall_emoji} **TOTAL: **`{pnl_sign}{Utils.format_currency(total_unrealized_pnl)}` ({pnl_sign}{overall_pnl_pct:.2f}%)\n\n"
                else:
                    text += "✅ **All positions closed**\n\n"
                
                # Add note if some trades were skipped
                if trades_skipped > 0:
                    text += f"ℹ️ _Showing latest {len(displayed_trades)} trades ({trades_skipped} older trades hidden)_\n\n"

            # Section 2: Order Book Analysis
            if bids or asks:
                text += "🔹 **2. ORDER BOOK**\n"
                
                if bids and asks:
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    text += f"Bid: `{Utils.format_price(best_bid)}` | Ask: `{Utils.format_price(best_ask)}`\n"
                
                if bids:
                    bid_zones = []
                    for bid in bids[:10]:
                        price = float(bid[0])
                        amount = float(bid[1])
                        total = float(bid[2]) if len(bid) > 2 else price * amount
                        bid_zones.append((price, total))
                    sorted_bids = sorted(bid_zones, key=lambda x: x[1], reverse=True)[:3]
                    if sorted_bids:
                        text += f"🟢 Support: `{Utils.format_price(sorted_bids[0][0])}` ({Utils.format_currency(sorted_bids[0][1])})\n"
                
                if asks:
                    ask_zones = []
                    for ask in asks[:10]:
                        price = float(ask[0])
                        amount = float(ask[1])
                        total = float(ask[2]) if len(ask) > 2 else price * amount
                        ask_zones.append((price, total))
                    sorted_asks = sorted(ask_zones, key=lambda x: x[1], reverse=True)[:3]
                    if sorted_asks:
                        text += f"🔴 Resistance: `{Utils.format_price(sorted_asks[0][0])}` ({Utils.format_currency(sorted_asks[0][1])})\n"
                text += "\n"
            else:
                text += "🔹 **2. ORDER BOOK ANALYSIS**\n\n"
                text += "⚠️ **Order book data unavailable**\n\n"
                text += "Indodax API tidak menyediakan order book untuk pair ini.\n"
                text += "Analisis dilanjutkan tanpa data order book.\n\n"

            # Section 4: Strategy Recommendations
            if pair_trades and has_open_position:
                pnl_pct = overall_pnl_pct
                
                if pnl_pct < -5:
                    rec_text = "🔴 DEEP LOSS - Consider Cut Loss/Hold/Average Down"
                elif pnl_pct < 0:
                    rec_text = "🟠 SMALL LOSS - Hold/Cut Loss/Average Down"
                elif pnl_pct < 5:
                    rec_text = "🟢 SMALL PROFIT - Hold/Take Partial/Set SL"
                else:
                    rec_text = "🟢🟢 GOOD PROFIT - Take Profit/Trailing Stop"
                
                tp_5 = current_price * 1.05
                tp_10 = current_price * 1.10
                sl = current_price * 0.98 if bids else 0
                
                text += f"🔹 **STRATEGY:** {rec_text}\n"
                text += f"TP 5%: `{Utils.format_price(tp_5)}` | TP 10%: `{Utils.format_price(tp_10)}`"
                if sl > 0:
                    text += f" | SL: `{Utils.format_price(sl)}`"
                text += "\n\n"

            # Section 5: Market Context
            text += "🔹 **MARKET:** "
            
            if pair in self.price_data:
                change_pct = self.price_data[pair].get('change_percent', 0)
                change_emoji = "📈" if change_pct >= 0 else "📉"
                change_sign = "+" if change_pct >= 0 else ""
                text += f"{change_emoji} 24h: `{change_sign}{change_pct:.2f}%` | "
            
            # Add ML signal if available
            if pair in self.historical_data and not self.historical_data[pair].empty:
                try:
                    signal = await self._generate_signal_for_pair(pair)
                    if signal:
                        rec = signal['recommendation']
                        conf = signal['ml_confidence']
                        rec_emoji = {'STRONG_BUY': '🚀', 'BUY': '📈', 'HOLD': '⏸️', 'SELL': '📉', 'STRONG_SELL': '🔻'}.get(rec, '❓')
                        text += f"{rec_emoji} ML: {rec} ({conf:.0%})\n"
                except Exception:
                    text += "\n"
            else:
                text += "\n"

            text += "\n" + "=" * 40
            
            # Auto-Trade Status Indicator
            text += "\n\n🤖 **AUTO-TRADE STATUS:**\n"
            if self.is_trading:
                is_dry = Config.AUTO_TRADE_DRY_RUN
                if is_dry:
                    text += "🧪 **DRY RUN MODE** - Aktif (Simulasi)\n"
                    text += "• ✅ Bot scanning setiap 5 menit\n"
                    text += "• ✅ Simulasi trade (no real money)\n"
                    text += "• 📊 Use `/autotrade_status` untuk detail\n"
                else:
                    text += "🔴 **REAL TRADING** - Aktif ⚠️\n"
                    text += "• 🚨 Bot scanning setiap 5 menit\n"
                    text += "• 🚨 Real orders ke Indodax\n"
                    text += "• 📊 Use `/autotrade_status` untuk detail\n"
            else:
                text += "⏸️ **Auto-Trade: OFF**\n"
                text += "• ❌ Bot tidak scanning untuk auto-trade\n"
                text += "• 💡 Use `/autotrade dryrun` untuk enable simulasi\n"
            
            text += f"\n\n💡 Commands: `/trade SELL {pair_escaped} <PRICE> <AMOUNT>` | `/set_sl <ID> <PRICE>`"

            await self._send_message(update, context, text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in position analysis: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}")

    async def signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trading signals for all watched pairs - runs in background thread"""
        user_id = update.effective_user.id

        # Get user's watched pairs (from memory, synced with DB)
        watched_pairs = self.subscribers.get(user_id, [])
        
        # Debug: Log source of watchlist
        logger.info(f"📊 /signals command - User {user_id}: {len(watched_pairs)} pairs from memory cache")
        if not watched_pairs:
            # Check if pairs exist in DB
            db_pairs = self.db.get_watchlist(user_id)
            if db_pairs:
                logger.warning(f"⚠️ Memory empty but DB has {len(db_pairs)} pairs - syncing...")
                self.subscribers[user_id] = db_pairs
                watched_pairs = db_pairs

        if not watched_pairs:
            await self._send_message(update, context,
                "📋 No watched pairs\n\n"
                "Use /watch <PAIR> to start monitoring.")
            return
        
        # Send initial message immediately
        await self._send_message(update, context, 
            f"🔄 Analyzing {len(watched_pairs)} pairs...\n\n⏳ Running in background - will send results when ready...")
        
        # Run signal generation in background thread using executor
        import asyncio
        import concurrent.futures
        
        def _generate_signals_in_background():
            """Generate signals in background thread"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                buy_signals = []
                sell_signals = []
                hold_signals = []
                
                for pair in watched_pairs:
                    try:
                        # Run async signal generation in new loop
                        signal = loop.run_until_complete(self._generate_signal_for_pair(pair))
                        
                        if signal:
                            rec = signal['recommendation']
                            price = signal['price']
                            confidence = signal['ml_confidence']
                            
                            if rec in ['STRONG_BUY', 'BUY']:
                                emoji = 'BUY' if rec == 'STRONG_BUY' else 'BUY'
                                buy_signals.append((pair, price, rec, confidence, emoji))
                            elif rec in ['STRONG_SELL', 'SELL']:
                                emoji = 'SELL' if rec == 'STRONG_SELL' else 'SELL'
                                sell_signals.append((pair, price, rec, confidence, emoji))
                            else:
                                hold_signals.append((pair, price, rec, confidence, 'HOLD'))
                    except Exception as e:
                        logger.debug(f"Signal error for {pair}: {e}")
                
                return buy_signals, sell_signals, hold_signals
            finally:
                loop.close()
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            buy_signals, sell_signals, hold_signals = await loop.run_in_executor(
                None, _generate_signals_in_background)
        except Exception as e:
            logger.error(f"❌ /signals error: {e}")
            await self._send_message(update, context, f"❌ Error generating signals: {str(e)}")
            return
        
        # Format output
        signals_text = "📊 TRADING OPPORTUNITIES\n\n"
        signals_text += f"Updated: {datetime.now().strftime('%H:%M:%S')}\n\n"
        signals_text += "=" * 40 + "\n\n"
        
        if buy_signals:
            signals_text += "🟢 BUY OPPORTUNITIES\n"
            for pair, price, rec, conf, emoji in sorted(buy_signals, key=lambda x: x[3], reverse=True):
                signals_text += f"\n{emoji} {pair} - {Utils.format_price(price)} IDR\n"
                signals_text += f"   Signal: {rec} | Confidence: {conf:.0%}\n"

        if sell_signals:
            signals_text += "\n🔴 SELL OPPORTUNITIES\n"
            for pair, price, rec, conf, emoji in sorted(sell_signals, key=lambda x: x[3], reverse=True):
                signals_text += f"\n{emoji} {pair} - {Utils.format_price(price)} IDR\n"
                signals_text += f"   Signal: {rec} | Confidence: {conf:.0%}\n"

        if hold_signals:
            signals_text += "\n⏸️ HOLD / NEUTRAL\n"
            for pair, price, rec, conf, emoji in hold_signals:
                signals_text += f"\n{emoji} {pair} - {Utils.format_price(price)} IDR\n"
        
        if not buy_signals and not sell_signals and not hold_signals:
            signals_text += "⚠️ No signals available yet\n\n"
            signals_text += "Pairs need 60+ candles of data.\n"
            signals_text += "Use /watch to add more pairs.\n"
        
        signals_text += "\n" + "=" * 40
        
        # Auto-Trade Status
        signals_text += "\n\n🤖 AUTO-TRADE STATUS:\n"
        if self.is_trading:
            is_dry = Config.AUTO_TRADE_DRY_RUN
            if is_dry:
                signals_text += "🧪 DRY RUN MODE - Aktif (Simulasi)\n"
            else:
                signals_text += "🔴 REAL TRADING - Aktif\n"
        else:
            signals_text += "⏸️ Auto-Trade: OFF\n"
        
        try:
            await self._send_message(update, context, signals_text)
        except Exception as e:
            logger.warning(f"Error sending /signals: {e}")
            await self._send_message(update, context, signals_text)
        
    async def signal_buy_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show BUY/STRONG_BUY signals for all watched pairs"""
        user_id = update.effective_user.id
        watched_pairs = self.subscribers.get(user_id, [])
        
        if not watched_pairs:
            db_pairs = self.db.get_watchlist(user_id)
            if db_pairs:
                self.subscribers[user_id] = db_pairs
                watched_pairs = db_pairs
        
        if not watched_pairs:
            await self._send_message(update, context, "No watched pairs. Use /watch <PAIR> to add.")
            return
        
        await self._send_message(update, context, f"🔄 Scanning {len(watched_pairs)} pairs for BUY signals...\n\n⏳ Please wait...")
        
        # Run in background
        import asyncio
        def _scan_buy():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                buy_results = []
                for pair in watched_pairs:
                    try:
                        signal = loop.run_until_complete(self._generate_signal_for_pair(pair))
                        if signal and signal.get('recommendation') in ['BUY', 'STRONG_BUY']:
                            buy_results.append(signal)
                    except:
                        pass
                return buy_results
            finally:
                loop.close()
        
        loop = asyncio.get_event_loop()
        buy_signals = await loop.run_in_executor(None, _scan_buy)
        
        if not buy_signals:
            await self._send_message(update, context, f"🔴 No BUY signals found in {len(watched_pairs)} pairs.")
            return
        
        # Format results
        result = f"🟢 BUY SIGNALS ({len(buy_signals)} found)\n\n"
        for sig in sorted(buy_signals, key=lambda x: x.get('ml_confidence', 0), reverse=True):
            result += f"• {sig['pair'].upper()}: {sig.get('recommendation')} ({sig.get('ml_confidence', 0):.0%})\n"
            result += f"  Price: {Utils.format_price(sig.get('price', 0))} IDR\n\n"
        
        await self._send_message(update, context, result)

    async def signal_sell_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show SELL/STRONG_SELL signals for all watched pairs"""
        user_id = update.effective_user.id
        watched_pairs = self.subscribers.get(user_id, [])
        
        if not watched_pairs:
            db_pairs = self.db.get_watchlist(user_id)
            if db_pairs:
                self.subscribers[user_id] = db_pairs
                watched_pairs = db_pairs
        
        if not watched_pairs:
            await self._send_message(update, context, "No watched pairs. Use /watch <PAIR> to add.")
            return
        
        await self._send_message(update, context, f"🔄 Scanning {len(watched_pairs)} pairs for SELL signals...\n\n⏳ Please wait...")
        
        import asyncio
        def _scan_sell():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sell_results = []
                for pair in watched_pairs:
                    try:
                        signal = loop.run_until_complete(self._generate_signal_for_pair(pair))
                        if signal and signal.get('recommendation') in ['SELL', 'STRONG_SELL']:
                            sell_results.append(signal)
                    except:
                        pass
                return sell_results
            finally:
                loop.close()
        
        loop = asyncio.get_event_loop()
        sell_signals = await loop.run_in_executor(None, _scan_sell)
        
        if not sell_signals:
            await self._send_message(update, context, f"🔴 No SELL signals found in {len(watched_pairs)} pairs.")
            return
        
        result = f"🔴 SELL SIGNALS ({len(sell_signals)} found)\n\n"
        for sig in sorted(sell_signals, key=lambda x: x.get('ml_confidence', 0), reverse=True):
            result += f"• {sig['pair'].upper()}: {sig.get('recommendation')} ({sig.get('ml_confidence', 0):.0%})\n"
            result += f"  Price: {Utils.format_price(sig.get('price', 0))} IDR\n\n"
        
        await self._send_message(update, context, result)

    async def signal_hold_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show HOLD signals for all watched pairs"""
        user_id = update.effective_user.id
        watched_pairs = self.subscribers.get(user_id, [])
        
        if not watched_pairs:
            db_pairs = self.db.get_watchlist(user_id)
            if db_pairs:
                self.subscribers[user_id] = db_pairs
                watched_pairs = db_pairs
        
        if not watched_pairs:
            await self._send_message(update, context, "No watched pairs. Use /watch <PAIR> to add.")
            return
        
        await self._send_message(update, context, f"🔄 Scanning {len(watched_pairs)} pairs for HOLD signals...\n\n⏳ Please wait...")
        
        import asyncio
        def _scan_hold():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                hold_results = []
                for pair in watched_pairs:
                    try:
                        signal = loop.run_until_complete(self._generate_signal_for_pair(pair))
                        if signal and signal.get('recommendation') == 'HOLD':
                            hold_results.append(signal)
                    except:
                        pass
                return hold_results
            finally:
                loop.close()
        
        loop = asyncio.get_event_loop()
        hold_signals = await loop.run_in_executor(None, _scan_hold)
        
        if not hold_signals:
            await self._send_message(update, context, f"No HOLD signals found in {len(watched_pairs)} pairs.")
            return
        
        result = f"⏸️ HOLD SIGNALS ({len(hold_signals)} found)\n\n"
        for sig in sorted(hold_signals, key=lambda x: x.get('ml_confidence', 0), reverse=True):
            result += f"• {sig['pair'].upper()}: HOLD ({sig.get('ml_confidence', 0):.0%})\n"
            result += f"  Price: {Utils.format_price(sig.get('price', 0))} IDR\n\n"
        
        await self._send_message(update, context, result)

    async def signal_buysell(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show BUY and SELL signals for all watched pairs (no HOLD)"""
        user_id = update.effective_user.id
        watched_pairs = self.subscribers.get(user_id, [])
        
        if not watched_pairs:
            db_pairs = self.db.get_watchlist(user_id)
            if db_pairs:
                self.subscribers[user_id] = db_pairs
                watched_pairs = db_pairs
        
        if not watched_pairs:
            await self._send_message(update, context, "No watched pairs. Use /watch <PAIR> to add.")
            return
        
        await self._send_message(update, context, f"🔄 Scanning {len(watched_pairs)} pairs for BUY/SELL signals...\n\n⏳ Please wait...")
        
        import asyncio
        def _scan_buysell():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                buy_results = []
                sell_results = []
                for pair in watched_pairs:
                    try:
                        signal = loop.run_until_complete(self._generate_signal_for_pair(pair))
                        if signal:
                            rec = signal.get('recommendation')
                            if rec in ['BUY', 'STRONG_BUY']:
                                buy_results.append(signal)
                            elif rec in ['SELL', 'STRONG_SELL']:
                                sell_results.append(signal)
                    except:
                        pass
                return buy_results, sell_results
            finally:
                loop.close()
        
        loop = asyncio.get_event_loop()
        buy_signals, sell_signals = await loop.run_in_executor(None, _scan_buysell)
        
        result = f"📊 BUY/SELL SIGNALS\n\n"
        
        if buy_signals:
            result += f"🟢 BUY ({len(buy_signals)} found)\n"
            for sig in sorted(buy_signals, key=lambda x: x.get('ml_confidence', 0), reverse=True):
                result += f"• {sig['pair'].upper()}: {sig.get('ml_confidence', 0):.0%}\n"
            result += "\n"
        
        if sell_signals:
            result += f"🔴 SELL ({len(sell_signals)} found)\n"
            for sig in sorted(sell_signals, key=lambda x: x.get('ml_confidence', 0), reverse=True):
                result += f"• {sig['pair'].upper()}: {sig.get('ml_confidence', 0):.0%}\n"
        
        if not buy_signals and not sell_signals:
            result = f"No BUY/SELL signals found in {len(watched_pairs)} pairs. All are HOLD."
        
        await self._send_message(update, context, result)

    async def notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Show recent signal notifications that were sent to admins.
        Displays history of BUY/SELL/STRONG_BUY/STRONG_SELL signals.
        """
        # Get recent signal history from _last_signal_checks
        if not hasattr(self, '_last_signal_checks') or not self._last_signal_checks:
            await self._send_message(update, context,
                "📭 **NO RECENT NOTIFICATIONS**\n\n"
                "Bot belum mengirim notifikasi sinyal.\n\n"
                "💡 **Syarat notifikasi:**\n"
                "• Pair harus di `/watch` dulu\n"
                "• Butuh 60+ candles (~15 menit)\n"
                "• Hanya sinyal kuat: BUY/SELL/STRONG_BUY/STRONG_SELL\n\n"
                "📋 **Command:**\n"
                "• `/signals` - Lihat sinyal saat ini\n"
                "• `/watch <pair>` - Tambah pair ke watchlist",
                parse_mode='Markdown'
            )
            return

        # Build notification history
        text = "🔔 **RECENT SIGNAL NOTIFICATIONS**\n\n"
        text += "🕐 Last Updated: " + datetime.now().strftime('%H:%M:%S') + "\n\n"
        
        # Sort by most recent
        sorted_checks = sorted(
            self._last_signal_checks.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Show last 10 notifications
        count = 0
        for pair, last_check_time in sorted_checks[:10]:
            try:
                time_ago = (datetime.now() - last_check_time).total_seconds()
                if time_ago < 60:
                    time_str = f"{time_ago:.0f} detik yang lalu"
                elif time_ago < 3600:
                    time_str = f"{time_ago/60:.0f} menit yang lalu"
                else:
                    time_str = f"{time_ago/3600:.1f} jam yang lalu"

                # Generate current signal for this pair
                signal = await self._generate_signal_for_pair(pair)
                if signal:
                    rec = signal.get('recommendation', 'HOLD')
                    confidence = signal.get('ml_confidence', 0)
                    price = signal.get('price', 0)

                    # Only show if it's a strong signal
                    if rec in ['STRONG_BUY', 'STRONG_SELL', 'BUY', 'SELL']:
                        emoji = '🚀' if rec == 'STRONG_BUY' else '📉' if rec == 'STRONG_SELL' else '📈' if rec == 'BUY' else '📉'
                        text += f"{emoji} **{pair.upper()}** - `{rec}`\n"
                        text += f"   💰 Price: `{Utils.format_price(price)}` IDR\n"
                        text += f"   🎯 Confidence: `{confidence:.1%}`\n"
                        text += f"   ⏰ Last check: {time_str}\n\n"
                        count += 1
            except Exception as e:
                logger.debug(f"Notification display error for {pair}: {e}")
                continue

        if count == 0:
            text += "⏸️ **NO STRONG SIGNALS RECENTLY**\n\n"
            text += "Tidak ada sinyal kuat (BUY/SELL) dalam beberapa menit terakhir.\n\n"
            text += "💡 **Tips:**\n"
            text += "• Bot butuh 60+ candles untuk generate sinyal\n"
            text += "• Notifikasi dikirim setiap 5 menit per pair\n"
            text += "• Hanya sinyal kuat yang dikirim (BUY/SELL)\n\n"
            text += "📋 **Command:**\n"
            text += "• `/signals` - Lihat semua sinyal saat ini\n"
            text += "• `/watch <pair>` - Tambah pair ke watchlist"
        else:
            text += f"\n📊 **Total:** {count} strong signal(s)\n\n"
            text += "💡 **Next check:** 5 menit per pair\n"
            text += "📋 `/signals` - Lihat semua sinyal"

        await self._send_message(update, context, text, parse_mode='Markdown')

    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show portfolio balance and positions"""
        user_id = update.effective_user.id

        # Check if specific pair requested
        pair_filter = None
        if context.args and len(context.args) > 0:
            pair_filter = context.args[0].upper()

        # =====================================================================
        # FIX: Check if DRY RUN mode - use database balance instead of API
        # =====================================================================
        is_dry_run = Config.AUTO_TRADE_DRY_RUN or not Config.IS_API_KEY_CONFIGURED
        
        logger.info(f"💰 Balance command called - DRY_RUN: {Config.AUTO_TRADE_DRY_RUN}, API_CONFIGURED: {Config.IS_API_KEY_CONFIGURED}, is_dry_run: {is_dry_run}")
        
        if is_dry_run:
            # DRY RUN: Use database balance
            try:
                db_balance = self.db.get_balance(user_id)
                logger.info(f"✅ DRY RUN mode - Balance from DB for user {user_id}: {db_balance:,.0f} IDR")

                # Get user info
                with self.db.get_connection() as conn:
                    user_info = conn.execute(
                        'SELECT first_name, username FROM users WHERE user_id = ?',
                        (user_id,)
                    ).fetchone()

                user_name = user_info['first_name'] if user_info else 'User'
                username = user_info['username'] if user_info else 'N/A'

                # Get trade history for stats
                trade_history = self.db.get_trade_history(user_id, limit=1000)
                
                # Convert sqlite3.Row to dict for safe access
                closed_trades = []
                open_trades = self.db.get_open_trades(user_id)
                total_pnl = 0
                winning_count = 0
                
                for t in trade_history:
                    # Access sqlite3.Row with bracket notation
                    closed_at = t['closed_at'] if 'closed_at' in t.keys() else None
                    pnl = t['pnl'] if 'pnl' in t.keys() else 0
                    
                    if closed_at:
                        closed_trades.append(t)
                        if pnl:
                            total_pnl += pnl
                            if pnl > 0:
                                winning_count += 1
                
                win_rate = (winning_count / len(closed_trades) * 100) if closed_trades else 0
                
                text = f"""
💰 **DRY RUN Balance** 🧪

👤 **User:** {user_name} (@{username})
💵 **Virtual Balance:** `{Utils.format_currency(db_balance)}` IDR

📊 **Trading Stats:**
• Total Trades: {len(closed_trades)}
• Open Positions: {len(open_trades)}
• Win Rate: {win_rate:.1f}%
• Total P&L: `{Utils.format_currency(total_pnl)}` IDR

💡 **Note:** This is SIMULATION mode (no real money)
Use `/autotrade real` for actual trading (requires API keys)
"""
                
                # Show open positions if any
                if open_trades:
                    text += "\n📈 **Open Positions:**\n"
                    for trade in open_trades[:5]:
                        pnl = trade['pnl'] if 'pnl' in trade.keys() else 0
                        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                        text += f"\n{pnl_emoji} `{trade['pair']}` | Entry: `{Utils.format_price(trade['price'])}` | P&L: `{Utils.format_currency(pnl)}`"
                
                if len(text) > 4000:
                    text = text[:3900] + "\n... (truncated)"
                    
            except Exception as e:
                logger.error(f"DRY RUN balance error: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                text = f"❌ Error fetching DRY RUN balance: {str(e)}\n\nCheck logs for details."
        else:
            # REAL TRADING: Fetch from Indodax API
            try:
                from api.indodax_api import IndodaxAPI
                indodax = IndodaxAPI()
                indodax_balance = indodax.get_balance()

                if indodax_balance:
                    # Get all coin balances
                    balance_data = indodax_balance.get('balance', {})
                    balance_hold = indodax_balance.get('balance_hold', {})

                    # Calculate total IDR value
                    idr_available = float(balance_data.get('idr', 0))
                    idr_in_orders = float(balance_hold.get('idr', 0))

                    # Count crypto assets
                    crypto_text = []
                    total_crypto_value = 0

                    # Determine which pairs to show
                    if pair_filter:
                        # Show specific pair only
                        pairs_to_check = [pair_filter]
                    else:
                        # Show all watched pairs
                        pairs_to_check = self.subscribers.get(user_id, [])

                    for pair in pairs_to_check:
                        coin_name = pair.replace('/', '_').split('_')[0].lower()
                        avail = float(balance_data.get(coin_name, 0))
                        hold = float(balance_hold.get(coin_name, 0))
                        total = avail + hold

                        if total > 0:
                            # Get current price for valuation
                            if pair in self.price_data:
                                price = self.price_data[pair].get('last', 0)
                            else:
                                # Fallback: fetch from API
                                try:
                                    ticker = indodax.get_ticker(pair)
                                    price = ticker['last'] if ticker else 0
                                except Exception:
                                    price = 0

                            value_idr = total * price
                            total_crypto_value += value_idr
                            crypto_text.append(f"• `{coin_name.upper()}`: `{avail:,.0f}` (Available) + `{hold:,.0f}` (In Orders)")

                    total_value = idr_available + idr_in_orders + total_crypto_value

                    text = """
💰 **Indodax Balance**
"""
                    if pair_filter:
                        text += f"\n📊 Pair: `{pair_filter}`\n"

                    text += f"""
💵 **IDR Balance:**
• Available: `{Utils.format_currency(idr_available)}`
• In Orders: `{Utils.format_currency(idr_in_orders)}`

🪙 **Crypto Assets ({min(len(crypto_text), 10)}):**
"""
                    # Limit to 10 assets to avoid message too long
                    for ct in crypto_text[:10]:
                        text += ct + '\n'

                    if not crypto_text:
                        if pair_filter:
                            text += f"• No {pair_filter} assets found\n"
                        else:
                            text += "• No crypto assets\n"

                    text += f"\n💎 **Total Value:** `{Utils.format_currency(total_value)}`"

                    # Add risk metrics
                    metrics = self.risk_manager.get_risk_metrics(user_id)
                    text += f"""

📈 **Trading Stats:**
• Total Trades: {metrics['total_trades']}
• Win Rate: {metrics['win_rate']:.1f}%
• Open Positions: {metrics['open_positions']}
"""

                    # Truncate if too long
                    if len(text) > 4000:
                        text = text[:3900] + "\n... (truncated)"
                else:
                    text = "❌ Failed to fetch balance from Indodax"
            except Exception as e:
                logger.error(f"Balance command error: {e}")
                text = f"❌ Error: {str(e)}"
        
        await self._send_message(update, context, text, parse_mode='Markdown')

    async def trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trade history"""
        user_id = update.effective_user.id

        # Open trades (limit to 5)
        open_trades = self.db.get_open_trades(user_id)[:5]

        if open_trades:
            text = "📊 **Open Trades:**\n\n"
            for trade in open_trades:
                text += f"""
🔹 **{trade['pair']}**
• Type: {trade['type']}
• Entry: `{Utils.format_price(trade['price'])}` IDR
• Amount: {trade['amount']}
• Total: `{Utils.format_currency(trade['total'])}`
• Opened: {trade['opened_at']}
\n"""
        else:
            text = "📭 No open trades"

        # Send open trades first
        if len(text) > 4000:
            text = text[:3900] + "\n... (truncated)"
        await self._send_message(update, context, text, parse_mode='Markdown')

        # Show recent closed trades (last 3)
        closed_trades = self.db.get_trade_history(user_id, limit=3)
        if closed_trades:
            text = "🕐 **Recent Closed Trades:**\n"
            for trade in closed_trades:
                # Handle None values safely
                pnl = trade['profit_loss'] if trade['profit_loss'] is not None else 0.0
                pnl_pct = trade['profit_loss_pct'] if trade['profit_loss_pct'] is not None else 0.0
                pnl_sign = '+' if pnl >= 0 else ''
                text += f"• {trade['pair']}: {pnl_sign}{Utils.format_currency(pnl)} ({pnl_pct:.1f}%)\n"

            if len(text) > 4000:
                text = text[:3900] + "\n... (truncated)"
            await self._send_message(update, context, text, parse_mode='Markdown')

    async def sync_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sync trade history from Indodax API to database"""
        user_id = update.effective_user.id
        
        await self._send_message(update, context,
            "🔄 **Syncing trades from Indodax...**\n\n⏳ This may take a while...")
        
        try:
            # Get list of pairs to sync from user's watched pairs
            watched_pairs = self.subscribers.get(user_id, [])
            
            if not watched_pairs:
                # If no watched pairs, use config defaults
                watched_pairs = [p.strip().upper() for p in Config.WATCH_PAIRS]
            
            # Filter out invalid pairs
            valid_pairs = []
            for p in watched_pairs:
                if '/' in p and p.upper().endswith('/IDR'):
                    valid_pairs.append(p.upper())
                else:
                    logger.warning(f"⚠️ Skipping invalid pair during sync: {p}")
            watched_pairs = valid_pairs
            
            await self._send_message(update, context,
                f"🔄 **Syncing {len(watched_pairs)} pairs...**\n\n"
                f"Pairs: {', '.join(watched_pairs[:5])}{'...' if len(watched_pairs) > 5 else ''}")
            
            # Count trades by pair
            synced_count = 0
            pairs_synced = {}
            failed_pairs = []
            
            for pair in watched_pairs:
                try:
                    # Get trade history for THIS specific pair
                    pair_history = self.indodax.get_trade_history(pair=pair, limit=100)
                    
                    if not pair_history:
                        continue
                    
                    # Process trades for this pair
                    for idx, order in enumerate(pair_history):
                        # Now we know the pair because we queried per pair
                        order_id = order.get('order_id', '')
                        
                        # Debug: Log first order structure for each pair
                        if order_id and idx == 0:
                            logger.info(f"Sync {pair}: First order fields: {order}")
                        
                        trade_type = order.get('type', '').upper()  # buy/sell
                        
                        # Indodax returns different field names depending on the pair
                        price = float(order.get('price', 0))
                        
                        # Try to find amount field - Indodax uses pair-specific field names
                        # For BUY orders: look for order_<coin> or calculate from order_idr/price
                        # For SELL orders: look for order_<coin>
                        # Examples: order_btc, order_pippin, order_sol, order_doge, order_xrp, order_ada, order_br
                        amount = 0.0
                        
                        # Get pair symbol without IDR (e.g., 'pippin' from 'PIPPIN/IDR')
                        coin_symbol = pair.replace('/IDR', '').lower()
                        
                        # Try pair-specific field first (e.g., order_pippin for PIPPIN/IDR)
                        amount_field = f'order_{coin_symbol}'
                        if amount_field in order:
                            amount = float(order.get(amount_field, 0))
                        # Try alternative field names
                        elif 'order_btc' in order:
                            amount = float(order.get('order_btc', 0))
                        elif 'amount' in order:
                            amount = float(order.get('amount', 0))
                        elif 'volume' in order:
                            amount = float(order.get('volume', 0))
                        elif 'filled_amount' in order:
                            amount = float(order.get('filled_amount', 0))
                        # For BUY orders, calculate amount from order_idr / price
                        elif 'order_idr' in order and price > 0:
                            order_idr = float(order.get('order_idr', 0))
                            amount = order_idr / price
                        
                        # Calculate total if not provided
                        total_val = order.get('total', None)
                        if total_val:
                            total = float(total_val)
                        elif 'order_idr' in order:
                            total = float(order.get('order_idr', 0))
                        else:
                            total = price * amount
                            
                        fee = float(order.get('fee', 0))
                        
                        # Debug log if amount is 0
                        if amount == 0 and order_id:
                            logger.warning(f"Sync {pair}: Order {order_id} has amount=0, full data: {order}")
                        
                        # Parse timestamp - Indodax uses Unix timestamp (seconds)
                        timestamp_str = order.get('submit_time', '') or order.get('finish_time', '') or order.get('timestamp', '')
                        
                        try:
                            from datetime import datetime as dt
                            if timestamp_str:
                                # Convert Unix timestamp (seconds) to datetime
                                timestamp_int = int(timestamp_str)
                                # Check if timestamp is in milliseconds (> year 2100)
                                if timestamp_int > 4102444800:  # Year 2100 in seconds
                                    timestamp_int = timestamp_int // 1000  # Convert from ms
                                timestamp_dt = dt.fromtimestamp(timestamp_int)
                            else:
                                timestamp_dt = datetime.now()
                        except Exception as e:
                            logger.warning(f"Could not parse timestamp for order {order_id}: {e}")
                            timestamp_dt = datetime.now()
                        
                        # Skip invalid trades (amount = 0 or price = 0)
                        if amount <= 0 or price <= 0:
                            logger.debug(f"Skipping invalid order {order_id}: amount={amount}, price={price}")
                            continue
                        
                        # Add to database
                        trade_id = self.db.add_indodax_trade(
                            user_id=user_id,
                            pair=pair,
                            trade_type=trade_type,
                            price=price,
                            amount=amount,
                            total=total,
                            fee=fee,
                            indodax_order_id=order_id,
                            timestamp=timestamp_dt
                        )

                        if trade_id:
                            synced_count += 1
                            pairs_synced[pair] = pairs_synced.get(pair, 0) + 1
                    
                    logger.info(f"Sync: {pair} - {pairs_synced.get(pair, 0)} trades")
                    
                except Exception as e:
                    logger.error(f"Sync error for {pair}: {e}")
                    failed_pairs.append(pair)
            
            # Build summary
            if synced_count > 0:
                pairs_text = '\n'.join([f"• {p}: {c} trades" for p, c in sorted(pairs_synced.items(), key=lambda x: x[1], reverse=True)])
                failed_text = f"\n\n⚠️ **Failed pairs:** {', '.join(failed_pairs)}" if failed_pairs else ""
                await self._send_message(update, context,
                    f"✅ **Sync Complete!**\n\n"
                    f"📊 **{synced_count} trades synced**\n\n"
                    f"{pairs_text}{failed_text}\n\n"
                    f"Now use `/position <PAIR>` to analyze!")
            else:
                await self._send_message(update, context,
                    "ℹ️ **No trades found**\n\n"
                    "You haven't made any trades in the synced pairs.")
                    
        except Exception as e:
            logger.error(f"Sync error: {e}")
            await self._send_message(update, context,
                f"❌ **Sync failed:** {str(e)}\n\n"
                "Make sure Indodax API keys are configured.")

    async def market_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show market opportunities - pairs with significant price/volume changes"""
        await self._send_message(update, context, "🔄 **Scanning market...**\n\n⏳ Please wait...")
        
        try:
            from api.indodax_api import IndodaxAPI
            indodax = IndodaxAPI()
            
            # Get all tickers
            url = f"{indodax.base_url}/api/tickers"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                tickers = response.json().get('tickers', {})
                
                # Analyze each pair
                opportunities = []
                
                for pair_id, data in tickers.items():
                    pair = pair_id.upper().replace('_', '/') + '/IDR'
                    price = float(data.get('last', 0))
                    volume = float(data.get('vol', 0))
                    high = float(data.get('high', 0))
                    low = float(data.get('low', 0))
                    
                    # Calculate 24h change
                    if low > 0:
                        change_24h = ((price - low) / low) * 100
                    else:
                        change_24h = 0
                    
                    # Skip low-value pairs
                    if price < 100:
                        continue
                    
                    # Check if significant
                    if abs(change_24h) >= 3 or volume > 1_000_000_000:  # 3% change or 1B volume
                        opportunities.append({
                            'pair': pair,
                            'price': price,
                            'change': change_24h,
                            'volume': volume,
                            'high': high,
                            'low': low
                        })
                
                # Sort by absolute change
                opportunities.sort(key=lambda x: abs(x['change']), reverse=True)
                
                # Format output
                if opportunities:
                    text = "📊 **MARKET OPPORTUNITIES**\n\n"
                    text += f"🕐 Updated: {datetime.now().strftime('%H:%M:%S')}\n\n"
                    text += "=" * 40 + "\n\n"
                    
                    # Top gainers
                    gainers = [o for o in opportunities if o['change'] > 0][:5]
                    if gainers:
                        text += "🟢 **TOP GAINERS**\n\n"
                        for o in gainers:
                            text += f"• `{o['pair']}` - `{o['price']:,.0f}` IDR (`{o['change']:+.1f}%`)\n"
                            text += f"  Vol: `{Utils.format_currency(o['volume'])}`\n\n"
                    
                    # Top losers
                    losers = [o for o in opportunities if o['change'] < 0][:5]
                    if losers:
                        text += "\n🔴 **TOP LOSERS**\n\n"
                        for o in losers:
                            text += f"• `{o['pair']}` - `{o['price']:,.0f}` IDR (`{o['change']:+.1f}%`)\n"
                            text += f"  Vol: `{Utils.format_currency(o['volume'])}`\n\n"
                    
                    # High volume
                    high_vol = sorted(opportunities, key=lambda x: x['volume'], reverse=True)[:3]
                    if high_vol:
                        text += "\n🚀 **HIGH VOLUME**\n\n"
                        for o in high_vol:
                            text += f"• `{o['pair']}` - `{Utils.format_currency(o['volume'])}` IDR\n"
                    
                    text += "\n" + "=" * 40
                    text += "\n\n💡 **To Trade:**\n"
                    text += "`/trade BUY <PAIR> <PRICE> <IDR_AMOUNT>`\n"
                    text += "`/trade SELL <PAIR> <PRICE> <COIN_AMOUNT>`\n\n"
                    text += "⚡ **Auto-Trade:**\n"
                    text += "`/autotrade` to enable"
                    
                    await self._send_message(update, context, text, parse_mode='Markdown')
                else:
                    await self._send_message(update, context, "⚠️ **No significant opportunities**\n\nMarket is quiet right now.")
            else:
                await self._send_message(update, context, f"❌ **API Error**\n\nStatus: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Market scan error: {e}")
            await self._send_message(update, context, f"❌ **Error:** {str(e)}")

    async def performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trading performance metrics"""
        user_id = update.effective_user.id
        metrics = self.risk_manager.get_risk_metrics(user_id)

        # Get daily performance
        daily_perf = self.db.get_performance(user_id, days=7)

        text = f"""
📊 **Trading Performance**

📈 **Overall Stats:**
• Total Trades: {metrics['total_trades']}
• Win Rate: {metrics['win_rate']:.1f}%
• Total P&L: `{Utils.format_currency(metrics['total_pnl'])}`
• Sharpe Ratio: {metrics['sharpe_ratio']:.2f}

📅 **Last 7 Days:**
"""
        if daily_perf:
            for perf in daily_perf[:7]:
                pnl_sign = '+' if perf['total_profit_loss'] >= 0 else ''
                text += f"• {perf['date']}: {perf['total_trades']} trades, {pnl_sign}{Utils.format_currency(perf['total_profit_loss'])}\n"
        else:
            text += "• No trades yet\n"

        # Add risk summary
        text += f"""
🛡️ **Risk Summary:**
• Current Drawdown: {metrics.get('current_drawdown', 0):.1f}%
• Max Allowed: {Config.MAX_DRAWDOWN_PCT}%
• Daily Loss Limit: {Config.MAX_DAILY_LOSS_PCT}%
        """

        await self._send_message(update, context, text, parse_mode='Markdown')

    # =============================================================================
    # PRICE MONITORING COMMANDS
    # =============================================================================

    async def monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show monitored positions with SL/TP levels"""
        user_id = update.effective_user.id
        
        positions = self.price_monitor.get_monitored_positions(user_id)
        
        if not positions:
            await self._send_message(update, context, 
                "📭 **No Active Monitored Positions**\n\n"
                "Use `/watch <PAIR>` to start watching a pair.\n"
                "SL/TP will be set automatically when you open a trade.")
            return
        
        text = self.price_monitor.get_summary(user_id)
        await self._send_message(update, context, text, parse_mode='Markdown')

    async def set_stoploss(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set custom stop loss percentage"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return
        
        if not context.args or len(context.args) != 1:
            await self._send_message(update, context,
                "❌ **Format:** `/set_sl <PERCENTAGE>`\n"
                "Example: `/set_sl 3.5` (3.5% stop loss)")
            return
        
        try:
            sl_pct = float(context.args[0])
            if sl_pct <= 0 or sl_pct > 20:
                raise ValueError("Must be between 0-20%")
            
            # Update config (temporary, until restart)
            Config.STOP_LOSS_PCT = sl_pct
            
            await self._send_message(update, context,
                f"✅ **Stop Loss Updated**\n\n"
                f"🛑 New SL: `{sl_pct}%`\n\n"
                f"⚠️ This will apply to NEW trades only.\n"
                f"Existing positions keep their original SL.")
        except ValueError as e:
            await self._send_message(update, context, f"❌ Error: {str(e)}")

    async def set_takeprofit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set custom take profit percentage"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return
        
        if not context.args or len(context.args) != 1:
            await self._send_message(update, context,
                "❌ **Format:** `/set_tp <PERCENTAGE>`\n"
                "Example: `/set_tp 7.5` (7.5% take profit)")
            return
        
        try:
            tp_pct = float(context.args[0])
            if tp_pct <= 0 or tp_pct > 50:
                raise ValueError("Must be between 0-50%")
            
            # Update config (temporary, until restart)
            Config.TAKE_PROFIT_PCT = tp_pct
            
            await self._send_message(update, context,
                f"✅ **Take Profit Updated**\n\n"
                f"🎯 New TP: `{tp_pct}%`\n\n"
                f"⚠️ This will apply to NEW trades only.\n"
                f"Existing positions keep their original TP.")
        except ValueError as e:
            await self._send_message(update, context, f"❌ Error: {str(e)}")

    # =============================================================================
    # MANUAL SUPPORT/RESISTANCE COMMANDS
    # =============================================================================

    async def set_manual_sr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Set manual S/R levels for a pair.
        Usage: /set_sr PAIR S1 S2 R1 R2 [notes]
        Example: /set_sr BTCIDR 1200000000 1150000000 1280000000 1320000000 Key weekly levels
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        if not context.args or len(context.args) < 5:
            await self._send_message(update, context,
                "❌ **Format:** `/set_sr <PAIR> <S1> <S2> <R1> <R2> [notes]`\n\n"
                "Example:\n"
                "`/set_sr BTCIDR 1200000000 1150000000 1280000000 1320000000 [Key weekly levels]`")
            return

        try:
            pair = context.args[0].upper()
            s1 = float(context.args[1])
            s2 = float(context.args[2])
            r1 = float(context.args[3])
            r2 = float(context.args[4])
            notes = " ".join(context.args[5:]) if len(context.args) > 5 else ""

            # Validate levels
            if s1 <= s2:
                raise ValueError("S1 must be > S2 (support 1 closer to price)")
            if r1 >= r2:
                raise ValueError("R1 must be < R2 (resistance 1 closer to price)")
            if s1 >= r1:
                raise ValueError("S1 must be < R1 (support below resistance)")

            # Save manual levels
            success = self.sr_detector.set_manual_levels(pair, s1, s2, r1, r2, notes)
            
            if success:
                text = f"""
✅ **Manual S/R Set**

📊 **Pair:** `{pair}`
📉 **S1:** `{s1:,.0f}`
📉 **S2:** `{s2:,.0f}`
📈 **R1:** `{r1:,.0f}`
📈 **R2:** `{r2:,.0f}`

💬 **Notes:** {notes or "None"}

💡 **Info:** These levels will override auto-detection for this pair.
Works in both DRY RUN and REAL TRADE modes.
"""
                await self._send_message(update, context, text, parse_mode='Markdown')
            else:
                await self._send_message(update, context, "❌ Failed to save manual S/R levels")

        except ValueError as e:
            await self._send_message(update, context, f"❌ Error: {str(e)}")
        except Exception as e:
            await self._send_message(update, context, f"❌ Unexpected error: {str(e)}")

    async def view_manual_sr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        View manual S/R levels for a pair or all pairs.
        Usage: /view_sr [PAIR]
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        pair = context.args[0].upper() if context.args else None

        if pair:
            levels = self.sr_detector.get_manual_levels(pair)
            if not levels:
                await self._send_message(update, context, f"❌ No manual S/R levels for `{pair}`")
                return

            text = f"""
📊 **Manual S/R Levels**

📈 **Pair:** `{pair.upper()}`
📉 **S1:** `{levels['support_1']:,.0f}`
📉 **S2:** `{levels['support_2']:,.0f}`
📈 **R1:** `{levels['resistance_1']:,.0f}`
📈 **R2:** `{levels['resistance_2']:,.0f}`

💬 **Notes:** {levels.get('notes', 'None')}

💡 **Status:** Active (overrides auto-detection)
"""
            await self._send_message(update, context, text, parse_mode='Markdown')
        else:
            # Show all pairs
            all_levels = self.sr_detector.manual_levels
            if not all_levels:
                await self._send_message(update, context, "📋 No manual S/R levels set.\n\nUse `/set_sr <PAIR> <S1> <S2> <R1> <R2> [notes]` to add.")
                return

            text = "📋 **Manual S/R Levels**\n\n"
            for p, lvls in all_levels.items():
                text += f"**{p.upper()}**: S1={lvls['support_1']:,.0f} | S2={lvls['support_2']:,.0f} | R1={lvls['resistance_1']:,.0f} | R2={lvls['resistance_2']:,.0f}\n"

            text += f"\n📊 **Total Pairs:** {len(all_levels)}"
            await self._send_message(update, context, text, parse_mode='Markdown')

    async def delete_manual_sr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Delete manual S/R levels for a pair.
        Usage: /delete_sr <PAIR>
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        if not context.args or len(context.args) != 1:
            await self._send_message(update, context, "❌ **Format:** `/delete_sr <PAIR>`\n\nExample: `/delete_sr BTCIDR`")
            return

        pair = context.args[0].upper()
        pair_lower = pair.lower()

        if pair_lower not in self.sr_detector.manual_levels:
            await self._send_message(update, context, f"❌ No manual S/R levels for `{pair}`")
            return

        del self.sr_detector.manual_levels[pair_lower]
        success = self.sr_detector.save_manual_levels(self.sr_detector.manual_levels)

        if success:
            await self._send_message(update, context, f"✅ Manual S/R levels for `{pair}` deleted.\n\nAuto-detection will now be used for this pair.")
        else:
            await self._send_message(update, context, "❌ Failed to delete manual S/R levels")

    # =============================================================================
    # AUTO SELL COMMAND
    # =============================================================================

    async def trade_auto_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Auto-sell all open positions with custom percentage"""
        user_id = update.effective_user.id

        # Check admin only
        if user_id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        # Check if API key configured
        if not Config.IS_API_KEY_CONFIGURED:
            await self._send_message(update, context,
                "❌ **API Key Not Configured**\n\n"
                "⚠️ Add Indodax API keys to .env first:\n"
                "• INDODAX_API_KEY=your_key\n"
                "• INDODAX_SECRET_KEY=your_secret")
            return

        # Parse: /trade_auto_sell PIPPIN/IDR 3  (3% profit target)
        if not context.args or len(context.args) != 2:
            await self._send_message(update, context,
                "❌ **Format:** `/trade_auto_sell <PAIR> <PERCENTAGE>`\n\n"
                "💡 **Example:**\n"
                "`/trade_auto_sell PIPPIN/IDR 3`\n\n"
                "📊 **How it works:**\n"
                "• Bot monitors your open positions for the pair\n"
                "• When price reaches +X% → auto SELL\n"
                "• When price drops below -2% → auto SELL (Stop Loss)\n"
                "• Bot sends notification when position closes\n\n"
                "⚠️ **This affects ALL open positions for the pair**")
            return

        try:
            pair = context.args[0].upper().strip()
            target_pct = float(context.args[1])

            if target_pct <= 0 or target_pct > 50:
                raise ValueError("Percentage must be between 0-50%")

            # Get open trades for this pair
            open_trades = self.db.get_open_trades(user_id)
            pair_trades = [t for t in open_trades if t['pair'] == pair and t['type'] == 'BUY']

            if not pair_trades:
                await self._send_message(update, context,
                    f"❌ **No open BUY positions for {pair}**\n\n"
                    f"Use `/trade BUY {pair} <PRICE> <AMOUNT>` first.")
                return

            # Calculate SL/TP levels
            sl_pct = 2.0  # Fixed 2% stop loss
            tp_pct = target_pct

            # Confirm with user
            positions_text = '\n'.join([
                f"• ID:{t['id']} | Entry: `{t['price']:,.0f}` | Amount: `{t['amount']}`"
                for t in pair_trades[:5]
            ])

            if len(pair_trades) > 5:
                positions_text += f"\n• ... and {len(pair_trades) - 5} more"

            confirm_text = f"""
🤖 **AUTO-SELL ACTIVATED**

📊 **Pair:** `{pair}`
🎯 **Take Profit:** `+{target_pct}%`
🛑 **Stop Loss:** `-2%` (auto cut loss)

📋 **Monitored Positions ({len(pair_trades)}):**
{positions_text}

⚙️ **How it works:**
• Bot checks price every time WebSocket updates
• When price hits +{target_pct}% → **auto SELL**
• When price drops -2% → **auto SELL** (stop loss)
• You'll get Telegram notification after close

⏰ Monitoring started now!

Reply `STOP` to cancel monitoring
            """

            # Store auto-sell config
            pending_key = f"auto_sell_{user_id}_{pair}"
            context.user_data[pending_key] = {
                'pair': pair,
                'tp_pct': tp_pct,
                'sl_pct': sl_pct,
                'active': True,
                'timestamp': datetime.now()
            }

            # Set price levels for all positions (with partial take profit)
            for trade in pair_trades:
                entry_price = trade['price']
                stop_loss = entry_price * (1 - sl_pct / 100)
                # Partial TP: TP1 di setengah target, TP2 di target penuh
                take_profit_1 = entry_price * (1 + tp_pct / 2 / 100)
                take_profit_2 = entry_price * (1 + tp_pct / 100)

                self.price_monitor.set_price_level(
                    user_id=user_id,
                    trade_id=trade['id'],
                    pair=pair,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit_1=take_profit_1,
                    take_profit_2=take_profit_2,
                    amount=trade['amount']
                )

            await self._send_message(update, context, confirm_text, parse_mode='Markdown')
            logger.info(f"🤖 Auto-sell activated for {pair}: TP=+{tp_pct}%, SL=-{sl_pct}%")

        except ValueError as e:
            await self._send_message(update, context, f"❌ Error: {str(e)}")
        except Exception as e:
            logger.error(f"Auto-sell command error: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}")

    async def top_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show Top 50 pairs by 24h volume from Indodax"""
        msg = await update.message.reply_text("📊 **Loading Top 50 Volume...**\n\n⏳ Mengambil data dari Indodax...")

        try:
            from api.indodax_api import IndodaxAPI
            indodax = IndodaxAPI()

            # Get all tickers
            all_tickers = indodax.get_all_tickers()

            if not all_tickers:
                await msg.edit_text(
                    "❌ **Gagal mengambil data ticker**\n\n"
                    "Pastikan koneksi internet lancar.\n"
                    "Coba lagi dalam beberapa menit."
                )
                return

            # Sort by volume (descending) - highest first
            all_tickers.sort(key=lambda x: x['volume'], reverse=True)

            # Take top 50
            top_50 = all_tickers[:50]

            # Build message - use plain text to avoid markdown/HTML parsing issues
            timestamp = datetime.now().strftime('%H:%M:%S')
            vol_msg = "📊 TOP 50 VOLUME (24h)\n\n"
            vol_msg += f"🕐 {timestamp} WIB\n\n"
            vol_msg += "Rank | Pair | Volume 24h | Price | Change\n"
            vol_msg += "-" * 50 + "\n"

            for i, ticker in enumerate(top_50, 1):
                pair = ticker['pair'].replace('IDR', '/IDR')
                volume_idr = ticker['volume']
                price = ticker['last']
                change_pct = ticker.get('change_percent')

                # Format volume in Rupiah - THIS IS WHAT INDODAX WEBSITE SHOWS!
                if volume_idr >= 1_000_000_000:
                    vol_str = f"{volume_idr/1_000_000_000:.2f}M"  # Juta Rupiah
                elif volume_idr >= 1_000_000:
                    vol_str = f"{volume_idr/1_000_000:.1f}Jt"  # Juta Rupiah
                elif volume_idr >= 1_000:
                    vol_str = f"{volume_idr/1_000:.0f}Rb"  # Ribu Rupiah
                else:
                    vol_str = f"{volume_idr:.0f}"

                # Format price
                if price >= 1000:
                    price_str = f"{price:,.0f}"
                elif price >= 1:
                    price_str = f"{price:,.2f}"
                else:
                    price_str = f"{price:,.4f}"

                # Change display - handle None
                if change_pct is None:
                    change_emoji = "⚪"
                    change_str = "-"
                elif change_pct > 0:
                    change_emoji = "🟢"
                    change_str = f"+{change_pct:.2f}%"
                elif change_pct < 0:
                    change_emoji = "🔴"
                    change_str = f"{change_pct:.2f}%"
                else:
                    change_emoji = "⚪"
                    change_str = "0.00%"

                vol_msg += f"{i:2d}. {pair:<12} {vol_str:>8} {price_str:>10} {change_emoji} {change_str}\n"

            vol_msg += "\n💡 Tips:\n"
            vol_msg += "• Volume tinggi = Likuiditas bagus\n"
            vol_msg += "• /watch <pair> untuk monitoring\n"
            vol_msg += "• /signal <pair> untuk analisa\n"
            vol_msg += "• DYOR! Volume ≠ Profit guarantee\n"
            
            # Auto-add top 5 pairs to watchlist
            added_count = 0
            current_watchlist = [p.strip().upper() for p in Config.WATCH_PAIRS]
            
            vol_msg += "\n\n✅ Auto-added ke WATCHLIST:\n"
            for ticker in top_50[:5]:  # Top 5
                pair_name = ticker['pair'].upper().replace('IDR', 'IDR')
                if pair_name not in current_watchlist:
                    # Add to Config.WATCH_PAIRS (in memory only, not persisted)
                    # Note: This adds to runtime watchlist only
                    added_count += 1
                    vol_msg += f"• {pair_name}\n"
                else:
                    vol_msg += f"• {pair_name} ✓ (already in watchlist)\n"
            
            if added_count > 0:
                # Update runtime watchlist - add unique pairs
                new_pairs = [ticker['pair'].upper().replace('IDR', 'IDR') for ticker in top_50[:5]]
                existing = [p.strip().upper() for p in Config.WATCH_PAIRS]
                for p in new_pairs:
                    if p not in existing:
                        Config.WATCH_PAIRS.append(p)
                logger.info(f"📊 Added top {added_count} volume pairs to watchlist")
            
            await msg.edit_text(vol_msg)

        except Exception as e:
            logger.error(f"Top volume error: {e}")
            await msg.edit_text(f"Error loading top volume: {str(e)}\n\nCoba lagi dalam beberapa menit.")

    # =============================================================================
    # MANUAL TRADING COMMAND
    # =============================================================================

    async def trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Execute manual trade via Indodax API - delegates to scalper module for sync"""
        user_id = update.effective_user.id

        # Check if manual trading is enabled
        if not Config.MANUAL_TRADING_ENABLED:
            await self._send_message(update, context,
                "❌ **Manual Trading is DISABLED**\n\n"
                "⚠️ Enable in .env: `MANUAL_TRADING_ENABLED=true`\n"
                "Then restart bot.")
            return

        # Check if API key configured
        if not Config.IS_API_KEY_CONFIGURED:
            await self._send_message(update, context,
                "❌ **API Key Not Configured**\n\n"
                "⚠️ Add Indodax API keys to .env first:\n"
                "• INDODAX_API_KEY=your_key\n"
                "• INDODAX_SECRET_KEY=your_secret")
            return

        # Check admin only
        if user_id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        # FIX: Delegate to scalper module for synchronized position tracking
        if self.scalper and context.args:
            order_type = context.args[0].upper()
            if order_type == 'BUY' and len(context.args) >= 4:
                # /trade BUY <pair> <price> <idr> → delegate to /s_buy
                pair = context.args[1]
                price = context.args[2]
                idr_amount = context.args[3]
                # Build new context args for s_buy: <pair> <price> <idr>
                context.args = [pair, price, idr_amount]
                logger.info("🔄 Delegating /trade BUY to scalper module")
                await self.scalper.cmd_buy(update, context)
                return
            elif order_type == 'SELL' and len(context.args) >= 4:
                # /trade SELL <pair> <price> <amount> → delegate to /s_sell
                pair = context.args[1]
                price = context.args[2]
                coin_amount = context.args[3]
                context.args = [pair, price, coin_amount]
                logger.info("🔄 Delegating /trade SELL to scalper module")
                await self.scalper.cmd_sell(update, context)
                return

        # Fallback: old behavior if scalper not available or args missing
        if not context.args or len(context.args) < 4:
            await self._send_message(update, context,
                "❌ **Format:** `/trade <BUY/SELL> <PAIR> <PRICE> <AMOUNT>`\n\n"
                "💡 **BUY Example:**\n"
                "`/trade BUY btcidr 150000000 100000000`\n"
                "• Price: 150,000,000 IDR\n"
                "• Amount: 100,000,000 IDR (will buy ~0.67 BTC)\n\n"
                "💡 **SELL Example:**\n"
                "`/trade SELL btcidr 150000000 0.01`\n"
                "• Price: 150,000,000 IDR\n"
                "• Amount: 0.01 BTC (will sell for ~1,500,000 IDR)\n\n"
                "📊 **Parameters:**\n"
                "• BUY/SELL - Order type\n"
                "• PAIR - Trading pair\n"
                "• PRICE - Price in IDR\n"
                "• AMOUNT - For BUY: IDR amount | For SELL: Coin amount")
            return

        try:
            order_type = context.args[0].upper()
            pair = context.args[1].upper()
            price = float(context.args[2])
            amount_input = float(context.args[3])

            # Validate order type
            if order_type not in ['BUY', 'SELL']:
                raise ValueError("Order type must be BUY or SELL")

            # For BUY: amount_input is IDR, convert to coin amount
            # For SELL: amount_input is coin amount
            if order_type == 'BUY':
                coin_amount = round(amount_input / price, 8)  # FIX: Round to 8 decimals for Indodax
                display_amount = f"`{Utils.format_currency(amount_input)}` IDR ({coin_amount:.6f} {pair.split('/')[0]})"
            else:
                coin_amount = amount_input
                display_amount = f"`{amount_input}` {pair.split('/')[0]}"

            total = price * coin_amount

            # Send confirmation request with normalized pair display
            api_pair_display = self._normalize_pair_for_indodax(pair)
            confirm_text = f"""
⚠️ **CONFIRM TRADE?**

📊 **Order Details:**
• Type: `{order_type}`
• Pair: `{pair}` → `{api_pair_display}` (Indodax format)
• Price: `{Utils.format_price(price)}` IDR
• Amount: {display_amount}
• Total: `{Utils.format_currency(total)}`

🛡️ **Risk Settings:**
• Stop Loss: `{Config.STOP_LOSS_PCT}%`
• Take Profit: `{Config.TAKE_PROFIT_PCT}%`

⏰ Expires in 30 seconds

**Reply YES to confirm, NO to cancel**
            """

            # Store pending order with coin_amount
            pending_key = f"pending_{user_id}"
            context.user_data[pending_key] = {
                'order_type': order_type,
                'pair': pair,
                'price': price,
                'amount': coin_amount,  # Always store as coin amount
                'timestamp': datetime.now()
            }

            await update.message.reply_text(confirm_text, parse_mode='Markdown')
            
        except ValueError as e:
            await self._send_message(update, context, f"❌ Error: {str(e)}")
        except Exception as e:
            logger.error(f"Trade command error: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}")

    async def execute_manual_trade(self, user_id, order_data):
        """Execute manual trade via Indodax API"""
        try:
            from api.indodax_api import IndodaxAPI
            indodax = IndodaxAPI()

            pair = order_data['pair']
            order_type = order_data['order_type']
            price = order_data['price']
            amount = order_data['amount']  # This is now coin_amount
            total = price * amount

            # FIX: Auto-convert pair format for Indodax API
            # zenidr → zen_idr, btcidr → btc_idr, pippinidr → pippin_idr
            api_pair = self._normalize_pair_for_indodax(pair)
            logger.info(f"🔄 Pair format: {pair} → {api_pair}")

            # =====================================================================
            # DRY RUN MODE: Simulate trade without calling real API
            # =====================================================================
            if Config.AUTO_TRADE_DRY_RUN:
                coin_name = api_pair.split('_')[0].upper()
                fee = total * Config.TRADING_FEE_RATE  # 0.3%

                # Record to database (dry run)
                trade_id = self.db.add_trade(
                    user_id=user_id,
                    pair=pair,
                    trade_type=order_type,
                    price=price,
                    amount=amount,
                    total=total,
                    fee=fee,
                    signal_source='manual_dryrun',
                    ml_confidence=0
                )

                # FIX: Also register in scalper's active_positions so it shows in /s_posisi
                if hasattr(self, 'scalper') and self.scalper:
                    self.scalper.add_manual_position(pair, price, amount, total, trade_id)

                success_text = (
                    f"✅ **DRY RUN ORDER EXECUTED!**\n\n"
                    f"📊 *Order Details:*\n"
                    f"• Pair: `{pair}` → `{api_pair}`\n"
                    f"• Type: `{order_type}`\n"
                    f"• Price: `{Utils.format_price(price)}` IDR\n"
                    f"• Amount: `{amount:.8f}` {coin_name}\n"
                    f"• Total: `{Utils.format_currency(total)}` IDR\n"
                    f"• Fee (0.3%): `{Utils.format_currency(fee)}` IDR\n\n"
                    f"📈 *Trade ID:* `{trade_id}`\n\n"
                    f"⚠️ **Note:** Ini DRY RUN — tidak ada real trade di Indodax!\n"
                    f"💡 Posisi sekarang muncul di `/s_posisi`"
                )
                return success_text

            # =====================================================================
            # REAL TRADING MODE: Execute actual order via Indodax API
            # =====================================================================
            # Check balance BEFORE placing order
            balance = indodax.get_balance()
            if balance and 'balance' in balance:
                if order_type == 'BUY':
                    fee = total * Config.TRADING_FEE_RATE
                    total_with_fee = total + fee
                    idr_balance = float(balance['balance'].get('idr', 0))

                    if idr_balance < total_with_fee:
                        return (
                            f"❌ **Insufficient Balance!**\n\n"
                            f"💰 **Required:** `{Utils.format_currency(total_with_fee)}` IDR\n"
                            f"   (Order: `{Utils.format_currency(total)}` + Fee 0.3%: `{Utils.format_currency(fee)}`)\n\n"
                            f"🏦 **Available:** `{Utils.format_currency(idr_balance)}` IDR\n\n"
                            f"💡 Please deposit more IDR to your Indodax account."
                        )
                else:
                    coin_name_real = api_pair.split('_')[0]
                    coin_balance = float(balance['balance'].get(coin_name_real, 0))
                    if coin_balance < amount:
                        return (
                            f"❌ **Insufficient {coin_name_real.upper()} Balance!**\n\n"
                            f"💰 **Required:** `{amount:.8f}` {coin_name_real.upper()}\n"
                            f"🏦 **Available:** `{coin_balance:.8f}` {coin_name_real.upper()}"
                        )

            # Execute order
            result = indodax.create_order(api_pair, order_type.lower(), price, amount)

            if result and result.get('success') == 1 and 'return' in result:
                # Get updated balance and open orders
                balance_after = indodax.get_balance()
                open_orders = indodax.get_open_orders(pair)
                
                # Get coin name from pair
                coin_name = pair.replace('/', '_').split('_')[0].lower()
                
                # Calculate available balance and in-order amount
                available_balance = float(balance_after.get('balance', {}).get(coin_name, 0))
                balance_hold = float(balance_after.get('balance_hold', {}).get(coin_name, 0))
                
                # Calculate total in open orders for this pair
                in_orders = balance_hold  # Use balance_hold as it's more accurate
                order_details = []
                
                # Handle both list and dict response
                if isinstance(open_orders, list):
                    orders_list = open_orders
                elif isinstance(open_orders, dict) and 'orders' in open_orders:
                    orders_list = open_orders['orders']
                else:
                    orders_list = []
                
                for order in orders_list:
                    # Try different key names for remaining amount
                    order_amount = float(order.get('remaining', order.get('amount', 0)))
                    order_type_order = order.get('type', 'unknown').upper()
                    order_details.append(f"  • Order #{order.get('order_id')}: {order_amount:,.0f} {coin_name.upper()} ({order_type_order})")
                
                # Determine order status
                if balance_hold > 0:
                    status_text = "⏳ *Status:* **OPEN** (waiting for buyer)"
                else:
                    status_text = "✅ *Status:* **FILLED** (order executed)"
                
                # Save to database
                trade_id = self.db.add_trade(
                    user_id=user_id,
                    pair=pair,
                    trade_type=order_type,
                    price=price,
                    amount=amount,
                    total=price * amount,
                    fee=0,  # Will be updated later
                    signal_source='manual',
                    ml_confidence=0
                )

                # Set price monitoring for SL/TP (with partial take profit)
                tp_data = self.trading_engine.calculate_stop_loss_take_profit(price, order_type)
                stop_loss = tp_data['stop_loss']
                take_profit_1 = tp_data['take_profit_1']
                take_profit_2 = tp_data['take_profit_2']
                self.price_monitor.set_price_level(
                    user_id, trade_id, pair, price, 
                    stop_loss, take_profit_1, take_profit_2, amount
                )

                # Send success notification with balance info
                # Escape Markdown special characters in dynamic values
                order_id = str(result.get('return', {}).get('order_id', 'N/A')).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
                pair_escaped = pair.replace('_', '\\_').replace('*', '\\*') if pair else 'N/A'

                success_text = (
                    f"✅ *ORDER EXECUTED SUCCESSFULLY!*\n\n"
                    f"📊 *Order Details:*\n"
                    f"• Type: `{order_type}`\n"
                    f"• Pair: `{pair_escaped}`\n"
                    f"• Price: `{Utils.format_price(price)}` IDR\n"
                    f"• Amount: `{amount:,.0f}` {coin_name.upper()}\n"
                    f"• Total: `{Utils.format_currency(price * amount)}`\n"
                    f"• Order ID: `{order_id}`\n"
                    f"• {status_text}\n\n"
                    f"💰 *{coin_name.upper()} Balance:*\n"
                    f"• Available: `{available_balance:,.0f}` {coin_name.upper()}\n"
                    f"• In Orders: `{in_orders:,.0f}` {coin_name.upper()}\n"
                )
                
                if order_details:
                    success_text += "\n📋 *Active Orders:*\n" + '\n'.join(order_details)
                
                # SL/TP depends on order type
                if order_type.upper() == 'SELL':
                    sl_label = f"📉 Stop Loss: {Utils.format_price(stop_loss)} IDR (buy back lower)"
                    tp_label = f"📈 Take Profit: {Utils.format_price(take_profit)} IDR (buy back lower)"
                else:
                    sl_label = f"📉 Stop Loss: {Utils.format_price(stop_loss)} IDR (sell lower)"
                    tp_label = f"📈 Take Profit: {Utils.format_price(take_profit)} IDR (sell higher)"
                
                success_text += (
                    f"\n\n🛡️ *Auto-Monitoring:*\n"
                    f"• {sl_label}\n"
                    f"• {tp_label}\n\n"
                    f"🔔 Bot will notify when SL/TP is hit!"
                )

                return success_text
            else:
                error_msg = str(result).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
                return f"❌ Order Failed\n\nError: {error_msg}"

        except Exception as e:
            logger.error(f"Manual trade execution error: {e}")
            error_msg = str(e).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
            return f"❌ Error Executing Order\n\n{error_msg}"

    # =============================================================================
    # CANCEL TRADE COMMAND
    # =============================================================================

    async def cancel_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel a pending or open order"""
        user_id = update.effective_user.id
        
        # Check if cancel is enabled
        if not Config.CANCEL_TRADE_ENABLED:
            await self._send_message(update, context,
                "❌ **Cancel Trade is DISABLED**\n\n"
                "⚠️ Enable in .env: `CANCEL_TRADE_ENABLED=true`")
            return
        
        # Check admin only
        if user_id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return
        
        # Check if API key configured
        if not Config.IS_API_KEY_CONFIGURED:
            await self._send_message(update, context,
                "❌ **API Key Not Configured**\n\n"
                "Add Indodax API keys to .env first.")
            return
        
        # Parse command: /cancel <ORDER_ID> or /cancel <PAIR>
        if not context.args:
            await self._send_message(update, context,
                "❌ **Format:** `/cancel <ORDER_ID>` or `/cancel <PAIR>`\n\n"
                "💡 **Examples:**\n"
                "`/cancel 12345678` - Cancel by order ID\n"
                "`/cancel PIPPIN/IDR` - Cancel all orders for pair\n\n"
                "📊 **Get Order ID from:**\n"
                "• /trades - View recent trades\n"
                "• Trade confirmation message")
            return
        
        try:
            from api.indodax_api import IndodaxAPI
            indodax = IndodaxAPI()
            
            arg = context.args[0]
            
            # Check if argument is order ID (numeric) or pair
            if arg.isdigit():
                # Cancel by order ID
                order_id = int(arg)
                
                # Find order in database
                open_trades = self.db.get_open_trades(user_id)
                trade_to_cancel = None
                
                for trade in open_trades:
                    # Check if order_id matches (you may need to store order_id in DB)
                    if trade['id'] == order_id:
                        trade_to_cancel = trade
                        break
                
                if not trade_to_cancel:
                    await self._send_message(update, context,
                        f"❌ **Order Not Found**\n\n"
                        f"Order ID `{order_id}` not found in open trades.\n\n"
                        f"Use `/trades` to see open orders.")
                    return
                
                # Cancel on Indodax
                pair = trade_to_cancel['pair']
                # pair_symbol = Config.get_pair_symbol(pair)  # Not needed for cancel API

                # Indodax cancel requires order_id and pair
                result = indodax.cancel_order(pair, str(order_id))
                
                if result and result.get('success', False) or 'order_id' in str(result):
                    # Update database
                    self.db.close_trade(
                        trade_id=order_id,
                        close_price=trade_to_cancel['price'],
                        pnl=0,
                        pnl_pct=0
                    )
                    
                    await self._send_message(update, context,
                        f"✅ **Order Cancelled Successfully!**\n\n"
                        f"📊 **Order Details:**\n"
                        f"• Order ID: `{order_id}`\n"
                        f"• Pair: `{pair}`\n"
                        f"• Type: `{trade_to_cancel['type']}`\n"
                        f"• Price: `{trade_to_cancel['price']:,.0f}` IDR\n"
                        f"• Amount: `{trade_to_cancel['amount']}`\n\n"
                        f"💰 Funds returned to your balance.")
                else:
                    await self._send_message(update, context,
                        f"❌ **Cancel Failed**\n\n"
                        f"Indodax response: {result}")
                
            else:
                # Cancel by pair - cancel all open orders for pair
                pair = arg.upper()
                # Config.get_pair_symbol(pair) - pair format already correct

                # Get open orders from Indodax
                open_orders = indodax.get_open_orders(pair)
                
                if not open_orders:
                    await self._send_message(update, context,
                        f"❌ **No Open Orders for {pair}**\n\n"
                        f"No orders to cancel.")
                    return
                
                # Cancel each order
                cancelled_count = 0
                for order in open_orders:
                    order_id = order.get('order_id', order.get('id'))
                    result = indodax.cancel_order(pair, str(order_id))
                    
                    if result:
                        cancelled_count += 1
                
                await self._send_message(update, context,
                    f"✅ **Cancelled {cancelled_count} Order(s)**\n\n"
                    f"📊 **Pair:** `{pair}`\n"
                    f"🗑️ **Cancelled:** {cancelled_count} order(s)\n\n"
                    f"💰 Funds returned to your balance.")
                    
        except Exception as e:
            logger.error(f"Cancel trade error: {e}")
            await self._send_message(update, context, f"❌ **Error:** {str(e)}")

    # =============================================================================
    # ADMIN COMMANDS
    # =============================================================================
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced admin status command"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return
        
        import psutil
        
        uptime_seconds = time.time() - self.start_time
        uptime_str = f"{uptime_seconds/3600:.1f}h" if uptime_seconds >= 3600 else f"{uptime_seconds/60:.1f}m"
        
        # Get system info
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Count active pairs
        active_pairs = len(set(p for pairs in self.subscribers.values() for p in pairs))
        
        text = f"""
🤖 **Bot Status - {datetime.now().strftime('%H:%M:%S')}**

🔐 **Authentication:**
• Token: {'✅ Valid' if self.app else '❌ Invalid'}
• Admin Access: {'✅ Enabled' if Config.ADMIN_IDS else '❌ Disabled'}
• API Key: {'✅ Configured' if Config.IS_API_KEY_CONFIGURED else '❌ Not Configured'}

⏱️ **Performance:**
• Uptime: {uptime_str}
• CPU Usage: {cpu_percent}%
• Memory: {memory.percent}% ({memory.used/1024/1024:.0f}MB / {memory.total/1024/1024:.0f}MB)

📡 **Connections:**
• WebSocket: {'🟢 Connected' if self.ws_connected else '🔴 Disconnected'}
• Telegram API: ✅ Active
• Database: ✅ Connected

📊 **Activity:**
• Total Users: {len(self.subscribers)}
• Active Pairs: {active_pairs}
• Watched Pairs: {', '.join(set(p for pairs in self.subscribers.values() for p in pairs)) or 'None'}

🎯 **Trading:**
• Auto-Trading: {'🟢 ON' if self.is_trading else '🔴 OFF'}
• Auto-Trade Enabled: {'✅ Yes' if Config.AUTO_TRADING_ENABLED else '⚠️ No (Signals Only)'}
• ML Model: {'✅ Loaded' if self.ml_model else '❌ Not Loaded'}

🛡️ **Risk Settings:**
• Stop Loss: `{Config.STOP_LOSS_PCT}%`
• Take Profit: `{Config.TAKE_PROFIT_PCT}%`
• Min Trade: `{Utils.format_currency(Config.MIN_TRADE_AMOUNT)}`
• Max Trade: `{Utils.format_currency(Config.MAX_TRADE_AMOUNT)}`
        """
        
        # Add keyboard for quick admin actions
        keyboard = [
            [
                InlineKeyboardButton("🔄 Restart Bot", callback_data="admin_restart"),
                InlineKeyboardButton("📊 View Logs", callback_data="admin_logs")
            ],
            [
                InlineKeyboardButton("🤖 Retrain ML", callback_data="admin_retrain"),
                InlineKeyboardButton("📈 Backtest", callback_data="admin_backtest")
            ]
        ]
        
        await update.message.reply_text(
            text, 
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enable auto-trading (admin only)"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        self.is_trading = True
        logger.info("🟢 Auto-trading ENABLED by admin")

        await update.message.reply_text(
            "✅ **Auto-trading ENABLED**\n\n"
            "Bot will now:\n"
            "• Analyze markets every 5 minutes\n"
            "• Execute trades when signals are strong\n"
            "• Apply stop-loss & take-profit automatically\n"
            "• Enforce risk management rules\n\n"
            "Use `/stop_trading` to pause.",
            parse_mode='Markdown'
        )

    async def stop_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Disable auto-trading (admin only)"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        self.is_trading = False
        logger.info("🔴 Auto-trading DISABLED by admin")

        await update.message.reply_text(
            "⏸️ **Auto-trading DISABLED**\n\n"
            "• No new trades will be executed\n"
            "• Existing positions remain open\n"
            "• Signals still generated for manual review\n\n"
            "Use `/start_trading` to resume.",
            parse_mode='Markdown'
        )

    async def emergency_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        🚨 HEDGE FUND: KILL SWITCH
        Emergency stop: flatten all positions, cancel all orders, halt trading.
        This is the nuclear option — use when something is seriously wrong.
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        user_id = update.effective_user.id

        # Log the emergency
        logger.critical(f"🚨 EMERGENCY STOP triggered by admin {user_id}")

        # Step 1: Halt all trading immediately
        self.is_trading = False
        logger.critical("🛑 Step 1: Trading HALTED")

        # Step 2: Get all open positions
        open_trades = self.db.get_open_trades(user_id)
        flatten_count = 0
        errors = []

        if open_trades:
            logger.critical(f"📊 Step 2: Flattening {len(open_trades)} open positions...")

            for trade in open_trades:
                try:
                    pair = trade['pair']
                    entry_price = trade['price']
                    amount = trade['amount']
                    trade_id = trade['id']

                    # Get current price
                    ticker = self.indodax.get_ticker(pair)
                    if ticker:
                        current_price = ticker['last']

                        # Execute market sell (DRY RUN or REAL)
                        if Config.AUTO_TRADE_DRY_RUN:
                            # Simulated flatten
                            pnl_pct = ((current_price - entry_price) / entry_price) * 100
                            self.db.close_trade(trade_id, current_price, amount)
                            logger.critical(f"  [DRY RUN] Flattened {pair}: {amount} @ {current_price:,.0f} | PnL: {pnl_pct:+.2f}%")
                            flatten_count += 1
                        else:
                            # REAL flatten via Indodax API
                            if Config.IS_API_KEY_CONFIGURED:
                                result = self.indodax.create_order(pair, 'sell', current_price, amount)
                                if result and result.get('success') == 1:
                                    order_id = result.get('return', {}).get('order_id', 'N/A')
                                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                                    self.db.close_trade(trade_id, current_price, amount, order_id=order_id, reason="EMERGENCY FLATTEN")
                                    logger.critical(f"  [REAL] Flattened {pair}: {amount} @ {current_price:,.0f} | PnL: {pnl_pct:+.2f}% | Order: {order_id}")
                                    flatten_count += 1
                                else:
                                    errors.append(f"Failed to sell {pair}: {result}")
                            else:
                                errors.append(f"API keys not configured — cannot execute real flatten for {pair}")
                    else:
                        errors.append(f"Could not get price for {pair}")

                except Exception as e:
                    errors.append(f"Error flattening {trade.get('pair', 'unknown')}: {e}")
                    logger.critical(f"  ❌ Error: {e}")
        else:
            logger.info("✅ No open positions to flatten")

        # Step 3: Clear price monitoring
        try:
            self.price_monitor.clear_all_levels(user_id)
        except Exception:
            pass

        # Step 4: Clear signal queues
        try:
            if self.signal_queue.is_available():
                self.signal_queue.clear_all()
        except Exception:
            pass

        # Build response
        text = f"""
🚨 **EMERGENCY STOP EXECUTED** 🚨

⚠️ **Triggered by:** Admin {user_id}
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 **Actions Taken:**
• Trading: **HALTED** 🔴
• Positions Flattened: **{flatten_count}**
• Open Positions: **{len(open_trades)}**
• Signal Queue: **CLEARED**

"""
        if errors:
            text += f"⚠️ **Errors ({len(errors)}):**\n"
            for err in errors[:5]:
                text += f"• {err}\n"
            if len(errors) > 5:
                text += f"... and {len(errors)-5} more\n"
            text += "\n"

        text += """
📋 **Next Steps:**
1. Review what triggered this emergency
2. Check logs for details
3. Fix the root cause
4. Use `/start_trading` to resume when ready
5. Use `/trades` to review flattened positions

⚠️ **WARNING:** This is the NUCLEAR option.
Only use when system is malfunctioning or
market conditions are extremely dangerous.
"""

        await update.message.reply_text(text, parse_mode='Markdown')

        # Send to all admins
        for admin_id in Config.ADMIN_IDS:
            if admin_id != user_id:
                try:
                    await self.app.bot.send_message(
                        chat_id=admin_id,
                        text=f"🚨 **EMERGENCY STOP** triggered by admin {user_id}\n"
                             f"Positions flattened: {flatten_count}\n"
                             f"Check /status for details.",
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass

    async def metrics_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        📊 HEDGE FUND: System metrics dashboard
        Shows real-time performance, risk, and ML metrics.
        """
        import psutil
        import time

        # System metrics
        process = psutil.Process()
        mem_mb = process.memory_info().rss / 1024 / 1024
        cpu_pct = process.cpu_percent(interval=0.1)

        # Bot metrics
        uptime_seconds = time.time() - self.start_time
        uptime_str = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m"

        # Trade metrics
        user_id = update.effective_user.id
        trade_history = self.db.get_trade_history(user_id, limit=1000)
        open_trades = self.db.get_open_trades(user_id)

        total_trades = len(trade_history)
        winning_trades = sum(1 for t in trade_history if t.get('profit_loss', 0) > 0)
        losing_trades = sum(1 for t in trade_history if t.get('profit_loss', 0) <= 0)
        win_rate = (winning_trades / max(total_trades, 1)) * 100
        total_pnl = sum(t.get('profit_loss', 0) for t in trade_history)

        # Signal metrics
        signal_count = 0
        strong_signals = 0
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now', '-24 hours')")
                signal_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM signals WHERE signal_type IN ('STRONG_BUY', 'STRONG_SELL') AND timestamp > datetime('now', '-24 hours')")
                strong_signals = cursor.fetchone()[0]
        except Exception:
            pass

        # Cache metrics
        cache_info = redis_price_cache.get_info()
        redis_status = "✅ Connected" if cache_info['redis_connected'] else "⚠️ Fallback (dict)"

        # ML model status
        ml_status = "✅ Fitted" if getattr(self.ml_model, '_is_fitted', False) else "⏳ Not trained"
        ml_accuracy = getattr(self.ml_model, 'last_accuracy', 'N/A')

        # Queue metrics
        queue_size = self.signal_queue.get_queue_size() if self.signal_queue.is_available() else 0

        text = f"""
📊 **SYSTEM METRICS DASHBOARD**

🖥️ **System:**
• Memory: `{mem_mb:.0f} MB`
• CPU: `{cpu_pct:.1f}%`
• Uptime: `{uptime_str}`

💰 **Trading:**
• Total Trades: `{total_trades}`
• Open Positions: `{len(open_trades)}`
• Win Rate: `{win_rate:.1f}%` ({winning_trades}W / {losing_trades}L)
• Total PnL: `{Utils.format_currency(total_pnl)}`

📡 **Signals (24h):**
• Total Signals: `{signal_count}`
• Strong Signals: `{strong_signals}`
• Queue Pending: `{queue_size}`

🤖 **ML Model:**
• Status: {ml_status}
• Last Accuracy: `{ml_accuracy}`

💾 **Cache:**
• Redis: {redis_status}
• Cached Pairs: `{cache_info['local_cache_size']}`

🔒 **Risk:**
• Mode: `{'🧪 DRY RUN' if Config.AUTO_TRADE_DRY_RUN else '🔴 REAL'}`
• Trading: `{'🟢 Active' if self.is_trading else '🔴 Paused'}`
"""

        await update.message.reply_text(text, parse_mode='Markdown')

    async def autotrade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle auto-trading ON/OFF with status check"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        # Check if args provided for mode selection
        if context.args:
            mode = context.args[0].lower()
            if mode in ['dryrun', 'dry_run', 'simulation']:
                self.is_trading = True
                self._save_auto_trade_mode(True)
                logger.info("🟡 Auto-trading ENABLED in DRY RUN mode via /autotrade dryrun")
                
                # Count total trades so far
                user_id = list(self.subscribers.keys())[0] if self.subscribers else 1
                closed_count = len(self.db.get_trade_history(user_id, limit=10000))
                open_count = len(self.db.get_open_trades(user_id))
                all_count = closed_count + open_count
                
                text = f"""
🧪 **AUTO-TRADING: DRY RUN MODE** 🧪

✅ **Simulation Mode ACTIVE**

📊 **Current Status:**
• Total Trades Executed: `{all_count}`
• Open Positions: `{open_count}`
• Closed Trades: `{closed_count}`
• Mode: SIMULATION (no real money)

🤖 **Bot will simulate:**
• Scanning watched pairs every 5 minutes
• Generating BUY/SELL signals (confidence >65%)
• Applying Stop Loss (-2%) & Take Profit (+5%)
• Enforcing risk limits (max 5% daily loss)

💡 Use `/autotrade_status` to see detailed history
Use `/trades` to view all trade records
                """
            elif mode in ['real', 'live', 'normal']:
                # Security warning: Check if API keys are configured
                if not Config.IS_API_KEY_CONFIGURED:
                    api_warning = """
❌ **INDODAX API KEYS NOT CONFIGURED**

To enable real trading, you must set:
• INDODAX_API_KEY
• INDODAX_SECRET_KEY

in your `.env` file.

⚠️ Cannot enable real mode without API keys!
⏹️ Using Dry-Run mode as default.
                    """
                    await self._send_message(update, context, api_warning, parse_mode='Markdown')
                    return

                self.is_trading = True
                self._save_auto_trade_mode(False)
                logger.info("🔴 Auto-trading ENABLED in REAL mode via /autotrade real")
                text = """
⚠️ **AUTO-TRADING: REAL MODE** ⚠️

🚨 **WARNING: REAL MONEY AT RISK**

🤖 **Bot will actually:**
• Execute REAL BUY/SELL orders on Indodax
• Use your actual balance from API
• Apply Stop Loss & Take Profit
• Generate real trades with real consequences

📊 **Requirements:**
• Must have `/watch` active pairs
• Need 60+ candles of data
• Strong signal confidence (>65%)
• Valid Indodax API keys with trade permissions

⚠️ **Risk Warning:**
• Real trades use REAL money
• Start with small amounts
• Monitor positions closely
• You can lose money

Use `/autotrade dryrun` to switch to simulation
Use `/autotrade off` to DISABLE
                """
            elif mode in ['off', 'disable', 'stop']:
                self.is_trading = False
                logger.info("🔴 Auto-trading DISABLED via /autotrade off")
                text = """
⏸️ **AUTO-TRADING DISABLED**

📋 **Current Status:**
• No new auto-trades will execute
• Existing positions remain active
• SL/TP monitoring still works
• Manual trading (`/trade`) still works

💡 **To Resume:**
Use `/autotrade dryrun` for simulation
Use `/autotrade real` for real trading
                """
            else:
                text = """
❓ **Usage:** `/autotrade [mode]`

📋 **Available modes:**
• `dryrun` - Simulation mode (no real trades)
• `real` - Live trading (real money)
• `off` - Disable auto-trading

💡 **Example:**
`/autotrade dryrun`
                """
        else:
            # Toggle trading state (legacy behavior)
            self.is_trading = not self.is_trading

            if self.is_trading:
                dry_run_status = "DRY RUN 🧪" if Config.AUTO_TRADE_DRY_RUN else "REAL ⚠️"
                logger.info(f"🟢 Auto-trading ENABLED via /autotrade - Mode: {dry_run_status}")
                mode_text = "🧪 **DRY RUN (Simulation)**" if Config.AUTO_TRADE_DRY_RUN else "⚠️ **REAL Trading**"
                warning_text = """• ✅ Trades are SIMULATED (no real money)
• ✅ Perfect for testing and learning
• ✅ Risk-free strategy validation""" if Config.AUTO_TRADE_DRY_RUN else """• 🚨 Trades use REAL money from Indodax
• 🚨 Start with small amounts first
• 🚨 Monitor positions regularly"""

                text = f"""
✅ **AUTO-TRADING ENABLED**

{mode_text}

🤖 **Bot will:**
• Scan watched pairs every 5 minutes
• Execute BUY/SELL when signal strength > 65%
• Apply Stop Loss (-2%) & Take Profit (+5%)
• Enforce risk limits (max 5% daily loss)

📊 **Requirements:**
• Must have `/watch` active pairs
• Need 60+ candles of data
• Strong signal confidence (>65%)

⚠️ **Risk Warning:**
{warning_text}

Use `/autotrade` again to DISABLE
                """
            else:
                logger.info("🔴 Auto-trading DISABLED via /autotrade")
                text = """
⏸️ **AUTO-TRADING DISABLED**

📋 **Current Status:**
• No new auto-trades will execute
• Existing positions remain active
• SL/TP monitoring still works
• Manual trading (`/trade`) still works

💡 **To Resume:**
Use `/autotrade` again to ENABLE
                """

        await self._send_message(update, context, text, parse_mode='Markdown')

    async def autotrade_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed auto-trading status and history"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        user_id = update.effective_user.id

        # Get auto-trading stats
        text = "🤖 **AUTO-TRADING STATUS**\n\n"

        # Current state
        status_emoji = "🟢" if self.is_trading else "🔴"
        status_text = "ACTIVE" if self.is_trading else "PAUSED"
        text += f"📊 **Status:** {status_emoji} {status_text}\n\n"
        
        # Show mode (dry run or real)
        if self.is_trading:
            is_dry_run = Config.AUTO_TRADE_DRY_RUN
            if is_dry_run:
                text += "🧪 **Mode: DRY RUN (Simulation)**\n"
                text += "• ⚠️ NO real money being used\n"
                text += "• ✅ All trades are simulated for testing\n\n"
            else:
                text += "🔴 **Mode: REAL TRADING**\n"
                text += "• 🚨 WARNING: Real money at risk\n"
                text += "• Actual orders sent to Indodax\n\n"

        # Get today's auto-trades
        today = datetime.now().strftime('%Y-%m-%d')
        auto_trades = self.db.get_trade_history(user_id, limit=50)

        # Filter today's trades
        today_trades = []
        dry_run_trades = []
        real_trades = []
        
        for trade in auto_trades:
            # Convert sqlite3.Row to dict
            trade_dict = dict(trade) if hasattr(trade, 'keys') else trade

            if trade_dict.get('signal_source') == 'auto' or 'auto' in str(trade_dict.get('notes', '')).lower():
                trade_date = trade_dict.get('opened_at', '')
                if isinstance(trade_date, datetime):
                    if trade_date.strftime('%Y-%m-%d') == today:
                        today_trades.append(trade_dict)
                        # Check if dry run or real
                        notes = str(trade_dict.get('notes', '')).lower()
                        if 'dry run' in notes:
                            dry_run_trades.append(trade_dict)
                        else:
                            real_trades.append(trade_dict)
                elif isinstance(trade_date, str) and today in trade_date:
                    today_trades.append(trade_dict)
                    notes = str(trade_dict.get('notes', '')).lower()
                    if 'dry run' in notes:
                        dry_run_trades.append(trade_dict)
                    else:
                        real_trades.append(trade_dict)

        # Today's performance
        text += f"📈 **Today's Activity ({today}):**\n"
        text += f"• Total Auto Trades: {len(today_trades)}\n"
        
        if dry_run_trades:
            text += f"  - 🧪 Dry Run: {len(dry_run_trades)}\n"
        if real_trades:
            text += f"  - 🔴 Real: {len(real_trades)}\n"

        if today_trades:
            wins = sum(1 for t in today_trades if t.get('profit_loss', 0) > 0)
            losses = len(today_trades) - wins
            total_pnl = sum(t.get('profit_loss', 0) for t in today_trades)

            text += f"• Wins: {wins} | Losses: {losses}\n"
            text += f"• P&L: `{Utils.format_currency(total_pnl)}` IDR\n"

            # Show recent trades
            text += "\n📋 **Recent Auto-Trades:**\n"
            for trade in today_trades[:5]:
                pair = trade.get('pair', 'N/A')
                trade_type = trade.get('type', 'N/A')
                pnl = trade.get('profit_loss', 0)
                pnl_sign = '+' if pnl >= 0 else ''
                status = "✅" if pnl > 0 else "❌" if pnl < 0 else "⏳"
                
                # Check if dry run
                notes = str(trade.get('notes', '')).lower()
                is_dry = 'dry run' in notes
                mode_icon = "🧪" if is_dry else "🔴"

                text += f"\n{mode_icon} {status} `{trade_type}` {pair}\n"
                text += f"   P&L: {pnl_sign}{Utils.format_currency(pnl)} IDR\n"
        else:
            text += "• No auto-trades today\n"

        # Open positions from auto-trading
        open_trades = self.db.get_open_trades(user_id)
        auto_open = []
        dry_run_open = []
        real_open = []

        for trade in open_trades:
            # Convert sqlite3.Row to dict
            trade_dict = dict(trade) if hasattr(trade, 'keys') else trade
            if trade_dict.get('signal_source') == 'auto':
                auto_open.append(trade_dict)
                notes = str(trade_dict.get('notes', '')).lower()
                if 'dry run' in notes:
                    dry_run_open.append(trade_dict)
                else:
                    real_open.append(trade_dict)

        if auto_open:
            text += f"\n📊 **Open Auto-Trade Positions ({len(auto_open)}):**\n"
            if dry_run_open:
                text += f"\n🧪 **Dry Run Positions ({len(dry_run_open)}):**\n"
            if real_open:
                text += f"\n🔴 **Real Positions ({len(real_open)}):**\n"
                
            for trade in auto_open[:5]:
                pair = trade.get('pair', 'N/A')
                trade_type = trade.get('type', 'N/A')
                price = trade.get('price', 0)
                amount = trade.get('amount', 0)
                total = trade.get('total', 0)
                notes = str(trade.get('notes', '')).lower()
                is_dry = 'dry run' in notes
                mode_icon = "🧪" if is_dry else "•"

                text += f"\n{mode_icon} `{trade_type}` {pair}\n"
                text += f"   Entry: `{Utils.format_price(price)}` IDR | Amount: `{amount}`\n"
                text += f"   Value: `{Utils.format_currency(total)}` IDR\n"
        else:
            text += "\n📊 Open Positions: 0\n"

        # Risk metrics
        metrics = self.risk_manager.get_risk_metrics(user_id)
        text += "\n🛡️ **Risk Metrics:**\n"
        daily_pnl = metrics.get('daily_pnl', 0)
        text += f"• Daily Loss: `{Utils.format_currency(daily_pnl)}`\n"
        text += f"• Daily Limit: {Config.MAX_DAILY_LOSS_PCT}%\n"
        text += f"• Total Trades: {metrics.get('total_trades', 0)}\n"

        # Last scan time
        text += f"\n⏱️ **Last Scan:** {self.last_ml_update.get(list(self.subscribers.get(user_id, []))[0] if self.subscribers.get(user_id) else 'N/A', 'N/A')}\n" if self.subscribers.get(user_id) else "\n⏱️ **Last Scan:** N/A\n"

        text += "\n💡 **Commands:**\n"
        text += "• `/autotrade dryrun` - Enable simulation mode\n"
        text += "• `/autotrade real` - Enable real trading\n"
        text += "• `/autotrade off` - Disable auto-trading\n"
        text += "• `/trades` - View all trades\n"
        text += "• `/balance` - Check balance\n"

        await self._send_message(update, context, text, parse_mode='Markdown')

    async def set_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Change auto-trade check interval via command: /set_interval <minutes>"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        if not context.args:
            text = f"""
⏱️ **Auto-Trade Interval**

Current interval: **{self.auto_trade_interval_minutes} minutes**

📝 **Usage:**
`/set_interval <minutes>`

⚡ **Presets:**
• `/set_interval 1` → Fast (scalping)
• `/set_interval 2` → Medium-fast
• `/set_interval 3` → Balanced (recommended)
• `/set_interval 5` → Conservative (default)

⚠️ **Note:**
• Lower = lebih sering cek, tapi bisa banyak false signal
• Higher = lebih akurat, tapi bisa telat entry
• Minimum: 1 menit | Maximum: 30 menit
"""
            await self._send_message(update, context, text, parse_mode='Markdown')
            return

        try:
            new_interval = int(context.args[0])
            
            if new_interval < 1:
                await self._send_message(update, context, "❌ Minimum interval: 1 menit")
                return
            if new_interval > 30:
                await self._send_message(update, context, "❌ Maximum interval: 30 menit")
                return

            old_interval = self.auto_trade_interval_minutes
            self.auto_trade_interval_minutes = new_interval
            
            # Clear last_ml_update so new interval applies immediately
            self.last_ml_update.clear()

            text = f"""
✅ **Interval Updated**

⏱️ Old interval: {old_interval} minutes
⏱️ New interval: **{new_interval} minutes**

🔄 Next scan will use the new interval.
"""
            await self._send_message(update, context, text, parse_mode='Markdown')
            
            logger.info(f"⏱️ Auto-trade interval changed: {old_interval} → {new_interval} minutes")

        except ValueError:
            await self._send_message(update, context, "❌ Invalid number. Use: `/set_interval 3`", parse_mode='Markdown')

    async def scheduler_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show scheduler and signal queue status"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        text = "📅 **SCHEDULER STATUS**\n\n"

        # Scheduler info
        sched_status = self.task_scheduler.get_status()
        text += f"🔄 Running: {'✅ Yes' if sched_status.get('running') else '❌ No'}\n"
        text += f"📋 Tasks: {len(sched_status.get('tasks', {}))}\n\n"

        # Task details
        for name, info in sched_status.get('tasks', {}).items():
            next_run = info.get('next_run_in', 0)
            next_str = f"{next_run:.0f}s" if next_run < 60 else f"{next_run/60:.1f}m"
            status_icon = "❌" if info.get('last_error') else "✅"
            text += f"{status_icon} **{name}**\n"
            text += f"   📝 {info.get('description', '')}\n"
            text += f"   ⏱️ Every: {info['interval_seconds']}s | Runs: {info['run_count']}\n"
            text += f"   🕐 Last: {info['last_run']} | Next: {next_str}\n"
            if info.get('last_error'):
                text += f"   ⚠️ Error: {info['last_error'][:50]}\n"
            text += "\n"

        # Signal Queue info
        text += "📊 **SIGNAL QUEUE**\n"
        if self.signal_queue.is_available():
            stats = self.signal_queue.get_stats()
            text += "✅ Redis: Connected\n"
            text += f"📦 Pending: {stats.get('pending', 0)}\n"
            text += f"⏭️ Skipped: {stats.get('skipped_count', 0)}\n"
            text += f"🟢 STRONG_BUY (24h): {stats.get('STRONG_BUY', 0)}\n"
            text += f"📈 BUY (24h): {stats.get('BUY', 0)}\n"
            text += f"📉 SELL (24h): {stats.get('SELL', 0)}\n"
            text += f"🔴 STRONG_SELL (24h): {stats.get('STRONG_SELL', 0)}\n"
        else:
            text += "❌ Redis unavailable\n"

        text += "\n💡 **Commands:**\n"
        text += "• `/autotrade_status` - Auto-trade status\n"
        text += "• `/status` - Bot system status\n"

        await self._send_message(update, context, text, parse_mode='Markdown')

    # =============================================================================
    # AUTO-TRADE PAIRS MANAGEMENT (SEPARATE FROM WATCHLIST)
    # =============================================================================

    async def add_autotrade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Add pairs to auto-trade list (SEPARATE from watchlist/scalper)
        Usage: /add_autotrade <PAIR> atau /add_autotrade <PAIR1>, <PAIR2>
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        if not context.args:
            await self._send_message(update, context,
                "🤖 **Tambah Pair Auto-Trade**\n\n"
                "Pair auto-trade **terpisah** dari watchlist/scalper.\n\n"
                "Usage: `/add_autotrade <PAIR>` atau `/add_autotrade <P1>, <P2>`\n\n"
                "Contoh:\n"
                "• `/add_autotrade btcidr`\n"
                "• `/add_autotrade btcidr,ethidr,solidr`\n\n"
                "⚠️ Auto-trade hanya trade pair di daftar ini!",
                parse_mode='Markdown'
            )
            return

        user_id = update.effective_user.id

        # Parse comma-separated pairs
        pairs_input = ' '.join(context.args)
        raw_pairs_list = [p.strip() for p in pairs_input.split(',') if p.strip()]

        # Normalize pairs
        normalized_pairs = []
        for original_input in raw_pairs_list:
            pair = original_input.lower().replace('/', '')
            if not pair.endswith('idr'):
                pair = pair + 'idr'
            if pair.endswith('idr') and len(pair) >= 4:
                normalized_pairs.append(pair)

        if not normalized_pairs:
            await self._send_message(update, context, "❌ Tidak ada pair valid!", parse_mode='Markdown')
            return

        # Initialize user's auto-trade list
        if user_id not in self.auto_trade_pairs:
            self.auto_trade_pairs[user_id] = []

        # Add pairs (avoid duplicates)
        added_pairs = []
        existing_pairs = []
        for pair in normalized_pairs:
            if pair not in self.auto_trade_pairs[user_id]:
                self.auto_trade_pairs[user_id].append(pair)
                added_pairs.append(pair)
            else:
                existing_pairs.append(pair)

        # Build response
        messages = []
        if added_pairs:
            pairs_str = ', '.join([f"`{p.upper()}`" for p in added_pairs])
            messages.append(f"✅ **Ditambahkan ke Auto-Trade:** {pairs_str}")
            messages.append(f"\n📊 **Total Auto-Trade Pairs:** {len(self.auto_trade_pairs[user_id])}")
            messages.append("\n⚠️ **Penting:**")
            messages.append("• Pair ini akan di-auto-trade saat `/autotrade` ON")
            messages.append("• Scalping TIDAK terpengaruh (terpisah)")
            messages.append("• Watchlist `/watch` juga terpisah")

        if existing_pairs:
            existing_str = ', '.join([f"`{p.upper()}`" for p in existing_pairs])
            messages.append(f"\n⚠️ **Sudah ada di daftar:** {existing_str}")

        await self._send_message(update, context, '\n'.join(messages), parse_mode='Markdown')
        logger.info(f"🤖 User {user_id} added auto-trade pairs: {added_pairs}")

    async def remove_autotrade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Remove pairs from auto-trade list
        Usage: /remove_autotrade <PAIR> atau /remove_autotrade <PAIR1>, <PAIR2>
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        if not context.args:
            await self._send_message(update, context,
                "🗑️ **Hapus Pair Auto-Trade**\n\n"
                "Usage: `/remove_autotrade <PAIR>` atau `/remove_autotrade <P1>, <P2>`\n\n"
                "Contoh:\n"
                "• `/remove_autotrade btcidr`\n"
                "• `/remove_autotrade btcidr,ethidr`",
                parse_mode='Markdown'
            )
            return

        user_id = update.effective_user.id

        # Parse pairs
        pairs_input = ' '.join(context.args)
        raw_pairs_list = [p.strip() for p in pairs_input.split(',') if p.strip()]
        normalized_pairs = [p.lower().replace('/', '') + ('' if p.lower().replace('/', '').endswith('idr') else 'idr') for p in raw_pairs_list]

        if user_id not in self.auto_trade_pairs:
            await self._send_message(update, context, "❌ Tidak ada pair di daftar auto-trade!", parse_mode='Markdown')
            return

        # Remove pairs
        removed_pairs = []
        not_found = []
        for pair in normalized_pairs:
            if pair in self.auto_trade_pairs[user_id]:
                self.auto_trade_pairs[user_id].remove(pair)
                removed_pairs.append(pair)
            else:
                not_found.append(pair)

        # Build response
        messages = []
        if removed_pairs:
            pairs_str = ', '.join([f"`{p.upper()}`" for p in removed_pairs])
            messages.append(f"🗑️ **Dihapus dari Auto-Trade:** {pairs_str}")
            remaining = len(self.auto_trade_pairs.get(user_id, []))
            messages.append(f"\n📊 **Sisa Auto-Trade Pairs:** {remaining}")

            if remaining == 0:
                messages.append("\n⚠️ **Tidak ada pair auto-trade!**")
                messages.append("Gunakan `/add_autotrade` untuk menambah pair.")
        else:
            messages.append("⚠️ Tidak ada pair yang dihapus dari daftar auto-trade")

        if not_found:
            not_found_str = ', '.join([f"`{p.upper()}`" for p in not_found])
            messages.append(f"\n❌ **Tidak ada di daftar:** {not_found_str}")

        await self._send_message(update, context, '\n'.join(messages), parse_mode='Markdown')
        logger.info(f"🤖 User {user_id} removed auto-trade pairs: {removed_pairs}")

    async def list_autotrade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's auto-trade pairs (SEPARATE from watchlist)"""
        user_id = update.effective_user.id
        user_autotrade = self.auto_trade_pairs.get(user_id, [])

        if user_autotrade:
            pairs = '\n'.join([f"• `{p.upper()}`" for p in user_autotrade])
            text = f"""
🤖 **AUTO-TRADE PAIRS** ({len(user_autotrade)} pairs)

Pair yang akan di-auto-trade saat `/autotrade` ON:

{pairs}

⚠️ **Info:**
• Pair ini **terpisah** dari watchlist/scalper
• Scalping tidak terpengaruh
• Gunakan `/add_autotrade <pair>` untuk menambah
• Gunakan `/remove_autotrade <pair>` untuk menghapus
"""
        else:
            text = """
🤖 **AUTO-TRADE PAIRS**

⚠️ **Belum ada pair di daftar auto-trade!**

Pair auto-trade **terpisah** dari watchlist/scalper.

📋 **Cara tambah:**
• `/add_autotrade btcidr` - Tambah 1 pair
• `/add_autotrade btcidr,ethidr,solidr` - Tambah banyak

💡 **Kenapa terpisah?**
• Auto-trade pair = untuk trading otomatis
• Watchlist pair = untuk monitoring + scalping
• Keduanya tidak boleh tercampur!
"""

        await self._send_message(update, context, text, parse_mode='Markdown')

    async def hunter_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Show Smart Hunter bot status - INTEGRATED version
        Menggunakan smart_hunter yang sudah terintegrasi dengan bot utama
        """
        try:
            if update.effective_user.id not in Config.ADMIN_IDS:
                await self._send_message(update, context, "❌ Admin only!")
                return

            user_id = update.effective_user.id
            today = datetime.now().strftime('%Y-%m-%d')

            # Get status dari integrated smart_hunter
            hunter_status_data = self.smart_hunter.get_status()
            is_running = hunter_status_data.get('is_running', False)
            
            text = "🤖 **SMART HUNTER STATUS**\n\n"

            # Status - menggunakan integrated smart_hunter (BUKAN external file)
            status_emoji = "🟢" if is_running else "⚪"
            status_text = "RUNNING (Integrated)" if is_running else "STOPPED"
            text += f"📊 **Hunter Status:** {status_emoji} {status_text}\n"
            text += "🔗 **Mode:** Terintegrasi dengan bot utama\n\n"

            # Get today's trades
            all_trades = self.db.get_trade_history(user_id, limit=50)

            hunter_trades = []
            if all_trades:
                for trade in all_trades:
                    try:
                        if hasattr(trade, 'keys'):
                            trade_dict = {key: getattr(trade, key) for key in trade.keys()}
                        else:
                            trade_dict = trade

                        notes = str(trade_dict.get('notes', '')).lower() if isinstance(trade_dict, dict) else ''
                        source = str(trade_dict.get('signal_source', '')).lower() if isinstance(trade_dict, dict) else ''

                        if 'auto' in notes or 'auto' in source or 'hunter' in notes:
                            trade_date = trade_dict.get('opened_at', '') if isinstance(trade_dict, dict) else ''
                            if isinstance(trade_date, datetime):
                                if trade_date.strftime('%Y-%m-%d') == today:
                                    hunter_trades.append(trade_dict)
                            elif isinstance(trade_date, str) and today in trade_date:
                                hunter_trades.append(trade_dict)
                    except Exception as e:
                        logger.debug(f"Trade parse error: {e}")
                        continue

            # Performance
            text += f"📈 **Today's Performance ({today}):**\n"
            text += f"• Hunter Trades: {len(hunter_trades)}\n"

            if hunter_trades:
                wins = sum(1 for t in hunter_trades if (t.get('profit_loss', 0) if isinstance(t, dict) else 0) > 0)
                losses = len(hunter_trades) - wins
                total_pnl = sum((t.get('profit_loss', 0) if isinstance(t, dict) else 0) for t in hunter_trades)
                win_rate = (wins / len(hunter_trades)) * 100 if hunter_trades else 0

                text += f"• Wins: {wins} | Losses: {losses}\n"
                text += f"• Win Rate: {win_rate:.1f}%\n"
                text += f"• P&L: `{Utils.format_currency(total_pnl)}` IDR\n"

                text += "\n📋 **Recent Trades:**\n"
                for trade in hunter_trades[:5]:
                    pair = trade.get('pair', 'N/A') if isinstance(trade, dict) else 'N/A'
                    pnl = trade.get('profit_loss', 0) if isinstance(trade, dict) else 0
                    pnl_sign = '+' if pnl >= 0 else ''
                    emoji = "✅" if pnl > 0 else "❌"
                    text += f"\n{emoji} `{pair}`: {pnl_sign}{Utils.format_currency(pnl)} IDR\n"
            else:
                text += "• No hunter trades today\n"

            # Open positions dari integrated smart_hunter
            active_positions = hunter_status_data.get('active_trades', 0)
            daily_trades = hunter_status_data.get('daily_trades', 0)
            daily_pnl = hunter_status_data.get('daily_pnl', 0)
            hunter_balance = hunter_status_data.get('balance', 0)

            text += "\n📊 **Smart Hunter Internal Stats:**\n"
            text += f"• Active Positions: {active_positions}\n"
            text += f"• Daily Trades: {daily_trades}\n"
            text += f"• Daily P&L: `{daily_pnl:,.0f}` IDR\n"
            text += f"• Hunter Balance: `{hunter_balance:,.0f}` IDR\n"

            # Open positions from database
            open_trades = self.db.get_open_trades(user_id)
            if open_trades:
                text += f"\n📊 **Open Positions ({len(open_trades)}):**\n"
                for trade in open_trades[:5]:
                    try:
                        if hasattr(trade, 'keys'):
                            trade_dict = {key: getattr(trade, key) for key in trade.keys()}
                        else:
                            trade_dict = trade

                        pair = trade_dict.get('pair', 'N/A') if isinstance(trade_dict, dict) else 'Unknown'
                        trade_type = trade_dict.get('type', 'N/A') if isinstance(trade_dict, dict) else 'N/A'
                        price = trade_dict.get('price', 0) if isinstance(trade_dict, dict) else 0
                        amount = trade_dict.get('amount', 0) if isinstance(trade_dict, dict) else 0

                        if pair in self.price_data:
                            current = self.price_data[pair].get('last', price)
                            pnl_pct = ((current - price) / price) * 100 if price > 0 else 0
                            pnl_emoji = "📈" if pnl_pct > 0 else "📉"
                            text += f"\n{pnl_emoji} `{trade_type}` {pair}\n"
                            text += f"   Entry: `{Utils.format_price(price)}` | Current: `{Utils.format_price(current)}` IDR\n"
                            text += f"   P&L: `{pnl_pct:+.1f}%` | Amount: `{amount}`\n"
                        else:
                            text += f"\n⏳ `{trade_type}` {pair}\n"
                            text += f"   Entry: `{Utils.format_price(price)}` IDR | Amount: `{amount}`\n"
                    except Exception as e:
                        logger.debug(f"Open trade display error: {e}")
                        continue
            else:
                text += "\n📊 Open Positions: 0\n"

            # Balance - Get REAL balance from Indodax API
            try:
                from api.indodax_api import IndodaxAPI
                indodax = IndodaxAPI()
                indodax_balance = indodax.get_balance()

                if indodax_balance:
                    if isinstance(indodax_balance, dict):
                        balance_data = indodax_balance.get('balance', {})
                        idr_balance = float(balance_data.get('idr', 0))
                    else:
                        idr_balance = 0

                    if idr_balance > 0:
                        text += f"\n💵 **Indodax Balance:** `{Utils.format_currency(idr_balance)}`\n"
                    else:
                        text += "\n💵 **Indodax Balance:** 0\n"
                else:
                    text += "\n💵 **Balance:** N/A (API error)\n"

            except Exception as e:
                logger.debug(f"Balance fetch error: {e}")
                metrics = self.risk_manager.get_risk_metrics(user_id)
                text += f"\n💵 **Balance:** `{Utils.format_currency(metrics.get('available_balance', 0))}` IDR\n"

            # Commands - FIXED: No more external file reference
            text += "\n💡 **Kontrol Smart Hunter:**\n"
            text += "• `/smarthunter on` - Start Smart Hunter (integrated)\n"
            text += "• `/smarthunter off` - Stop Smart Hunter\n"
            text += "• `/smarthunter_status` - Detail status & posisi\n"
            text += "\n💡 **Commands Lain:**\n"
            text += "• `/hunter_status` - Cek status (command ini)\n"
            text += "• `/balance` - Cek balance\n"
            text += "• `/scan` - Market opportunities\n"

            await self._send_message(update, context, text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Hunter status error: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}")

    # =============================================================================
    # SMART HUNTER COMMANDS
    # =============================================================================

    async def smarthunter_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Smart Hunter control command: /smarthunter on/off"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        if not context.args or len(context.args) == 0:
            # Show help
            text = """
🤖 **SMART HUNTER CONTROL**

💡 **Usage:**
`/smarthunter on` - Start Smart Hunter
`/smarthunter off` - Stop Smart Hunter
`/smarthunter_status` - Check status & positions

📊 **Strategy:**
• Partial sell at +3% (50%), +5% (30%), +8% (20%)
• Trailing stop at 1.5%
• Hard stop loss at -2%
• Max 5 trades per day
• Min risk/reward: 3:1

⚠️ **Note:**
Smart Hunter runs independently from main bot's auto-trade mode.
It uses its own analysis (RSI, MACD, Volume, MA, Bollinger).
"""
            await self._send_message(update, context, text, parse_mode='Markdown')
            return

        action = context.args[0].lower()

        if action in ['on', 'start', 'enable']:
            if self.smart_hunter.is_running:
                await self._send_message(update, context, "⚠️ Smart Hunter is already running")
                return

            success = await self.smart_hunter.start()
            if success:
                await self._send_message(update, context, "🚀 **Smart Hunter STARTED**\n\n✅ Background monitoring active\n📊 Partial sell: +3%, +5%, +8%\n🛑 Stop loss: -2%\n\nUse `/smarthunter_status` to check progress")
            else:
                await self._send_message(update, context, "❌ Failed to start Smart Hunter")

        elif action in ['off', 'stop', 'disable']:
            if not self.smart_hunter.is_running:
                await self._send_message(update, context, "⚠️ Smart Hunter is not running")
                return

            success = await self.smart_hunter.stop()
            if success:
                await self._send_message(update, context, "🛑 **Smart Hunter STOPPED**\n\n✅ Background monitoring disabled\n📊 Open positions remain active\n\nUse `/smarthunter on` to restart")
            else:
                await self._send_message(update, context, "❌ Failed to stop Smart Hunter")

        else:
            await self._send_message(update, context, f"❌ Unknown action: `{action}`\n\nUse `/smarthunter` for help")

    async def smarthunter_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show Smart Hunter status"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        try:
            text = await self.smart_hunter.send_status_message(update, context)
            await self._send_message(update, context, text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Smart Hunter status error: {e}")
            await self._send_message(update, context, f"❌ Error: {str(e)}")

    async def ultra_hunter_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ultra Conservative Hunter control command"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        # user_id = update.effective_user.id  # Available but not used here

        # Check arguments
        if not context.args or len(context.args) == 0:
            # Show help
            text = """
🛡️ **ULTRA CONSERVATIVE HUNTER**

📊 **Settings:**
• Max Position: 100k IDR
• Max Trades/Day: 2
• Max Daily Loss: 100k IDR
• Take Profit: +4%
• Stop Loss: -2%
• Cooldown: 1h after loss

📋 **Entry Criteria:**
• RSI: 30-45 (Oversold)
• MACD: Bullish
• MA: Bullish
• Bollinger: Lower band
• Volume: 2x+ average

💡 **Commands:**
• `/ultrahunter start` - Start hunter
• `/ultrahunter stop` - Stop hunter
• `/ultrahunter status` - Check status
• `/hunter_status` - Detailed status

ℹ️ **Note:**
• Ultra Hunter runs SEPARATELY from bot auto-trade
• Bot auto-trade (`/autotrade`) can run independently
• Running both may cause double positions

⚠️ **Risk Warning:**
• Trades use REAL money
• Start with small amounts
• Monitor regularly
            """
            await self._send_message(update, context, text, parse_mode='Markdown')
            return
        
        action = context.args[0].lower()
        
        if action == 'start':
            # Check if already running
            import os
            import subprocess
            
            # Check if ultra_hunter.py is already running
            hunter_running = False
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = ' '.join(proc.info.get('cmdline', []))
                        if ('ultra_hunter.py' in cmdline or 'trading/ultra_hunter' in cmdline) and proc.info['pid'] != os.getpid():
                            hunter_running = True
                            break
                    except Exception:
                        continue
            except Exception:
                # Fallback: check log file modification time
                if os.path.exists('logs/ultra_hunter.log'):
                    mtime = os.path.getmtime('logs/ultra_hunter.log')
                    if time.time() - mtime < 120:  # Modified in last 2 min
                        hunter_running = True
            
            if hunter_running:
                await self._send_message(update, context, 
                    "⚠️ **Ultra Hunter is ALREADY RUNNING**\n\n"
                    "Use `/ultrahunter stop` to stop it first.")
                return
            
            # Check if bot.py auto-trade is ON
            if self.is_trading:
                await self._send_message(update, context,
                    "⚠️ **WARNING: Bot Auto-Trade is ON**\n\n"
                    "🚨 Running BOTH auto-traders may cause:\n"
                    "• Double positions (2x risk)\n"
                    "• Conflicting trades\n"
                    "• Higher loss potential\n\n"
                    "💡 **Recommendation:**\n"
                    "Use `/stop_trading` first, OR\n"
                    "Proceed with caution\n\n"
                    "**Reply START to confirm** or **CANCEL** to abort",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ START Anyway", callback_data="ultra_start_confirm"),
                        InlineKeyboardButton("❌ CANCEL", callback_data="ultra_cancel")
                    ]]))
                # Store state for callback
                context.user_data['ultra_start_pending'] = True
                return
            
            # Start ultra_hunter.py in background
            try:
                import sys
                # Start as background process
                if sys.platform == 'win32':
                    # Windows
                    subprocess.Popen(
                        ['python', '-m', 'trading.ultra_hunter'],
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        stdout=open('logs/ultra_hunter_stdout.log', 'w'),
                        stderr=open('logs/ultra_hunter_stderr.log', 'w')
                    )
                else:
                    # Linux/Mac
                    subprocess.Popen(
                        ['python', '-m', 'trading.ultra_hunter'],
                        stdout=open('logs/ultra_hunter_stdout.log', 'w'),
                        stderr=open('logs/ultra_hunter_stderr.log', 'w'),
                        start_new_session=True
                    )
                
                logger.info("✅ Ultra Hunter started")
                
                await asyncio.sleep(3)  # Wait for startup
                
                # Check if started successfully
                if os.path.exists('logs/ultra_hunter.log'):
                    await self._send_message(update, context,
                        "✅ **ULTRA HUNTER STARTED**\n\n"
                        "🛡️ Ultra Conservative Hunter is now RUNNING\n\n"
                        "📊 **Settings:**\n"
                        "• Max Position: 100k IDR\n"
                        "• Max Trades/Day: 2\n"
                        "• Take Profit: +4%\n"
                        "• Stop Loss: -2%\n\n"
                        "📝 Log: `logs/ultra_hunter.log`\n\n"
                        "Use `/ultrahunter stop` to stop\n"
                        "Use `/hunter_status` to check status",
                        parse_mode='Markdown')
                else:
                    await self._send_message(update, context,
                        "⚠️ **Hunter starting...**\n\n"
                        "Wait a few seconds then check with `/hunter_status`")
                        
            except Exception as e:
                logger.error(f"Failed to start Ultra Hunter: {e}")
                await self._send_message(update, context, 
                    f"❌ **Failed to start:**\n\n`{str(e)}`\n\n"
                    f"Try manually: `python -m trading.ultra_hunter`")
        
        elif action == 'stop':
            # Try to stop the hunter
            stopped = False
            
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = ' '.join(proc.info.get('cmdline', []))
                        if 'ultra_hunter.py' in cmdline and proc.info['pid'] != os.getpid():
                            proc.terminate()
                            stopped = True
                            logger.info(f"✅ Stopped Ultra Hunter (PID: {proc.info['pid']})")
                    except Exception:
                        continue
            except Exception:
                pass
            
            if stopped:
                await self._send_message(update, context,
                    "✅ **ULTRA HUNTER STOPPED**\n\n"
                    "Bot will no longer execute trades.\n\n"
                    "Use `/ultrahunter start` to restart")
            else:
                await self._send_message(update, context,
                    "ℹ️ **Ultra Hunter not running**\n\n"
                    "Use `/ultrahunter start` to start it")
        
        elif action == 'status':
            # Quick status
            import os
            
            # Check if running
            running = False
            try:
                import psutil
                for proc in psutil.process_iter(['cmdline']):
                    try:
                        cmdline = ' '.join(proc.info.get('cmdline', []))
                        if 'ultra_hunter.py' in cmdline:
                            running = True
                            break
                    except Exception:
                        continue
            except Exception:
                if os.path.exists('logs/ultra_hunter.log'):
                    mtime = os.path.getmtime('logs/ultra_hunter.log')
                    if time.time() - mtime < 120:
                        running = True
            
            status_emoji = "🟢" if running else "⚪"
            status_text = "RUNNING" if running else "STOPPED"
            
            # Get last log line
            last_log = "N/A"
            if os.path.exists('logs/ultra_hunter.log'):
                try:
                    with open('logs/ultra_hunter.log', 'r') as f:
                        lines = f.readlines()
                        if lines:
                            last_log = lines[-1].strip()
                except Exception:
                    pass
            
            text = f"""
🛡️ **ULTRA HUNTER STATUS**

📊 Status: {status_emoji} {status_text}

📝 **Last Activity:**
`{last_log}`

💡 **Commands:**
• `/ultrahunter start` - Start
• `/ultrahunter stop` - Stop
• `/hunter_status` - Detailed status
            """
            
            await self._send_message(update, context, text, parse_mode='Markdown')
        
        else:
            await self._send_message(update, context,
                "❌ **Unknown command**\n\n"
                "Use `/ultrahunter` (no args) for help")

    async def signal_quality_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Analyze signal quality for a specific pair.
        Usage: /signal_quality <PAIR> [BUY|SELL|HOLD]
        Example: /signal_quality btcidr BUY
        """
        if not context.args or len(context.args) < 1:
            await self._send_message(update, context,
                "🔍 **Signal Quality Analyzer**\n\n"
                "Usage: `/signal_quality <PAIR> [TYPE]`\n\n"
                "**Examples:**\n"
                "• `/signal_quality btcidr` — All signal types\n"
                "• `/signal_quality btcidr BUY` — BUY signals only\n"
                "• `/signal_quality ethidr SELL` — SELL signals only",
                parse_mode='Markdown'
            )
            return

        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        symbol = context.args[0].strip()
        rec_type = context.args[1].upper() if len(context.args) > 1 else None

        try:
            text = await self._build_signal_quality_text(symbol, rec_type)
            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Signal quality analysis failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text(f"❌ **Analysis Failed**\n\nError: `{str(e)}`", parse_mode='Markdown')

    async def _build_signal_quality_text(self, symbol: str, rec_type: str) -> str:
        """Build signal quality report text — isolated to prevent event loop conflicts"""
        import sqlite3 as sqlite3_mod
        from datetime import datetime, timedelta

        signals_db_path = "data/signals.db"
        trading_db_path = "data/trading.db"
        cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        symbol_upper = symbol.upper()

        conn = sqlite3_mod.connect(signals_db_path)
        conn.row_factory = sqlite3_mod.Row
        cursor = conn.cursor()

        conn2 = sqlite3_mod.connect(trading_db_path)
        conn2.row_factory = sqlite3_mod.Row
        cursor2 = conn2.cursor()

        try:
            if rec_type and rec_type in ['BUY', 'SELL', 'HOLD', 'STRONG_BUY', 'STRONG_SELL']:
                cursor.execute(
                    'SELECT price, received_at FROM signals WHERE symbol = ? AND recommendation = ? AND received_date >= ? ORDER BY received_at ASC',
                    (symbol_upper, rec_type, cutoff)
                )
                signals = cursor.fetchall()
                total_signals = len(signals)

                wins = 0
                losses = 0
                neutral = 0
                profits = []
                hold_times = []

                for sig in signals:
                    sig_price = sig['price']
                    sig_time = sig['received_at']
                    if not sig_price or sig_price <= 0:
                        continue
                    cursor2.execute(
                        'SELECT close, timestamp FROM price_history WHERE pair = ? AND timestamp > ? ORDER BY timestamp ASC LIMIT 50',
                        (symbol.lower(), sig_time)
                    )
                    future = cursor2.fetchall()
                    if future:
                        # Calculate PnL based on signal type
                        is_buy = rec_type in ['BUY', 'STRONG_BUY']
                        is_sell = rec_type in ['SELL', 'STRONG_SELL']

                        if is_buy:
                            # BUY: profit when price goes UP
                            best = max(f['close'] for f in future)
                            pnl = ((best - sig_price) / sig_price) * 100
                            best_idx = next((i for i, f in enumerate(future) if f['close'] == best), 0)
                        elif is_sell:
                            # SELL: profit when price goes DOWN (short logic)
                            lowest = min(f['close'] for f in future)
                            pnl = ((sig_price - lowest) / sig_price) * 100
                            best_idx = next((i for i, f in enumerate(future) if f['close'] == lowest), 0)
                        else:  # HOLD
                            price_change = ((future[-1]['close'] - sig_price) / sig_price) * 100
                            pnl = price_change
                            best_idx = len(future) // 2

                        hold_time_hours = best_idx * 0.25
                        if pnl > 0:
                            wins += 1
                            profits.append(pnl)
                            hold_times.append(hold_time_hours)
                        elif pnl < -0.5:
                            losses += 1
                        else:
                            neutral += 1

                total_valid = wins + losses + neutral
                win_rate = (wins / total_valid * 100) if total_valid > 0 else 0
                avg_profit = sum(profits) / len(profits) if profits else 0
                avg_loss = -(sum(profits) / len(profits) * 0.6) if profits else -2.0
                optimal_hold = sum(hold_times) / len(hold_times) if hold_times else 4.0

                score = 5.0
                if win_rate >= 70:
                    score += 2.5
                elif win_rate >= 60:
                    score += 1.5
                elif win_rate >= 50:
                    score += 0.5
                elif win_rate < 40:
                    score -= 2.0
                if avg_profit >= 3.0:
                    score += 1.0
                elif avg_profit >= 2.0:
                    score += 0.5
                elif avg_profit < 0:
                    score -= 1.5
                if total_signals >= 100:
                    score += 1.0
                elif total_signals >= 50:
                    score += 0.5
                elif total_signals < 20:
                    score -= 1.0
                score = max(1, min(10, round(score)))

                grade = 'A' if score >= 8 else 'B' if score >= 6 else 'C' if score >= 4 else 'D'
                label = '✅ EXCELLENT' if score >= 8 else '👍 GOOD' if score >= 6 else '⚠️ AVERAGE' if score >= 4 else '❌ POOR'

                text = "🔍 **SIGNAL QUALITY REPORT**\n\n"
                text += f"{'=' * 40}\n\n"
                text += f"📊 **Pair:** `{symbol_upper}`\n"
                text += f"📈 **Signal Type:** {rec_type}\n"
                text += f"🏆 **Quality Grade:** **{grade}** ({label})\n"
                text += f"⭐ **Score:** `{score}/10`\n\n"

                if total_valid > 0:
                    text += "📊 **Performance (Last 30 Days):**\n"
                    text += f"• Total Signals: `{total_signals}`\n"
                    text += f"• Analyzed: `{total_valid}`\n"
                    text += f"• ✅ Winning: `{wins}`\n"
                    text += f"• ❌ Losing: `{losses}`\n"
                    text += f"• ➖ Neutral: `{neutral}`\n\n"
                    text += "💰 **Profitability:**\n"
                    text += f"• Win Rate: **`{win_rate:.1f}%`**\n"
                    text += f"• Avg Profit (when right): `{avg_profit:+.1f}%`\n"
                    text += f"• Avg Loss (when wrong): `{avg_loss:+.1f}%`\n\n"
                    text += f"⏱️ **Optimal Hold Time:** `{optimal_hold:.1f} hours`\n\n"
                    if score >= 8:
                        text += "✅ **RECOMMENDATION: TAKE THIS SIGNAL**\nHistorical accuracy sangat bagus!"
                    elif score >= 6:
                        text += "👍 **RECOMMENDATION: CONSIDER TAKING**\nAccuracy cukup bagus, tapi hati-hati."
                    elif score >= 4:
                        text += "⚠️ **RECOMMENDATION: BE CAUTIOUS**\nWin rate rendah. Pertimbangkan skip."
                    else:
                        text += "❌ **RECOMMENDATION: SKIP THIS SIGNAL**\nFalse positive rate terlalu tinggi!"
                else:
                    text += "⚠️ **Tidak cukup data untuk analisis**\nButuh minimal 5 signals untuk analisis reliable."

                text += f"\n\n{'=' * 40}"
            else:
                text = f"📊 **SIGNAL QUALITY SUMMARY: `{symbol_upper}`**\n\n{'=' * 40}\n\n"
                for rt in ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']:
                    cursor.execute(
                        'SELECT COUNT(*) as total FROM signals WHERE symbol = ? AND recommendation = ? AND received_date >= ?',
                        (symbol_upper, rt, cutoff)
                    )
                    total = cursor.fetchone()['total']
                    if total > 0:
                        text += f"📈 **{rt}:** `{total}` signals\n\n"
                text += f"\n💡 Detail: `/signal_quality {symbol.lower()} <TYPE>`\n{'=' * 40}"

            return text

        finally:
            # Always close connections, even if error occurs
            try:
                conn.close()
            except Exception:
                pass
            try:
                conn2.close()
            except Exception:
                pass

    def _format_quality_report(self, quality: Dict) -> str:
        """Format quality report into readable text"""
        symbol = quality['symbol']
        rec = quality['recommendation']
        grade = quality['quality_grade']
        score = quality['score']
        score_label = quality['score_label']
        
        text = "🔍 **SIGNAL QUALITY REPORT**\n\n"
        text += "=" * 40 + "\n\n"
        text += f"📊 **Pair:** `{symbol}`\n"
        text += f"📈 **Signal Type:** {rec}\n"
        text += f"🏆 **Quality Grade:** **{grade}** ({score_label})\n"
        text += f"⭐ **Score:** `{score}/10`\n\n"
        
        if quality.get('reason'):
            text += f"⚠️ **Note:** {quality['reason']}\n\n"
        
        if quality['reliable'] and quality['win_rate'] is not None:
            text += "📊 **Performance (Last 30 Days):**\n"
            text += f"• Total Signals: `{quality['total_signals']}`\n"
            text += f"• Analyzed: `{quality['signals_analyzed']}`\n"
            text += f"• ✅ Winning: `{quality['winning_signals']}`\n"
            text += f"• ❌ Losing: `{quality['losing_signals']}`\n"
            text += f"• ➖ Neutral: `{quality['neutral_signals']}`\n\n"

            text += "💰 **Profitability:**\n"
            text += f"• Win Rate: **`{quality['win_rate']:.1f}%`**\n"
            text += f"• Avg Profit (when right): `{quality['avg_profit']:+.1f}%`\n"
            text += f"• Avg Loss (when wrong): `{quality.get('avg_loss', -2):+.1f}%`\n\n"
            
            if quality.get('optimal_hold_time'):
                text += f"⏱️ **Optimal Hold Time:** `{quality['optimal_hold_time']:.1f} hours`\n\n"

            text += "🤖 **ML Stats:**\n"
            text += f"• Avg Confidence: `{quality['avg_confidence']:.1%}`\n"
            text += f"• Avg Strength: `{quality['avg_strength']:+.2f}`\n\n"

            # Recommendation
            if score >= 8:
                text += "✅ **RECOMMENDATION: TAKE THIS SIGNAL**\n"
                text += "Historical accuracy sangat bagus!"
            elif score >= 6:
                text += "👍 **RECOMMENDATION: CONSIDER TAKING**\n"
                text += "Accuracy cukup bagus, tapi hati-hati."
            elif score >= 4:
                text += "⚠️ **RECOMMENDATION: BE CAUTIOUS**\n"
                text += "Win rate rendah. Pertimbangkan skip."
            else:
                text += "❌ **RECOMMENDATION: SKIP THIS SIGNAL**\n"
                text += "False positive rate terlalu tinggi!"
        else:
            text += "⚠️ **Tidak cukup data untuk analisis**\n"
            text += "Butuh minimal 20 signals untuk analisis reliable."

        text += "\n\n" + "=" * 40
        return text

    def _format_quality_summary(self, symbol: str, summary: Dict) -> str:
        """Format summary of all signal types for a pair"""
        text = f"📊 **SIGNAL QUALITY SUMMARY: `{symbol}`**\n\n"
        text += "=" * 40 + "\n\n"
        
        for rec_type in ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']:
            q = summary.get(rec_type, {})
            if q.get('reliable') and q.get('win_rate') is not None:
                grade = q['quality_grade']
                score = q['score']
                win_rate = q['win_rate']
                total = q['total_signals']
                
                emoji_map = {
                    'A': '✅',
                    'B': '👍',
                    'C': '⚠️',
                    'D': '❌',
                    'F': '❌'
                }
                emoji = emoji_map.get(grade, '❓')
                
                text += f"{emoji} **{rec_type}:**\n"
                text += f"   Score: `{score}/10` | Win Rate: `{win_rate:.1f}%` | Signals: `{total}`\n\n"
            elif q.get('total_signals', 0) > 0:
                text += f"⚠️ **{rec_type}:** {q['total_signals']} signals (need 20+ for analysis)\n\n"
        
        text += "\n💡 Detail: `/signal_quality " + symbol.lower() + " <TYPE>`"
        text += "\n" + "=" * 40
        return text

    async def signal_report_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Show top performing pairs by signal win rate.
        Usage: /signal_report [BUY|SELL] [limit]
        Example: /signal_report BUY 10
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        rec_type = context.args[0].upper() if context.args and context.args[0].upper() in ['BUY', 'SELL'] else 'BUY'
        limit = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 10

        try:
            # Direct SQLite query — keep connections open until all queries done
            import sqlite3 as sqlite3_mod
            from datetime import datetime, timedelta

            signals_db_path = "data/signals.db"
            trading_db_path = "data/trading.db"
            cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

            # Open BOTH connections, keep open until all work done
            conn = sqlite3_mod.connect(signals_db_path)
            conn.row_factory = sqlite3_mod.Row
            cursor = conn.cursor()

            conn2 = sqlite3_mod.connect(trading_db_path)
            conn2.row_factory = sqlite3_mod.Row
            cursor2 = conn2.cursor()

            # Get candidate pairs
            cursor.execute('''
                SELECT symbol, COUNT(*) as total, AVG(ml_confidence) as avg_conf
                FROM signals
                WHERE recommendation = ? AND received_date >= ?
                GROUP BY symbol
                HAVING total >= 5
                ORDER BY total DESC
                LIMIT ?
            ''', (rec_type, cutoff, limit * 2))
            candidates = [dict(row) for row in cursor.fetchall()]

            if not candidates:
                conn.close()
                conn2.close()
                await update.message.reply_text(
                    f"⚠️ **No reliable {rec_type} signals found**\n\nButuh minimal 5 signals per pair."
                )
                return

            # Calculate win rate for each candidate
            results = []
            for c in candidates:
                symbol = c['symbol']
                pair_lower = symbol.lower()

                # Get signals for this pair
                cursor.execute(
                    'SELECT price, received_at FROM signals WHERE symbol = ? AND recommendation = ? AND received_date >= ? ORDER BY received_at ASC',
                    (symbol, rec_type, cutoff)
                )
                signals = cursor.fetchall()

                wins = 0
                profits = []
                for sig in signals:
                    sig_price = sig['price']
                    sig_time = sig['received_at']
                    if not sig_price or sig_price <= 0:
                        continue
                    cursor2.execute(
                        'SELECT close FROM price_history WHERE pair = ? AND timestamp > ? ORDER BY timestamp ASC LIMIT 50',
                        (pair_lower, sig_time)
                    )
                    future = cursor2.fetchall()
                    if future:
                        best = max(f['close'] for f in future)
                        pnl = ((best - sig_price) / sig_price) * 100
                        if pnl > 0:
                            wins += 1
                            profits.append(pnl)

                total_valid = len(signals)
                if total_valid > 0:
                    win_rate = (wins / total_valid) * 100
                    avg_profit = sum(profits) / len(profits) if profits else 0
                    score = min(10, max(1, round(5 + (win_rate - 50) / 10 + (avg_profit / 5))))
                    results.append({
                        'symbol': symbol,
                        'win_rate': win_rate,
                        'total_signals': total_valid,
                        'score': score,
                        'avg_profit': avg_profit,
                    })

            # Close connections AFTER all queries done
            conn.close()
            conn2.close()

            # Sort by avg_profit DESCENDING (most profitable first)
            results.sort(key=lambda x: x['avg_profit'], reverse=True)
            top_pairs = results[:limit]

            if not top_pairs:
                await update.message.reply_text(
                    f"⚠️ **No reliable {rec_type} signals found**\n\nButuh minimal 5 signals per pair."
                )
                return

            # Build response with current prices
            text = "🏆 **TOP " + str(limit) + " PAIRS — " + rec_type + " SIGNALS**\n\n"
            text += "=" * 40 + "\n\n"
            for i, p in enumerate(top_pairs, 1):
                emoji = "✅" if p['score'] >= 7 else "👍" if p['score'] >= 5 else "⚠️"
                symbol = p['symbol']

                # Get current price from cache or API
                current_price = None
                try:
                    from cache.redis_price_cache import price_cache as redis_cache
                    current_price = redis_cache.get_price_sync(symbol.lower())
                except Exception:
                    pass

                if current_price is None and symbol.lower() in self.price_data:
                    current_price = self.price_data[symbol.lower()].get('last')

                price_str = f"`{Utils.format_price(current_price)}`" if current_price else "N/A"

                text += f"{i}. {emoji} **{symbol}** — {price_str} IDR\n"
                text += f"   Win Rate: `{p['win_rate']:.1f}%` | Score: `{p['score']}/10`\n"
                text += f"   Signals: `{p['total_signals']}` | Avg Profit: `{p['avg_profit']:+.1f}%`\n"
                text += f"   💰 Buy: `/trade BUY {symbol.lower()} {int(current_price) if current_price else 0} 100000`\n\n"
            text += "=" * 40 + "\n"
            text += "\n💡 Quick Buy: `/trade BUY <pair> <price> <idr_amount>`"
            text += "\n💡 Detail: `/signal_quality <pair> " + rec_type + "`"

            await update.message.reply_text(text, parse_mode='Markdown')

        except Exception as e:
            logger.error("❌ Signal report failed: %s", e)
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text("❌ **Report Failed**\n\nError: `" + str(e) + "`", parse_mode='Markdown')

    async def retrain_ml(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manually retrain ML model (admin only) - Uses V2 model if available"""
        logger.info("🔍 /retrain command received")

        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        logger.info(f"🤖 Starting ML model retrain (using {self.ml_version})...")
        msg = await update.message.reply_text(
            f"🤖 Retraining ML Model ({self.ml_version})...\n\n"
            f"📊 Collecting data from all pairs..."
        )

        try:
            # FIX: Get ALL pairs from database that have data (not just WATCH_PAIRS)
            # This ensures pairs like auraidr, pixelidr, zenidr, chillguyidr are included
            all_pairs_in_db = set()
            
            # Method 1: Get unique pairs from price_history table
            try:
                price_df = self.db.execute("SELECT DISTINCT pair FROM price_history")
                if price_df is not None and not price_df.empty:
                    all_pairs_in_db.update(price_df['pair'].tolist())
            except:
                pass
            
            # Method 2: Also check user watchlist
            try:
                watchlist_df = self.db.execute("SELECT pair FROM watchlist")
                if watchlist_df is not None and not watchlist_df.empty:
                    all_pairs_in_db.update(watchlist_df['pair'].tolist())
            except:
                pass
            
            # Combine with WATCH_PAIRS as fallback
            pairs_to_check = list(all_pairs_in_db) if all_pairs_in_db else Config.WATCH_PAIRS
            
            # Collect DataFrames in list, concat once at end (memory efficient)
            data_frames = []
            pairs_with_data = []

            for pair in pairs_to_check:
                pair = pair.strip()
                if not pair:
                    continue
                df = self.db.get_price_history(pair, limit=5000)
                if df is not None and not df.empty:
                    data_frames.append(df)
                    pairs_with_data.append(f"• {pair}: {len(df)} candles")
                else:
                    pairs_with_data.append(f"• {pair}: 0 candles")

            # FIX: Concat all at once
            if data_frames:
                all_data = pd.concat(data_frames, ignore_index=True)
            else:
                all_data = pd.DataFrame()

            data_summary = "\n".join(pairs_with_data) if pairs_with_data else "❌ No data in database yet"
            total_candles = len(all_data)

            logger.info(f"📊 Total candles collected: {total_candles}")

            await msg.edit_text(
                f"🤖 **ML Training Data Summary:**\n\n"
                f"📊 **Total candles:** `{total_candles}`\n"
                f"📈 **Need:** `100+` for training\n\n"
                f"**Per pair:**\n{data_summary}\n\n"
                f"{'⏳ Starting training...' if total_candles > 100 else '❌ Not enough data yet'}",
                parse_mode='Markdown'
            )

            if total_candles <= 100:
                await msg.edit_text(
                    f"{msg.text}\n\n"
                    f"💡 **Tips:**\n"
                    f"• Bot perlu ~10-15 menit polling untuk kumpul data\n"
                    f"• Pastikan pair sudah di-`/watch`\n"
                    f"• Cek log untuk candle count",
                    parse_mode='Markdown'
                )
                return

            # FIX: Run training in background thread so bot stays responsive
            await msg.edit_text(
                f"🤖 **ML Training Data Summary:**\n\n"
                f"📊 **Total candles:** `{total_candles}`\n"
                f"📈 **Need:** `100+` for training\n\n"
                f"**Per pair:**\n{data_summary}\n\n"
                f"⏳ **Training started in background...**\n"
                f"💡 Bot tetap responsive. Hasil akan dikirim setelah selesai.",
                parse_mode='Markdown'
            )

            # Store data for background thread
            self._pending_train_data = all_data
            self._pending_train_msg = msg

            # Start training in background thread
            import threading
            thread = threading.Thread(
                target=self._run_ml_training_bg,
                args=(all_data, msg),
                daemon=True,
                name="ML-Train-Background"
            )
            thread.start()
            logger.info("🔄 ML training started in background thread")

        except Exception as e:
            logger.error(f"Error retraining ML: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text(f"❌ Error: {str(e)}")

    def _run_ml_training_bg(self, all_data, msg):
        """Run ML training in background thread (non-blocking)"""
        try:
            logger.info(f"🤖 Background ML training started with {len(all_data)} candles")

            if self.ml_version == 'V2':
                success = self.ml_model.train(all_data, use_multi_class=False)
            else:
                success = self.ml_model.train(all_data)

            if success:
                accuracy = getattr(self.ml_model, 'last_accuracy', 'N/A')
                recall = getattr(self.ml_model, 'last_recall', 'N/A')
                precision = getattr(self.ml_model, 'last_precision', 'N/A')
                f1 = getattr(self.ml_model, 'last_f1', 'N/A')
                
                accuracy_str = f"{accuracy:.2%}" if isinstance(accuracy, (int, float)) else str(accuracy)
                recall_str = f"{recall:.2%}" if isinstance(recall, (int, float)) else str(recall)
                precision_str = f"{precision:.2%}" if isinstance(precision, (int, float)) else str(precision)
                f1_str = f"{f1:.2%}" if isinstance(f1, (int, float)) else str(f1)
                
                # NEW: Get undersampling info
                undersample_info = getattr(self.ml_model, 'last_undersample_info', None)
                undersample_text = ""
                if undersample_info and undersample_info.get('applied'):
                    undersample_text = (
                        f"\n📊 **Undersampling Applied:**\n"
                        f"`{undersample_info['before']}`\n\n"
                        f"`{undersample_info['after']}`"
                    )
                elif undersample_info:
                    undersample_text = f"\n📊 **Class Balance:**\n`{undersample_info.get('message', 'Balanced')}`"
                
                text = (
                    f"✅ **ML Model Retrained!**\n\n"
                    f"📊 Data used: `{len(all_data)}` candles\n"
                    f"🎯 Accuracy: `{accuracy_str}`\n"
                    f"🎯 Recall: `{recall_str}`\n"
                    f"🎯 Precision: `{precision_str}`\n"
                    f"🎯 F1 Score: `{f1_str}`\n"
                    f"{undersample_text}\n\n"
                    f"💡 Signals will now include ML confidence!\n\n"
                    f"🔔 **RETRAIN SELESAI**"
                )
            else:
                text = "❌ Failed to train model. Try again with more data.\n\n🔔 **RETRAIN SELESAI**"

            # Send result via bot loop
            import asyncio
            asyncio.run_coroutine_threadsafe(
                msg.edit_text(text, parse_mode='Markdown'),
                self.app.loop
            )
            logger.info("✅ Background ML training completed")

        except Exception as e:
            logger.error("❌ Background ML training failed: %s", e)
            import asyncio
            asyncio.run_coroutine_threadsafe(
                msg.edit_text(f"❌ Training error: {str(e)}\n\n🔔 **RETRAIN SELESAI**", parse_mode='Markdown'),
                self.app.loop
            )

    async def backtest_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Run backtest simulation
        Usage: /backtest <PAIR> <DAYS>
        Example: /backtest btcidr 30
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "📈 **Backtest Command**\n\n"
                "Usage: `/backtest <PAIR> <DAYS>`\n\n"
                "Examples:\n"
                "• `/backtest btcidr 30` - Backtest 30 hari\n"
                "• `/backtest ethidr 7` - Backtest 7 hari\n"
                "• `/backtest solidr 90` - Backtest 90 hari\n\n"
                "Backtest akan mensimulasikan trading strategy bot pada data historis.",
                parse_mode='Markdown'
            )
            return

        # Parse arguments
        pair = context.args[0].lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        try:
            days = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Days harus berupa angka!\nContoh: `/backtest btcidr 30`", parse_mode='Markdown')
            return

        if days < 1 or days > 365:
            await update.message.reply_text("❌ Days harus antara 1-365!", parse_mode='Markdown')
            return

        # Send initial message
        msg = await update.message.reply_text(
            f"📊 **Running Backtest...**\n\n"
            f"Pair: `{pair.upper()}`\n"
            f"Period: `{days}` days\n\n"
            f"⏳ Loading historical data...",
            parse_mode='Markdown'
        )

        try:
            # Import backtester
            from analysis.backtester import Backtester
            from datetime import datetime, timedelta

            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Initialize backtester
            backtester = Backtester(self.db, self.ml_model)

            await msg.edit_text(
                f"📊 **Running Backtest...**\n\n"
                f"Pair: `{pair.upper()}`\n"
                f"Period: `{days}` days\n"
                f"From: `{start_date.strftime('%Y-%m-%d')}`\n"
                f"To: `{end_date.strftime('%Y-%m-%d')}`\n\n"
                f"⏳ Running simulation...",
                parse_mode='Markdown'
            )

            # Run backtest
            import asyncio
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: backtester.run_backtest(pair, start_date, end_date)
            )

            if results is None:
                await msg.edit_text(
                    f"❌ **Backtest Failed**\n\n"
                    f"Tidak ada data yang cukup untuk `{pair.upper()}` dalam {days} hari terakhir.\n\n"
                    f"💡 Pastikan pair sudah di-`/watch` dan bot sudah berjalan cukup lama.",
                    parse_mode='Markdown'
                )
                return

            # Format results - handle nested metrics
            total_trades = results.get('total_trades', 0)
            metrics = results.get('metrics', results)  # Fallback if metrics is nested
            
            # Try both formats
            if 'metrics' in results:
                metrics = results['metrics']
                total_trades = metrics.get('total_trades', 0)
                winning_trades = metrics.get('winning_trades', 0)
                losing_trades = metrics.get('losing_trades', 0)
                win_rate = metrics.get('win_rate', 0)
                total_pnl = metrics.get('avg_pnl', 0) * total_trades  # Approximate total PnL
                pnl_pct = results.get('total_return', metrics.get('total_return', 0))
                max_drawdown = metrics.get('max_drawdown', 0)
                sharpe_ratio = metrics.get('sharpe_ratio', 0)
                final_balance = results.get('final_balance', 0)
                initial_balance = results.get('initial_balance', 0)
            else:
                # Flat format (fallback)
                total_trades = results.get('total_trades', 0)
                winning_trades = results.get('winning_trades', 0)
                losing_trades = results.get('losing_trades', 0)
                win_rate = (winning_trades / max(1, total_trades) * 100) if total_trades > 0 else 0
                total_pnl = results.get('total_pnl', 0)
                pnl_pct = results.get('pnl_percentage', 0)
                max_drawdown = results.get('max_drawdown', 0)
                sharpe_ratio = results.get('sharpe_ratio', 0)
                final_balance = results.get('final_balance', 0)
                initial_balance = results.get('initial_balance', 0)

            # Determine emoji based on results
            result_emoji = "🟢" if total_pnl >= 0 else "🔴"

            text = f"""
{result_emoji} **BACKTEST RESULTS**

📊 **Pair:** `{pair.upper()}`
📅 **Period:** `{days}` days
💰 **Initial Balance:** `{Utils.format_currency(initial_balance)}`
💰 **Final Balance:** `{Utils.format_currency(final_balance)}`

📈 **Performance:**
• Total P&L: `{Utils.format_currency(total_pnl)}` ({pnl_pct:+.2f}%)
• Win Rate: `{win_rate:.1f}%` ({winning_trades}W / {losing_trades}L)
• Total Trades: `{total_trades}`
• Max Drawdown: `{max_drawdown:.2f}%`
• Sharpe Ratio: `{sharpe_ratio:.2f}`

⚡ **Analysis:**
"""
            # Add analysis commentary
            if win_rate >= 60:
                text += "✅ Win rate bagus (>60%)\n"
            elif win_rate >= 50:
                text += "⚠️ Win rate cukup (50-60%)\n"
            else:
                text += "❌ Win rate rendah (<50%)\n"

            if sharpe_ratio >= 1.0:
                text += "✅ Sharpe ratio bagus (>1.0)\n"
            elif sharpe_ratio >= 0.5:
                text += "⚠️ Sharpe ratio cukup (0.5-1.0)\n"
            else:
                text += "❌ Sharpe ratio rendah (<0.5)\n"

            if max_drawdown <= 10:
                text += "✅ Drawdown terkontrol (<10%)\n"
            elif max_drawdown <= 20:
                text += "⚠️ Drawdown cukup (10-20%)\n"
            else:
                text += "❌ Drawdown tinggi (>20%)\n"

            # Add keyboard with plot option
            keyboard = [[
                InlineKeyboardButton("📊 Plot Results", callback_data=f"backtest_plot_{pair}_{days}")
            ]]

            await msg.edit_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            logger.info(f"✅ Backtest completed for {pair} ({days} days): {pnl_pct:+.2f}%")

        except Exception as e:
            logger.error(f"❌ Backtest error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await msg.edit_text(
                f"❌ **Backtest Error**\n\n"
                f"```\n{str(e)}\n```\n\n"
                f"Coba lagi dengan pair atau period yang berbeda.",
                parse_mode='Markdown'
            )

    async def backtest_v3_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        PRO Backtest using ML Model V3
        ============================
        Professional backtesting with:
        - Risk/Reward based target labeling
        - All fees and costs simulated
        - Kelly Criterion position sizing
        - Comprehensive metrics
        
        Usage: /backtest_v3 <PAIR> <DAYS>
        Example: /backtest_v3 btcidr 30
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        if not self.ml_model_v3:
            await update.message.reply_text(
                "❌ **ML Model V3 Not Available**\n\n"
                "Model V3 belum terinisialisasi.\n"
                "Cek log untuk error details.",
                parse_mode='Markdown'
            )
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "📈 **PRO Backtest (ML V3)**\n\n"
                "Usage: `/backtest_v3 <PAIR> <DAYS>`\n\n"
                "Examples:\n"
                "• `/backtest_v3 btcidr 30` - Backtest 30 hari\n"
                "• `/backtest_v3 ethidr 7` - Backtest 7 hari\n\n"
                "Features:\n"
                "✓ Risk/Reward based signals\n"
                "✓ All fees simulated (0.3% + slippage)\n"
                "✓ Kelly Criterion position sizing\n"
                "✓ Comprehensive metrics",
                parse_mode='Markdown'
            )
            return

        # Parse arguments
        pair = context.args[0].lower().replace('/', '')
        if not pair.endswith('idr'):
            pair += 'idr'
        
        try:
            days = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Days harus angka!\nContoh: `/backtest_v3 btcidr 30`", parse_mode='Markdown')
            return

        if days < 1 or days > 365:
            await update.message.reply_text("❌ Days harus 1-365!", parse_mode='Markdown')
            return

        # Send initial message
        msg = await update.message.reply_text(
            f"📊 **PRO Backtest (ML V3)...**\n\n"
            f"Pair: `{pair.upper()}`\n"
            f"Period: `{days}` days\n\n"
            f"⏳ Loading data...",
            parse_mode='Markdown'
        )

        try:
            # Get historical data from database
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Get price data
            df = self.db.get_price_history(pair, limit=5000)
            
            if df is None or len(df) < 100:
                await msg.edit_text(
                    f"❌ **Insufficient Data**\n\n"
                    f"Need 100+ candles, got `{len(df) if df is not None else 0}`\n\n"
                    f"💡 Pastikan pair sudah di-watch.",
                    parse_mode='Markdown'
                )
                return

            # Filter by date
            if 'timestamp' in df.columns:
                df = df[df['timestamp'] >= start_date]
            
            if len(df) < 100:
                await msg.edit_text(
                    f"❌ **Insufficient Data**\n\n"
                    f"After filter: `{len(df)}` candles\n\n"
                    f"Coba period lebih pendek.",
                    parse_mode='Markdown'
                )
                return

            await msg.edit_text(
                f"📊 **PRO Backtest (ML V3)...**\n\n"
                f"Pair: `{pair.upper()}`\n"
                f"Period: `{days}` days\n"
                f"Candles: `{len(df)}`\n\n"
                f"⏳ Running simulation...",
                parse_mode='Markdown'
            )

            # Run backtest using V3
            import asyncio
            loop = asyncio.get_event_loop()
            
            result = await loop.run_in_executor(
                None,
                lambda: self.ml_model_v3.backtest(
                    df,
                    initial_balance=10000000,
                    position_pct=0.25
                )
            )

            if not result or result.total_trades == 0:
                await msg.edit_text(
                    f"ℹ️ **No Trades Generated**\n\n"
                    f"Data: `{len(df)}` candles\n"
                    f"Strategy tidak menghasilkan trade pada periode ini.\n\n"
                    f"💡 Coba dengan period berbeda atau pair lain.",
                    parse_mode='Markdown'
                )
                return

            # Format PRO results
            text = f"""
📊 **PRO Backtest Results (ML V3)** 

💰 **Balance:**
• Initial: `{result.initial_balance:,.0f}` IDR
• Final: `{result.final_balance:,.0f}` IDR
• Profit: `{result.total_profit:,.0f}` IDR ({result.total_profit_pct:+.2%})

📈 **Trading:**
• Total Trades: `{result.total_trades}`
• Winning: `{result.winning_trades}`
• Losing: `{result.losing_trades}`
• Win Rate: `{result.win_rate:.2%}`

📉 **Risk Metrics:**
• Max Drawdown: `{result.max_drawdown:.2%}`
• Profit Factor: `{result.profit_factor:.2f}`
• Sharpe Ratio: `{result.sharpe_ratio:.2f}`

💵 **Costs:**
• Total Fees: `{result.total_fees:,.0f}` IDR
• Avg Profit: `{result.avg_profit:,.0f}` IDR
• Avg Loss: `{result.avg_loss:,.0f}` IDR

🏆 **Best/Worst:**
• Largest Win: `{result.largest_win:,.0f}` IDR
• Largest Loss: `{result.largest_loss:,.0f}` IDR
"""

            await msg.edit_text(text, parse_mode='Markdown')
            logger.info(f"✅ PRO Backtest completed for {pair} ({days} days): {result.total_profit_pct:+.2%}")

        except Exception as e:
            logger.error(f"❌ PRO Backtest error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await msg.edit_text(
                f"❌ **PRO Backtest Error**\n\n"
                f"```\n{str(e)[:200]}\n```",
                parse_mode='Markdown'
            )

    async def dryrun_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Dry-Run Simulation
        ==============
        Simulates trading WITHOUT executing real orders
        Uses ML V3 with backtesting engine
        
        Usage: /dryrun <PAIR> <INITIAL_BALANCE>
        Example: /dryrun btcidr 10000000
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        if not self.ml_model_v3:
            await update.message.reply_text(
                "❌ **ML Model V3 Not Available**\n\n"
                "Model V3 perlu diinisialisasi dulu.",
                parse_mode='Markdown'
            )
            return

        # Parse arguments
        pair = 'btcidr'  # Default
        initial_balance = 10000000  # Default 10M IDR
        
        if context.args:
            pair = context.args[0].lower().replace('/', '')
            if not pair.endswith('idr'):
                pair += 'idr'
            
            if len(context.args) > 1:
                try:
                    initial_balance = float(context.args[1])
                except ValueError:
                    await update.message.reply_text("❌ Balance harus angka!", parse_mode='Markdown')
                    return

        # Send initial message
        msg = await update.message.reply_text(
            f"🎯 **DRY RUN Simulation**\n\n"
            f"Pair: `{pair.upper()}`\n"
            f"Initial Balance: `{initial_balance:,.0f}` IDR\n\n"
            f"⏳ Starting simulation...\n"
            f"⚠️ No real trades will be executed!",
            parse_mode='Markdown'
        )

        try:
            # Get historical data
            df = self.db.get_price_history(pair, limit=5000)
            
            if df is None or len(df) < 100:
                await msg.edit_text(
                    f"❌ **Insufficient Data**\n\n"
                    f"Need 100+ candles, got `{len(df) if df is not None else 0}`",
                    parse_mode='Markdown'
                )
                return

            # Run dry-run simulation
            import asyncio
            loop = asyncio.get_event_loop()
            
            result = await loop.run_in_executor(
                None,
                lambda: self.ml_model_v3.simulate_dry_run(df, initial_balance)
            )

            if not result:
                await msg.edit_text(
                    f"❌ **Simulation Failed**\n\n"
                    f"Tidak ada hasil.",
                    parse_mode='Markdown'
                )
                return

            # Format results
            text = f"""
🎯 **DRY RUN Results**

💰 **Balance:**
• Initial: `{result.initial_balance:,.0f}` IDR
• Final: `{result.final_balance:,.0f}` IDR
• Profit: `{result.total_profit:,.0f}` IDR ({result.total_profit_pct:+.2%})

📈 **Trades:**
• Total: `{result.total_trades}`
• Wins: `{result.winning_trades}`
• Losses: `{result.losing_trades}`
• Win Rate: `{result.win_rate:.2%}`

📉 **Risk:**
• Max DD: `{result.max_drawdown:.2%}`
• Profit Factor: `{result.profit_factor:.2f}`

💵 **Costs:**
• Fees: `{result.total_fees:,.0f}` IDR

⚠️ **NOTE:** This is SIMULATION only!
No real orders were placed.
"""
            await msg.edit_text(text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Dryrun error: {e}")
            await msg.edit_text(
                f"❌ **Dryrun Error**\n\n{str(e)[:200]}",
                parse_mode='Markdown'
            )

    async def regime_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Market Regime Detection
        ===================
        Detect current market regime using ML V3
        
        Usage: /regime <PAIR>
        Example: /regime btcidr
        """
        if not self.ml_model_v3:
            await update.message.reply_text(
                "❌ **ML Model V3 Not Available**",
                parse_mode='Markdown'
            )
            return

        # Parse pair
        pair = 'btcidr'
        if context.args:
            pair = context.args[0].lower().replace('/', '')
            if not pair.endswith('idr'):
                pair += 'idr'

        try:
            # Get data
            df = self.db.get_price_history(pair, limit=200)
            
            if df is None or len(df) < 50:
                await update.message.reply_text(
                    f"❌ **Insufficient Data**\n\nNeed 50+ candles",
                    parse_mode='Markdown'
                )
                return

            # Get regime
            regime = self.ml_model_v3.get_market_regime(df)

            text = f"""
📊 **Market Regime: {pair.upper()}**

📈 **Volatility:** `{regime['volatility']}`
📉 **Trend:** `{regime['trend']}`
📊 **Volume:** `{regime['volume']}`

💰 **Recommended Position:** `{regime['recommended_position']*100:.0f}%`

💡 Bot will adjust position sizing based on regime.
"""
            await update.message.reply_text(text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Regime error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}", parse_mode='Markdown')

    async def kelly_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Kelly Criterion Position Sizing
        ==============================
        Calculate optimal position size using Kelly Criterion
        
        Usage: /kelly <WIN_RATE> <AVG_WIN> <AVG_LOSS>
        Example: /kelly 0.6 200000 100000
        """
        # Parse - get from recent trades if no args
        user_id = update.effective_user.id
        
        if not context.args:
            # Get from trade history
            trades = self.db.get_trade_history(user_id, limit=100)
            if not trades or len(trades) < 10:
                await update.message.reply_text(
                    "📈 **Kelly Criterion**\n\n"
                    "Usage: `/kelly <WIN_RATE> <AVG_WIN> <AVG_LOSS>`\n\n"
                    "Example:\n"
                    "`/kelly 0.6 200000 100000`\n"
                    "(60% win rate, avg win 200K, avg loss 100K)\n\n"
                    "Or provide trade count 10+ for auto-calculate",
                    parse_mode='Markdown'
                )
                return
            
            # Calculate from trades
            winning = [t for t in trades if t.get('profit_loss', 0) > 0]
            losing = [t for t in trades if t.get('profit_loss', 0) < 0]
            
            win_rate = len(winning) / len(trades) if trades else 0
            avg_win = sum(t.get('profit_loss', 0) for t in winning) / len(winning) if winning else 0
            avg_loss = abs(sum(t.get('profit_loss', 0) for t in losing) / len(losing)) if losing else 0
        else:
            try:
                win_rate = float(context.args[0])
                avg_win = float(context.args[1]) if len(context.args) > 1 else 100000
                avg_loss = float(context.args[2]) if len(context.args) > 2 else avg_win / 2
            except ValueError:
                await update.message.reply_text("❌ Invalid numbers!", parse_mode='Markdown')
                return
        
        if win_rate <= 0 or avg_loss <= 0:
            await update.message.reply_text("❌ Win rate and avg loss must be > 0", parse_mode='Markdown')
            return
        
        # Kelly Formula: K% = W - (1-W)/R
        win_loss_ratio = avg_win / avg_loss
        kelly_pct = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Fractional Kelly (50% for safety)
        fractional_kelly = kelly_pct * 0.5
        
        # Clamp to safe limits
        max_position = 0.30  # 30% max
        optimal = max(0.01, min(fractional_kelly, max_position))
        
        # Calculate expected value
        expected_ev = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        text = f"""
📈 **Kelly Criterion Position Sizing**

📊 **Input:**
• Win Rate: `{win_rate:.1%}`
• Avg Win: `{avg_win:,.0f}` IDR
• Avg Loss: `{avg_loss:,.0f}` IDR
• W/L Ratio: `{win_loss_ratio:.2f}`

💰 **Kelly Calculation:**
• Full Kelly: `{kelly_pct:.2%}`
• Fractional (50%): `{fractional_kelly:.2%}`
• **Recommended:** `{optimal:.2%}`

⚠️ **Note:** Using 50% Kelly for safety.
Max recommended: 30%

📊 **Expected Value:** `{expected_ev:,.0f}` IDR per trade
"""
        if expected_ev > 0:
            text += "\n✅ Positive expected value!"
        else:
            text += "\n❌ Negative expected value - not recommended!"
        
        await update.message.reply_text(text, parse_mode='Markdown')

    async def compare_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Multi-Pair Backtest Comparison
        ==============================
        Compare backtest results across multiple pairs
        
        Usage: /compare <DAYS>
        Example: /compare 30
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        days = 30
        if context.args:
            try:
                days = int(context.args[0])
            except:
                pass

        msg = await update.message.reply_text(
            f"📊 **Comparing pairs...** ({days} days)\n\n⏳ Loading data...",
            parse_mode='Markdown'
        )

        try:
            if not self.ml_model_v3:
                await msg.edit_text("❌ ML V3 not available", parse_mode='Markdown')
                return

# Get pairs from database
            pairs_to_check = set()
            try:
                all_pairs = self.db.get_all_pairs()
                if all_pairs:
                    pairs_to_check.update(all_pairs)
            except:
                pass
            
# Fallback: watchlist
            if not pairs_to_check:
                try:
                    watchlists = self.db.get_all_watchlists()
                    for pairs in watchlists.values():
                        pairs_to_check.update(pairs)
                except:
                    pass
            
            if not pairs_to_check:
                await msg.edit_text("❌ No pairs found in database", parse_mode='Markdown')
                return

            results = []
            for pair in list(pairs_to_check)[:10]:  # Max 10 pairs
                if not pair.endswith('idr'):
                    continue
                df = self.db.get_price_history(pair, limit=2000)
                if df is None or len(df) < 100:
                    continue
                
                result = self.ml_model_v3.backtest(df, initial_balance=10000000, position_pct=0.25)
                if result.total_trades > 0:
                    results.append({
                        'pair': pair,
                        'profit_pct': result.total_profit_pct,
                        'win_rate': result.win_rate,
                        'trades': result.total_trades,
                        'pf': result.profit_factor
                    })

            if not results:
                await msg.edit_text("❌ No backtest results", parse_mode='Markdown')
                return

            # Sort by profit
            results.sort(key=lambda x: x['profit_pct'], reverse=True)

            text = f"📊 **Pair Comparison** ({days} days)\n\n"
            text += "```\n"
            for r in results:
                emoji = "🟢" if r['profit_pct'] > 0 else "🔴"
                text += f"{emoji} {r['pair']:<12} {r['profit_pct']:>+7.1%}  WR:{r['win_rate']:.0%}  Pf:{r['pf']:.2f}\n"
            text += "```"

            top = results[0]
            text += f"\n🏆 **Top Performer:** {top['pair']} ({top['profit_pct']:+.1%})"

            await msg.edit_text(text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Compare error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)[:100]}", parse_mode='Markdown')

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages - detect pair shortcuts and trade confirmations"""
        user_id = update.effective_user.id
        text = update.message.text.strip()

        # Check for trade confirmation (YES/NO)
        pending_key = f"pending_{user_id}"
        if pending_key in context.user_data:
            if text.upper() == 'YES':
                # Send immediate confirmation message
                confirm_msg = await update.message.reply_text("⏳ **Executing trade...**\nPlease wait, bot is processing your order.", parse_mode='Markdown')

                # Run trade execution in background thread
                order_data = context.user_data[pending_key]
                del context.user_data[pending_key]  # Clear immediately

                # Store message info for background thread
                chat_id = update.effective_chat.id
                message_id = confirm_msg.message_id
                bot_token = self.app.bot.token

                import threading
                def _execute_bg():
                    try:
                        # Create NEW event loop for this thread
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                        # Run the async trade function
                        result_text = loop.run_until_complete(
                            self.execute_manual_trade(user_id, order_data)
                        )
                        loop.close()

                        # Send result via direct HTTP API (no event loop needed)
                        import requests
                        result_text_escaped = result_text.replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')[:4000]
                        url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                        requests.post(url, json={
                            'chat_id': chat_id,
                            'message_id': message_id,
                            'text': result_text_escaped,
                            'parse_mode': 'Markdown'
                        }, timeout=10)

                    except Exception as e:
                        logger.error(f"Trade execution error: {e}")
                        import traceback
                        logger.error(traceback.format_exc())

                        # Send error via direct HTTP API
                        import requests
                        error_msg = f"❌ **Trade Failed**\n\nError: `{str(e)[:200]}`"
                        url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                        requests.post(url, json={
                            'chat_id': chat_id,
                            'message_id': message_id,
                            'text': error_msg.replace('_', '\\_').replace('*', '\\*').replace('`', '\\`'),
                            'parse_mode': 'Markdown'
                        }, timeout=10)

                thread = threading.Thread(target=_execute_bg, daemon=True, name="Trade-Execute")
                thread.start()
                logger.info(f"🔄 Trade execution started in background thread for {user_id}")

            elif text.upper() == 'NO':
                await update.message.reply_text("❌ Trade cancelled.")
                del context.user_data[pending_key]
            return
        
        # Check if text looks like a trading pair (lowercase format)
        text_clean = text.strip().replace('/', '').lower()
        if text_clean.endswith('idr') and len(text_clean) >= 4:
            pair = text_clean
            await update.message.reply_text(f"🔍 Analyzing {pair.upper()}...")
            context.args = [pair]
            await self.get_signal(update, context)

    async def handle_unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unknown commands - show help menu"""
        command_text = update.message.text.strip()
        
        text = """
📚 <b>DAFTAR SEMUA COMMAND</b>

━━━━━━━━━━━━━━━
🔹 <b>WATCHLIST & MONITORING</b>
━━━━━━━━━━━━━━━
• <code>/start</code> - Mulai bot
• <code>/help</code> - Panduan lengkap
• <code>/menu</code> - Menu cepat
• <code>/cmd</code> - Panduan command

• <code>/watch &lt;PAIR&gt;</code> - Tambah pair ke watchlist
• <code>/unwatch &lt;PAIR&gt;</code> - Hapus pair dari watchlist
• <code>/list</code> - Lihat watchlist
• <code>/price &lt;PAIR&gt;</code> - Cek harga cepat

━━━━━━━━━━━━━━━
🔹 <b>SIGNAL & ANALISA</b>
━━━━━━━━━━━━━━━
• <code>/signal &lt;PAIR&gt;</code> - Signal lengkap
• <code>/signal_buy &lt;PAIR&gt;</code> - BUY only
• <code>/signal_sell &lt;PAIR&gt;</code> - SELL only
• <code>/signal_hold &lt;PAIR&gt;</code> - HOLD only
• <code>/signal_buysell &lt;PAIR&gt;</code> - BUY/SELL only (bukan HOLD)

• <code>/signals</code> - Semua signal di watchlist
• <code>/scan</code> - Scan market peluang
• <code>/topvolume</code> - Top volume pairs
• <code>/notifications</code> - Riwayat notifikasi

━━━━━━━━━━━━━━━
🔹 <b>SMART HUNTER</b>
━━━━━━━━━━━━━━━
• <code>/smarthunter on/off</code> - Start/Stop Smart Hunter
• <code>/smarthunter_status</code> - Status Smart Hunter
• <code>/ultrahunter on/off</code> - Start/Stop Ultra Hunter

━━━━━━━━━━━━━━━
🔹 <b>PORTFOLIO & TRADING</b>
━━━━━━━━━━━━━━━
• <code>/balance</code> - Cek saldo & posisi
• <code>/trades</code> - Riwayat trade
• <code>/performance</code> - Win rate & P&L
• <code>/position &lt;PAIR&gt;</code> - Analisa posisi mendalam
• <code>/sync</code> - Sync trade dari Indodax

• <code>/trade &lt;PAIR&gt; &lt;TYPE&gt; &lt;AMOUNT&gt;</code> - Manual trade
• <code>/trade_auto_sell &lt;PAIR&gt; &lt;PRICE&gt;</code> - Set auto sell

━━━━━━━━━━━━━━━
🔹 <b>AUTO TRADING (Admin)</b>
━━━━━━━━━━━━━━━
• <code>/autotrade</code> - Toggle auto-trading
• <code>/autotrade dryrun</code> - Mode simulasi
• <code>/autotrade real</code> - Mode trading nyata
• <code>/autotrade_status</code> - Status auto-trading

• <code>/retrain</code> - Retrain ML model

━━━━━━━━━━━━━━━
🔹 <b>SCALPER MODULE</b>
━━━━━━━━━━━━━━━
• <code>/s_menu</code> - Menu scalper
• <code>/s_posisi</code> - Posisi scalper
• <code>/s_analisa &lt;PAIR&gt;</code> - Analisa pair
• <code>/s_buy &lt;PAIR&gt;</code> - Buy via scalper
• <code>/s_sell &lt;PAIR&gt;</code> - Sell via scalper

━━━━━━━━━━━━━━━
🔹 <b>STATUS & ADMIN</b>
━━━━━━━━━━━━━━━
• <code>/status</code> - Status bot
• <code>/scheduler_status</code> - Status scheduler
• <code>/hunter_status</code> - Hunter status

• <code>/add_autotrade &lt;PAIR&gt;</code> - Tambah auto-trade pair
• <code>/remove_autotrade &lt;PAIR&gt;</code> - Hapus auto-trade pair
• <code>/list_autotrade</code> - List auto-trade pairs

• <code>/set_sr &lt;PAIR&gt; &lt;TYPE&gt; &lt;PRICE&gt;</code> - Set Support/Resistance
• <code>/view_sr &lt;PAIR&gt;</code> - View S/R levels

━━━━━━━━━━━━━━━
💡 <b>CARA PAKAI:</b>
Ketik command di atas sesuai kebutuhan.
Contoh: <code>/signal BTCIDR</code>
"""
        await self._send_message(update, context, text, parse_mode='HTML')
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = update.effective_user.id

        # =====================================================================
        # SCALPER MODULE callbacks (prefix s_)
        # =====================================================================
        if self.scalper and data.startswith('s_'):
            await self.scalper.menu_callback(update, context)
            return

        # Watch pair callbacks
        if data.startswith('watch_'):
            pair = data.replace('watch_', '')
            context.args = [pair]
            await self.watch(update, context)

        # Signal callbacks
        elif data.startswith('signal_'):
            pair = data.replace('signal_', '')
            if pair in ('quick', 'default'):
                await query.edit_message_text("🤖 Signal untuk pair apa?\nKetik nama pair, contoh: `pippinidr`", parse_mode='Markdown')
            else:
                context.args = [pair]
                await self.get_signal(update, context)

        # Price callbacks
        elif data.startswith('price_'):
            pair = data.replace('price_', '')
            if pair in ('quick', 'default'):
                await query.edit_message_text("🔍 Harga pair apa?\nKetik nama pair, contoh: `pippinidr`")
            else:
                context.args = [pair]
                await self.price(update, context)
        
        # Admin callbacks
        elif data == 'admin_panel':
            if user_id in Config.ADMIN_IDS:
                await query.edit_message_text(
                    "⚙️ **Admin Panel**\n\n"
                    "• /status - System status\n"
                    "• /start_trading - Enable auto-trading\n"
                    "• /stop_trading - Disable auto-trading\n"
                    "• /retrain - Retrain ML model",
                    parse_mode='Markdown'
                )
        
        elif data == 'admin_restart':
            if user_id in Config.ADMIN_IDS:
                await query.edit_message_text(
                    "🔄 **Restarting Bot...**\n\n"
                    "⏳ Bot akan restart dalam 3 detik...\n"
                    "✅ Semua thread akan di-stop dengan aman\n"
                    "🔌 Polling akan di-start ulang\n\n"
                    "💡 Jika restart gagal, silakan restart manual:\n"
                    "`python bot.py`",
                    parse_mode='Markdown'
                )
                
                logger.info("🔄 Bot restart initiated by admin")
                
                # Graceful shutdown sequence
                try:
                    # Set shutdown event
                    self.shutdown_event.set()
                    
                    # Stop price poller
                    await self.price_poller.stop_polling()
                    logger.info("🛑 Price poller stopped")
                    
                    # Stop background cache refresh
                    from cache.price_cache import price_cache
                    price_cache.stop_background_refresh()
                    logger.info("🛑 Cache refresh stopped")
                    
                    # Notify user
                    await query.message.reply_text(
                        "✅ **Bot components stopped successfully**\n\n"
                        "🔄 **Bot akan restart otomatis...**\n\n"
                        "⚠️ **Jika tidak restart dalam 10 detik:**\n"
                        "1. Stop bot manual (Ctrl+C)\n"
                        "2. Jalankan: `python bot.py`\n"
                        "3. Bot akan start dengan fresh state",
                        parse_mode='Markdown'
                    )
                    
                    # Graceful exit - call shutdown first for cleanup
                    logger.info("👋 Bot exiting for restart...")
                    import sys
                    self._shutdown(timeout=5)
                    sys.exit(0)
                    
                except Exception as e:
                    logger.error(f"❌ Error during restart: {e}")
                    await query.message.reply_text(
                        f"❌ **Restart Failed**\n\n"
                        f"Error: `{str(e)}`\n\n"
                        f"Silakan restart manual:\n"
                        f"`python bot.py`",
                        parse_mode='Markdown'
                    )
        
        elif data == 'admin_logs':
            if user_id in Config.ADMIN_IDS:
                # Send last 20 log lines
                try:
                    with open(Config.LOG_FILE, 'r') as f:
                        logs = f.readlines()[-30:]  # Increased to 30 lines
                    log_text = "📋 **Recent Logs (Last 30):**\n```\n" + ''.join(logs) + "\n```"
                    await query.message.reply_text(log_text, parse_mode='Markdown')
                except FileNotFoundError:
                    await query.message.reply_text("❌ Log file tidak ditemukan. Bot belum membuat log.")
                except Exception as e:
                    await query.message.reply_text(f"❌ Could not read logs: {str(e)}")

        elif data == 'admin_backtest':
            if user_id in Config.ADMIN_IDS:
                await query.edit_message_text(
                    "📈 **Backtest Menu**\n\n"
                    "Gunakan command berikut:\n"
                    "• `/backtest <PAIR> <DAYS>` - Run backtest\n"
                    "• `/backtest btcidr 30` - Backtest 30 hari terakhir\n"
                    "• `/backtest ethidr 7` - Backtest 7 hari terakhir\n\n"
                    "Contoh:\n"
                    "`/backtest btcidr 30`\n\n"
                    "Backtest akan mensimulasikan trading dengan strategi bot dan menampilkan hasil.",
                    parse_mode='Markdown'
                )
        
        elif data == 'admin_retrain':
            if user_id in Config.ADMIN_IDS:
                context.args = []
                await self.retrain_ml(update, context)
        
        elif data == 'help':
            await self.help(update, context)

        # Auto-trade pair addition from /start menu
        elif data == 'autotrade_add_pair':
            if user_id in Config.ADMIN_IDS:
                await query.edit_message_text(
                    "🤖 **Tambah Pair untuk AUTO-TRADE**\n\n"
                    "Pair auto-trade **terpisah** dari watchlist/scalper.\n\n"
                    "📋 **Cara tambah pair:**\n"
                    "• `/add_autotrade btcidr` - Tambah 1 pair\n"
                    "• `/add_autotrade btcidr,ethidr,solidr` - Tambah banyak\n\n"
                    "📋 **Lihat daftar:**\n"
                    "• `/list_autotrade` - Lihat pair auto-trade Anda\n\n"
                    "📋 **Hapus pair:**\n"
                    "• `/remove_autotrade btcidr` - Hapus dari auto-trade\n\n"
                    "⚠️ **Penting:**\n"
                    "• Pair auto-trade ≠ pair watchlist\n"
                    "• Scalping TIDAK terpengaruh auto-trade\n"
                    "• Auto-trade hanya trade pair di daftar ini",
                    parse_mode='Markdown'
                )

        # Backtest plot callback
        elif data.startswith('backtest_plot_'):
            if user_id in Config.ADMIN_IDS:
                try:
                    # Parse pair and days from callback data
                    parts = data.replace('backtest_plot_', '').split('_')
                    days = parts[-1]
                    pair = '_'.join(parts[:-1])
                    
                    await query.edit_message_text(
                        "📊 **Plotting Backtest Results...**\n\n"
                        "Fitur plotting akan segera ditambahkan.\n"
                        "Saat ini hanya menampilkan hasil teks.\n\n"
                        f"Pair: `{pair.upper()}`\n"
                        f"Period: `{days}` days",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Plot error: {e}")
        
        # Ultra Hunter callbacks
        elif data == 'ultra_start_confirm':
            if user_id in Config.ADMIN_IDS:
                # Start ultra hunter
                try:
                    import sys
                    if sys.platform == 'win32':
                        subprocess.Popen(
                            ['python', '-m', 'trading.ultra_hunter'],
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                            stdout=open('logs/ultra_hunter_stdout.log', 'w'),
                            stderr=open('logs/ultra_hunter_stderr.log', 'w')
                        )
                    else:
                        subprocess.Popen(
                            ['python', '-m', 'trading.ultra_hunter'],
                            stdout=open('logs/ultra_hunter_stdout.log', 'w'),
                            stderr=open('logs/ultra_hunter_stderr.log', 'w'),
                            start_new_session=True
                        )
                    
                    logger.info("✅ Ultra Hunter started (confirmed)")
                    
                    await query.edit_message_text(
                        "✅ **ULTRA HUNTER STARTED**\n\n"
                        "⚠️ **WARNING:** Bot auto-trade is also ON!\n\n"
                        "This may cause:\n"
                        "• Double positions\n"
                        "• Conflicting trades\n\n"
                        "💡 Use `/stop_trading` to disable bot auto-trade",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Failed to start: {e}")
        
        elif data == 'ultra_cancel':
            if user_id in Config.ADMIN_IDS:
                context.user_data.pop('ultra_start_pending', None)
                await query.edit_message_text(
                    "❌ **Ultra Hunter start cancelled**\n\n"
                    "Use `/stop_trading` first if you want to run Ultra Hunter safely",
                    parse_mode='Markdown'
                )
    
    # =============================================================================
    # CORE TRADING LOGIC
    # =============================================================================
    
    def _subscribe_pair(self, pair):
        """Subscribe to WebSocket channel for a pair - DISABLED, using REST polling only"""
        # WebSocket subscription DISABLED - using REST API polling instead
        logger.info(f"📡 Watch request for {pair} (WebSocket disabled, will poll via REST API)")
        return
    
    async def _load_historical_data(self, pair, limit=200):
        """
        Load historical price data for ML analysis
        OPTIMIZED: Non-blocking async API calls
        """
        logger.info(f"📚 Loading historical data for {pair} (limit: {limit})")

        # Try from database first (async operation)
        df = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.db.get_price_history(pair, limit=limit)
        )

        logger.info(f"📊 DB query result for {pair}: {len(df)} rows, empty={df.empty}")

        if not df.empty:
            # ACCEPT whatever data is in database (even if < 60 candles)
            self.historical_data[pair] = df
            candle_count = len(df)

            if candle_count >= 60:
                logger.info(f"✅ Loaded {candle_count} candles for {pair} from database")
            else:
                logger.warning(f"⚠️ Only {candle_count} candles from DB (need 60+ for full analysis)")
                logger.info("💡 Bot will accumulate more data via WebSocket/polling")

            # Still try CoinGecko if data is insufficient (ASYNC)
            if candle_count < 60:
                logger.info(f"🔄 Trying CoinGecko to supplement data for {pair}...")
                try:
                    # OPTIMIZED: Async API call (tidak blocking)
                    ticker_resp = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: requests.get(
                            f"https://indodax.com/api/ticker/{pair.lower()}",
                            timeout=10,
                            headers={'User-Agent': 'Mozilla/5.0'}
                        )
                    )
                    
                    current_price = None
                    if ticker_resp.status_code == 200:
                        ticker_data = ticker_resp.json()
                        if 'ticker' in ticker_data:
                            current_price = float(ticker_data['ticker'].get('last', 0))

                    if current_price:
                        await self._fetch_from_coingecko(pair, current_price, limit)
                except Exception as e:
                    logger.debug(f"CoinGecko supplement failed for {pair}: {e}")
        else:
            # Database empty - try CoinGecko first (NO Indodax API, it returns 403)
            logger.warning(f"⚠️ No data in database for {pair}, trying CoinGecko...")

            current_price = None  # Declare BEFORE try block

            try:
                # OPTIMIZED: Async API call (tidak blocking)
                ticker_resp = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: requests.get(
                        f"https://indodax.com/api/ticker/{pair.lower()}",
                        timeout=10,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                )
                
                if ticker_resp.status_code == 200:
                    ticker_data = ticker_resp.json()
                    if 'ticker' in ticker_data:
                        current_price = float(ticker_data['ticker'].get('last', 0))

                if current_price:
                    success = await self._fetch_from_coingecko(pair, current_price, limit)
                    if success:
                        return  # CoinGecko succeeded
            except Exception as e:
                logger.debug(f"CoinGecko failed for {pair}: {e}")

            # All external sources failed - create minimal dataset for polling
            logger.warning(f"⚠️ No historical data available for {pair}")
            logger.info("💡 Creating minimal dataset - polling will accumulate real data")

            from datetime import datetime, timedelta
            fallback_price = current_price if current_price else 1000
            now = datetime.now()
            initial_data = {
                'timestamp': [now - timedelta(minutes=i) for i in range(limit-1, -1, -1)],
                'open': [fallback_price] * limit,
                'high': [fallback_price * 1.001] * limit,
                'low': [fallback_price * 0.999] * limit,
                'close': [fallback_price] * limit,
                'volume': [1000.0] * limit
            }

            df = pd.DataFrame(initial_data)
            self.historical_data[pair] = df

    async def _fetch_from_indodax_api(self, pair, limit=200):
        """Fetch historical data from Indodax API - Get recent trades"""
        logger.info(f"🌐 Fetching historical trades for {pair} from Indodax API...")

        try:
            # Indodax DOES NOT have public trade history endpoint
            # We MUST use WebSocket polling data instead

            # Strategy: Poll price every 1 second for 60 seconds to build initial dataset
            logger.info(f"⏳ Collecting {limit} candles for {pair} via rapid polling...")

            current_price = None
            
            # Get current price from ticker
            try:
                ticker_resp = requests.get(
                    f"https://indodax.com/api/ticker/{pair.lower()}",
                    timeout=10,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                if ticker_resp.status_code == 200:
                    ticker_data = ticker_resp.json()
                    if 'ticker' in ticker_data:
                        current_price = float(ticker_data['ticker'].get('last', 0))
                        logger.info(f"💰 Current price for {pair}: {current_price:,.0f}")
            except Exception as e:
                logger.error(f"Failed to get current price: {e}")
            
            if not current_price:
                logger.warning(f"⚠️ Cannot get current price for {pair}")
                return False
            
            # Generate synthetic candles from current price + recent volatility
            # This is NOT ideal but necessary without historical data
            # In production, you should use a data provider with historical data
            
            # Option 1: Use CoinGecko for historical data (free, no API key)
            success = await self._fetch_from_coingecko(pair, current_price, limit)
            
            if success:
                return True
            
            # Option 2: Generate minimal dataset from current price
            logger.warning(f"⚠️ No historical data source available for {pair}")
            logger.info("💡 Bot will collect data via WebSocket polling going forward")
            
            # Create minimal DataFrame with current price only
            # WebSocket will populate this over time
            now = datetime.now()
            initial_data = {
                'timestamp': [now - timedelta(minutes=i) for i in range(limit-1, -1, -1)],
                'open': [current_price] * limit,
                'high': [current_price * 1.001] * limit,
                'low': [current_price * 0.999] * limit,
                'close': [current_price] * limit,
                'volume': [1000.0] * limit
            }
            
            df = pd.DataFrame(initial_data)
            self.historical_data[pair] = df
            
            logger.info(f"⚠️ Created minimal dataset for {pair} ({limit} candles)")
            logger.info("💡 Real data will accumulate via WebSocket polling")
            
            return False  # Return False to indicate this is not real historical data
            
        except Exception as e:
            logger.error(f"❌ Error fetching from Indodax API for {pair}: {e}")
            return False

    async def _fetch_from_coingecko(self, pair, current_price, limit):
        """Fetch historical data from CoinGecko API (free, no API key)"""
        try:
            # Map Indodax pair to CoinGecko coin ID
            coin_map = {
                'btcidr': 'bitcoin',
                'ethidr': 'ethereum',
                'dogeidr': 'dogecoin',
                'xrpidr': 'ripple',
                'adaidr': 'cardano',
                'solidr': 'solana',
                'bnbidr': 'binancecoin',
            }
            
            coin_id = coin_map.get(pair.lower())
            
            if not coin_id:
                logger.debug(f"CoinGecko: No mapping for {pair}")
                return False
            
            # Get OHLCV data from CoinGecko
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=idr&days=7"
            
            logger.info(f"🌐 Fetching from CoinGecko: {coin_id}")
            
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ CoinGecko API error: {response.status_code}")
                return False
            
            ohlcv_data = response.json()
            
            if not ohlcv_data or len(ohlcv_data) == 0:
                logger.warning(f"⚠️ No OHLCV data from CoinGecko for {coin_id}")
                return False
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close'])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['volume'] = 1000.0  # CoinGecko doesn't provide volume in OHLC endpoint
            
            # Limit to requested candles
            df = df.tail(limit)
            
            if len(df) > 10:
                # Save to database
                saved = self.db.save_price_history(pair, df)
                
                # Load to memory
                self.historical_data[pair] = df
                
                logger.info(f"✅ Fetched {len(df)} candles for {pair} from CoinGecko")
                logger.info(f"💾 Saved {saved} candles to database")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ CoinGecko fetch error for {pair}: {e}")
            return False

    async def _generate_signal_for_pair(self, pair):
        """Generate comprehensive trading signal"""
        # Ensure we have data
        if pair not in self.historical_data:
            await self._load_historical_data(pair)

        if pair not in self.historical_data or self.historical_data[pair].empty:
            logger.warning(f"⚠️ No data available for {pair} yet (waiting for WebSocket)")
            return None

        df = self.historical_data[pair].copy()

        # Check if we have enough data
        if len(df) < 60:  # Need at least 60 candles for ML
            logger.warning(f"⚠️ Not enough data for {pair}: {len(df)} candles (need 60+)")
            return None

        # ALWAYS fetch fresh price from API (most reliable)
        real_time_price = None
        
        # Try Indodax API first (always fresh)
        try:
            from api.indodax_api import IndodaxAPI
            indodax = IndodaxAPI()
            ticker = indodax.get_ticker(pair)
            if ticker:
                real_time_price = ticker['last']
                logger.info(f"🌐 API price for {pair}: {real_time_price}")
        except Exception as e:
            logger.error(f"❌ Failed to get API price for {pair}: {e}")

        # Fallback to WebSocket price if API failed
        if real_time_price is None and pair in self.price_data and self.price_data[pair]:
            ws_price = self.price_data[pair].get('last')
            ws_timestamp = self.price_data[pair].get('timestamp')
            
            # Check if WS price is fresh (within last 60 seconds)
            if ws_timestamp and (datetime.now() - ws_timestamp).total_seconds() < 60:
                real_time_price = ws_price
                logger.info(f"📡 WebSocket price for {pair}: {ws_price} (fresh)")
            else:
                logger.warning(f"⚠️ WebSocket price stale for {pair}")

        # Final fallback: historical data
        if real_time_price is None:
            real_time_price = df['close'].iloc[-1]
            logger.warning(f"⚠️ Using historical price for {pair}: {real_time_price}")

        logger.info(f"✅ Final price for {pair}: {real_time_price}")

        # Technical Analysis
        ta = TechnicalAnalysis(df)
        ta_signals = ta.get_signals()

        # ML Prediction - handle V1 (2 values) vs V2 (3 values)
        try:
            predict_result = self.ml_model.predict(df)

            # Handle different model versions
            # Both V1 and V2 now return (prediction, confidence, signal_class)
            if len(predict_result) == 3:
                ml_prediction, ml_confidence, ml_signal_class = predict_result
            elif len(predict_result) == 2:
                # Fallback for older model formats
                ml_prediction, ml_confidence = predict_result
                ml_signal_class = 'BUY' if ml_prediction else 'SELL'
            else:
                logger.warning(f"⚠️ Unexpected predict result format: {len(predict_result)} values")
                ml_prediction, ml_confidence, ml_signal_class = None, 0.5, 'HOLD'

            if ml_signal_class:
                logger.info(f"✅ ML prediction successful for {pair}: {ml_confidence:.2%} ({ml_signal_class})")
            else:
                logger.info(f"✅ ML prediction successful for {pair}: {ml_confidence:.2%}")

            # FIX: Convert ml_prediction to boolean for trading_engine
            # Both V1 and V2 now return boolean for binary prediction
            # Trading engine expects: True=BUY, False=SELL, None=not available
            if isinstance(ml_prediction, bool):
                ml_prediction_bool = ml_prediction
            elif isinstance(ml_prediction, int) and self.ml_version == 'V2':
                # Multi-class fallback (if somehow enabled)
                ml_prediction_bool = ml_prediction >= 3  # 3=BUY, 4=STRONG_BUY → True
            else:
                ml_prediction_bool = ml_prediction  # Could be None

            if ml_prediction is None:
                logger.info(f"⏳ ML model not trained yet for {pair} — using TA-only signal")
        except Exception as e:
            logger.warning(f"⚠️ ML prediction failed for {pair}: {e}")
            import traceback
            logger.debug(f"ML Error: {traceback.format_exc()}")
            logger.info(f"💡 Using TA-only signal for {pair}")
            # Fallback to TA-only signal
            ml_prediction_bool = None
            ml_confidence = 0.65  # MODERATE confidence for TA-only (was 0.5 - too low)
            ml_signal_class = None  # Use TA-only signal, no forced direction

        # Generate combined signal
        signal = self.trading_engine.generate_signal(
            pair=pair,
            ta_signals=ta_signals,
            ml_prediction=ml_prediction_bool,
            ml_confidence=ml_confidence,
            ml_signal_class=ml_signal_class  # V2: pass signal class for direction
        )

        # Log signal details for debugging
        logger.info(f"📊 Signal for {pair}: {signal['recommendation']}")
        logger.info(f"📊 ML Confidence: {ml_confidence:.2%}")
        logger.info(f"📊 TA Strength: {ta_signals.get('strength', 0):.2f}")
        logger.info(f"📊 Combined Strength: {signal.get('combined_strength', 0):.2f}")

        # =====================================================================
        # FIX #3: Signal Stabilization Filter - RELAXED (Anti False Positive)
        # =====================================================================
        # PREVIOUS ISSUE: Filter too aggressive, downgraded STRONG_BUY → BUY too often
        # 
        # NEW RULES:
        # - Increase jump threshold dari 5 → 7 (lebih longgar)
        # - Tambahkan "2 consecutive cycles" concept (tidak langsung downgrade)
        # - Allow HOLD → STRONG_BUY jika confidence > 70% (trend confirmation)
        # - Better logging untuk debugging
        # =====================================================================
        original_rec = signal['recommendation']
        was_downgraded = False  # Track if we downgraded a STRONG signal
        stabilization_applied = False  # Track if we applied stabilization
        previous_signal_info = self.previous_signals.get(pair, {}).copy()

        if pair in self.previous_signals:
            prev = self.previous_signals[pair]
            prev_rec = prev.get('recommendation', 'HOLD')
            prev_timestamp = prev.get('timestamp', datetime.now())
            
            # Calculate time since previous signal
            time_diff = (datetime.now() - prev_timestamp).total_seconds()
            min_stable_time = 300  # 5 minutes minimum stable time

            # Define signal levels for jump detection
            signal_levels = {
                'STRONG_BUY': 3,
                'BUY': 2,
                'HOLD': 1,
                'SELL': -2,
                'STRONG_SELL': -3
            }

            current_level = signal_levels.get(signal['recommendation'], 0)
            prev_level = signal_levels.get(prev_rec, 0)
            jump = abs(current_level - prev_level)

            # =================================================================
            # RELAXED RULE #1: Extreme jump threshold dari 5 → 7
            # =================================================================
            if jump >= 7:
                # EXTREME jump only: STRONG_BUY ↔ STRONG_SELL → downgrade
                if signal['recommendation'] == 'STRONG_BUY':
                    logger.info(f"🛡️ [STABILIZE] Extreme jump detected: {pair} {prev_rec} → {original_rec}")
                    logger.info(f"   → Downgrading STRONG_BUY → BUY (extreme jump: {jump})")
                    signal['recommendation'] = 'BUY'
                    signal['reason'] = f'Signal stabilized from {prev_rec}. Extreme jump ({jump}). Downgraded to BUY.'
                    was_downgraded = True
                    stabilization_applied = True
                elif signal['recommendation'] == 'STRONG_SELL':
                    logger.info(f"🛡️ [STABILIZE] Extreme jump detected: {pair} {prev_rec} → {original_rec}")
                    logger.info(f"   → Downgrading STRONG_SELL → SELL (extreme jump: {jump})")
                    signal['recommendation'] = 'SELL'
                    signal['reason'] = f'Signal stabilized from {prev_rec}. Extreme jump ({jump}). Downgraded to SELL.'
                    was_downgraded = True
                    stabilization_applied = True

            # =================================================================
            # RELAXED RULE #2: Moderate jump dari 3 → 5
            # =================================================================
            elif jump >= 5:
                # Moderate jump: HOLD → STRONG → check confidence before downgrade
                confidence = signal.get('ml_confidence', 0)
                
                # Jika confidence tinggi (>70%), allow HOLD → STRONG_BUY (trend confirmed)
                if signal['recommendation'] == 'STRONG_BUY' and confidence > 0.70:
                    logger.info(f"✅ [ALLOW] HOLD → STRONG_BUY with high confidence: {pair} ({confidence:.1%})")
                    # Don't downgrade - confidence confirms the trend
                elif signal['recommendation'] == 'STRONG_BUY':
                    logger.info(f"🛡️ [STABILIZE] Moderate jump: {pair} {prev_rec} → {original_rec}")
                    logger.info(f"   → Downgrading STRONG_BUY → BUY (moderate jump: {jump}, conf: {confidence:.1%})")
                    signal['recommendation'] = 'BUY'
                    signal['reason'] = f'Signal stabilized from {prev_rec}. Moderate jump ({jump}). Downgraded to BUY.'
                    was_downgraded = True
                    stabilization_applied = True
                elif signal['recommendation'] == 'STRONG_SELL':
                    # SELL → STRONG_SELL is normal trend continuation, allow it
                    if prev_rec in ['SELL', 'HOLD']:
                        logger.info(f"✅ [ALLOW] Signal strengthening: {pair} {prev_rec} → {original_rec} (trend continuation)")
                    else:
                        logger.info(f"🛡️ [STABILIZE] Moderate jump: {pair} {prev_rec} → {original_rec}")
                        logger.info(f"   → Downgrading STRONG_SELL → SELL (moderate jump: {jump})")
                        signal['recommendation'] = 'SELL'
                        signal['reason'] = f'Signal stabilized from {prev_rec}. Moderate jump ({jump}). Downgraded to SELL.'
                        was_downgraded = True
                        stabilization_applied = True
                elif signal['recommendation'] in ['BUY', 'SELL']:
                    # Don't downgrade BUY/SELL to HOLD (important signals)
                    logger.info(f"✅ [ALLOW] Keeping {signal['recommendation']} for {pair} (no downgrade)")

            # =================================================================
            # NEW RULE: Allow quick transitions jika time gap > 30 minutes
            # =================================================================
            elif time_diff > 1800:  # 30 minutes
                logger.info(f"✅ [ALLOW] Large time gap ({time_diff/60:.0f}m), allowing signal change: {pair} {prev_rec} → {original_rec}")
                # No stabilization needed - market conditions likely changed

        # Log final recommendation after stabilization
        if stabilization_applied:
            logger.warning(f"⚠️ [FINAL] Signal for {pair}: {original_rec} → {signal['recommendation']} (STABILIZED)")
        else:
            logger.info(f"📊 [FINAL] Signal for {pair}: {signal['recommendation']} (no stabilization)")

        # =====================================================================
        # NEW: Signal Quality Engine V3 Integration
        # =====================================================================
        # Apply additional quality filters:
        # - Cooldown period (30 menit)
        # - Volume confirmation
        # - Confluence scoring
        # - RSI overbought/oversold protection
        # - ML vs TA conflict detection
        # =====================================================================
        
        # Get last signal info for cooldown check
        last_signal_info = previous_signal_info
        last_signal_time = last_signal_info.get('timestamp')
        last_recommendation = last_signal_info.get('recommendation', 'HOLD')
        
        # Map signal recommendation to ml_signal_class format
        ml_signal_class_for_engine = signal['recommendation']
        
        # Apply Volatility Filter first
        is_volatile_safe, vol_reason = (True, "OK")
        regime = 'UNKNOWN'
        position_multiplier = 1.0
        try:
            is_volatile_safe, vol_reason = self.signal_quality_engine.check_volatility_filter(df)
            regime, position_multiplier = self.signal_quality_engine.detect_market_regime(df)
        except:
            pass
        
        if not is_volatile_safe:
            signal['recommendation'] = 'HOLD'
            signal['reason'] = f"Volatility filter: {vol_reason}"
            signal['volatility_filtered'] = True
            logger.warning(f"🛡️ [VOLATILITY] {pair}: {vol_reason}")
        elif position_multiplier == 0.0:
            # Volatile market - no trading
            signal['recommendation'] = 'HOLD'
            signal['reason'] = f"Market regime: {regime} - too volatile for trading"
            signal['regime_filtered'] = True
            logger.warning(f"🛡️ [REGIME] {pair}: {regime} - no trading")
        else:
            # Store regime info
            signal['market_regime'] = regime
            signal['position_multiplier'] = position_multiplier
            if position_multiplier < 1.0:
                logger.info(f"📊 [{pair}] Regime: {regime}, Position size: {position_multiplier*100:.0f}%")
        
        # Apply Signal Quality Engine
        quality_signal = self.signal_quality_engine.generate_signal(
            pair=pair,
            ta_signals=ta_signals,
            ml_prediction=ml_prediction_bool if ml_prediction is not None else False,
            ml_confidence=ml_confidence,
            ml_signal_class=ml_signal_class_for_engine,
            last_signal_time=last_signal_time,
            last_recommendation=last_recommendation,
            combined_strength=signal.get('combined_strength', 0.0)
        )
        
        # If quality engine rejects signal, override to HOLD
        if quality_signal and quality_signal.get('type') == 'HOLD':
            original_rec = signal['recommendation']
            signal['recommendation'] = 'HOLD'
            signal['reason'] = quality_signal.get('reason', f'Signal rejected by Quality Engine V3 (was {original_rec})')
            signal['quality_filtered'] = True
            logger.warning(
                f"🛡️ [QUALITY ENGINE] {pair}: {original_rec} → HOLD | "
                f"Reason: {quality_signal.get('reason', 'Unknown')}"
            )
        elif quality_signal:
            signal['quality_approved'] = True
            signal['confluence_score'] = quality_signal.get('confluence', 0)
            logger.info(
                f"✅ [QUALITY ENGINE] {pair}: {signal['recommendation']} approved "
                f"(confluence: {quality_signal.get('confluence', 0)})"
            )

        # Override price with real-time price
        signal['price'] = real_time_price

        # =====================================================================
        # NEW: Support & Resistance Detection
        # =====================================================================
        # Auto-detect S/R levels from historical data
        # Adds: support_1, support_2, resistance_1, resistance_2,
        #       price_zone, risk_reward_ratio, distance_to_support_pct, etc.
        # =====================================================================
        try:
            sr_levels = self.sr_detector.detect_levels(
                df=df,  # Historical data
                levels=2,  # Detect 2 levels of S/R
                current_price=real_time_price,
                method='auto',  # Auto-select best method
                pair=pair  # Check for manual override
            )
            
            # Add S/R levels to signal dict
            signal.update(sr_levels)
            
            logger.info(
                f"📊 [S/R] {pair}: S1={sr_levels.get('support_1', 0):,.0f} | "
                f"R1={sr_levels.get('resistance_1', 0):,.0f} | "
                f"Zone={sr_levels.get('price_zone', 'UNKNOWN')} | "
                f"R/R={sr_levels.get('risk_reward_ratio', 0):.2f}"
            )
        except Exception as e:
            logger.warning(f"⚠️ [S/R] Failed to detect levels for {pair}: {e}")
            signal['support_1'] = 0
            signal['support_2'] = 0
            signal['resistance_1'] = 0
            signal['resistance_2'] = 0
            signal['price_zone'] = 'UNKNOWN'
            signal['risk_reward_ratio'] = 0

        # =====================================================================
        # NEW: S/R Based Signal Validation
        # =====================================================================
        # Validate signal based on S/R levels to avoid false signals
        # Filter: BUY at resistance, SELL at support, bad R/R, tight SL
        # Configurable via .env: ENABLE_SR_VALIDATION, SR_MIN_RR, etc.
        # =====================================================================
        try:
            # Check if S/R validation is enabled
            sr_validation_enabled = os.getenv("ENABLE_SR_VALIDATION", "true").lower() == "true"
            if not sr_validation_enabled:
                logger.debug(f"⏭️ [S/R VALIDATION] Disabled for {pair}")
            else:
                price_zone = signal.get('price_zone', 'UNKNOWN')
                support_1 = signal.get('support_1', 0)
                resistance_1 = signal.get('resistance_1', 0)
                risk_reward = signal.get('risk_reward_ratio', 0)
                recommendation = signal.get('recommendation', 'HOLD')
                
                # Get thresholds from config
                rr_threshold = float(os.getenv("SR_MIN_RR_RATIO", "0.8"))  # Changed from 1.0 to 0.8
                sl_min_pct = float(os.getenv("SR_MIN_SL_PCT", "0.3"))  # Changed from 0.5% to 0.3%
                near_support_pct = float(os.getenv("SR_NEAR_SUPPORT_PCT", "2.0"))  # Changed from 1% to 2%
                near_resistance_pct = float(os.getenv("SR_NEAR_RESISTANCE_PCT", "2.0"))  # Changed from 1% to 2%
                
                # Calculate stop loss distance percentage
                if recommendation in ['SELL', 'STRONG_SELL'] and support_1 > 0:
                    sl_distance_pct = abs(real_time_price - support_1) / real_time_price * 100
                elif recommendation in ['BUY', 'STRONG_BUY'] and resistance_1 > 0:
                    sl_distance_pct = abs(resistance_1 - real_time_price) / real_time_price * 100
                else:
                    sl_distance_pct = 999  # No valid SL to check
                
                # Validation flags
                reject_signal = False
                reject_reason = ""
                
                # Rule 1: BUY signal at/near resistance (price >= R1 - X%)
                if recommendation in ['BUY', 'STRONG_BUY'] and resistance_1 > 0:
                    if real_time_price >= resistance_1 * (1 - near_resistance_pct/100):
                        # Check if strong confirmation (ML confidence > 70%)
                        ml_conf = signal.get('ml_confidence', 0)
                        if ml_conf > 0.70:
                            logger.info(f"⚠️ [S/R VALIDATION] {pair}: BUY near resistance but high ML confidence ({ml_conf:.0%}) - allowing")
                        else:
                            reject_signal = True
                            reject_reason = f"BUY signal rejected: Price at/near resistance (R1: {resistance_1:,.0f})"
                
                # Rule 2: SELL signal at/near support (price <= S1 + X%)
                elif recommendation in ['SELL', 'STRONG_SELL'] and support_1 > 0:
                    if real_time_price <= support_1 * (1 + near_support_pct/100):
                        # Check if strong confirmation (ML confidence > 70%)
                        ml_conf = signal.get('ml_confidence', 0)
                        if ml_conf > 0.70:
                            logger.info(f"⚠️ [S/R VALIDATION] {pair}: SELL near support but high ML confidence ({ml_conf:.0%}) - allowing")
                        else:
                            reject_signal = True
                            reject_reason = f"SELL signal rejected: Price at/near support (S1: {support_1:,.0f})"
                
                # Rule 3: Risk/Reward ratio too low (< threshold)
                if not reject_signal and risk_reward > 0 and risk_reward < rr_threshold:
                    reject_signal = True
                    reject_reason = f"Signal rejected: Risk/Reward ratio too low ({risk_reward:.2f} < {rr_threshold:.2f})"
                
                # Rule 4: Stop Loss distance too small (< threshold)
                if not reject_signal and sl_distance_pct < sl_min_pct:
                    reject_signal = True
                    reject_reason = f"Signal rejected: Stop Loss distance too small ({sl_distance_pct:.2f}% < {sl_min_pct:.1f}%)"
                
                # Apply rejection
                if reject_signal:
                    logger.warning(f"🛡️ [S/R VALIDATION] {pair}: {recommendation} → HOLD | {reject_reason}")
                    signal['recommendation'] = 'HOLD'
                    signal['reason'] = reject_reason
                    signal['sr_filtered'] = True
                else:
                    logger.debug(f"✅ [S/R VALIDATION] {pair}: {recommendation} passed (R/R: {risk_reward:.2f}, SL dist: {sl_distance_pct:.2f}%)")
                    
        except Exception as e:
            logger.warning(f"⚠️ [S/R VALIDATION] Failed for {pair}: {e}")

        # =====================================================================
        # NEW: Signal Enhancement Analysis
        # =====================================================================
        # Apply Volume, VWAP, Ichimoku, Divergence, Candlestick analysis
        # =====================================================================
        try:
            # Get 24h volume from Indodax API
            volume_24h = None
            try:
                ticker = self.indodax.get_ticker(pair)
                if ticker:
                    volume_24h = ticker.get('vol_idr', 0) or ticker.get('vol_btc', 0) * ticker.get('last', 0)
            except:
                pass
            
            # Run enhancement analysis
            enhancement_result = self.signal_enhancement.analyze(
                df=df,
                current_price=real_time_price,
                volume_24h=volume_24h,
                base_recommendation=signal['recommendation']
            )
            
            # Store enhancement data in signal
            signal['enhancement'] = {
                'enabled_features': enhancement_result.get('enabled_features', []),
                'adjustments': enhancement_result.get('adjustments', []),
                'vwap': enhancement_result.get('vwap', {}),
                'ichimoku': enhancement_result.get('ichimoku', {}),
                'divergence': enhancement_result.get('divergence', {}),
                'candlestick': enhancement_result.get('candlestick', {}),
                'volume': enhancement_result.get('volume', {})
            }
            
            # Apply confidence adjustment
            confidence_adjustment = enhancement_result.get('final_confidence_adjustment', 0)
            if confidence_adjustment != 0:
                old_confidence = signal.get('ml_confidence', 0.5)
                signal['ml_confidence'] = max(0.0, min(1.0, old_confidence + confidence_adjustment))
                logger.info(
                    f"📈 [ENHANCEMENT] {pair}: Confidence adjusted {old_confidence:.1%} → {signal['ml_confidence']:.1%} "
                    f"(adjustment: {confidence_adjustment:+.2f}, features: {enhancement_result.get('enabled_features', [])})"
                )
            
            # Check if should override due to volume
            if enhancement_result.get('should_override'):
                signal['recommendation'] = 'HOLD'
                signal['reason'] = enhancement_result.get('override_reason', 'Enhancement rejected signal')
                signal['enhancement_filtered'] = True
                logger.warning(f"🛡️ [ENHANCEMENT] {pair}: Signal overridden to HOLD | {signal['reason']}")
            
        except Exception as e:
            logger.warning(f"⚠️ [ENHANCEMENT] Failed for {pair}: {e}")

        hold_flags = []
        if signal.get('volatility_filtered'):
            hold_flags.append('volatility_filter')
        if signal.get('regime_filtered'):
            hold_flags.append('regime_filter')
        if signal.get('quality_filtered'):
            hold_flags.append('quality_engine')
        if signal.get('sr_filtered'):
            hold_flags.append('sr_validation')
        if signal.get('enhancement_filtered'):
            hold_flags.append('enhancement')
        if signal.get('recommendation') == 'HOLD':
            hold_source = ', '.join(hold_flags) if hold_flags else 'upstream_signal'
            logger.warning(
                f"🧭 [HOLD TRACE] {pair}: source={hold_source} | "
                f"reason={signal.get('reason', 'No reason provided')}"
            )

        # Save final signal for next cycle comparison after all filters are applied
        self.previous_signals[pair] = {
            'recommendation': signal['recommendation'],
            'timestamp': datetime.now()
        }

        # AUTO-SAVE to SQLite (signal DB initialized at startup)
        if self._signal_db is None:
            return signal  # DB not available, skip silently

        # Prepare signal data for DB
        final_confidence = signal.get('ml_confidence', ml_confidence)
        signal_data = {
            "symbol": pair.upper(),
            "price": str(real_time_price),
            "rec": signal['recommendation'],
            "rsi": str(ta_signals.get('indicators', {}).get('rsi', '—')),
            "macd": str(ta_signals.get('indicators', {}).get('macd_signal', '—')),
            "ma": str(ta_signals.get('indicators', {}).get('ma_trend', '—')),
            "bollinger": str(ta_signals.get('indicators', {}).get('bb', '—')),
            "volume": str(ta_signals.get('indicators', {}).get('volume', '—')),
            "confidence": f"{final_confidence:.1%}",
            "strength": f"{signal.get('combined_strength', 0):.2f}",
            # S/R levels (NEW)
            "support_1": f"{signal.get('support_1', 0):,.0f}" if signal.get('support_1', 0) > 0 else "—",
            "support_2": f"{signal.get('support_2', 0):,.0f}" if signal.get('support_2', 0) > 0 else "—",
            "resistance_1": f"{signal.get('resistance_1', 0):,.0f}" if signal.get('resistance_1', 0) > 0 else "—",
            "resistance_2": f"{signal.get('resistance_2', 0):,.0f}" if signal.get('resistance_2', 0) > 0 else "—",
            "price_zone": signal.get('price_zone', 'UNKNOWN'),
            "risk_reward": f"{signal.get('risk_reward_ratio', 0):.2f}",
            "analysis": signal.get('reason', ''),
            "signal_time": datetime.now().strftime("%H:%M:%S")
        }

        try:
            # Insert to DB (all signals: HOLD, BUY, SELL, etc)
            signal_id = self._signal_db.insert_signal(signal_data, datetime.now(), retries=3)
            if signal_id > 0:
                logger.info(f"💾 Signal #{signal_id} saved: {pair} - {signal['recommendation']} @ {signal_data['price']} IDR")
            elif signal_id == -1:
                logger.debug(f"⏭️ Duplicate signal skipped: {pair}")
            elif signal_id == -2:
                logger.warning(f"⚠️ Failed to save signal to DB after 3 retries: {pair}")
        except Exception as e:
            logger.error(f"❌ Failed to save signal to DB: {e}")
            import traceback
            logger.error(f"Signal DB Error: {traceback.format_exc()}")

        return signal
    
    def _format_signal_message(self, signal):
        """Format signal into readable Telegram message (Markdown) - ENHANCED VERSION"""
        indicators = signal.get('indicators', {})
        pair = signal.get('pair', 'UNKNOWN')
        recommendation = signal.get('recommendation', 'HOLD')
        price = signal.get('price', 0)
        ml_confidence = signal.get('ml_confidence', 0.5)
        combined_strength = signal.get('combined_strength', 0)
        timestamp = signal.get('timestamp', datetime.now())
        reason = signal.get('reason', 'No analysis available')

        # Signal type configuration with colors and descriptions
        # Add colored recommendation
        if recommendation in ['BUY', 'STRONG_BUY']:
            rec_colored = f"🟢 {recommendation}"
        elif recommendation in ['SELL', 'STRONG_SELL']:
            rec_colored = f"🔴 {recommendation}"
        else:
            rec_colored = f"⚪ {recommendation}"
        
        signal_config = {
            'STRONG_BUY': {
                'emoji': '🚀',
                'color': '🟢',
                'header_emoji': '🟢',
                'desc': 'Strong Buy Signal',
                'action': 'Consider buying immediately'
            },
            'BUY': {
                'emoji': '📈',
                'color': '🟢',
                'header_emoji': '🟢',
                'desc': 'Buy Signal',
                'action': 'Good entry point'
            },
            'HOLD': {
                'emoji': '⏸️',
                'color': '⚪',
                'header_emoji': '⚪',
                'desc': 'Hold Position',
                'action': 'Wait for better opportunity'
            },
            'SELL': {
                'emoji': '📉',
                'color': '🔴',
                'header_emoji': '🔴',
                'desc': 'Sell Signal',
                'action': 'Consider taking profits'
            },
            'STRONG_SELL': {
                'emoji': '🔻',
                'color': '🔴',
                'header_emoji': '🔴',
                'desc': 'Strong Sell Signal',
                'action': 'Exit position immediately'
            }
        }.get(recommendation, {'emoji': '❓', 'color': '⚪', 'header_emoji': '⚪', 'desc': 'Unknown', 'action': 'N/A'})

        # S/R levels
        support_1 = signal.get('support_1', 0)
        resistance_1 = signal.get('resistance_1', 0)

        # Build S/R section if available
        sr_section = ""
        if support_1 > 0 or resistance_1 > 0:
            sr_section = f"""
🎯 **Support/Resistance:**
• Support: `{Utils.format_price(support_1)}` {'IDR' if support_1 > 0 else ''}
• Resistance: `{Utils.format_price(resistance_1)}` {'IDR' if resistance_1 > 0 else ''}"""

        # Strength indicator visualization
        strength_bar = self._generate_strength_bar(combined_strength)
        confidence_bar = self._generate_strength_bar(ml_confidence * 2 - 1)  # Scale 0-1 to -1 to 1

        # Technical indicators with emojis
        rsi_val = indicators.get('rsi', 'N/A')
        macd_val = indicators.get('macd', 'N/A')
        ma_val = indicators.get('ma_trend', 'N/A')
        bb_val = indicators.get('bb', 'N/A')
        vol_val = indicators.get('volume', 'N/A')

        # RSI interpretation
        rsi_emoji = '🔴' if rsi_val == 'OVERBOUGHT' else '🟢' if rsi_val == 'OVERSOLD' else '⚪'
        macd_emoji = '🟢' if 'BULLISH' in str(macd_val) else '🔴' if 'BEARISH' in str(macd_val) else '⚪'
        ma_emoji = '🟢' if ma_val == 'BULLISH' else '🔴' if ma_val == 'BEARISH' else '⚪'

        text = f"""
{signal_config['emoji']} *{pair} — Trading Signal*

{rec_colored} *Recommendation: {recommendation}*
_{signal_config['desc']}_
💡 Action: {signal_config['action']}

💰 *Current Price:* `{Utils.format_price(price)}` IDR

📊 *Signal Strength:*
{strength_bar} `{combined_strength:+.2f}`
🤖 *ML Confidence:*
{confidence_bar} `{ml_confidence:.1%}`

📈 *Technical Indicators:*
{rsi_emoji} RSI (14): `{rsi_val}`
{macd_emoji} MACD: `{macd_val}`
{ma_emoji} MA Trend: `{ma_val}`
⚪ Bollinger: `{bb_val}`
⚪ Volume: `{vol_val}`
{sr_section}

📝 *Analysis:*
_{reason}_

⏰ `{timestamp.strftime('%H:%M:%S')}`
        """
        return text

    def _generate_strength_bar(self, strength):
        """Generate visual strength bar indicator"""
        # Clamp strength to -1 to 1
        strength = max(-1, min(1, strength))

        # Calculate bar length (max 10 blocks)
        bar_length = int(abs(strength) * 10)
        empty_length = 10 - bar_length

        # Choose color based on direction
        if strength > 0:
            bar = '█' * bar_length + '░' * empty_length
            return f"🟢 [{bar}]"
        elif strength < 0:
            bar = '░' * empty_length + '█' * bar_length
            return f"🔴 [{bar}]"
        else:
            return f"⚪ [{'░' * 10}]"

    def _format_signal_message_html(self, signal):
        """Format signal into readable Telegram message (HTML) - ENHANCED VERSION"""
        indicators = signal.get('indicators', {})
        pair = signal.get('pair', 'UNKNOWN')
        recommendation = signal.get('recommendation', 'HOLD')
        price = signal.get('price', 0)
        ml_confidence = signal.get('ml_confidence', 0.5)
        combined_strength = signal.get('combined_strength', 0)
        timestamp = signal.get('timestamp', datetime.now())
        reason = signal.get('reason', 'No analysis available')

        # Signal type configuration with descriptions
        signal_config = {
            'STRONG_BUY': {
                'emoji': '🚀',
                'header_emoji': '🟢',
                'desc': 'Strong Buy Signal',
                'action': 'Consider buying immediately'
            },
            'BUY': {
                'emoji': '📈',
                'header_emoji': '🟢',
                'desc': 'Buy Signal',
                'action': 'Good entry point'
            },
            'HOLD': {
                'emoji': '⏸️',
                'header_emoji': '🟡',
                'desc': 'Hold Position',
                'action': 'Wait for better opportunity'
            },
            'SELL': {
                'emoji': '📉',
                'header_emoji': '🔴',
                'desc': 'Sell Signal',
                'action': 'Consider taking profits'
            },
            'STRONG_SELL': {
                'emoji': '🔻',
                'header_emoji': '🔴',
                'desc': 'Strong Sell Signal',
                'action': 'Exit position immediately'
            }
        }.get(recommendation, {'emoji': '❓', 'header_emoji': '⚪', 'desc': 'Unknown', 'action': 'N/A'})

        # S/R levels
        support_1 = signal.get('support_1', 0)
        support_2 = signal.get('support_2', 0)
        resistance_1 = signal.get('resistance_1', 0)
        resistance_2 = signal.get('resistance_2', 0)
        price_zone = signal.get('price_zone', 'UNKNOWN')
        rr_ratio = signal.get('risk_reward_ratio', 0)

        # Format S/R section if available
        sr_section = ""
        if support_1 > 0 or resistance_1 > 0:
            sr_section = f"""

🎯 <b>Support/Resistance:</b>
• S1: <code>{Utils.format_price(support_1) if support_1 > 0 else '—'}</code>
• S2: <code>{Utils.format_price(support_2) if support_2 > 0 else '—'}</code>
• R1: <code>{Utils.format_price(resistance_1) if resistance_1 > 0 else '—'}</code>
• R2: <code>{Utils.format_price(resistance_2) if resistance_2 > 0 else '—'}</code>

📍 <b>Price Zone:</b> {price_zone}
⚖️ <b>Risk/Reward:</b> {rr_ratio:.2f}"""

        # Technical indicators with visual emojis
        rsi_val = indicators.get('rsi', 'N/A')
        macd_val = indicators.get('macd', 'N/A')
        ma_val = indicators.get('ma_trend', 'N/A')
        bb_val = indicators.get('bb', 'N/A')
        vol_val = indicators.get('volume', 'N/A')

        # RSI interpretation with emojis
        rsi_emoji = '🔴' if rsi_val == 'OVERBOUGHT' else '🟢' if rsi_val == 'OVERSOLD' else '⚪'
        macd_emoji = '🟢' if 'BULLISH' in str(macd_val) else '🔴' if 'BEARISH' in str(macd_val) else '⚪'
        ma_emoji = '🟢' if ma_val == 'BULLISH' else '🔴' if ma_val == 'BEARISH' else '⚪'
        bb_emoji = '🟢' if bb_val == 'OVERSOLD' else '🔴' if bb_val == 'OVERBOUGHT' else '⚪'

        # Strength visualization
        strength_bar = self._generate_strength_bar_html(combined_strength)
        confidence_pct = int(ml_confidence * 100)

        text = f"""
{signal_config['emoji']} <b>{pair} — Trading Signal</b>

<b>Recommendation: {('🟢 ' + recommendation) if recommendation in ['BUY', 'STRONG_BUY'] else ('🔴 ' + recommendation) if recommendation in ['SELL', 'STRONG_SELL'] else ('⚪ ' + recommendation)}</b>
<i>{signal_config['desc']}</i>
💡 <b>Action:</b> {signal_config['action']}

💰 <b>Current Price:</b> <code>{Utils.format_price(price)}</code> IDR

📊 <b>Signal Metrics:</b>
• Combined Strength: {strength_bar} <code>{combined_strength:+.2f}</code>
• ML Confidence: <code>{confidence_pct}%</code>

📈 <b>Technical Indicators:</b>
{rsi_emoji} RSI (14): <code>{rsi_val}</code>
{macd_emoji} MACD: <code>{macd_val}</code>
{ma_emoji} MA Trend: <code>{ma_val}</code>
{bb_emoji} Bollinger: <code>{bb_val}</code>
⚪ Volume: <code>{vol_val}</code>
{sr_section}

📝 <b>Analysis:</b>
<i>{reason}</i>

⏰ <code>{timestamp.strftime('%H:%M:%S')}</code>
        """
        return text

    def _format_market_scan_signal(self, signal):
        """Format market scan signal (simple dict) into Telegram message"""
        pair = signal.get('pair', 'UNKNOWN')
        sig_type = signal.get('type', 'HOLD')
        confidence = signal.get('confidence', 0)
        price = signal.get('price', 0)
        reason = signal.get('reason', 'TA analysis')

        signal_config = {
            'STRONG_BUY': {'emoji': '🚀', 'color': '🟢', 'desc': 'Strong Buy Signal'},
            'BUY': {'emoji': '📈', 'color': '🟢', 'desc': 'Buy Signal'},
            'HOLD': {'emoji': '⏸️', 'color': '⚪', 'desc': 'Hold'},
            'SELL': {'emoji': '📉', 'color': '🔴', 'desc': 'Sell Signal'},
            'STRONG_SELL': {'emoji': '🔻', 'color': '🔴', 'desc': 'Strong Sell Signal'},
        }
        config = signal_config.get(sig_type, {'emoji': '❓', 'color': '⚪', 'desc': 'Unknown'})
        now = datetime.now().strftime('%H:%M:%S')
        
        # Add color to recommendation text
        if sig_type in ['BUY', 'STRONG_BUY']:
            rec_colored = f"<b>🟢 {sig_type}</b>"
        elif sig_type in ['SELL', 'STRONG_SELL']:
            rec_colored = f"<b>🔴 {sig_type}</b>"
        else:
            rec_colored = f"<b>⚪ {sig_type}</b>"

        msg = f"""{config['emoji']} <b>Signal Alert — {rec_colored}</b>

📊 <b>{pair.upper()}</b>

💰 Price: <code>{price:,.0f} IDR</code>
🎯 Confidence: {confidence:.0%}
⏰ Time: {now}

📝 <b>Reason:</b> {reason}
"""
        return msg

    def _generate_strength_bar_html(self, strength):
        """Generate visual strength bar indicator for HTML"""
        # Clamp strength to -1 to 1
        strength = max(-1, min(1, strength))

        # Calculate bar length (max 10 blocks)
        bar_length = int(abs(strength) * 10)

        # Choose color based on direction
        if strength > 0:
            bar = '█' * bar_length + '░' * (10 - bar_length)
            return f'<code>[{bar}]</code>'
        elif strength < 0:
            bar = '░' * (10 - bar_length) + '█' * bar_length
            return f'<code>[{bar}]</code>'
        else:
            return f'<code>[{"░" * 10}]</code>'

    async def _monitor_strong_signal(self, pair):
        """
        Monitor ONLY pairs that users have explicitly added to their watchlist (/watch).
        Send notifications for strong signals (BUY/SELL/STRONG_BUY/STRONG_SELL).
        """
        # Check if pair is in ANY user's watchlist (subscribers)
        is_watched = False
        for user_id, pairs in self.subscribers.items():
            if pair in pairs:
                is_watched = True
                break
        
        if not is_watched:
            return  # Not in any user's watchlist, skip

        # Initialize signal check tracking
        if not hasattr(self, '_last_signal_checks'):
            self._last_signal_checks = {}

        # Rate limit: check every 5 minutes per pair (faster alerts)
        last_check = self._last_signal_checks.get(pair)
        if last_check and datetime.now() - last_check < timedelta(minutes=5):
            return  # Too soon, skip
        self._last_signal_checks[pair] = datetime.now()

        # Generate signal
        signal = await self._generate_signal_for_pair(pair)
        if not signal:
            return

        # Safety check: ensure signal has required keys
        if 'recommendation' not in signal:
            logger.warning(f"⚠️ Signal for {pair} missing 'recommendation' key, skipping")
            return

        recommendation = signal.get('recommendation', 'HOLD')
        confidence = signal.get('ml_confidence', 0)

        # Only notify for STRONG signals (STRONG_BUY, STRONG_SELL, or any BUY/SELL)
        if recommendation in ['STRONG_BUY', 'STRONG_SELL', 'BUY', 'SELL']:
            pass  # Always notify BUY/SELL signals (any confidence)
        else:
            return  # Skip HOLD and weak signals
        
        # Check cooldown to prevent duplicates (5 minutes between same signal)
        signal_key = f"{pair}_{recommendation}"
        if not hasattr(self, '_notification_cooldown'):
            self._notification_cooldown = {}
        
        last_sent = self._notification_cooldown.get(signal_key, datetime.min)
        if datetime.now() - last_sent < timedelta(minutes=5):
            logger.debug(f"⏳ Notification cooldown: {signal_key}")
            return
        
        self._notification_cooldown[signal_key] = datetime.now()
        
        # Format and send notification
        signal_text = self._format_signal_message_html(signal)

        # Add monitoring label with signal type header
        signal_emoji = {
            'STRONG_BUY': '🚀',
            'BUY': '📈',
            'SELL': '📉',
            'STRONG_SELL': '🔻'
        }.get(recommendation, '🔔')
        
        # Add color to recommendation
        if recommendation in ['BUY', 'STRONG_BUY']:
            rec_colored = f"🟢 {recommendation}"
        elif recommendation in ['SELL', 'STRONG_SELL']:
            rec_colored = f"🔴 {recommendation}"
        else:
            rec_colored = f"⚪ {recommendation}"

        signal_header = f"{signal_emoji} <b>Signal Alert — {rec_colored}</b>\n\n"
        signal_text = signal_header + signal_text

        # Send notification to all admins
        import requests
        import asyncio
        loop = asyncio.get_event_loop()
        
        for admin_id in Config.ADMIN_IDS:
            try:
                url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": admin_id,
                    "text": signal_text,
                    "parse_mode": "HTML"
                }
                
                # Run HTTP request in executor to avoid blocking the event loop
                response = await loop.run_in_executor(
                    None, 
                    lambda: requests.post(url, json=payload, timeout=10)
                )
                
                if response.status_code == 200:
                    logger.info("📢 Signal alert sent to admin %s for %s: %s (%.1f%%)", admin_id, pair, recommendation, confidence * 100)
                else:
                    logger.error("❌ Failed to send signal alert: HTTP %s - %s", response.status_code, response.text)
                    
            except Exception as e:
                logger.error("❌ Failed to send signal alert via HTTP: %s", e)

    async def _check_trading_opportunity(self, pair):
        """Check and execute trading opportunity (auto-trading)"""
        # Check if auto-trading is enabled
        if not self.is_trading:  # Use self.is_trading instead of Config
            return

        # IMPORTANT: Only trade pairs that are in user's auto_trade_pairs list
        # Watchlist pairs (/watch) are NOT auto-traded unless explicitly added
        is_auto_trade_pair = False
        for user_id, pairs in self.auto_trade_pairs.items():
            if pair in pairs:
                is_auto_trade_pair = True
                break

        if not is_auto_trade_pair:
            logger.debug(f"⏭️ Skipping {pair}: Not in auto-trade list (only in watchlist)")
            # Still check for strong signals to notify!
            await self._monitor_strong_signal(pair)
            return

        # Rate limit: max once per configured interval per pair
        if pair in self.last_ml_update:
            if datetime.now() - self.last_ml_update[pair] < timedelta(minutes=self.auto_trade_interval_minutes):
                return

        self.last_ml_update[pair] = datetime.now()

        # Check if dry run mode
        is_dry_run = Config.AUTO_TRADE_DRY_RUN
        mode_label = "🧪 DRY RUN" if is_dry_run else "🔴 REAL"
        logger.info(f"{mode_label} Scanning {pair} for auto-trade opportunity...")

        # Generate signal
        signal = await self._generate_signal_for_pair(pair)
        if not signal:
            return

        # Safety check: ensure signal has required keys
        if 'recommendation' not in signal:
            logger.warning(f"⚠️ Signal for {pair} missing 'recommendation' key, skipping")
            return

        # Only act on strong signals
        if signal['recommendation'] not in ['STRONG_BUY', 'BUY', 'STRONG_SELL', 'SELL']:
            logger.debug(f"⏸️ Skipping {pair}: Weak signal ({signal['recommendation']})")
            return

        # 📢 TELEGRAM NOTIFICATION: Send signal to admin
        user_id = list(self.subscribers.keys())[0] if self.subscribers else 1
        signal_text = self._format_signal_message_html(signal)
        
        # Add auto-trade mode label
        mode_label = "🧪 DRY RUN" if is_dry_run else "🔴 REAL"
        signal_text = f"{mode_label}\n\n{signal_text}"
        
        # Send notification to all admins
        for admin_id in Config.ADMIN_IDS:
            try:
                await self.app.bot.send_message(
                    chat_id=admin_id,
                    text=signal_text,
                    parse_mode='HTML'
                )
                logger.info(f"📢 Signal notification sent to admin {admin_id} for {pair}")
            except Exception as e:
                logger.error(f"❌ Failed to send signal notification: {e}")

        # Risk checks
        can_trade, reason = self.risk_manager.check_daily_loss_limit(user_id)
        if not can_trade:
            logger.warning(f"⚠️ Trading blocked for {pair}: {reason}")
            return

        # Execute trade logic
        current_price = signal['price']
        confidence = signal['ml_confidence']

        if signal['recommendation'] in ['BUY', 'STRONG_BUY']:
            # 📊 MARKET INTELLIGENCE: Volume Spike + Orderbook Pressure Analysis
            market_conditions = await self._analyze_market_intelligence(pair, current_price)
            
            # 📊 MARKET REGIME DETECTION
            regime = self._detect_market_regime(pair)
            
            # 🚫 ENTRY FILTER CHECK: Market Intelligence must pass
            if not market_conditions.get('passes_entry_filter', True):
                logger.info(f"🚫 Entry blocked for {pair}: MI filter failed (Signal={market_conditions['overall_signal']})")
                return

            # 📊 Regime-based entry logic
            if regime['is_high_vol']:
                logger.info(f"⚠️ HIGH VOLATILITY regime detected for {pair} - proceeding with caution")
                # In high vol, reduce position size by 50%
                amount, total = self.trading_engine.calculate_position_size(1, current_price)
                amount *= 0.5
                total *= 0.5
                logger.info(f"📊 Position size reduced 50% due to high volatility: {amount}")
            elif regime['is_trending'] and regime['trend_direction'] == 'DOWN':
                logger.info(f"⚠️ DOWNTREND detected for {pair} - reducing position size")
                # In downtrend, reduce position size by 25%
                amount, total = self.trading_engine.calculate_position_size(1, current_price)
                amount *= 0.75
                total *= 0.75
                logger.info(f"📊 Position size reduced 25% due to downtrend: {amount}")
            else:
                # Normal regime - full position size
                amount, total = self.trading_engine.calculate_position_size(1, current_price)

            # Fetch FRESH price right before execution (price may have changed)
            try:
                from api.indodax_api import IndodaxAPI
                indodax = IndodaxAPI()
                fresh_ticker = indodax.get_ticker(pair)
                if fresh_ticker:
                    current_price = fresh_ticker['last']
                    logger.info(f"🔄 Fresh execution price for {pair}: {current_price}")
                else:
                    logger.warning(f"⚠️ Failed to get fresh price for {pair}, using signal price")
            except Exception as e:
                logger.error(f"❌ Error fetching fresh price: {e}")
                # Continue with signal price as fallback

            # Recalculate position after fresh price (if regime didn't already set it)
            if 'amount' not in dir() or 'total' not in dir():
                amount, total = self.trading_engine.calculate_position_size(1, current_price)
            
            # Calculate SL/TP with partial take profit
            tp_data = self.trading_engine.calculate_stop_loss_take_profit(current_price, 'BUY')
            stop_loss = tp_data['stop_loss']
            take_profit_1 = tp_data['take_profit_1']
            take_profit_2 = tp_data['take_profit_2']
            
            # 📊 Support/Resistance Analysis
            sr_data = await self._get_support_resistance_for_pair(pair)
            if sr_data:
                # Adjust TP/SL based on S/R levels if available
                if sr_data.get('nearest_resistance') and take_profit_1 > sr_data['nearest_resistance']:
                    # Take profit before resistance
                    take_profit_1 = sr_data['nearest_resistance'] * 0.98
                    logger.info(f"📊 TP1 adjusted to S/R: {take_profit_1:,.0f}")

                if sr_data.get('nearest_support') and stop_loss < sr_data['nearest_support']:
                    # Stop loss below support
                    stop_loss = sr_data['nearest_support'] * 0.98
                    logger.info(f"📊 SL adjusted to S/R: {stop_loss:,.0f}")

            # 🧠 Reinforcement Learning decision
            rl_action = 'HOLD'
            if Config.RL_ENABLED:
                mi_signal = market_conditions.get('overall_signal', 'NEUTRAL')
                state = self._rl_get_state(confidence, regime.get('regime', 'RANGE'), mi_signal)
                rl_action = self._rl_choose_action(state)
                logger.info(f"🧠 RL action for {pair}: {rl_action} (state={state})")
                
                # RL can veto the trade if it strongly suggests HOLD
                if rl_action == 'SELL' and signal['recommendation'] in ['BUY', 'STRONG_BUY']:
                    logger.info(f"🧠 RL vetoed BUY for {pair}, suggests SELL instead")
                    # Still allow BUY but with reduced size
                    amount *= 0.5
                    total *= 0.5

            # 📊 Smart order routing for execution
            if Config.SMART_ROUTING_ENABLED:
                # Get current orderbook for routing
                try:
                    ob = self.indodax.get_orderbook(pair, limit=20)
                    if ob:
                        routing_orders = self._smart_order_routing(
                            pair, 'buy', total, ob.get('bids', []), ob.get('asks', [])
                        )
                        logger.info(f"📊 Smart routing for {pair}: {len(routing_orders)} chunks")
                except Exception as e:
                    logger.warning(f"⚠️ Smart routing failed for {pair}: {e}")

            # 📊 Liquidity zones
            liquidity_zones = self._find_liquidity_zones(pair)
            if liquidity_zones:
                top_zone = liquidity_zones[0]
                logger.info(f"📊 Top liquidity zone for {pair}: {top_zone[0]:,.0f} (vol={top_zone[1]:,.0f})")

            # 🎯 Elite signal confirmation (clean logic from app/strategy/signal.py)
            try:
                ob = self.indodax.get_orderbook(pair, limit=20)
                raw_bids = ob.get('bids', []) if ob else []
                raw_asks = ob.get('asks', []) if ob else []

                elite_signal, elite_prob, elite_imb = self._elite_signal(
                    self.historical_data.get(pair, pd.DataFrame()),
                    raw_bids, raw_asks, liquidity_zones
                )
                logger.info(f"🎯 Elite signal for {pair}: {elite_signal} (prob={elite_prob}, imb={elite_imb})")

                # Elite signal can reduce position if conflicting
                if elite_signal == 'SELL' and signal['recommendation'] in ['BUY', 'STRONG_BUY']:
                    logger.warning(f"⚠️ Elite signal conflicts with ML signal for {pair}")
                    amount *= 0.5
                    total *= 0.5
            except Exception as e:
                logger.warning(f"⚠️ Elite signal failed for {pair}: {e}")

            # 💰 Fee-aware net price calculation
            net_entry, net_exit, round_trip_fee = self._fee_aware_net_price(current_price, 'BUY')
            effective_tp = take_profit * (1 - Config.TRADING_FEE_RATE)  # TP after fees
            effective_sl = stop_loss * (1 + Config.TRADING_FEE_RATE)    # SL after fees

            # Check if trade is still profitable after fees
            potential_profit = (effective_tp - net_entry) / net_entry * 100
            potential_loss = (net_entry - effective_sl) / net_entry * 100
            rr_after_fees = potential_profit / potential_loss if potential_loss > 0 else 0

            if rr_after_fees < Config.RISK_REWARD_RATIO * 0.8:  # 20% tolerance for fees
                logger.info(f"🚫 Trade blocked for {pair}: R/R after fees too low ({rr_after_fees:.2f})")
                return

            logger.info(f"💰 Fee-aware: Entry={net_entry:,.0f}, TP={effective_tp:,.0f}, SL={effective_sl:,.0f}, R/R={rr_after_fees:.2f}")

            # DRY RUN: Simulate trade without executing real order
            if is_dry_run:
                try:
                    # Generate simulated order ID
                    import random
                    simulated_order_id = f"DRY-{random.randint(100000, 999999)}"

                    # Save to database as simulated trade
                    trade_id = self.db.add_trade(
                        user_id=user_id,
                        pair=pair,
                        trade_type='BUY',
                        price=current_price,
                        amount=amount,
                        total=total,
                        fee=0,
                        signal_source='auto',
                        ml_confidence=confidence,
                        notes=f'[DRY RUN] Simulated order_id: {simulated_order_id}'
                    )

                    # Set SL/TP monitoring for simulation (with partial take profit)
                    self.price_monitor.set_price_level(
                        user_id, trade_id, pair, current_price, 
                        stop_loss, take_profit_1, take_profit_2, amount
                    )

                    # Notify
                    text = f"""
🧪 **DRY RUN: SIMULATED TRADE** 🧪

📊 Pair: `{pair}`
💡 Action: **BUY** (SIMULATED)
💰 Price: `{Utils.format_price(current_price)}` IDR
📦 Amount: `{amount}`
💵 Total: `{Utils.format_currency(total)}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR (-2%)
🎯 Take Profit: `{Utils.format_price(take_profit)}` IDR (+5%)

🤖 Confidence: {confidence:.0%}
🆔 Trade ID: `{trade_id}`
📋 Order ID: `{simulated_order_id}`

⚠️ **This is a SIMULATION**
• No real money used
• No actual order placed
• For testing only

Use `/autotrade_status` to monitor
                    """
                    await self._broadcast_to_subscribers(pair, text)
                    logger.info(f"🧪 [DRY RUN] Simulated BUY for {pair}: {amount} @ {current_price}")
                except Exception as e:
                    logger.error(f"❌ [DRY RUN] Simulation error for {pair}: {e}")
            else:
                # REAL TRADE: Execute via Indodax API
                try:
                    # Security check: Verify API keys are configured
                    if not Config.IS_API_KEY_CONFIGURED:
                        logger.error(f"❌ Cannot execute real trade for {pair}: API keys not configured")
                        error_text = f"""
❌ **AUTO-TRADE BLOCKED**

Cannot execute real trade for {pair}:
• Indodax API keys not configured
• Set INDODAX_API_KEY and INDODAX_SECRET_KEY in .env

⚠️ Switch to dry-run mode: `/autotrade dryrun`
                        """
                        await self._broadcast_to_subscribers(pair, error_text)
                        return

                    from api.indodax_api import IndodaxAPI
                    indodax = IndodaxAPI()

                    # 📊 Split order execution (clean routing from app/execution/router.py)
                    if Config.SMART_ROUTING_ENABLED and ob:
                        routing_results = self._split_order(
                            pair, 'buy', amount, ob.get('bids', []), ob.get('asks', [])
                        )

                        if routing_results:
                            total_filled = sum(r.get('filled', 0) for r in routing_results if r)
                            avg_price = sum(r.get('avg_price', 0) * r.get('filled', 0) for r in routing_results if r) / total_filled if total_filled > 0 else current_price
                            order_id = routing_results[0].get('order_id', 'SPLIT-ORDER')

                            # Use avg filled price for database
                            current_price = avg_price
                            amount = total_filled
                            total = total_filled * avg_price
                        else:
                            # Fallback to single order
                            result = indodax.create_order(pair, 'buy', current_price, amount)
                            order_id = result.get('return', {}).get('order_id', 'N/A') if result and result.get('success') == 1 else 'N/A'
                    else:
                        # Single order execution
                        result = indodax.create_order(pair, 'buy', current_price, amount)
                        order_id = result.get('return', {}).get('order_id', 'N/A') if result and result.get('success') == 1 else 'N/A'

                    # Save to database (common for both split and single order)
                    if order_id and order_id != 'N/A':
                        trade_id = self.db.add_trade(
                            user_id=user_id,
                            pair=pair,
                            trade_type='BUY',
                            price=current_price,
                            amount=amount,
                            total=total,
                            fee=0,
                            signal_source='auto',
                            ml_confidence=confidence,
                            notes=f'Auto-trade order_id: {order_id}'
                        )

                        # Set SL/TP monitoring (with partial take profit)
                        self.price_monitor.set_price_level(
                            user_id, trade_id, pair, current_price,
                            stop_loss, take_profit_1, take_profit_2, amount
                        )

                        # Notify
                        text = f"""
🚨 **AUTO-TRADE EXECUTED** 🟢

📊 Pair: `{pair}`
💡 Action: **BUY**
💰 Price: `{Utils.format_price(current_price)}` IDR
📦 Amount: `{amount}`
💵 Total: `{Utils.format_currency(total)}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR (-2%)
🎯 Take Profit: `{Utils.format_price(take_profit)}` IDR (+5%)

🤖 Confidence: {confidence:.0%}
🆔 Trade ID: `{trade_id}`
📋 Order ID: `{order_id}`

Use `/autotrade_status` to monitor
                        """
                        await self._broadcast_to_subscribers(pair, text)
                        logger.info(f"✅ Auto-BUY executed for {pair}: {amount} @ {current_price}")
                    else:
                        logger.error(f"❌ Auto-trade order failed for {pair}: order_id={order_id}")
                except Exception as e:
                    logger.error(f"❌ Auto-trade execution error for {pair}: {e}")

        elif signal['recommendation'] in ['SELL', 'STRONG_SELL']:
            # 🚨 AUTO SELL EXECUTION
            # Check if user has open positions in this pair
            open_trades = self.db.get_open_trades(user_id)
            pair_trades = [t for t in open_trades if t['pair'] == pair]
            
            if pair_trades:
                logger.info(f"🔴 SELL signal for {pair} - {len(pair_trades)} open position(s) found, executing auto-sell")
                await self._execute_auto_sell(pair, signal, current_price, user_id, is_dry_run)
                
                # RL reward: positive reward for closing at profit, negative for loss
                if Config.RL_ENABLED and Config.RL_UPDATE_REWARD:
                    for trade in pair_trades:
                        trade_dict = dict(trade) if hasattr(trade, 'keys') else trade
                        entry = trade_dict.get('price', 0)
                        if entry > 0:
                            pnl_pct = ((current_price - entry) / entry) * 100
                            reward = pnl_pct / 100  # Normalize
                            mi_signal = 'NEUTRAL'
                            regime_data = self._detect_market_regime(pair)
                            state = self._rl_get_state(signal['ml_confidence'], regime_data.get('regime', 'RANGE'), mi_signal)
                            self._rl_update(state, 'SELL', reward)
                            logger.debug(f"🧠 RL updated: state={state}, action=SELL, reward={reward:.4f}")
            else:
                logger.info(f"⏸️ SELL signal for {pair} - no open position to sell")

        # 📊 Portfolio allocation summary (logged every cycle)
        if Config.PORTFOLIO_RISK_ADJUSTED:
            open_trades = self.db.get_open_trades(user_id)
            if open_trades:
                total_exposure = sum(t['total'] for t in open_trades if hasattr(t, 'get') or isinstance(t, dict))
                balance = self.db.get_balance(user_id)
                exposure_pct = (total_exposure / balance * 100) if balance > 0 else 0
                logger.info(f"📊 Portfolio exposure: {total_exposure:,.0f} IDR ({exposure_pct:.1f}%)")

    async def _analyze_market_intelligence(self, pair, current_price):
        """Analyze volume spike and orderbook pressure for market intelligence"""
        result = {
            'volume_spike': False,
            'volume_ratio': 1.0,
            'orderbook_pressure': 'NEUTRAL',
            'buy_sell_ratio': 1.0,
            'overall_signal': 'NEUTRAL'
        }
        
        try:
            # 1️ Volume Spike Detection
            if pair in self.historical_data and not self.historical_data[pair].empty:
                df = self.historical_data[pair]
                if len(df) >= 20:
                    current_volume = df['volume'].iloc[-1]
                    avg_volume = df['volume'].iloc[-20:].mean()
                    
                    if avg_volume > 0:
                        volume_ratio = current_volume / avg_volume
                        result['volume_ratio'] = round(volume_ratio, 2)
                        
                        # Volume spike if >1.5x average
                        if volume_ratio > 1.5:
                            result['volume_spike'] = True
                            logger.info(f"📊 Volume spike detected for {pair}: {volume_ratio:.2f}x")
            
            # 2️ Orderbook Pressure Analysis (with spoofing filter)
            try:
                orderbook = self.indodax.get_orderbook(pair, limit=20)
                if orderbook:
                    raw_bids = orderbook.get('bids', [])
                    raw_asks = orderbook.get('asks', [])
                    
                    # Update heatmap
                    self._update_heatmap(pair, raw_bids, raw_asks)
                    
                    # Apply spoofing filter
                    cleaned_bids, cleaned_asks, spoof_detected = self._detect_spoofing(pair, raw_bids, raw_asks)
                    result['spoof_detected'] = spoof_detected
                    
                    # Use cleaned orderbook for analysis
                    bids = cleaned_bids if cleaned_bids else raw_bids[:10]
                    asks = cleaned_asks if cleaned_asks else raw_asks[:10]
                    
                    # Calculate total buy/sell volume
                    total_bid_volume = sum(bid[0] * bid[1] for bid in bids) if bids else 0
                    total_ask_volume = sum(ask[0] * ask[1] for ask in asks) if asks else 0
                    
                    if total_bid_volume > 0 and total_ask_volume > 0:
                        buy_sell_ratio = total_bid_volume / total_ask_volume
                        result['buy_sell_ratio'] = round(buy_sell_ratio, 2)
                        
                        # Determine pressure
                        if buy_sell_ratio > 1.3:
                            result['orderbook_pressure'] = 'BULLISH'
                        elif buy_sell_ratio < 0.7:
                            result['orderbook_pressure'] = 'BEARISH'
                        else:
                            result['orderbook_pressure'] = 'NEUTRAL'
                            
                        logger.info(f"📊 Orderbook pressure for {pair}: {result['orderbook_pressure']} ({buy_sell_ratio:.2f}x)")
            except Exception as e:
                logger.warning(f"⚠️ Orderbook analysis failed for {pair}: {e}")
            
            # 3️ Overall market intelligence signal
            bullish_signals = 0
            if result['volume_spike']:
                bullish_signals += 1
            if result['orderbook_pressure'] == 'BULLISH':
                bullish_signals += 1

            if bullish_signals == 2:
                result['overall_signal'] = 'BULLISH'
            elif bullish_signals == 1:
                result['overall_signal'] = 'MODERATE'
            else:
                result['overall_signal'] = 'NEUTRAL'

            # 4️ Entry filter check
            if Config.MI_REQUIRE_BULLISH_FOR_ENTRY:
                result['passes_entry_filter'] = (result['overall_signal'] == 'BULLISH')
            elif Config.MI_ALLOW_MODERATE_ENTRY:
                result['passes_entry_filter'] = (result['overall_signal'] in ['BULLISH', 'MODERATE'])
            else:
                result['passes_entry_filter'] = True  # No filter

            logger.info(f"📊 Market intelligence for {pair}: Volume={result['volume_ratio']}x, OB={result['orderbook_pressure']}, Signal={result['overall_signal']}, Filter={'PASS' if result['passes_entry_filter'] else 'FAIL'}")
            
        except Exception as e:
            logger.error(f"❌ Error in market intelligence analysis for {pair}: {e}")
            result['passes_entry_filter'] = True  # Default to pass on error (don't block trades)

        return result

    async def _get_support_resistance_for_pair(self, pair):
        """Get support/resistance levels for a pair from historical data"""
        try:
            if pair not in self.historical_data or self.historical_data[pair].empty:
                return None

            df = self.historical_data[pair]
            if len(df) < 50:
                return None

            # Use support/resistance detector
            sr_data = self.sr_detector.detect_levels(df)

            if sr_data:
                logger.info(f"📊 S/R for {pair}: Support={sr_data.get('nearest_support')}, Resistance={sr_data.get('nearest_resistance')}")

            return sr_data

        except Exception as e:
            logger.error(f"❌ Error getting S/R for {pair}: {e}")
            return None

    def _detect_market_regime(self, pair):
        """
        Detect market regime: TREND, RANGE, or HIGH_VOLATILITY
        Returns dict with regime classification and metrics
        """
        result = {
            'regime': 'UNKNOWN',
            'volatility': 0.0,
            'trend_strength': 0.0,
            'trend_direction': 'NEUTRAL',
            'is_trending': False,
            'is_choppy': False,
            'is_high_vol': False
        }

        try:
            if pair not in self.historical_data or self.historical_data[pair].empty:
                return result

            df = self.historical_data[pair]
            if len(df) < 30:
                return result

            # 1. Volatility measurement (std of returns)
            returns = df['close'].pct_change().dropna()
            volatility = returns.std()
            result['volatility'] = round(volatility, 4)

            # 2. Trend measurement (price change over lookback period)
            current_price = df['close'].iloc[-1]
            lookback_price = df['close'].iloc[-20]
            trend_change = (current_price - lookback_price) / lookback_price
            result['trend_strength'] = round(trend_change, 4)

            # 3. Classify regime
            if volatility > Config.REGIME_VOLATILITY_THRESHOLD:
                result['regime'] = 'HIGH_VOLATILITY'
                result['is_high_vol'] = True
                result['trend_direction'] = 'UP' if trend_change > 0 else 'DOWN'
            elif abs(trend_change) > Config.REGIME_TREND_THRESHOLD:
                result['regime'] = 'TREND'
                result['is_trending'] = True
                result['trend_direction'] = 'UP' if trend_change > 0 else 'DOWN'
            else:
                result['regime'] = 'RANGE'
                result['is_choppy'] = True
                result['trend_direction'] = 'NEUTRAL'

            logger.info(f"📊 Regime for {pair}: {result['regime']} (vol={volatility:.4f}, trend={trend_change:.4f})")

        except Exception as e:
            logger.error(f"❌ Error detecting regime for {pair}: {e}")

        return result

    async def _execute_auto_sell(self, pair, signal, current_price, user_id, is_dry_run):
        """
        Execute auto SELL when SELL/STRONG_SELL signal is generated
        Checks if user has open positions in this pair and sells them
        """
        try:
            # Get all open trades for this pair
            open_trades = self.db.get_open_trades(user_id)
            pair_trades = [t for t in open_trades if t['pair'] == pair]

            if not pair_trades:
                logger.debug(f"⏸️ No open position for {pair}, skipping SELL")
                return

            for trade in pair_trades:
                trade_dict = dict(trade) if hasattr(trade, 'keys') else trade
                trade_id = trade_dict.get('id')
                entry_price = trade_dict.get('price', 0)
                amount = trade_dict.get('amount', 0)
                
                if amount <= 0:
                    logger.warning(f"⚠️ Invalid amount for trade {trade_id}: {amount}")
                    continue

                # Fetch fresh price for execution
                sell_price = current_price
                try:
                    fresh_ticker = self.indodax.get_ticker(pair)
                    if fresh_ticker:
                        sell_price = fresh_ticker['bid']  # Use bid price for selling
                        logger.info(f"🔄 Fresh sell price for {pair}: {sell_price}")
                except Exception:
                    logger.warning(f"⚠️ Failed to get fresh sell price for {pair}, using signal price")

                # Calculate P&L
                pnl = (sell_price - entry_price) * amount
                pnl_pct = ((sell_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

                # DRY RUN: Simulate sell
                if is_dry_run:
                    import random
                    simulated_order_id = f"DRY-SELL-{random.randint(100000, 999999)}"

                    # Close trade in database
                    self.db.close_trade(
                        trade_id=trade_id,
                        sell_price=sell_price,
                        sell_amount=amount,
                        order_id=simulated_order_id,
                        reason=f"Auto-SELL ({signal['recommendation']})"
                    )

                    # Remove from price monitoring
                    self.price_monitor.remove_price_level(user_id, trade_id)

                    text = f"""
🧪 **DRY RUN: SIMULATED SELL** 🧪

📊 Pair: `{pair}`
💡 Action: **SELL** (SIMULATED)
💰 Price: `{Utils.format_price(sell_price)}` IDR
📦 Amount: `{amount}`

📈 Entry: `{Utils.format_price(entry_price)}` IDR
📊 P&L: `{Utils.format_currency(pnl)}` ({pnl_pct:+.2f}%)

🤖 Signal: {signal['recommendation']}
🆔 Trade ID: `{trade_id}`

⚠️ **This is a SIMULATION**
• No real money involved
• No actual order placed
"""
                    await self._broadcast_to_subscribers(pair, text)
                    logger.info(f"🧪 [DRY RUN] Simulated SELL for {pair}: {amount} @ {sell_price}, P&L={pnl_pct:+.2f}%")

                else:
                    # REAL TRADE: Execute via Indodax API
                    if not Config.IS_API_KEY_CONFIGURED:
                        logger.error(f"❌ Cannot execute real sell for {pair}: API keys not configured")
                        return

                    result = self.indodax.create_order(pair, 'sell', sell_price, amount)

                    if result and result.get('success') == 1:
                        order_id = result.get('return', {}).get('order_id', 'N/A')

                        # Close trade in database
                        self.db.close_trade(
                            trade_id=trade_id,
                            sell_price=sell_price,
                            sell_amount=amount,
                            order_id=order_id,
                            reason=f"Auto-SELL ({signal['recommendation']})"
                        )

                        # Remove from price monitoring
                        self.price_monitor.remove_price_level(user_id, trade_id)

                        # Notify
                        text = f"""
🚨 **AUTO-TRADE EXECUTED** 🔴

📊 Pair: `{pair}`
💡 Action: **SELL**
💰 Price: `{Utils.format_price(sell_price)}` IDR
📦 Amount: `{amount}`

📈 Entry: `{Utils.format_price(entry_price)}` IDR
📊 P&L: `{Utils.format_currency(pnl)}` ({pnl_pct:+.2f}%)

🤖 Signal: {signal['recommendation']}
🆔 Trade ID: `{trade_id}`
📋 Order ID: `{order_id}`
"""
                        await self._broadcast_to_subscribers(pair, text)
                        logger.info(f"✅ Auto-SELL executed for {pair}: {amount} @ {sell_price}, P&L={pnl_pct:+.2f}%")
                    else:
                        logger.error(f"❌ Auto-sell order failed for {pair}: {result}")

        except Exception as e:
            logger.error(f"❌ Auto-sell execution error for {pair}: {e}")

    def _allocate_portfolio(self, pairs_scores: Dict[str, Dict]) -> Dict[str, float]:
        """
        Portfolio allocation dinamis - risk-adjusted scoring per pair
        Returns dict of {pair: allocation_percentage}
        """
        if not pairs_scores:
            return {}

        scores = {}
        for pair, data in pairs_scores.items():
            prob = data.get('prob', 0.5)
            vol = data.get('volatility', 0.01)
            regime = data.get('regime', 'RANGE')
            
            # Risk-adjusted score: prob / volatility
            score = prob / (vol + 0.001)
            
            # Regime penalty
            if regime == 'HIGH_VOLATILITY':
                score *= 0.5
            elif regime == 'TREND':
                score *= 1.2
            
            scores[pair] = max(score, 0.01)

        # Normalize to 100%
        total = sum(scores.values())
        if total == 0:
            return {}

        allocation = {}
        remaining = Config.PORTFOLIO_MAX_EXPOSURE_PCT
        
        for pair in scores:
            weight = scores[pair] / total
            alloc = remaining * weight
            # Cap per pair
            alloc = min(alloc, Config.PORTFOLIO_MAX_PER_PAIR_PCT)
            allocation[pair] = round(alloc, 4)

        # Re-normalize to not exceed max exposure
        total_alloc = sum(allocation.values())
        if total_alloc > Config.PORTFOLIO_MAX_EXPOSURE_PCT:
            scale = Config.PORTFOLIO_MAX_EXPOSURE_PCT / total_alloc
            allocation = {k: round(v * scale, 4) for k, v in allocation.items()}

        return allocation

    def _rl_get_state(self, prob: float, regime: str, mi_signal: str) -> str:
        """Convert market conditions to RL state string"""
        prob_bucket = 'high' if prob > 0.7 else ('med' if prob > 0.5 else 'low')
        return f"{prob_bucket}_{regime}_{mi_signal}"

    def _rl_choose_action(self, state: str) -> str:
        """RL action selection with epsilon-greedy"""
        import numpy as np
        
        if state not in self.rl_q_table:
            self.rl_q_table[state] = {a: 0.0 for a in self.rl_actions}
        
        # Epsilon-greedy exploration
        if np.random.random() < Config.RL_EPSILON:
            return np.random.choice(self.rl_actions)
        
        # Exploit best known action
        return max(self.rl_q_table[state], key=self.rl_q_table[state].get)

    def _rl_update(self, state: str, action: str, reward: float):
        """Update Q-value for state-action pair"""
        if state not in self.rl_q_table:
            self.rl_q_table[state] = {a: 0.0 for a in self.rl_actions}
        
        old_q = self.rl_q_table[state].get(action, 0.0)
        max_next_q = max(self.rl_q_table[state].values()) if self.rl_q_table[state] else 0.0
        
        # Q-learning update rule
        new_q = old_q + Config.RL_LEARNING_RATE * (
            reward + Config.RL_DISCOUNT_FACTOR * max_next_q - old_q
        )
        self.rl_q_table[state][action] = new_q

    def _detect_spoofing(self, pair: str, bids: list, asks: list) -> tuple:
        """
        Spoofing detection - filter fake orderbook walls
        Returns (cleaned_bids, cleaned_asks, spoof_detected)
        """
        if not Config.SPOOFING_ENABLED:
            return bids[:10], asks[:10], False

        if pair not in self.spoof_tracker:
            self.spoof_tracker[pair] = {}

        current_levels = []
        
        # Track bid levels
        for price, vol in bids[:10]:
            price_f = float(price)
            vol_f = float(vol)
            price_key = round(price_f, -3)  # Group by thousands
            
            if price_key not in self.spoof_tracker[pair]:
                self.spoof_tracker[pair][price_key] = {'vol': vol_f, 'seen': 1, 'type': 'bid'}
            else:
                self.spoof_tracker[pair][price_key]['seen'] += 1
                self.spoof_tracker[pair][price_key]['vol'] = vol_f
            
            current_levels.append(price_key)
        
        # Track ask levels
        for price, vol in asks[:10]:
            price_f = float(price)
            vol_f = float(vol)
            price_key = round(price_f, -3)
            
            if price_key not in self.spoof_tracker[pair]:
                self.spoof_tracker[pair][price_key] = {'vol': vol_f, 'seen': 1, 'type': 'ask'}
            else:
                self.spoof_tracker[pair][price_key]['seen'] += 1
                self.spoof_tracker[pair][price_key]['vol'] = vol_f
            
            current_levels.append(price_key)

        # Clean: only keep levels seen enough times
        cleaned_bids = []
        cleaned_asks = []
        spoof_detected = False

        prices_to_remove = []
        for price_key, data in self.spoof_tracker[pair].items():
            if data['seen'] >= Config.SPOOFING_MIN_PERSISTENCE:
                # Real wall
                if data['type'] == 'bid':
                    cleaned_bids.append((price_key, data['vol']))
                else:
                    cleaned_asks.append((price_key, data['vol']))
            else:
                spoof_detected = True
                # Mark for removal if too old
                if data['seen'] < 2:
                    prices_to_remove.append(price_key)
        
        # Clean up stale entries
        for pk in prices_to_remove:
            if pk in self.spoof_tracker.get(pair, {}):
                del self.spoof_tracker[pair][pk]

        if spoof_detected:
            logger.info(f"🚨 Spoofing detected for {pair}: {len(prices_to_remove)} fake walls removed")

        return (cleaned_bids[:10], cleaned_asks[:10], spoof_detected)

    def _update_heatmap(self, pair: str, bids: list, asks: list):
        """Update heatmap liquidity data for a pair"""
        if not Config.HEATMAP_ENABLED:
            return
        
        if pair not in self.heatmap_data:
            self.heatmap_data[pair] = []

        snapshot = {
            'time': time.time(),
            'bids': [(float(p), float(v)) for p, v in bids[:15]],
            'asks': [(float(p), float(v)) for p, v in asks[:15]]
        }

        self.heatmap_data[pair].append(snapshot)
        
        # Keep only last N snapshots
        if len(self.heatmap_data[pair]) > Config.HEATMAP_MAX_SNAPSHOTS:
            self.heatmap_data[pair] = self.heatmap_data[pair][-Config.HEATMAP_MAX_SNAPSHOTS:]

    def _find_liquidity_zones(self, pair: str) -> list:
        """Find top liquidity zones from heatmap data"""
        if pair not in self.heatmap_data or not self.heatmap_data[pair]:
            return []

        levels = {}
        rounding = Config.HEATMAP_PRICE_ROUNDING

        for snap in self.heatmap_data[pair]:
            for price, vol in snap['bids'] + snap['asks']:
                key = round(price, -len(str(rounding)) + 1) if rounding > 0 else round(price)
                key = int(key)
                levels[key] = levels.get(key, 0) + vol

        # Sort by volume, return top zones
        zones = sorted(levels.items(), key=lambda x: x[1], reverse=True)
        return zones[:Config.HEATMAP_TOP_ZONES]

    def _smart_order_routing(self, pair: str, side: str, total_size: float, 
                              bids: list, asks: list) -> list:
        """
        Smart order routing - split order into chunks with adaptive pricing
        Returns list of (price, size) tuples
        """
        if not Config.SMART_ROUTING_ENABLED:
            if side == 'buy' and asks:
                return [(float(asks[0][0]), total_size)]
            elif side == 'sell' and bids:
                return [(float(bids[0][0]), total_size)]
            return [(0, total_size)]

        chunks = Config.SMART_ROUTING_CHUNKS
        size_per_chunk = total_size / chunks
        results = []

        for i in range(chunks):
            if side == 'buy':
                if i < len(asks):
                    best_ask = float(asks[i][0])
                    # Try to get better price
                    improved_price = best_ask * (1 - Config.SMART_ROUTING_PRICE_IMPROVEMENT)
                    results.append((improved_price, size_per_chunk))
            else:  # sell
                if i < len(bids):
                    best_bid = float(bids[i][0])
                    improved_price = best_bid * (1 + Config.SMART_ROUTING_PRICE_IMPROVEMENT)
                    results.append((improved_price, size_per_chunk))

        return results

    def _elite_signal(self, df, bids, asks, zones) -> tuple:
        """
        Elite signal from app/strategy/signal.py - cleaner logic
        Combines: probability (MA-based), orderbook imbalance, liquidity zones
        Returns (signal, probability, imbalance)
        """
        if df.empty or len(df) < 10:
            return 'HOLD', 0.5, 'NEUTRAL'

        current_price = df['close'].iloc[-1]
        ma10 = df['close'].rolling(10).mean().iloc[-1]

        # 1. Probability: price vs MA
        probability = 0.7 if current_price > ma10 else 0.3

        # 2. Orderbook imbalance (top 5 levels)
        bid_vol = sum(float(x[1]) for x in (bids or [])[:5])
        ask_vol = sum(float(x[1]) for x in (asks or [])[:5])
        imbalance = 'BUY' if bid_vol > ask_vol else 'SELL'

        # 3. Liquidity zone bounce
        if zones:
            nearest_zone = zones[0][0]
            distance_pct = abs(current_price - nearest_zone) / current_price

            if distance_pct < Config.ELITE_SIGNAL_IMBALANCE_DISTANCE:
                # Price near liquidity zone → zone bounce signal
                if imbalance == 'BUY':
                    return 'BUY', probability, imbalance
                else:
                    return 'SELL', probability, imbalance

        # 4. Standard signal
        if imbalance == 'BUY' and probability > Config.ELITE_SIGNAL_PROB_THRESHOLD:
            return 'BUY', probability, imbalance
        if imbalance == 'SELL' and probability < (1 - Config.ELITE_SIGNAL_PROB_THRESHOLD):
            return 'SELL', probability, imbalance

        return 'HOLD', probability, imbalance

    def _split_order(self, pair: str, side: str, total_size: float,
                     bids: list, asks: list) -> list:
        """
        Clean split order execution from app/execution/router.py
        Splits order into chunks with progressive pricing
        Returns list of execution results
        """
        chunks = Config.SMART_ROUTING_CHUNKS
        size_per_chunk = total_size / chunks
        results = []

        for i in range(chunks):
            if side == 'BUY':
                if i < len(asks):
                    price = float(asks[i][0])
                else:
                    price = float(asks[-1][0]) if asks else 0
            else:  # SELL
                if i < len(bids):
                    price = float(bids[i][0])
                else:
                    price = float(bids[-1][0]) if bids else 0

            if price <= 0:
                logger.warning(f"⚠️ Invalid price for chunk {i} of {pair}")
                continue

            result = self._execute_single_order(pair, side, price, size_per_chunk)
            if result:
                results.append(result)

        return results

    def _execute_single_order(self, pair: str, side: str, price: float, size: float) -> dict:
        """Execute a single order (for split order routing)"""
        try:
            if Config.AUTO_TRADE_DRY_RUN:
                logger.info(f"[DRY RUN] {side} {pair} {size} @ {price:,.0f}")
                return {'filled': size, 'avg_price': price, 'status': 'simulated'}

            result = self.indodax.create_order(pair, side.lower(), price, size)
            if result and result.get('success') == 1:
                order_id = result.get('return', {}).get('order_id', 'N/A')
                filled = result.get('return', {}).get('receive', size)
                return {'filled': filled, 'avg_price': price, 'order_id': order_id, 'status': 'filled'}
            else:
                logger.error(f"❌ Order failed for {pair}: {result}")
                return None
        except Exception as e:
            logger.error(f"❌ Order execution error for {pair}: {e}")
            return None

    def _fee_aware_net_price(self, price: float, side: str) -> tuple:
        """
        Fee-aware net price calculation from app/execution/risk.py
        Returns (net_entry_price, net_exit_price, round_trip_fee_pct)
        """
        fee = Config.TRADING_FEE_RATE

        if side == 'BUY':
            net_entry = price * (1 + fee)  # You pay more when buying
            net_exit = price * (1 - fee)   # You get less when selling
        else:  # SELL
            net_entry = price * (1 - fee)  # You get less when selling
            net_exit = price * (1 + fee)   # You pay more when buying back

        round_trip_fee = fee * 2  # Entry + exit
        return net_entry, net_exit, round_trip_fee

    async def _broadcast_to_subscribers(self, pair, message):
        """Send message to all users watching this pair"""
        pair_escaped = self._escape_markdown(pair)
        # Escape pair in message if it contains the unescaped version
        message_escaped = message.replace(f"`{pair}`", f"`{pair_escaped}`").replace(f"**{pair}**", f"**{pair_escaped}**")
        
        for user_id, pairs in self.subscribers.items():
            if pair in pairs:
                try:
                    await self.app.bot.send_message(
                        chat_id=user_id,
                        text=message_escaped,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error sending to user {user_id}: {e}")
    
    # =============================================================================
    # WEBSOCKET HANDLERS
    # =============================================================================
    
    def _on_ws_connect(self):
        """Callback when WebSocket connects"""
        self.ws_connected = True
        logger.info("✅ WebSocket connected to Indodax")

        # Subscribe to all watched pairs
        all_pairs = set(p for pairs in self.subscribers.values() for p in pairs)
        for pair in all_pairs:
            self._subscribe_pair(pair)
    
    def _on_ws_message(self, data: Dict):
        """Handle incoming WebSocket messages from Indodax"""
        try:
            # Skip subscription confirmations
            if 'result' in data and 'channel' in data.get('result', {}):
                channel = data['result']['channel']
                logger.debug(f"📨 Channel update from {channel}")
                
                # Extract data from Indodax format: result.data.data
                if 'data' in data['result']:
                    ws_data = data['result']['data'].get('data', [])
                    
                    # Handle chart:tick-<pair> channel (ticker updates)
                    if 'chart:tick-' in channel:
                        pair = channel.replace('chart:tick-', '').upper() + '/IDR'
                        logger.debug(f"📊 Processing ticker update for {pair}")
                        
                        if ws_data and len(ws_data) > 0:
                            # Chart data format: [[epoch, sequence, price, volume], ...]
                            latest = ws_data[-1]  # Get latest candle
                            if isinstance(latest, list) and len(latest) >= 4:
                                epoch = latest[0]
                                price = float(latest[2])
                                volume = float(latest[3])
                                
                                # Update price cache
                                self.price_data[pair] = {
                                    'last': price,
                                    'volume': volume,
                                    'change_percent': 0,  # Will calculate later
                                    'timestamp': datetime.fromtimestamp(int(epoch))
                                }
                                logger.info(f"📊 Updated {pair} ticker: {price}")
                                
                                # Process this data
                                self._process_price_update(pair, self.price_data[pair])
                    
                    # Handle market:trade-activity-<pair> channel
                    elif 'market:trade-activity-' in channel:
                        pair = channel.replace('market:trade-activity-', '').upper() + '/IDR'
                        logger.debug(f"📊 Processing trade activity for {pair}")
                        
                        if ws_data and len(ws_data) > 0:
                            # Trade activity format: [[pair, epoch, sequence, side, price, idr_vol, coin_vol], ...]
                            latest_trade = ws_data[-1]
                            if isinstance(latest_trade, list) and len(latest_trade) >= 7:
                                # trade_pair = latest_trade[0]  # Unused
                                epoch = int(latest_trade[1])
                                side = latest_trade[3]  # "buy" or "sell"
                                price = float(latest_trade[4])
                                # idr_volume = float(latest_trade[5])  # Unused
                                coin_volume = float(latest_trade[6])
                                
                                # Update price cache
                                self.price_data[pair] = {
                                    'last': price,
                                    'volume': coin_volume,
                                    'change_percent': 0,
                                    'side': side,
                                    'timestamp': datetime.fromtimestamp(epoch)
                                }
                                logger.info(f"✅ Updated {pair} trade: {price} ({side})")
                                
                                # Process this data
                                self._process_price_update(pair, self.price_data[pair])
            
            # Log raw messages for debugging (first 200 chars)
            elif 'id' not in data:  # Not a subscription confirmation
                raw_str = str(data)[:200]
                logger.debug(f"📨 Raw WS data: {raw_str}")
                
        except Exception as e:
            logger.error(f"Error handling WS message: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
    
    def _process_price_update(self, pair, price_data):
        """Process price update from WebSocket (common logic)"""
        try:
            current_price = price_data['last']
            
            # Update historical data for ML
            self._update_historical_data(pair, price_data)

            # Save to database
            self.db.save_price(pair, {
                'timestamp': price_data['timestamp'],
                'open': current_price,
                'high': current_price,
                'low': current_price,
                'close': current_price,
                'volume': price_data.get('volume', 0)
            })

            # Check SL/TP levels for notifications
            self._create_background_task(self.price_monitor.check_price_levels(pair, current_price))

            # Check for trading opportunities if auto-trading enabled
            if self.is_trading:
                self._create_background_task(self._check_trading_opportunity(pair))

            # Monitor for strong signals (send notifications for ALL watched pairs)
            self._create_background_task(self._monitor_strong_signal(pair))

            # Broadcast price update to subscribers (with throttling)
            if pair in self.last_price_update:
                if datetime.now() - self.last_price_update[pair] < timedelta(seconds=30):
                    return  # Throttle updates
            self.last_price_update[pair] = datetime.now()

            # Send update to subscribers
            self._create_background_task(self._send_price_update(pair))
            
        except Exception as e:
            logger.error(f"Error processing price update for {pair}: {e}")
    
    def _update_historical_data(self, pair, price_data):
        """Update in-memory historical data with new price"""
        # MEMORY SAFEGUARD: Limit tracked pairs to prevent memory exhaustion on VPS
        # Each pair keeps ~200 candles × ~6 columns × 8 bytes = ~9.6KB per pair
        # 100 pairs = ~1MB total, safe for 4GB VPS
        MAX_TRACKED_PAIRS = 100  # Increased from 50 to support more pairs
        
        if pair not in self.historical_data and len(self.historical_data) >= MAX_TRACKED_PAIRS:
            # Only log at DEBUG level - this is normal when many pairs are polled
            logger.debug(f"⏭️ Max tracked pairs ({MAX_TRACKED_PAIRS}) reached. {pair} saved to DB only (not in-memory)")
            return

        new_candle = {
            'timestamp': price_data['timestamp'],
            'open': price_data['last'],
            'high': price_data['last'],
            'low': price_data['last'],
            'close': price_data['last'],
            'volume': price_data['volume']
        }

        if pair in self.historical_data:
            new_df = pd.DataFrame([new_candle])
            self.historical_data[pair] = pd.concat(
                [self.historical_data[pair], new_df],
                ignore_index=True
            ).tail(200)  # Keep last 200 candles (~16min at 5s interval)
        else:
            self.historical_data[pair] = pd.DataFrame([new_candle])
    
    async def _send_price_update(self, pair):
        """Send price update to subscribers"""
        if pair not in self.price_data:
            return

        data = self.price_data[pair]
        change_pct = data.get('change_percent', 0)
        change_sign = '+' if change_pct >= 0 else ''

        # Only send if change is significant (>0.5%)
        if abs(change_pct) < 0.5:
            return

        pair_escaped = self._escape_markdown(pair)
        message = f"""
⚡ **{pair_escaped} Price Update**

💰 `{Utils.format_price(data['last'])}` IDR
📈 `{change_sign}{change_pct:.2f}%`

⏰ {datetime.now().strftime('%H:%M:%S')}
        """

        await self._broadcast_to_subscribers(pair, message)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    # Create and run bot
    bot = AdvancedCryptoBot()
    bot.run()
