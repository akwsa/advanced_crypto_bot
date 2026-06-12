#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tujuan: Orchestrator utama bot trading Telegram (runtime, command handlers, integrasi modul).
# Caller: entrypoint eksekusi langsung `python3 bot.py`.
# Dependensi: core/*, analysis/*, autotrade/*, autohunter/*, signals/*, workers/*, bot_parts/*.
# Main Functions: class AdvancedCryptoBot dan command handlers publik.
# Side Effects: DB read/write, HTTP API call (Indodax/Telegram), background thread/task, cache state mutation.
"""
🤖 Advanced Crypto Trading Bot
🔗 Indodax WebSocket + Telegram + Machine Learning
📊 Real-time signals, auto-trading, risk management
"""

import asyncio
import json
import os
import threading
import time
import subprocess
import warnings
import requests
from datetime import datetime, timedelta
from html import escape as html_escape

from core.telegram_html import sanitize_telegram_html, escape_telegram_html
from typing import Dict, List

# Suppress sklearn internal parallel warning (floods terminal)
warnings.filterwarnings('ignore', message=r'.*sklearn\.utils\.parallel\.delayed.*')

# Telegram
from telegram import BotCommand, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
from core.handler_registry import register_bot_handlers

# Local modules - API
from api.indodax_api import IndodaxAPI

# Local modules - Analysis
from analysis.technical_analysis import TechnicalAnalysis
from analysis.ml_model import MLTradingModel
from analysis.ml_model_v2 import MLTradingModelV2  # NEW: Improved ML model V2
from analysis.ml_model_v3 import MLTradingModelV3, create_model as create_ml_v3  # PRO: ML model V3 with backtesting
from analysis.ml_model_v4 import MLTradingModelV4  # NEW: Trade outcome based ML V4
from analysis.ml_signal_trainer import SignalOutcomeLabeler, train_model_from_signals  # NEW: Signal outcome labeling
from analysis.signal_analyzer import SignalAnalyzer  # NEW: Signal Quality Analyzer
from analysis.support_resistance import SupportResistanceDetector  # NEW: S/R Level Detection
from analysis.analyze_signals import AnalyzeSignals  # NEW: Quick BUY/SELL analysis

# Local modules - Trading
from autotrade.trading_engine import TradingEngine
from autotrade.risk_manager import RiskManager
from autotrade.portfolio import Portfolio
from autotrade.price_monitor import PriceMonitor
from autotrade.runtime import (
    analyze_market_intelligence,
    check_trading_opportunity,
    detect_market_regime,
    execute_auto_sell,
    get_support_resistance_for_pair,
    monitor_strong_signal,
    process_price_update_signal_tasks,
)
from scalper.scalper_module import ScalperModule  # Scalper integration
from autohunter.smart_hunter_integration import SmartHunterBotIntegration  # Smart Hunter integration
from autohunter.ultra_hunter_integration import UltraHunterBotIntegration  # Ultra Hunter integration

# Local modules - Signals
from signals.signal_quality_engine import SignalQualityEngine  # NEW: Signal Quality Engine V3
from signals.signal_queue import signal_queue, scheduler  # Phase 4: Signal Queue + Scheduler
from signals.signal_pipeline import generate_signal_for_pair
from signals.signal_formatter import (
    format_market_scan_signal,
    format_signal_message,
    format_signal_message_html,
    generate_strength_bar,
    generate_strength_bar_html,
)
from signals.near_miss import build_near_miss_summary, format_near_miss_report_html

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
from bot_parts.formatting import (
    build_signal_overview_html,
    format_signal_list_price,
    format_signal_scan_line_html,
    format_signal_section_html,
    signal_visual,
)
from bot_parts.command_texts import (
    TELEGRAM_BOT_COMMANDS,
    build_commands_text,
    build_help_html,
    build_main_menu_html,
    build_menu_section_html,
    build_menu_markdown,
    build_start_html,
)
from bot_parts.admin_panels import (
    build_admin_panel_markup,
    build_admin_panel_text,
)
from bot_parts.dashboard_heartbeat import start_bot_heartbeat_thread
from bot_parts.telegram_keyboards import (
    build_android_reply_keyboard,
    build_menu_panel_keyboard,
    build_quick_keyboard,
)
from bot_parts.charts import build_signal_chart_image
from bot_parts.microstructure import (
    detect_spoofing,
    elite_signal,
    execute_single_order,
    fee_aware_net_price,
    find_liquidity_zones,
    smart_order_routing,
    split_order,
    update_heatmap,
)
from bot_parts.state_sync import (
    clear_watchlist_in_db,
    load_watchlist_from_db,
    preload_historical_data,
    remove_watchlist_from_db,
    sync_watchlist_to_db,
)

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
        self._logger = logger

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

        # NEW: ML Model V4 (Trade outcome based)
        self.ml_model_v4 = None
        try:
            self.ml_model_v4 = MLTradingModelV4()
            if self.ml_model_v4.is_fitted:
                logger.info("✅ ML Model V4 loaded (trade outcome based)")
            else:
                logger.info("⏳ ML Model V4 initialized but not yet trained — will attempt auto-train in background")
                # Auto-train V4 in background if not fitted but signal outcomes exist
                def _auto_train_v4():
                    try:
                        from analysis.ml_signal_trainer import train_model_from_signals
                        v4_success, v4_msg = train_model_from_signals(
                            self, tp_pct=3, sl_pct=2, window=10, days_back=30
                        )
                        if v4_success and getattr(self, '_last_signal_outcomes', None):
                            v4_train_success = self.ml_model_v4.train_from_outcomes(
                                self._last_signal_outcomes
                            )
                            if v4_train_success:
                                v4_status = self.ml_model_v4.get_status()
                                logger.info(
                                    f"✅ ML V4 auto-trained at startup: "
                                    f"win_rate={v4_status.get('win_rate'):.1%}, "
                                    f"profit_factor={v4_status.get('profit_factor'):.2f}"
                                )
                    except Exception as e:
                        logger.warning(f"⚠️ ML V4 auto-train at startup failed: {e}")
                threading.Thread(target=_auto_train_v4, daemon=True, name="V4-AutoTrain-Startup").start()
        except Exception as e:
            logger.warning(f"⚠️ Failed to load ML V4: {e}")

        self.trading_engine = TradingEngine(self.db, self.ml_model)
        self.risk_manager = RiskManager(self.db)
        self.portfolio_manager = Portfolio(self.db)  # FIX: renamed from self.portfolio to avoid name collision with portfolio() command handler
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
        self._heavy_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="HeavyDB")
        logger.info("✅ Heavy DB executor initialized (upgraded to 4 workers)")

        # Telegram setup with increased timeouts for unreliable networks
        self.app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN) \
            .post_init(self._post_init) \
            .connect_timeout(30.0) \
            .read_timeout(30.0) \
            .write_timeout(30.0) \
            .pool_timeout(30.0) \
            .get_updates_connect_timeout(30.0) \
            .get_updates_read_timeout(30.0) \
            .get_updates_write_timeout(30.0) \
            .get_updates_pool_timeout(30.0) \
            .build()

        # Telegram access control (default-deny)
        self.allowed_user_ids = set(getattr(Config, "ALLOWED_USER_IDS", [])) | set(getattr(Config, "ADMIN_IDS", []))
        self._load_telegram_access_control()

        # Initialize Scalper Module (use main bot's dry-run config + token + admin IDs)
        self.scalper = ScalperModule(
            self.app,
            admin_ids=Config.ADMIN_IDS,  # Pass admin IDs from main config
            is_standalone=False,
            use_main_bot_config=True,
            main_bot_config=Config,
            main_bot_token=Config.TELEGRAM_BOT_TOKEN,  # Pass main bot's token
            main_bot=self,  # Pass main bot reference for signal generation
            force_real_trading=True,
        )

        # Keep money automation locked to DRY RUN after Scalper is initialized.
        # Scalper no longer inherits AUTO_TRADE_DRY_RUN; AutoTrade/SmartHunter/
        # AutoHunter still do.
        self._enable_startup_dryrun_autotrade()

        # Cleanup broken DRY RUN trades with amount=0 (legacy bug, fixed 2026-06-07)
        self._cleanup_broken_dryrun_trades()

        # Rebuild SL/TP monitoring for open trades that survived restart
        self.price_monitor.rebuild_from_open_trades(self.db, self.trading_engine)

        # Initialize Smart Hunter Integration
        # Smart/Ultra Hunter must stay dry-run even though Scalper is real-only.
        self.smart_hunter = SmartHunterBotIntegration(
            main_bot=self,
            db=self.db,
            indodax_api=self.indodax,
            dry_run=True,
        )

        # Initialize Ultra Hunter Integration
        self.ultra_hunter = UltraHunterBotIntegration(
            main_bot=self,
            db=self.db,
            dry_run=True,
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

        # Trading state (preserve is_trading if already set by _enable_startup_dryrun_autotrade)
        if not hasattr(self, 'is_trading'):
            self.is_trading = False
        self.start_time = time.time()
        self.last_ml_update: Dict[str, datetime] = {}
        self.last_price_update: Dict[str, datetime] = {}

        # Background task tracking (for async tasks)
        self.background_tasks = set()
        self._signal_result_cache = {}
        self._signal_inflight_tasks = {}
        self._signal_generation_semaphore = threading.BoundedSemaphore(value=4)

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

        # ML V4 signal outcomes (populated by train_model_from_signals)
        self._last_signal_outcomes = None

        # Load auto-trade mode from database (persistent setting)
        self._load_auto_trade_mode()
        self._load_signal_notifications_mode()
        self._load_signal_notification_filter()

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

        # NEW: Initialize Adaptive Learning Engine
        try:
            from analysis.adaptive_learning import AdaptiveLearningEngine
            self._adaptive_engine = AdaptiveLearningEngine(self.db)
            logger.info("🧠 Adaptive Learning Engine initialized")
        except Exception as e:
            logger.warning(f"⚠️ Adaptive Learning init failed: {e}")
            self._adaptive_engine = None

        # NEW: Start TMA Dashboard Server (legacy, port 8090 to avoid code-server conflict)
        try:
            from api.tma_server import start_tma_server
            tma_port = int(os.getenv("TMA_DASHBOARD_PORT", "8090"))
            self._tma_server = start_tma_server(self.db, port=tma_port)
            logger.info(f"📱 TMA Dashboard server started on http://0.0.0.0:{tma_port}")
        except Exception as e:
            logger.warning(f"⚠️ TMA server init failed: {e}")
            self._tma_server = None

        # NEW: Start FastAPI Dashboard (revamp v2 — port 8091)
        try:
            import uvicorn
            from dashboard_api.main import app as dashboard_app
            api_port = int(os.getenv("DASHBOARD_API_PORT", "8091"))

            def _run_dashboard_api():
                config = uvicorn.Config(
                    dashboard_app, host="0.0.0.0", port=api_port,
                    log_level="warning", access_log=False,
                )
                server = uvicorn.Server(config)
                server.run()

            threading.Thread(target=_run_dashboard_api, daemon=True, name="DashboardAPI").start()
            logger.info(f"🌐 Dashboard API v2 starting on http://0.0.0.0:{api_port}")
        except Exception as e:
            logger.warning(f"⚠️ Dashboard API v2 failed: {e}")

    def _load_watchlist_from_db(self) -> Dict[int, List[str]]:
        """Load watchlist from database on startup"""
        return load_watchlist_from_db(self)

    def _preload_historical_data(self):
        """Preload historical data from DB into memory at startup."""
        preload_historical_data(self)

    def _sync_watchlist_to_db(self, user_id: int, pair: str):
        """Sync single pair addition to database"""
        sync_watchlist_to_db(self, user_id, pair)

    def _remove_watchlist_from_db(self, user_id: int, pair: str):
        """Sync single pair removal from database"""
        remove_watchlist_from_db(self, user_id, pair)

    def _clear_watchlist_in_db(self, user_id: int = None):
        """Clear watchlist in database (for specific user or all)"""
        clear_watchlist_in_db(self, user_id)

    def _load_telegram_access_control(self):
        """Load persisted Telegram whitelist users into memory."""
        try:
            active_users = set(self.db.get_active_telegram_users())
            self.allowed_user_ids |= active_users
            logger.info(
                "🔐 Telegram access control loaded: %s allowed users (%s admin, %s active registered)",
                len(self.allowed_user_ids),
                len(getattr(Config, "ADMIN_IDS", [])),
                len(active_users),
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to load Telegram access control from DB: {e}")

    def _is_authorized(self, user_id: int, admin_only: bool = False) -> bool:
        """Return True if user is allowed to use the bot."""
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return False
        if admin_only:
            return user_id in set(getattr(Config, "ADMIN_IDS", []))
        return user_id in self.allowed_user_ids

    async def _deny_unauthorized(self, update, context, admin_only: bool = False):
        """Reject unauthorized Telegram updates with a minimal message."""
        user_id = getattr(getattr(update, "effective_user", None), "id", None)
        chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
        logger.warning(
            "🔒 Telegram access denied user=%s chat=%s admin_only=%s",
            user_id,
            chat_id,
            admin_only,
        )
        if update and getattr(update, "callback_query", None):
            try:
                await update.callback_query.answer("Unauthorized", show_alert=True)
            except Exception:
                pass
        await self._send_message(update, context, "❌ Access denied.")
        return False

    async def _require_authorized(self, update, context, admin_only: bool = False):
        """Gate helper for all Telegram handlers."""
        user = getattr(update, "effective_user", None)
        chat = getattr(update, "effective_chat", None)
        user_id = getattr(user, "id", None)
        if chat is not None and getattr(chat, "type", None) != "private":
            return await self._deny_unauthorized(update, context, admin_only=admin_only)
        if not self._is_authorized(user_id, admin_only=admin_only):
            return await self._deny_unauthorized(update, context, admin_only=admin_only)
        try:
            if user_id is not None:
                self.db.upsert_telegram_user(
                    user_id,
                    username=getattr(user, "username", None),
                    first_name=getattr(user, "first_name", None),
                    role="admin" if user_id in set(getattr(Config, "ADMIN_IDS", [])) else "user",
                    is_active=1,
                )
        except Exception as e:
            logger.debug(f"Telegram user upsert skipped: {e}")
        return True

    def _normalize_pair_key(self, pair: str) -> str:
        """Normalize pair names for runtime state comparisons."""
        return str(pair or "").lower().replace("/", "").replace("_", "")

    def _select_top_volume_pairs(self, tickers, limit: int = 50, min_volume_idr: float = 500_000_000):
        """Return highest-volume official IDR tickers above the configured minimum volume."""
        selected = []
        for ticker in tickers or []:
            if not isinstance(ticker, dict):
                continue
            pair_key = self._normalize_pair_key(ticker.get("pair"))
            if not pair_key.endswith("idr"):
                continue
            try:
                volume_idr = float(ticker.get("volume", 0) or 0)
            except (TypeError, ValueError):
                continue
            if volume_idr <= float(min_volume_idr):
                continue
            normalized_ticker = dict(ticker)
            normalized_ticker["pair"] = pair_key
            normalized_ticker["volume"] = volume_idr
            selected.append(normalized_ticker)

        selected.sort(key=lambda x: float(x.get("volume", 0) or 0), reverse=True)
        return selected[:limit]

    async def _refresh_watchlist_from_top_volume(
        self,
        user_id: int,
        limit: int = 33,
        min_volume_idr: float = 500_000_000,
    ):
        """Refresh user's watchlist: fetch top-volume IDR pairs from Indodax,
        deactivate pairs below threshold, activate top pairs.
        
        Called by:
        - /refresh_watchlist Telegram command (manual refresh)
        - _enable_startup_dryrun_autotrade (auto-refresh on bot restart)
        - autotrade() dryrun activation
        
        Returns dict with summary: {active_count, new_pairs, deactivated_count, top_pairs}
        """
        result = {
            "active_count": 0,
            "new_pairs": [],
            "deactivated_count": 0,
            "top_pairs": [],
            "error": None,
        }
        
        if not getattr(self, "indodax", None):
            result["error"] = "Indodax API client tidak tersedia"
            return result
        
        try:
            # 1. Fetch real-time ticker data dari Indodax
            tickers = self.indodax.get_all_tickers()
            if not tickers:
                result["error"] = "Gagal fetch data dari Indodax (response kosong)"
                return result
            
            # 2. Select top N pairs by IDR volume above threshold
            selected = self._select_top_volume_pairs(
                tickers,
                limit=limit,
                min_volume_idr=min_volume_idr,
            )
            
            top_pairs = [item["pair"] for item in selected]
            top_volumes = {item["pair"]: item["volume"] for item in selected}
            
            # 3. Get current active pairs before refresh
            old_pairs = set(self.db.get_watchlist(user_id))
            new_pair_set = set(top_pairs)
            
            # 4. Bulk upsert: deactivate all old, activate new top pairs
            deactivated, activated = self.db.bulk_upsert_watchlist(user_id, top_pairs)
            
            # 5. Determine truly new pairs (weren't in old watchlist)
            truly_new = [p for p in top_pairs if p not in old_pairs]
            
            # 6. Sync subscribers list (in-memory) for consistency
            if user_id not in self.subscribers:
                self.subscribers[user_id] = []
            self.subscribers[user_id] = list(top_pairs)
            
            # 7. Auto-sync ke auto_trade_pairs jika autotrade sedang aktif
            if self.is_trading and hasattr(self, "auto_trade_pairs") and self.auto_trade_pairs is not None:
                self.auto_trade_pairs[user_id] = list(top_pairs)
                logger.info(
                    "🔄 Auto-trade pairs synced after watchlist refresh: %d pairs",
                    len(top_pairs),
                )
            
            result.update({
                "active_count": activated,
                "new_pairs": truly_new,
                "deactivated_count": deactivated,
                "top_pairs": top_pairs,
                "top_volumes": top_volumes,
            })
            
            logger.info(
                "🔄 Watchlist refreshed for user %d: %d active (was %d), %d new, "
                "%d deactivated. Top pair: %s (Vol: %.0f IDR)",
                user_id, activated, deactivated, len(truly_new),
                deactivated - activated if deactivated > activated else 0,
                top_pairs[0] if top_pairs else "N/A",
                top_volumes.get(top_pairs[0], 0) if top_pairs else 0,
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to refresh watchlist for user {user_id}: {e}")
            result["error"] = str(e)
        
        return result

    async def register_access(self, update, context):
        """Register a Telegram user with the configured invite code."""
        user = getattr(update, "effective_user", None)
        user_id = getattr(user, "id", None)
        if user_id in set(getattr(Config, "ADMIN_IDS", [])):
            self.allowed_user_ids.add(user_id)
            self.db.register_telegram_user(
                user_id,
                username=getattr(user, "username", None),
                first_name=getattr(user, "first_name", None),
                role="admin",
                invite_code="admin",
            )
            await self._send_message(update, context, "✅ Admin sudah terdaftar.")
            return

        invite_code = getattr(Config, "TELEGRAM_INVITE_CODE", "")
        provided_code = (context.args[0].strip() if getattr(context, "args", None) else "")
        if not invite_code or provided_code != invite_code:
            logger.warning("🔒 Telegram registration rejected user=%s", user_id)
            await self._send_message(update, context, "❌ Kode registrasi tidak valid.")
            return

        self.allowed_user_ids.add(user_id)
        self.db.register_telegram_user(
            user_id,
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            role="user",
            invite_code="used",
        )
        await self._send_message(update, context, "✅ Registrasi berhasil. Akses bot sudah aktif.")


    def _collect_normalized_training_data(
        self,
        pairs_to_check=None,
        limit: int = 2000,
        min_candles: int = 100,
        include_small_groups: bool = True,
        include_zero_summary: bool = True,
    ):
        """
        Collect price history for ML training with pair-name normalization.

        Variants such as BTCIDR, btcidr, BTC_IDR, and BTC/IDR are grouped
        under one canonical key before they are displayed or passed to ML.
        """
        normalized_groups = {}

        def add_pair(raw_pair):
            raw_pair = str(raw_pair or "").strip()
            norm_pair = self._normalize_pair_key(raw_pair)
            if norm_pair:
                normalized_groups.setdefault(norm_pair, set()).add(raw_pair)

        db_pairs = []
        try:
            db_pairs = self.db.get_all_pairs()
        except Exception as e:
            logger.debug(f"Could not load DB pairs for retrain normalization: {e}")

        if pairs_to_check is None:
            for pair in db_pairs:
                add_pair(pair)

            try:
                watchlists = self.db.get_all_watchlists()
                for pairs in watchlists.values():
                    for pair in pairs:
                        add_pair(pair)
            except Exception as e:
                logger.debug(f"Could not load watchlist pairs for retrain normalization: {e}")

        else:
            for pair in pairs_to_check:
                add_pair(pair)

            wanted_norms = set(normalized_groups)
            for pair in db_pairs:
                if self._normalize_pair_key(pair) in wanted_norms:
                    add_pair(pair)

        if not normalized_groups:
            for pair in Config.WATCH_PAIRS:
                add_pair(pair)

        data_frames = []
        pairs_with_data = []

        for norm_pair in sorted(normalized_groups):
            variant_frames = []
            variants = sorted(normalized_groups[norm_pair], key=lambda p: str(p).lower())

            for variant in variants:
                df = self.db.get_price_history(variant, limit=limit)
                if df is None or df.empty:
                    continue

                normalized_df = df.copy()
                normalized_df["pair"] = norm_pair
                variant_frames.append(normalized_df)

            if not variant_frames:
                if include_zero_summary:
                    pairs_with_data.append(f"• `{norm_pair.upper()}`: 0 candles")
                continue

            combined_df = pd.concat(variant_frames, ignore_index=True)
            if "timestamp" in combined_df.columns:
                combined_df = combined_df.sort_values("timestamp")
                combined_df = combined_df.drop_duplicates(subset=["timestamp"], keep="last")

            candle_count = len(combined_df)
            if include_small_groups or candle_count >= min_candles:
                data_frames.append(combined_df)
                pairs_with_data.append(f"• `{norm_pair.upper()}`: {candle_count} candles")

                if len(variants) > 1:
                    logger.info(
                        "🔁 Normalized retrain pair %s from variants: %s",
                        norm_pair.upper(),
                        ", ".join(variants),
                    )
            elif candle_count > 0:
                logger.warning(f"⚠️  {norm_pair.upper()}: only {candle_count} candles (need {min_candles}+)")

        return data_frames, pairs_with_data

    def _runtime_keys_for_pair(self, mapping, pair: str):
        pair_norm = self._normalize_pair_key(pair)
        return [
            key for key in list(getattr(mapping, "keys", lambda: [])())
            if self._normalize_pair_key(key) == pair_norm
            or self._normalize_pair_key(key).startswith(pair_norm)
        ]

    def _get_active_signal_pairs(self):
        """Return pairs that are actively watched or configured for auto-trade."""
        active_pairs = []
        seen = set()
        for source in (self.subscribers, self.auto_trade_pairs):
            for pairs in source.values():
                for pair in pairs:
                    pair_norm = self._normalize_pair_key(pair)
                    if pair_norm and pair_norm not in seen:
                        seen.add(pair_norm)
                        active_pairs.append(pair_norm)
        return active_pairs

    def _cleanup_pair_runtime_state(self, pair: str, remove_auto_trade: bool = False, user_id: int = None):
        """Remove stale in-memory and queued signal state for a deleted pair."""
        pair_norm = self._normalize_pair_key(pair)
        if not pair_norm:
            return {"queue": 0, "auto_removed": 0}

        for mapping_name in (
            "price_data",
            "historical_data",
            "previous_signals",
            "last_ml_update",
            "last_price_update",
            "_signal_result_cache",
            "_last_signal_checks",
            "_notification_cooldown",
            "_last_scan_signals",
        ):
            mapping = getattr(self, mapping_name, None)
            if isinstance(mapping, dict):
                for key in self._runtime_keys_for_pair(mapping, pair_norm):
                    mapping.pop(key, None)

        inflight = getattr(self, "_signal_inflight_tasks", None)
        if isinstance(inflight, dict):
            for key in self._runtime_keys_for_pair(inflight, pair_norm):
                task = inflight.pop(key, None)
                if task and hasattr(task, "cancel"):
                    task.cancel()

        auto_removed = 0
        if remove_auto_trade:
            users = [user_id] if user_id is not None else list(self.auto_trade_pairs.keys())
            for uid in users:
                pairs = self.auto_trade_pairs.get(uid, [])
                kept_pairs = [p for p in pairs if self._normalize_pair_key(p) != pair_norm]
                auto_removed += len(pairs) - len(kept_pairs)
                if kept_pairs:
                    self.auto_trade_pairs[uid] = kept_pairs
                else:
                    self.auto_trade_pairs.pop(uid, None)

        queued_removed = 0
        queue = getattr(self, "signal_queue", None)
        if queue and hasattr(queue, "purge_pair"):
            try:
                queued_removed = queue.purge_pair(pair_norm) or 0
            except Exception as e:
                logger.debug(f"Signal queue purge skipped for {pair_norm}: {e}")

        logger.info(
            "🧹 Runtime state cleaned for %s (queued=%s, auto_removed=%s)",
            pair_norm,
            queued_removed,
            auto_removed,
        )
        return {"queue": queued_removed, "auto_removed": auto_removed}
    
    def run(self):
        """Start the bot with graceful shutdown handling"""
        logger.info("🚀 Starting Advanced Crypto Trading Bot...")

        # Global flag for clean shutdown
        self.shutdown_event = threading.Event()
        
        # Track background threads for cleanup
        self.background_threads = []

        # Register OS signal handlers for graceful shutdown (SIGTERM, SIGINT)
        import signal
        import atexit

        def _signal_handler(signum, frame):
            signame = signal.Signals(signum).name
            logger.info(f"🛑 Received {signame}, initiating graceful shutdown...")
            self._shutdown()
            # Exit program after shutdown completes
            import sys
            sys.exit(0)

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        def _atexit_handler():
            self._atexit_called = True
            if getattr(self, '_shutdown_in_progress', False):
                return
            try:
                self._shutdown()
            except Exception:
                pass

        atexit.register(_atexit_handler)
        logger.info("🛡️ Signal handlers registered (SIGTERM, SIGINT) and atexit cleanup enabled")

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

        # NEW: Publish lightweight bot heartbeat for the companion dashboard.
        # Best-effort only: Redis/dashboard failures must never crash trading.
        try:
            heartbeat_thread = start_bot_heartbeat_thread(
                self.state_manager,
                stop_event=self.shutdown_event,
            )
            self.background_threads.append(heartbeat_thread)
            logger.info("💓 Dashboard bot heartbeat started (Redis key: dashboard:bot:heartbeat)")
        except Exception as e:
            logger.debug(f"Dashboard heartbeat thread not started: {e}")

        # Start Telegram bot (polling or webhook based on config)
        if Config.WEBHOOK_ENABLED and Config.WEBHOOK_URL:
            logger.info("📱 Starting Telegram bot with WEBHOOK...")
            logger.info(f"🔗 Webhook URL: {Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}")
            logger.info(f"🌐 Listening on {Config.WEBHOOK_LISTEN}:{Config.WEBHOOK_PORT}")
            try:
                self.app.run_webhook(
                    listen=Config.WEBHOOK_LISTEN,
                    port=Config.WEBHOOK_PORT,
                    webhook_url=Config.WEBHOOK_URL + Config.WEBHOOK_PATH,
                    secret_token=Config.WEBHOOK_SECRET_TOKEN or None,
                    allowed_updates=Update.ALL_TYPES,
                )
            except Exception as e:
                logger.error(f"❌ Bot crashed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self._shutdown()
        else:
            logger.info("📱 Starting Telegram bot with POLLING...")
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
        Graceful shutdown with timeout.
        Stops all background threads, Telegram app, DB connections, and saves state.
        Designed to be safe even when called during Python interpreter teardown.
        """
        import time
        import asyncio

        def _safe_log(msg, level='info'):
            """Log safely during shutdown; suppress errors if logger is being torn down."""
            try:
                getattr(logger, level)(msg)
            except Exception:
                pass

        # Top-level safety net — never let an exception escape during shutdown
        try:
            # Prevent double-shutdown
            if getattr(self, '_shutdown_in_progress', False):
                _safe_log("⚠️ Shutdown already in progress, skipping duplicate call")
                return
            self._shutdown_in_progress = True

            _safe_log(f"🛑 Shutting down bot (timeout: {timeout}s)...")

            # Step 1: Set shutdown event
            self.shutdown_event.set()
            _safe_log("📴 Shutdown event set")

            # Step 2: Stop Telegram application gracefully
            try:
                if hasattr(self, 'app') and self.app and getattr(self.app, 'running', False):
                    _safe_log("📱 Stopping Telegram application...")

                    async def _stop_telegram():
                        await self.app.stop()
                        await self.app.shutdown()

                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(_stop_telegram())
                    except RuntimeError:
                        asyncio.run(_stop_telegram())
                    _safe_log("📱 Telegram application stopped")
                else:
                    _safe_log("📱 Telegram application already stopped (skipped)")
            except Exception as e:
                _safe_log(f"⚠️ Error stopping Telegram app: {e}", 'warning')

            # Step 3: Delete webhook if enabled
            try:
                if Config.WEBHOOK_ENABLED and hasattr(self, 'app') and self.app:
                    _safe_log("🧹 Deleting Telegram webhook...")

                    async def _delete_webhook():
                        await self.app.bot.delete_webhook(drop_pending_updates=True)

                    asyncio.run(_delete_webhook())
                    _safe_log("🧹 Webhook deleted")
            except Exception as e:
                _safe_log(f"⚠️ Error deleting webhook: {e}", 'warning')

            # Step 4: Stop scheduler
            try:
                if hasattr(self, 'task_scheduler'):
                    self.task_scheduler.stop()
                    _safe_log("📅 Scheduler stopped")
            except Exception as e:
                _safe_log(f"⚠️ Error stopping scheduler: {e}", 'warning')

            # Step 5: Stop async worker
            try:
                if hasattr(self, 'async_worker'):
                    self.async_worker.stop()
                    _safe_log("🔧 Async worker stopped")
            except Exception as e:
                _safe_log(f"⚠️ Error stopping async worker: {e}", 'warning')

            # Step 6: Wait for background threads (with timeout)
            start_time = time.time()
            for thread in self.background_threads:
                if thread.is_alive():
                    thread_name = thread.name or "unnamed"
                    _safe_log(f"⏳ Waiting for thread '{thread_name}'...")
                    thread.join(timeout=3)
                    if thread.is_alive():
                        _safe_log(f"⚠️ Thread '{thread_name}' didn't stop in time, skipping", 'warning')

            elapsed = time.time() - start_time
            _safe_log(f"⏱️ Thread cleanup took {elapsed:.1f}s")

            # Step 7: Stop heavy executor
            try:
                if hasattr(self, '_heavy_executor'):
                    self._heavy_executor.shutdown(wait=False, cancel_futures=True)
                    _safe_log("🧵 Heavy DB executor stopped")
            except Exception as e:
                _safe_log(f"⚠️ Error stopping heavy DB executor: {e}", 'warning')

            # Step 8: Close database connections explicitly
            try:
                if hasattr(self, 'db') and self.db:
                    if hasattr(self.db, 'close'):
                        self.db.close()
                        _safe_log("💾 Database connection closed")
                    else:
                        _safe_log("💾 Database connection will be closed automatically")
            except Exception as e:
                _safe_log(f"⚠️ Error closing database: {e}", 'warning')

            # Step 9: Final message
            total_elapsed = time.time() - start_time
            _safe_log(f"✅ Bot shutdown complete ({total_elapsed:.1f}s)")
            _safe_log("👋 Goodbye!")
        except Exception:
            # Absolute last resort — silently swallow anything that escapes
            pass

    def _start_redis_state_syncer(self):
        """Start background thread to sync state to Redis periodically"""
        def redis_sync_loop():
            import time
            import logging
            thread_logger = logging.getLogger('crypto_bot')
            
            sync_interval = 120  # Sync every 120 seconds (upgraded from 60)
            
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
        logger.info("✅ Redis state syncer started (120s interval)")

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
                        # FIX #5: os._exit(3) — sys.exit dari daemon thread hanya
                        # matikan thread itu, bukan proses utama. os._exit langsung
                        # terminate proses sehingga systemd/docker bisa restart.
                        # Bug HIGH #6 (audit 2026-06-07): WAL checkpoint sebelum
                        # os._exit untuk meminimalkan SQLite corruption window.
                        thread_logger.info("🔄 Requesting graceful restart...")
                        self._shutdown(timeout=5)
                        # Force WAL checkpoint pada semua DB sebelum hard exit.
                        # _shutdown sudah panggil db.close() per thread, tapi WAL
                        # frames bisa tetap tertinggal kalau writer thread tidak
                        # sempat checkpoint. PRAGMA wal_checkpoint(TRUNCATE) bersih.
                        try:
                            if hasattr(self, 'db') and self.db and hasattr(self.db, 'checkpoint_wal'):
                                self.db.checkpoint_wal(mode="TRUNCATE")
                        except Exception as ckpt_err:
                            thread_logger.warning(f"⚠️ Trading DB checkpoint failed: {ckpt_err}")
                        try:
                            if hasattr(self, '_signal_db') and self._signal_db and hasattr(self._signal_db, 'checkpoint_wal'):
                                self._signal_db.checkpoint_wal(mode="TRUNCATE")
                        except Exception as ckpt_err:
                            thread_logger.warning(f"⚠️ Signal DB checkpoint failed: {ckpt_err}")
                        import os as _os
                        _os._exit(3)  # Exit code 3 = restart requested

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
            interval_seconds=600,  # 10 minutes (upgraded from 15 min)
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

        # Task 5: Adaptive Learning Nightly Analysis (every 6 hours)
        scheduler.add_task(
            name="adaptive_analysis",
            interval_seconds=21600,  # 6 hours
            func=self._scheduled_adaptive_analysis,
            description="Analyze trade outcomes and update adaptive thresholds"
        )

        # Start scheduler
        scheduler.start()
        logger.info(f"📅 Scheduler started ({len(scheduler.tasks)} tasks)")

        # Phase 4b: Start Signal Queue worker (consumes queued signals for auto-trade)
        self._start_signal_queue_worker()

    # =============================================================================
    # SIGNAL QUEUE WORKER (Phase 4b)
    # =============================================================================

    def _start_signal_queue_worker(self):
        """Start background thread that consumes SignalQueue and executes trades."""
        if not hasattr(self, 'signal_queue') or not self.signal_queue.is_available():
            logger.info("📭 Signal Queue unavailable, skipping worker")
            return

        # Clear stale backlog on startup to avoid burst-processing old signals
        try:
            cleared = self.signal_queue.clear_all()
            logger.info(f"🧹 Signal Queue cleared {cleared} stale signals on startup")
        except Exception:
            pass

        def worker_loop():
            import asyncio
            from autotrade.runtime import check_trading_opportunity
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            last_processed = {}  # {(pair, signal_type): timestamp}
            COOLDOWN_SECONDS = 300  # 5 min cooldown per pair+type
            while not self.shutdown_event.is_set():
                try:
                    signal = self.signal_queue.pop_signal(timeout=5)
                    if signal:
                        pair = signal.get('pair')
                        signal_type = signal.get('signal_type')
                        confidence = signal.get('confidence', 0)
                        price = signal.get('price', 0)
                        key = (pair, signal_type)
                        now = time.time()

                        # Cooldown deduplication
                        if key in last_processed and (now - last_processed[key]) < COOLDOWN_SECONDS:
                            logger.debug(f"⏳ [SQ-WORKER] Cooldown skip {signal_type} {pair}")
                            self.signal_queue.mark_skipped(signal, "Cooldown deduplication")
                            time.sleep(2)
                            continue

                        logger.info(f"🔨 [SQ-WORKER] Processing {signal_type} {pair} @ {price:,.0f}")
                        last_processed[key] = now

                        # FIX 2026-06-07: Clear stale inflight tasks from other
                        # event loops before running check_trading_opportunity.
                        # _get_cached_signal stores asyncio tasks in
                        # _signal_inflight_tasks — if a task was created in the
                        # main Telegram event loop and the worker tries to await
                        # it from its own loop, it raises "attached to a
                        # different loop". Clearing the dict prevents this.
                        inflight = getattr(self, '_signal_inflight_tasks', None)
                        if isinstance(inflight, dict):
                            inflight.clear()

                        # FIX: Do NOT pass a minimal signal skeleton; let
                        # check_trading_opportunity regenerate the full signal via
                        # _get_cached_signal so notifications carry real indicators,
                        # combined_strength, ML confidence, and stabilization/quality
                        # gates instead of a stale market-scan snapshot.
                        try:
                            loop.run_until_complete(
                                check_trading_opportunity(self, pair, signal=None)
                            )
                            self.signal_queue.mark_done(signal['signal_id'])
                        except Exception as e:
                            logger.error(f"❌ [SQ-WORKER] Trade execution failed: {e}")
                            self.signal_queue.mark_skipped(signal, str(e))
                        # Throttle to avoid CPU spike and API rate limits
                        time.sleep(2)
                    else:
                        # No signal popped; brief nap
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"❌ [SQ-WORKER] Error: {e}")
                    time.sleep(5)
            loop.close()

        t = threading.Thread(target=worker_loop, daemon=True, name="SignalQueue-Worker")
        t.start()
        self.background_threads.append(t)
        logger.info("🔨 Signal Queue worker started")

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

                    active_pairs = self._get_active_signal_pairs()
                    if not active_pairs:
                        logger.info("📭 Market scan skipped: no watched or auto-trade pairs")
                        return

                    for pair in active_pairs:
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
                                elif abs(ta_strength) < 0.05:
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
            self.db.cleanup_old_price_data(days=30, max_db_size_gb=10)
            runtime_deleted = self.db.cleanup_old_runtime_history(days=30, max_db_size_gb=10)
            logger.info(f"🗑️ Cleaned up runtime history: {runtime_deleted}")
            if hasattr(self, '_signal_db') and self._signal_db:
                deleted_signals = self._signal_db.delete_old_signals(days=30, max_db_size_gb=10)
                logger.info(f"🗑️ Cleaned up {deleted_signals} old signals")
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

    def _scheduled_adaptive_analysis(self):
        """Run adaptive learning analysis every 6 hours"""
        try:
            if self._adaptive_engine:
                result = self._adaptive_engine.run_nightly_analysis()
                logger.info(
                    f"🧠 Adaptive analysis: {result['pairs_analyzed']} pairs, "
                    f"{result['v4_outcomes_7d']} V4 outcomes (7d)"
                )
        except Exception as e:
            logger.error(f"❌ Adaptive analysis error: {e}")

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

                # Collect normalized pair groups in list, concat once at end (memory efficient)
                data_frames, pairs_with_data = self._collect_normalized_training_data(
                    pairs_to_check=Config.WATCH_PAIRS,
                    limit=2000,
                    min_candles=100,
                    include_small_groups=False,
                    include_zero_summary=False,
                )

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

                    # NEW: Train V4 model from signal outcomes
                    try:
                        logger.info("🤖 Training ML V4 (trade outcome based)...")
                        v4_success, v4_msg = train_model_from_signals(
                            self, tp_pct=3, sl_pct=2, window=10, days_back=30
                        )
                        if v4_success and self._last_signal_outcomes:
                            if not self.ml_model_v4:
                                self.ml_model_v4 = MLTradingModelV4()
                            v4_train_success = self.ml_model_v4.train_from_outcomes(
                                self._last_signal_outcomes
                            )
                            if v4_train_success:
                                v4_status = self.ml_model_v4.get_status()
                                logger.info(
                                    f"✅ ML V4 trained: win_rate={v4_status.get('win_rate'):.1%}, "
                                    f"profit_factor={v4_status.get('profit_factor'):.2f}"
                                )
                                if send_to_telegram:
                                    self._send_telegram_admins(
                                        f"🤖 <b>ML V4 Trained (Trade Outcome)</b>\n\n"
                                        f"🎯 Win Rate: <code>{v4_status.get('win_rate', 0):.1%}</code>\n"
                                        f"📈 Profit Factor: <code>{v4_status.get('profit_factor', 0):.2f}</code>\n"
                                        f"💰 Expectancy: <code>{v4_status.get('expectancy', 0):.2f}%</code>\n\n"
                                        f"💡 Model now learns from actual trade results!"
                                    )
                    except Exception as e:
                        logger.warning(f"⚠️ ML V4 training skipped: {e}")

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
        """Send message to all admin Telegram IDs using the main Telegram app loop."""

        async def _async_send():
            bot = getattr(getattr(self, 'app', None), 'bot', None)
            if bot is None:
                logger.warning("⚠️ Telegram admin send skipped: app.bot not initialized")
                return
            for admin_id in Config.ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to send to admin {admin_id}: {e}")

        if not self._run_on_telegram_loop(_async_send()):
            logger.warning("⚠️ Telegram admin send skipped: Telegram loop unavailable")

    def _run_on_telegram_loop(self, coro):
        """Schedule a coroutine on the main Telegram/PTB event loop from any thread."""
        import asyncio

        loop = getattr(self, '_telegram_loop', None)
        app = getattr(self, 'app', None)
        if loop is None or app is None:
            try:
                coro.close()
            except Exception:
                pass
            return False
        if hasattr(loop, 'is_closed') and loop.is_closed():
            try:
                coro.close()
            except Exception:
                pass
            return False
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to schedule coroutine on Telegram loop: {e}")
            try:
                coro.close()
            except Exception:
                pass
            return False

    @staticmethod
    def _run_coroutine_in_private_loop(coro):
        """Run a coroutine in a short-lived private event loop for worker threads."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()


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

                # Collect normalized pair groups in list, concat once at end (memory efficient)
                data_frames, pairs_with_data = self._collect_normalized_training_data(
                    pairs_to_check=Config.WATCH_PAIRS,
                    limit=2000,
                    min_candles=100,
                    include_small_groups=False,
                    include_zero_summary=False,
                )

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
        register_bot_handlers(self)
        logger.info("📋 Registered all command handlers")

    async def _post_init(self, app):
        """Register Telegram's native slash-command menu after app initialization."""
        try:
            self._telegram_loop = asyncio.get_running_loop()
            commands = [
                BotCommand(command=command, description=description)
                for command, description in TELEGRAM_BOT_COMMANDS
            ]
            await app.bot.set_my_commands(commands)
            logger.info("📋 Telegram bot commands menu registered")
        except Exception as e:
            logger.warning(f"⚠️ Could not register Telegram bot commands: {e}")
        
        # Auto-refresh watchlist untuk semua admin users saat startup
        # Ini memastikan watchlist selalu up-to-date dengan volume real-time Indodax
        if self.is_trading:
            for admin_id in Config.ADMIN_IDS:
                try:
                    result = await self._refresh_watchlist_from_top_volume(
                        user_id=admin_id,
                        limit=33,
                        min_volume_idr=500_000_000,
                    )
                    if result.get("error"):
                        logger.warning(
                            "⚠️ Startup watchlist refresh failed for admin %d: %s",
                            admin_id, result["error"],
                        )
                    else:
                        logger.info(
                            "✅ Startup watchlist auto-refreshed for admin %d: "
                            "%d pairs active",
                            admin_id, result["active_count"],
                        )
                except Exception as e:
                    logger.warning(
                        "⚠️ Startup watchlist refresh error for admin %d: %s",
                        admin_id, e,
                    )
    
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
        """Save auto-trade mode to database (persistent setting)."""
        try:
            self.db.set_auto_trade_mode(is_dry_run)
            Config.AUTO_TRADE_DRY_RUN = is_dry_run
            mode_label = "🧪 DRY RUN" if is_dry_run else "🔴 REAL"
            logger.info(f"💾 Auto-trade mode saved to database: {mode_label}")
        except Exception as e:
            logger.error(f"❌ Failed to save auto-trade mode to database: {e}")

    def _enable_startup_dryrun_autotrade(self):
        """Apply `/autotrade dryrun` semantics automatically whenever bot.py starts.

        During the enforced dry-run period, every process start must come up in
        AutoTrade simulation mode. This intentionally does not call the Telegram
        command handler because startup has no Update/Context object; it applies
        the same state changes as `/autotrade dryrun`: trading enabled and
        persistent auto-trade mode set to DRY RUN.
        """
        self.is_trading = True
        self._save_auto_trade_mode(True)
        # Ensure signal notifications are ON so DRY RUN signals appear in Telegram
        self.signal_notifications_enabled = True
        try:
            self.db.set_signal_notifications_enabled(True)
        except Exception:
            pass
        logger.info("🟡 Startup command applied automatically: /autotrade dryrun (notifications ON)")

    def _cleanup_broken_dryrun_trades(self):
        """Close DRY RUN trades with amount=0 (legacy bug before 2026-06-07 fix)."""
        try:
            user_id = Config.ADMIN_IDS[0] if Config.ADMIN_IDS else 1
            open_trades = self.db.get_open_trades(user_id)
            closed_count = 0
            for trade in open_trades:
                trade_dict = dict(trade) if hasattr(trade, 'keys') else trade
                amount = float(trade_dict.get('amount', 0) or 0)
                notes = str(trade_dict.get('notes', '') or '').lower()
                if amount <= 0 and 'dry run' in notes:
                    trade_id = trade_dict.get('id')
                    self.db.close_trade(
                        trade_id=trade_id,
                        sell_price=trade_dict.get('price', 0),
                        sell_amount=0,
                        order_id='CLEANUP',
                        reason='BROKEN_AMOUNT_ZERO'
                    )
                    try:
                        self.price_monitor.remove_price_level(user_id, trade_id)
                    except Exception:
                        pass
                    closed_count += 1
            if closed_count > 0:
                logger.info(f"🧹 Cleaned up {closed_count} broken DRY RUN trades (amount=0)")
        except Exception as e:
            logger.debug(f"⚠️ Cleanup broken trades skipped: {e}")

    def _normalize_official_pair_key(self, pair: str) -> str:
        """Normalize a pair to the Indodax official no-separator key, e.g. btcidr."""
        normalized = str(pair or "").strip().lower().replace("/", "").replace("_", "")
        if normalized and not normalized.endswith("idr"):
            normalized += "idr"
        return normalized

    def _coin_from_pair(self, pair: str) -> str:
        """Return the coin symbol portion from an IDR pair."""
        pair_key = self._normalize_official_pair_key(pair)
        return pair_key[:-3] if pair_key.endswith("idr") else pair_key

    def _get_official_indodax_pair_set(self, ttl_seconds: int = 300):
        """Return official Indodax IDR pair keys, cached to avoid API spam."""
        now = time.time()
        cached_at = getattr(self, "_official_indodax_pairs_cached_at", 0)
        cached_pairs = getattr(self, "_official_indodax_pairs_cache", None)
        if cached_pairs is not None and now - cached_at < ttl_seconds:
            return cached_pairs

        pairs = set()
        try:
            tickers = self.indodax.get_all_tickers() if getattr(self, "indodax", None) else []
            for ticker in tickers or []:
                pair = ticker.get("pair") if isinstance(ticker, dict) else None
                pair_key = self._normalize_official_pair_key(pair)
                if pair_key.endswith("idr"):
                    pairs.add(pair_key)
        except Exception as e:
            logger.warning(f"⚠️ Failed to refresh official Indodax pairs: {e}")

        self._official_indodax_pairs_cache = pairs
        self._official_indodax_pairs_cached_at = now
        return pairs

    def _get_indodax_balance_snapshot(self, ttl_seconds: int = 30):
        """Return official Indodax balances, cached briefly for Telegram signal buttons."""
        now = time.time()
        cached_at = getattr(self, "_indodax_balance_cached_at", 0)
        cached_snapshot = getattr(self, "_indodax_balance_cache", None)
        if cached_snapshot is not None and now - cached_at < ttl_seconds:
            return cached_snapshot

        snapshot = {
            "available": {},
            "hold": {},
            "available_unavailable": True,
        }
        try:
            if getattr(Config, "IS_API_KEY_CONFIGURED", False) and getattr(self, "indodax", None):
                info = self.indodax.get_balance()
                if info and isinstance(info, dict):
                    snapshot = {
                        "available": info.get("balance", {}) or {},
                        "hold": info.get("balance_hold", {}) or {},
                        "available_unavailable": False,
                    }
        except Exception as e:
            logger.warning(f"⚠️ Failed to refresh Indodax balance snapshot: {e}")

        self._indodax_balance_cache = snapshot
        self._indodax_balance_cached_at = now
        return snapshot

    def _balance_amount_for_coin(self, coin: str, snapshot: dict) -> float:
        """Return total available+hold amount for a coin from an Indodax balance snapshot."""
        coin_key = str(coin or "").lower()
        total = 0.0
        for bucket in ("available", "hold"):
            try:
                total += float((snapshot.get(bucket, {}) or {}).get(coin_key, 0) or 0)
            except (TypeError, ValueError):
                continue
        return total

    def _has_scalper_position_amount(self, pair: str) -> bool:
        """Return True when the scalper has a local position amount for a pair."""
        try:
            scalper = getattr(self, "scalper", None)
            if not scalper:
                return False
            pair_key = self._normalize_official_pair_key(pair)
            position = getattr(scalper, "active_positions", {}).get(pair_key)
            return bool(position and float(position.get("amount") or 0) > 0)
        except Exception:
            return False

    def _build_signal_action_markup(self, signals):
        """
        Build Telegram action buttons for signal messages using official Indodax state.

        Safety policy:
        - Buttons are shown only for official Indodax IDR pairs.
        - BUY buttons route to Scalper only, never AutoTrade/Hunter.
        - SELL buttons appear only when Indodax/scalper has coin amount for that pair.
        - AutoTrade/Smart Hunter remain NO-MONEY/DRY-RUN; these buttons do not bypass Scalper confirmations.
        """
        if not signals:
            return None
        if isinstance(signals, dict):
            signal_list = [signals]
        else:
            signal_list = [s for s in signals if isinstance(s, dict)]
        if not signal_list:
            return None

        official_pairs = self._get_official_indodax_pair_set()
        if not official_pairs:
            return None

        balances = self._get_indodax_balance_snapshot()
        rows = []
        seen = set()
        for signal in signal_list:
            rec = str(signal.get("recommendation", "")).upper()
            pair_key = self._normalize_official_pair_key(signal.get("pair"))
            if not pair_key or pair_key in seen or pair_key not in official_pairs:
                continue
            seen.add(pair_key)

            if rec in ("BUY", "STRONG_BUY"):
                idr_amount = self._balance_amount_for_coin("idr", balances)
                if balances.get("available_unavailable") or idr_amount > 0:
                    rows.append([
                        InlineKeyboardButton(
                            f"🟢 BUY {pair_key.upper()} via Scalper",
                            callback_data=f"s_buy:{pair_key}",
                        )
                    ])
            elif rec in ("SELL", "STRONG_SELL"):
                coin = self._coin_from_pair(pair_key)
                coin_amount = self._balance_amount_for_coin(coin, balances)
                if coin_amount > 0 or self._has_scalper_position_amount(pair_key):
                    rows.append([
                        InlineKeyboardButton(
                            f"🔴 SELL {pair_key.upper()} via Scalper",
                            callback_data=f"s_sell:{pair_key}",
                        )
                    ])

        if not rows:
            return None
        rows.append([InlineKeyboardButton("📦 Posisi Scalper", callback_data="s_refresh_posisi")])
        return InlineKeyboardMarkup(rows)

    async def _send_signal_message_with_actions(self, update, context, signal, text=None):
        """Send one signal message with safe Scalper-only action buttons when allowed."""
        message_text = text or self._format_signal_message_html(signal)
        reply_markup = self._build_signal_action_markup(signal)
        kwargs = {"parse_mode": "HTML"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        await self._send_message(update, context, message_text, **kwargs)

    async def _send_signal_batch_with_actions(self, update, context, text, signals):
        """Send a signal batch with aggregate safe Scalper-only action buttons."""
        reply_markup = self._build_signal_action_markup(signals)
        kwargs = {"parse_mode": "HTML"}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        await self._send_message(update, context, text, **kwargs)

    def _lock_no_money_automation(self, reason: str = "safety policy"):
        """Force AutoTrade/AutoHunter/SmartHunter money automation into no-money mode."""
        try:
            self.is_trading = False
            self._save_auto_trade_mode(True)
        except Exception as e:
            logger.warning(f"⚠️ Failed to persist automation DRY RUN lock: {e}")
        logger.warning(f"🔒 Money automation locked to DRY RUN/NO MONEY ({reason})")

    def _load_signal_notifications_mode(self):
        """Load automatic signal notification setting from database."""
        try:
            self.signal_notifications_enabled = self.db.get_signal_notifications_enabled()
            status = "ON" if self.signal_notifications_enabled else "OFF"
            logger.info(f"🔔 Signal notifications loaded from database: {status}")
        except Exception as e:
            self.signal_notifications_enabled = True
            logger.warning(f"⚠️ Failed to load signal notification setting: {e}")
            logger.info("Using default: signal notifications ON")

    def _save_signal_notifications_mode(self, enabled: bool):
        """Persist automatic signal notification setting."""
        enabled = bool(enabled)
        self.signal_notifications_enabled = enabled
        try:
            self.db.set_signal_notifications_enabled(enabled)
            status = "ON" if enabled else "OFF"
            logger.info(f"💾 Signal notifications saved: {status}")
        except Exception as e:
            logger.error(f"❌ Failed to save signal notification setting: {e}")

    def _are_signal_notifications_enabled(self):
        """Return current automatic signal notification setting."""
        return getattr(self, "signal_notifications_enabled", True)

    # ----- Signal Notification Filter (BUY-only / SELL-only / actionable) -----
    SIGNAL_FILTER_LABELS = {
        'all': '📋 Semua sinyal (BUY, SELL, HOLD)',
        'buy': '🟢 Hanya BUY / STRONG_BUY',
        'sell': '🔴 Hanya SELL / STRONG_SELL',
        'actionable': '⚡ BUY + SELL (skip HOLD) — fokus scalping',
    }

    def _load_signal_notification_filter(self):
        """Load signal notification filter from database."""
        try:
            self.signal_notification_filter = self.db.get_signal_notification_filter()
            logger.info(f"🎯 Signal notification filter loaded: {self.signal_notification_filter}")
        except Exception as e:
            self.signal_notification_filter = 'all'
            logger.warning(f"⚠️ Failed to load signal notification filter: {e}")

    def _save_signal_notification_filter(self, mode: str):
        """Persist signal notification filter mode."""
        mode = (mode or 'all').lower()
        if mode not in self.SIGNAL_FILTER_LABELS:
            raise ValueError(f"Invalid signal notification filter: {mode}")
        self.signal_notification_filter = mode
        try:
            self.db.set_signal_notification_filter(mode)
            logger.info(f"💾 Signal notification filter saved: {mode}")
        except Exception as e:
            logger.error(f"❌ Failed to save signal notification filter: {e}")

    def _signal_passes_notification_filter(self, recommendation: str) -> bool:
        """Return True if an automatic/background signal alert may be pushed to Telegram."""
        rec = (recommendation or '').upper()
        return rec in ('BUY', 'STRONG_BUY', 'SELL', 'STRONG_SELL')

    async def _set_signal_notification_filter_cmd(self, update, context, mode: str):
        """Shared handler for admin-only signal notification filter changes."""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Command ini hanya untuk admin.")
            return

        try:
            self._save_signal_notification_filter(mode)
        except ValueError:
            await self._send_message(update, context, f"⚠️ Filter tidak valid: <code>{mode}</code>", parse_mode='HTML')
            return

        label = self.SIGNAL_FILTER_LABELS[mode]
        on_off = "ON" if self._are_signal_notifications_enabled() else "OFF"
        text = (
            f"✅ <b>Filter notifikasi sinyal disetel</b>\n\n"
            f"Mode: <b>{label}</b>\n"
            f"Notifikasi otomatis: <b>{on_off}</b>\n\n"
            f"<i>Ini hanya memengaruhi notifikasi sinyal otomatis. "
            f"Command manual seperti /signal, /signal buy, /signal sell "
            f"(alias /signal_buy dan /signal_sell) tetap menampilkan apa pun.</i>\n\n"
            f"Cek status: <code>/notif_status</code> atau <code>/signal_notif status</code>\n"
            f"Filter cepat: <code>/signal_notif buy|sell|both</code>\n"
            f"Reset ke semua: <code>/notif_all</code>"
        )
        await self._send_message(update, context, text, parse_mode='HTML')

    async def notif_buy(self, update, context):
        """Filter notifikasi otomatis hanya BUY/STRONG_BUY."""
        await self._set_signal_notification_filter_cmd(update, context, 'buy')

    async def notif_sell(self, update, context):
        """Filter notifikasi otomatis hanya SELL/STRONG_SELL."""
        await self._set_signal_notification_filter_cmd(update, context, 'sell')

    async def notif_scalp(self, update, context):
        """Filter notifikasi otomatis BUY+SELL (skip HOLD) untuk scalping."""
        await self._set_signal_notification_filter_cmd(update, context, 'actionable')

    async def notif_all(self, update, context):
        """Reset filter notifikasi ke semua sinyal."""
        await self._set_signal_notification_filter_cmd(update, context, 'all')

    async def notif_status(self, update, context):
        """Tampilkan status filter notifikasi sinyal."""
        mode = getattr(self, 'signal_notification_filter', 'all')
        label = self.SIGNAL_FILTER_LABELS.get(mode, mode)
        on_off = "ON" if self._are_signal_notifications_enabled() else "OFF"
        text = (
            "🔔 <b>Status Notifikasi Sinyal</b>\n\n"
            f"• Notif otomatis: <b>{on_off}</b> (atur via <code>/signal on</code> / <code>/signal off</code>)\n"
            f"• Filter aktif: <b>{label}</b>\n\n"
            "<b>Command filter:</b>\n"
            "• <code>/signal_notif buy</code> — hanya BUY / STRONG_BUY\n"
            "• <code>/signal_notif sell</code> — hanya SELL / STRONG_SELL\n"
            "• <code>/signal_notif both</code> — BUY + SELL (skip HOLD)\n"
            "• <code>/signal_notif status</code> — lihat status saat ini\n"
            "• <code>/notif_buy</code> — hanya BUY / STRONG_BUY\n"
            "• <code>/notif_sell</code> — hanya SELL / STRONG_SELL\n"
            "• <code>/notif_scalp</code> — BUY + SELL (skip HOLD)\n"
            "• <code>/notif_all</code> — semua sinyal\n"
            "• <code>/notif_status</code> — pesan ini\n\n"
            "<i>Filter ini hanya memengaruhi push notifikasi otomatis dari watchlist/auto-trade. "
            "Command manual seperti /signal, /signal buy, /signal sell "
            "(alias /signal_buy dan /signal_sell) tetap menampilkan apa pun.</i>"
        )
        await self._send_message(update, context, text, parse_mode='HTML')

    async def signal_notif(self, update, context):
        """Admin shortcut to set automatic Telegram signal notification filter."""
        if not context.args:
            await self._send_message(
                update,
                context,
                "🔔 <b>Format:</b> <code>/signal_notif buy|sell|both|status</code>\n\n"
                "• <code>buy</code> — hanya BUY / STRONG_BUY\n"
                "• <code>sell</code> — hanya SELL / STRONG_SELL\n"
                "• <code>both</code> — BUY + SELL (skip HOLD)\n"
                "• <code>status</code> — lihat filter aktif\n\n"
                "<i>Perubahan filter notifikasi adalah kontrol operasional admin.</i>",
                parse_mode='HTML',
            )
            return

        subcommand = context.args[0].strip().lower()
        mode_map = {
            'buy': 'buy',
            'sell': 'sell',
            'both': 'actionable',
            'bot': 'actionable',
        }

        if subcommand == 'status':
            await self.notif_status(update, context)
            return

        mode = mode_map.get(subcommand)
        if not mode:
            await self._send_message(
                update,
                context,
                f"⚠️ Opsi tidak valid: <code>{subcommand}</code>\n"
                "Gunakan <code>/signal_notif buy</code>, <code>/signal_notif sell</code>, "
                "<code>/signal_notif both</code>, atau <code>/signal_notif status</code>.",
                parse_mode='HTML',
            )
            return

        await self._set_signal_notification_filter_cmd(update, context, mode)

    # =============================================================================
    # TELEGRAM COMMAND HANDLERS
    # =============================================================================

    def _build_quick_keyboard(self, is_admin=False):
        """Build app-like Telegram quick-action buttons."""
        return build_quick_keyboard(is_admin=is_admin)

    def _build_android_reply_keyboard(self, is_admin=False):
        """Build persistent fallback keyboard aligned with /help quick actions."""
        return build_android_reply_keyboard(is_admin=is_admin)

    def _build_menu_panel_keyboard(self, section, is_admin=False):
        """Build contextual menu buttons for each main panel."""
        return build_menu_panel_keyboard(section, is_admin=is_admin)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message and menu"""
        user = update.effective_user
        self.db.add_user(user.id, user.username, user.first_name)

        is_admin = user.id in Config.ADMIN_IDS
        user_id = update.effective_user.id
        user_watchlist = self.subscribers.get(user_id, [])
        user_autotrade = self.auto_trade_pairs.get(user_id, [])

        text = build_start_html(
            first_name=user.first_name,
            is_admin=is_admin,
            is_trading=self.is_trading,
            is_dry_run=Config.AUTO_TRADE_DRY_RUN,
            watch_count=len(user_watchlist),
            autotrade_count=len(user_autotrade),
            dashboard_ready=bool(Config.DASHBOARD_URL),
        )

        keyboard = [
            [
                InlineKeyboardButton("📊 Market", callback_data="market_scan_quick"),
                InlineKeyboardButton("💼 Portfolio", callback_data="portfolio_quick"),
            ],
            [
                InlineKeyboardButton("🔔 Alerts", callback_data="notifications_quick"),
                InlineKeyboardButton("⚙️ Settings", callback_data="nav_settings"),
            ],
            [
                InlineKeyboardButton("📈 Signal", callback_data="signals_quick"),
                InlineKeyboardButton("💰 Price", callback_data="price_quick"),
            ],
        ]

        if user_watchlist:
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
            keyboard.append([InlineKeyboardButton("📘 Mulai dari Panduan", callback_data="help")])

        if is_admin and user_autotrade:
            keyboard.append([
                InlineKeyboardButton(f"🤖 Auto-Trade: {len(user_autotrade)} pair", callback_data="autotrade_add_pair")
            ])

        if Config.DASHBOARD_URL:
            keyboard.append([InlineKeyboardButton("📊 Dashboard", url=Config.DASHBOARD_URL)])

        if is_admin:
            keyboard.append([
                InlineKeyboardButton("🤖 Auto-Trade", callback_data="autotrade_quick"),
                InlineKeyboardButton("⚙️ Admin", callback_data="admin_panel"),
            ])

        await update.message.reply_text(
            "Keyboard cepat bawah disembunyikan. Pakai tombol menu di pesan /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"👤 User {user.id} started bot")
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Detailed help guide"""
        text = build_help_html()
        await self._send_message(
            update,
            context,
            text,
            parse_mode='HTML',
            reply_markup=self._build_quick_keyboard(update.effective_user.id in Config.ADMIN_IDS),
        )

    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show quick menu with all available commands"""
        is_admin = update.effective_user.id in Config.ADMIN_IDS
        user_id = update.effective_user.id
        text = build_main_menu_html(
            is_admin=is_admin,
            is_trading=self.is_trading,
            is_dry_run=Config.AUTO_TRADE_DRY_RUN,
            watch_count=len(self.subscribers.get(user_id, [])),
            autotrade_count=len(self.auto_trade_pairs.get(user_id, [])),
            dashboard_ready=bool(Config.DASHBOARD_URL),
        )
        await self._send_message(
            update,
            context,
            text,
            parse_mode='HTML',
            reply_markup=self._build_quick_keyboard(update.effective_user.id in Config.ADMIN_IDS),
        )

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show settings-oriented quick panel."""
        is_admin = update.effective_user.id in Config.ADMIN_IDS
        text = build_menu_section_html(
            "settings",
            is_admin=is_admin,
            dashboard_ready=bool(Config.DASHBOARD_URL),
        )
        await self._send_message(
            update,
            context,
            text,
            parse_mode='HTML',
            reply_markup=self._build_menu_panel_keyboard("settings", is_admin=is_admin),
        )

    async def _show_autotrade_quick_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show safe auto-trade panel without toggling state."""
        user_id = update.effective_user.id
        if user_id not in Config.ADMIN_IDS:
            await self._send_message(
                update,
                context,
                "🤖 <b>Auto-Trade</b>\n\n"
                "Fitur ini hanya untuk admin.\n\n"
                "Gunakan <code>/signal btcidr</code> atau <code>/scan</code> untuk analisa manual.",
                parse_mode='HTML',
                reply_markup=self._build_quick_keyboard(False),
            )
            return

        mode = "DRY RUN / simulasi" if Config.AUTO_TRADE_DRY_RUN else "REAL / uang asli"
        status = "ON" if self.is_trading else "OFF"
        text = (
            "🤖 <b>Auto-Trade</b>\n\n"
            f"Status: <b>{status}</b>\n"
            f"Mode uang: <b>{mode}</b>\n"
            f"Pair auto-trade: <code>{len(self.auto_trade_pairs.get(user_id, []))}</code>\n\n"
            "<b>Command aman:</b>\n"
            "• <code>/autotrade_status</code> lihat status detail\n"
            "• <code>/add_autotrade btcidr</code> tambah pair\n"
            "• <code>/remove_autotrade btcidr</code> hapus pair\n"
            "• <code>/autotrade dryrun</code> nyalakan simulasi\n"
            "• <code>/autotrade off</code> matikan\n\n"
            "Tombol ini tidak toggle otomatis agar tidak menyalakan trading tanpa sengaja."
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Status", callback_data="autotrade_status_quick"),
                InlineKeyboardButton("➕ Setup Pair", callback_data="autotrade_add_pair"),
            ],
            [InlineKeyboardButton("⬅️ Menu Utama", callback_data="menu_home")],
        ])
        await self._send_message(update, context, text, parse_mode='HTML', reply_markup=keyboard)

    async def _show_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin maintenance panel."""
        user_id = update.effective_user.id
        if user_id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        await self._send_message(
            update,
            context,
            build_admin_panel_text(),
            parse_mode='HTML',
            reply_markup=build_admin_panel_markup(),
        )

    async def commands_helper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show quick reference guide for all commands"""
        kategori = context.args[0] if context.args else None
        text = build_commands_text(kategori)

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
            send_to_telegram = self._are_signal_notifications_enabled()

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
                if send_to_telegram:
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

                # Honor /signal_notif filter (buy/sell/actionable/all)
                if not self._signal_passes_notification_filter(recommendation):
                    logger.info(
                        f"🎯 Initial signal alert filtered out for {pair}: {recommendation} "
                        f"(filter={getattr(self, 'signal_notification_filter', 'all')})"
                    )
                    return

                if send_to_telegram:
                    text = self._format_signal_message_html(signal)
                    await self._send_signal_message_with_actions(update, context, signal, text=text)
                else:
                    logger.info(f"🔕 Initial signal generated for {pair} (not pushed: notifications OFF)")
            else:
                if send_to_telegram:
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

    async def _save_price_history_background(self, pair, ohlcv):
        """Persist price history in the heavy executor so price ticks stay responsive."""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self._heavy_executor,
                lambda: self.db.save_price(pair, ohlcv),
            )
        except Exception as e:
            logger.error(f"❌ Failed to save price history for {pair}: {e}")

    async def _send_initial_signal_background(self, pair, update, context):
        """
        🚀 BACKGROUND TASK: Send initial signal (tidak blocking command response)
        """
        try:
            send_to_telegram = self._are_signal_notifications_enabled()
            if not send_to_telegram:
                logger.info(f"🔕 Background signal will be generated but NOT pushed to Telegram for {pair}: notifications OFF")

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

                # Honor /signal_notif filter (buy/sell/actionable/all)
                if not self._signal_passes_notification_filter(recommendation):
                    logger.info(
                        f"🎯 Background initial signal filtered out for {pair}: {recommendation} "
                        f"(filter={getattr(self, 'signal_notification_filter', 'all')})"
                    )
                    return

                if send_to_telegram:
                    text = self._format_signal_message_html(signal)
                    try:
                        await self._send_message(update, context, text, parse_mode='HTML')
                    except Exception as e:
                        logger.error(f"❌ Failed to send signal alert for {pair}: {e}")
                else:
                    logger.info(f"🔕 Background signal generated for {pair} (not pushed: notifications OFF)")
            else:
                if send_to_telegram:
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

    async def _safe_callback_reply(self, query, text):
        """Safely send a reply when a callback handler fails.
        Tries edit_message_text first, falls back to reply_text."""
        try:
            await query.edit_message_text(f"{text}\n\n💡 Coba lagi nanti atau gunakan command langsung.", parse_mode='HTML')
        except Exception:
            try:
                await query.message.reply_text(text, parse_mode='HTML')
            except Exception as e2:
                logger.error(f"_safe_callback_reply failed: {e2}")

    async def _run_callback_command(self, query, update, context, method, label):
        """Run a command handler from an inline button click with safety.
        Shows immediate 'loading' feedback, runs the command, catches errors."""
        try:
            await query.edit_message_text(f"⏳ {label}...")
        except Exception:
            pass
        try:
            await method(update, context)
        except Exception as e:
            logger.error(f"[CALLBACK] {label} error: {e}")
            await self._safe_callback_reply(query, f"❌ {label} gagal: {e}")

    async def _send_message(self, update, context, text, **kwargs):
        """Helper to send message for both command and callback query.
        Logs all failures so bugs are visible in logs.

        FIX 2026-06-07 v2: Robust error recovery —
        - HTML parse-mode fallback (html_escape retry)
        - Markdown parse-mode fallback (strip **, `, _ → plain text)
        - Event-loop mismatch fallback (RuntimeError 'different event loop' → retry on main loop if available)
        - Bare-text last-resort (strips ALL kwargs, no parse_mode)
        """
        edit_error = None
        reply_error = None

        async def _try_escaped_fallback(target_message, safe_kwargs, safe_text):
            """Multi-layer fallback: try with safe_kwargs, then bare, then fire-and-forget."""
            for attempt, (use_kwargs, label) in enumerate([
                (safe_kwargs, "safe_kwargs"),
                ({}, "bare"),
            ]):
                try:
                    await target_message.reply_text(safe_text, **use_kwargs)
                    return True
                except Exception as fb_err:
                    fb_str = str(fb_err)
                    if attempt == 0:
                        logger.debug("_send_message escape fallback lvl%d (%s) failed: %s",
                                     attempt + 1, label, fb_str)
                    # If event-loop mismatch even on bare, try scheduling on main loop
                    if 'different event loop' in fb_str.lower() or 'different loop' in fb_str.lower():
                        try:
                            loop_ref = getattr(self, '_telegram_loop', None)
                            if loop_ref and not loop_ref.is_closed():
                                import asyncio as _asyncio
                                _asyncio.run_coroutine_threadsafe(
                                    target_message.reply_text(safe_text),
                                    loop_ref
                                )
                                return True
                        except Exception:
                            pass
            return False

        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(text, **kwargs)
                return
            except Exception as e:
                edit_error = str(e)
                try:
                    await update.callback_query.message.reply_text(text, **kwargs)
                    return
                except Exception as e2:
                    reply_error = str(e2)
                    pm = kwargs.get('parse_mode')
                    if pm == 'HTML':
                        safe_kwargs = {k: v for k, v in kwargs.items()
                                       if k not in ('parse_mode',)}
                        safe_text = html_escape(str(text))
                        if await _try_escaped_fallback(
                            update.callback_query.message, safe_kwargs, safe_text
                        ):
                            return
                    elif pm == 'Markdown':
                        safe_kwargs = {k: v for k, v in kwargs.items()
                                       if k not in ('parse_mode',)}
                        safe_text = str(text).replace('**', '').replace('`', '').replace('_', '')
                        if await _try_escaped_fallback(
                            update.callback_query.message, safe_kwargs, safe_text
                        ):
                            return

        # Command or fallback path
        try:
            target = update.message or update.effective_message
            if target:
                await target.reply_text(text, **kwargs)
                return
        except Exception as e:
            err_str = str(e).lower()
            pm = kwargs.get('parse_mode')
            is_html_mode = pm == 'HTML'
            is_md_mode = pm == 'Markdown'
            is_parse_err = 'parse entities' in err_str or "can't parse" in err_str
            is_event_loop_err = 'different event loop' in err_str or 'different loop' in err_str
            target = update.message or update.effective_message

            if is_html_mode and target:
                # Strip parse_mode + risky kwargs, html_escape, retry
                safe_kwargs = {k: v for k, v in kwargs.items()
                               if k not in ('parse_mode',)}
                safe_text = html_escape(str(text))
                if await _try_escaped_fallback(target, safe_kwargs, safe_text):
                    return
            elif is_md_mode and target:
                # Strip Markdown markup, retry as plain text
                safe_kwargs = {k: v for k, v in kwargs.items()
                               if k not in ('parse_mode',)}
                safe_text = str(text).replace('**', '').replace('`', '').replace('_', '')
                if await _try_escaped_fallback(target, safe_kwargs, safe_text):
                    return
            elif is_event_loop_err and target:
                # Event loop mismatch — schedule on main loop
                try:
                    loop_ref = getattr(self, '_telegram_loop', None)
                    if loop_ref and not loop_ref.is_closed():
                        import asyncio as _asyncio
                        _asyncio.run_coroutine_threadsafe(
                            target.reply_text(html_escape(str(text))),
                            loop_ref
                        )
                        logger.debug("_send_message rescheduled on main loop after event-loop mismatch")
                        return
                except Exception as loop_fix_err:
                    logger.warning("_send_message loop-fix also failed: %s", loop_fix_err)

            logger.warning("_send_message failed (edit=%s, reply=%s, fallback=%s)",
                           edit_error, reply_error, str(e)[:120])
            # Don't raise — prevent cascading failures in command handlers
            return

        if edit_error or reply_error:
            logger.warning("_send_message fallback used: edit_err=%s, reply_err=%s",
                           edit_error, reply_error)

    async def _send_photo(self, update, photo, **kwargs):
        """Helper to send a photo for both command and callback query."""
        if update.message:
            await update.message.reply_photo(photo=photo, **kwargs)
        elif update.effective_message:
            await update.effective_message.reply_photo(photo=photo, **kwargs)
        elif update.callback_query:
            await update.callback_query.message.reply_photo(photo=photo, **kwargs)
    
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
            # FIX #3: Normalize ke lowercase — konsisten dengan /watch yang simpan lowercase
            pair = pair_input.replace('/', '').lower()
            if not pair.endswith('idr'):
                pair = pair + 'idr'
            
            normalized_pairs.append(pair)
            
            # Track normalization
            if pair_input.lower() != pair:
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
                self._cleanup_pair_runtime_state(pair, remove_auto_trade=False, user_id=user_id)
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

        still_autotrade = [
            p for p in removed_pairs
            if any(
                self._normalize_pair_key(p) == self._normalize_pair_key(auto_pair)
                for auto_pairs in self.auto_trade_pairs.values()
                for auto_pair in auto_pairs
            )
        ]
        if still_autotrade:
            auto_str = ', '.join([f"`{p}`" for p in still_autotrade])
            messages.append(
                f"\n⚠️ {auto_str} masih ada di daftar auto-trade. "
                f"Gunakan `/remove_autotrade {still_autotrade[0].lower()}` untuk stop auto-trade juga."
            )

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

    async def backfill_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Backfill profit feedback tables from trade history (admin only)."""
        user_id = update.effective_user.id

        if user_id not in Config.ADMIN_IDS:
            await update.effective_message.reply_text("❌ Admin only!")
            return

        msg = await update.effective_message.reply_text(
            "📊 **Running profit feedback backfill...**\n\n⏳ Please wait...",
            parse_mode='Markdown'
        )

        try:
            import asyncio
            from analysis.backfill_performance_metrics import run_backfill

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, run_backfill, "data/trading.db")

            if result["users"]:
                user_lines = "\n".join(
                    f"• User `{result_user_id}`: `{count}` day(s)"
                    for result_user_id, count in result["users"].items()
                )
            else:
                user_lines = "• No closed trades found yet"

            text = (
                "✅ **Profit Feedback Backfill Complete**\n\n"
                f"• DB: `{result['db_path']}`\n"
                f"• SELL rows rebuilt: `{result.get('legacy_sell_rows_rebuilt', 0)}`\n"
                f"• Trade outcomes: `{result.get('legacy_sell_rows_rebuilt', 0) + result.get('explicit_closed_rows_rebuilt', 0)}`\n"
                f"• Adaptive thresholds: `{result.get('adaptive_thresholds_rebuilt', 0)}`\n"
                f"• Daily rows rebuilt: `{result['daily_rows_rebuilt']}`\n"
                f"• Skipped unmatched: `{result.get('skipped_unmatched', 0)}`\n"
                f"• Skipped invalid: `{result.get('skipped_invalid', 0)}`\n"
                f"{user_lines}\n\n"
                "💡 Command ini aman dijalankan berulang. Data invalid tidak dimasukkan ke statistik."
            )
            await msg.edit_text(text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Performance backfill error: {e}")
            try:
                await msg.edit_text(
                    f"❌ Error during performance backfill:\n\n`{str(e)}`",
                    parse_mode='Markdown'
                )
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
            removed_pairs = list(self.subscribers.get(user_id, []))
            self._clear_watchlist_in_db(user_id)
            self.subscribers[user_id] = []
            for pair in removed_pairs:
                self._cleanup_pair_runtime_state(pair, remove_auto_trade=False, user_id=user_id)
            
            await self._send_message(update, context,
                "🗑️ **Watchlist Cleared!**\n\n"
                "Semua pair telah dihapus dari watchlist Anda.\n"
                "Gunakan `/watch <PAIR>` untuk menambahkan pair baru.",
                parse_mode='Markdown'
            )
            return
        
        if is_admin and (not context.args or context.args[0].lower() != 'all'):
            # Admin without 'all' arg: clear their own watchlist
            removed_pairs = list(self.subscribers.get(user_id, []))
            self._clear_watchlist_in_db(user_id)
            self.subscribers[user_id] = []
            for pair in removed_pairs:
                self._cleanup_pair_runtime_state(pair, remove_auto_trade=False, user_id=user_id)
            
            await self._send_message(update, context,
                "🗑️ **Watchlist Anda Cleared!**\n\n"
                "Gunakan `/clear_watchlist all` untuk hapus SEMUA watchlist semua user.",
                parse_mode='Markdown'
            )
            return
        
        if is_admin and context.args and context.args[0].lower() == 'all':
            # Admin with 'all' arg: clear ALL watchlists
            removed_pairs = sorted({
                pair
                for user_pairs in self.subscribers.values()
                for pair in user_pairs
            })
            deleted_count = self.db.clear_all_watchlists()
            self.subscribers.clear()
            for pair in removed_pairs:
                self._cleanup_pair_runtime_state(pair, remove_auto_trade=False)
            
            await self._send_message(update, context,
                f"🗑️ **SEMUA WATCHLIST CLEARED!**\n\n"
                f"• {deleted_count} records dihapus dari database\n"
                f"• Semua user watchlist dikosongkan\n"
                f"• Bot siap untuk fresh start",
                parse_mode='Markdown'
            )
            return

    async def refresh_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Refresh watchlist: ambil top 33 pair volume tertinggi dari Indodax.
        
        Pair dengan volume < 500M IDR dinonaktifkan.
        Hanya pair dengan volume besar & likuiditas tinggi yang masuk autotrade dryrun.
        
        Usage: /refresh_watchlist
        Admin only. Langsung update database + sync ke auto_trade_pairs.
        """
        user_id = update.effective_user.id
        
        if user_id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return
        
        # Kirim status "loading"
        status_msg = await self._send_message(
            update, context,
            "🔄 **Refresh Watchlist...**\n\n"
            "Mengambil data volume real-time dari Indodax...",
            parse_mode='Markdown',
        )
        
        # Jalankan refresh
        result = await self._refresh_watchlist_from_top_volume(
            user_id=user_id,
            limit=33,
            min_volume_idr=500_000_000,
        )
        
        if result.get("error"):
            await self._send_message(
                update, context,
                f"❌ **Refresh Gagal**\n\n{result['error']}",
                parse_mode='Markdown',
            )
            return
        
        # Build response
        active = result["active_count"]
        deactivated = result["deactivated_count"]
        new_pairs = result["new_pairs"]
        top_pairs = result["top_pairs"]
        volumes = result.get("top_volumes", {})
        
        # Top 5 preview dengan volume
        top_preview_lines = []
        for pair in top_pairs[:5]:
            vol = volumes.get(pair, 0)
            vol_str = f"{vol:,.0f}" if vol else "?"
            top_preview_lines.append(f"• `{pair.upper()}` — Vol: {vol_str} IDR")
        
        more_count = len(top_pairs) - 5 if len(top_pairs) > 5 else 0
        more_line = f"\n... dan {more_count} pair lainnya" if more_count > 0 else ""
        
        text = (
            f"✅ **WATCHLIST REFRESHED** ✅\n\n"
            f"📊 **Ringkasan:**\n"
            f"• Pair aktif: **{active}** (dari total {len(top_pairs)})\n"
            f"• Pair dinonaktifkan: **{deactivated - active}** (volume < 500M)\n"
            f"• Pair baru: **{len(new_pairs)}**\n\n"
            f"🏆 **Top Volume:**\n"
            + "\n".join(top_preview_lines) + more_line + "\n\n"
            f"⚡ Auto-sync ke autotrade: **{'✅ ON' if self.is_trading else '⏸️ OFF'}**\n\n"
            f"Gunakan `/autotrade dryrun` untuk mulai simulasi\n"
            f"Gunakan `/autotrade_status` untuk lihat status"
        )
        
        await self._send_message(update, context, text, parse_mode='Markdown')

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
            # ALWAYS fetch fresh price from API first without blocking the event loop
            ticker = await self.indodax.get_ticker_async(pair)
            
            if ticker:
                change_pct = ticker.get('change_percent', 0)
                change_sign = '+' if change_pct >= 0 else ''
                redis_status = "🔴 Dict" if not redis_price_cache.is_redis_available() else "🟢 Redis"

                text = f"""
💰 **{pair_escaped} - Current Price**

📊 Price: `{Utils.format_price(ticker['last'])}` IDR
📈 24h Change: `{change_sign}{change_pct:.2f}%`
💧 Volume: `{Utils.format_price(ticker['volume'])}`
🟢 Bid: `{Utils.format_price(ticker['bid'])}` IDR
🔴 Ask: `{Utils.format_price(ticker['ask'])}` IDR

⏰ Updated: {datetime.now().strftime('%H:%M:%S')}
💾 Cache: {redis_status}
                """
                
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
                "❌ **Format:** `/signal <PAIR>`\n"
                "Example: `/signal BTC/IDR`\n\n"
                "📊 Watchlist & notifikasi:\n"
                "• `/signal buy` - BUY/STRONG_BUY watchlist\n"
                "• `/signal sell` - SELL/STRONG_SELL watchlist\n"
                "• `/signal hold` - HOLD watchlist\n"
                "• `/signal buysell` - BUY + SELL watchlist\n"
                "• `/signal near` - near-miss BUY/SELL informatif\n"
                "• `/signal on|off` - nyalakan/matikan notif otomatis\n"
                "• `/signal_notif buy|sell|both` - saring notif otomatis ke Telegram",
                parse_mode='Markdown'
            )
            return

        subcommand = context.args[0].strip().lower()
        if subcommand in ("off", "on"):
            if update.effective_user.id not in Config.ADMIN_IDS:
                await self._send_message(update, context, "❌ Command ini hanya untuk admin.")
                return

            enabled = subcommand == "on"
            self._save_signal_notifications_mode(enabled)
            if enabled:
                text = (
                    "🔔 <b>Signal Notification: ON</b>\n\n"
                    "Bot akan mengirim notifikasi otomatis untuk signal actionable: "
                    "<b>BUY/STRONG_BUY</b> dan <b>SELL/STRONG_SELL</b>.\n"
                    "Signal <b>HOLD</b> tetap difilter/tidak dikirim otomatis."
                )
            else:
                text = (
                    "🔕 <b>Signal Notification: OFF</b>\n\n"
                    "Bot <b>tetap memproses dan menyimpan sinyal</b> (cooldown, cache, history),\n"
                    "hanya <b>tidak mengirim push notifikasi ke Telegram</b>.\n\n"
                    "Auto-trade flow tetap berjalan normal.\n\n"
                    "Command manual selalu aktif:\n"
                    "• <code>/signal btcidr</code>\n"
                    "• <code>/signals</code>\n"
                    "• <code>/signal buy</code> / <code>/signal sell</code>"
                )
            await self._send_message(update, context, text, parse_mode='HTML')
            return

        if subcommand in ("buy", "beli"):
            context.args = []
            await self.signal_buy_only(update, context)
            return

        if subcommand in ("sell", "jual"):
            context.args = []
            await self.signal_sell_only(update, context)
            return

        if subcommand in ("hold", "tahan", "wait", "neutral", "netral"):
            context.args = []
            await self.signal_hold_only(update, context)
            return

        if subcommand in ("buysell", "buy_sell", "buy-sell", "actionable"):
            context.args = []
            await self.signal_buysell(update, context)
            return

        if subcommand in ("near", "nearmiss", "near_miss", "near-miss"):
            context.args = []
            await self.signal_near_miss(update, context)
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
                await self._send_signal_message_with_actions(update, context, signal, text=text)
                try:
                    chart_df = self._get_chart_history_for_pair(pair)
                    chart_image = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: build_signal_chart_image(
                            pair,
                            chart_df,
                            signal=signal,
                        )
                    )
                    if chart_image:
                        await self._send_photo(
                            update,
                            chart_image,
                            caption=f"📊 {pair.upper()} chart ringkas",
                        )
                except Exception as chart_error:
                    logger.debug(f"Signal chart skipped for {pair}: {chart_error}")
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

    def _get_chart_history_for_pair(self, pair, min_points=20, limit=200):
        """Return the best available non-flat price history for Telegram charts."""
        import pandas as pd

        def _norm(value):
            return self._normalize_pair_key(value)

        def _is_useful(df):
            try:
                if df is None or getattr(df, "empty", True) or "close" not in df.columns or len(df) < min_points:
                    return False
                prices = pd.to_numeric(df["close"], errors="coerce").dropna()
                if len(prices) < min_points:
                    return False
                last = abs(float(prices.iloc[-1]))
                if last <= 0:
                    return False
                return ((float(prices.max()) - float(prices.min())) / last) >= 0.0001
            except Exception:
                return False

        pair_norm = _norm(pair)
        candidates = []
        for key, df in getattr(self, "historical_data", {}).items():
            if _norm(key) == pair_norm:
                candidates.append((key, df))

        for _, df in candidates:
            if _is_useful(df):
                return df

        db_pairs = [pair, str(pair).lower(), str(pair).upper()]
        if pair_norm:
            db_pairs.extend([pair_norm, pair_norm.upper()])
            if pair_norm.endswith("idr"):
                base = pair_norm[:-3]
                db_pairs.extend([f"{base}_idr", f"{base.upper()}_IDR", f"{base}/idr", f"{base.upper()}/IDR"])

        seen = set()
        for db_pair in db_pairs:
            key = str(db_pair)
            if key in seen:
                continue
            seen.add(key)
            try:
                df = self.db.get_price_history(key, limit=limit)
                if _is_useful(df):
                    self.historical_data[pair] = df
                    logger.info(f"📊 Chart history for {pair} loaded from DB key {key}: {len(df)} rows")
                    return df
            except Exception as e:
                logger.debug(f"Chart DB history lookup failed for {pair} via {key}: {e}")

        if candidates:
            logger.info(f"📊 Chart skipped for {pair}: only flat/synthetic history available")
        else:
            logger.info(f"📊 Chart skipped for {pair}: no chart history available")
        return None

    def _get_watched_pairs_for_user(self, user_id):
        """Get watched pairs from memory, falling back to database."""
        watched_pairs = self.subscribers.get(user_id, [])
        if not watched_pairs:
            db_pairs = self.db.get_watchlist(user_id)
            if db_pairs:
                self.subscribers[user_id] = db_pairs
                watched_pairs = db_pairs
        return watched_pairs

    async def _collect_watchlist_signals(self, watched_pairs, log_prefix="/signals"):
        """Generate signals for a watchlist in parallel."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _generate_single_signal(pair):
            signal = self._run_coroutine_in_private_loop(self._generate_signal_for_pair(pair))
            return pair, signal

        def _scan_parallel():
            results = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_generate_single_signal, pair): pair for pair in watched_pairs}
                for future in as_completed(futures):
                    pair = futures[future]
                    try:
                        _, signal = future.result()
                        if signal:
                            results.append(signal)
                    except Exception as e:
                        logger.debug(f"{log_prefix} scan error for {pair}: {e}")
            return results

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _scan_parallel)

    def _signal_row_to_runtime_signal(self, row):
        """Convert a signals.db row into the runtime signal shape used by Telegram formatters."""
        row = dict(row or {})
        recommendation = str(row.get("recommendation") or "HOLD").upper()
        symbol = row.get("symbol") or row.get("pair") or "UNKNOWN"
        timestamp = datetime.now()
        received_at = row.get("received_at")
        if received_at:
            try:
                timestamp = datetime.strptime(str(received_at), "%Y-%m-%d %H:%M:%S")
            except Exception:
                timestamp = datetime.now()

        return {
            "pair": str(symbol).lower(),
            "price": float(row.get("price") or 0),
            "recommendation": recommendation,
            "ml_confidence": float(row.get("ml_confidence") or 0),
            "combined_strength": float(row.get("combined_strength") or 0),
            "reason": row.get("analysis") or "Latest saved signal",
            "timestamp": timestamp,
            "final_gate_source": row.get("final_gate_source"),
            "price_source": row.get("price_source"),
            "indicators": {
                "rsi": row.get("rsi") or "N/A",
                "macd": row.get("macd") or "N/A",
                "ma_trend": row.get("ma_trend") or "N/A",
                "bb": row.get("bollinger") or "N/A",
                "volume": row.get("volume") or "N/A",
            },
        }

    def _get_latest_saved_watchlist_signals(self, watched_pairs, limit=None):
        """Return one latest saved signals.db snapshot per watched pair; never scans/generates new signals."""
        watched_norms = {self._normalize_pair_key(pair) for pair in watched_pairs if self._normalize_pair_key(pair)}
        if not watched_norms:
            return []

        signal_db = getattr(self, "_signal_db", None)
        if signal_db is None:
            from signals.signal_db import SignalDatabase
            signal_db = SignalDatabase("data/signals.db")
            self._signal_db = signal_db

        query_limit = limit or max(200, len(watched_norms) * 20)
        rows = signal_db.get_recent_signals(limit=query_limit)
        latest_by_pair = {}
        for row in rows:
            signal = self._signal_row_to_runtime_signal(row)
            pair_norm = self._normalize_pair_key(signal.get("pair"))
            if pair_norm in watched_norms and pair_norm not in latest_by_pair:
                latest_by_pair[pair_norm] = signal
            if len(latest_by_pair) >= len(watched_norms):
                break

        return list(latest_by_pair.values())

    async def _send_saved_signal_filter(self, update, context, direction):
        """Send filtered latest saved signals only. Does not scan pairs or generate fresh signals."""
        user_id = update.effective_user.id
        watched_pairs = self._get_watched_pairs_for_user(user_id)

        if not watched_pairs:
            await self._send_message(update, context, "No watched pairs. Use /watch <PAIR> to add.")
            return

        try:
            signals = self._get_latest_saved_watchlist_signals(watched_pairs)
        except Exception as e:
            logger.error(f"❌ /signal {direction.lower()} saved-signal filter error: {e}")
            await self._send_message(update, context, "❌ Gagal membaca signal tersimpan.")
            return

        direction = direction.upper()
        if direction == "BUY":
            filtered = [s for s in signals if s.get("recommendation") in ["BUY", "STRONG_BUY"]]
            if filtered:
                for batch in self._build_detailed_signal_message_batches(filtered):
                    await self._send_signal_batch_with_actions(update, context, batch, filtered)
        elif direction == "SELL":
            filtered = [s for s in signals if s.get("recommendation") in ["SELL", "STRONG_SELL"]]
            if filtered:
                for batch in self._build_detailed_signal_message_batches(filtered):
                    await self._send_signal_batch_with_actions(update, context, batch, filtered)
        else:
            filtered = [s for s in signals if s.get("recommendation") == "HOLD"]
            if filtered:
                result = self._build_signal_overview_html(
                    [],
                    [],
                    filtered,
                    updated_at=datetime.now().strftime('%H:%M:%S'),
                    include_hold=True,
                )
                await self._send_message(update, context, result, parse_mode='HTML')

        if not filtered:
            logger.info(
                "/signal %s found no matching latest saved signal; Telegram output suppressed "
                "(saved=%s watched=%s)",
                direction.lower(),
                len(signals),
                len(watched_pairs),
            )

    def _build_no_directional_signal_text(self, direction, watched_count, signals):
        """Explain why a directional watchlist scan returned no final signals."""
        direction = direction.upper()
        signal_count = len(signals)
        lines = [f"⚪ No {direction} signals found in {watched_count} pairs."]

        if not signals:
            lines.append("Tidak ada signal valid yang berhasil dibuat dari watchlist saat ini.")
            return "\n\n".join(lines)

        counts = {}
        for signal in signals:
            rec = str(signal.get("recommendation", "UNKNOWN")).upper()
            counts[rec] = counts.get(rec, 0) + 1

        lines.append(
            "Distribusi final: "
            f"BUY={counts.get('BUY', 0) + counts.get('STRONG_BUY', 0)}, "
            f"SELL={counts.get('SELL', 0) + counts.get('STRONG_SELL', 0)}, "
            f"HOLD={counts.get('HOLD', 0)}, "
            f"valid={signal_count}/{watched_count}."
        )

        if direction == "BUY":
            candidates = [
                signal for signal in signals
                if signal.get("recommendation") == "HOLD"
                and float(signal.get("combined_strength", 0) or 0) > 0
            ]
            title = "Kandidat BUY yang tertahan"
        else:
            candidates = [
                signal for signal in signals
                if signal.get("recommendation") == "HOLD"
                and float(signal.get("combined_strength", 0) or 0) < 0
            ]
            title = "Kandidat SELL yang tertahan"

        candidates.sort(key=lambda item: abs(float(item.get("combined_strength", 0) or 0)), reverse=True)
        if candidates:
            lines.append(f"{title}:")
            for signal in candidates[:3]:
                pair = str(signal.get("pair", "?")).upper()
                strength = float(signal.get("combined_strength", 0) or 0)
                confidence = float(signal.get("ml_confidence", 0) or 0)
                reason = str(signal.get("reason", "Tidak ada alasan detail")).strip()
                if len(reason) > 120:
                    reason = reason[:117] + "..."
                lines.append(f"• {pair}: strength={strength:+.2f}, ML={confidence:.1%} — {reason}")
        else:
            lines.append(f"Tidak ada kandidat {direction} awal yang cukup kuat setelah gate final.")

        return "\n".join(lines)

    def _build_detailed_signal_message_batches(self, signals, max_length=3500):
        """Batch detailed signal cards so directional scans reuse the single-pair formatter safely."""
        ordered_signals = sorted(
            signals,
            key=lambda item: item.get("ml_confidence", 0),
            reverse=True,
        )

        batches = []
        current_batch = []
        current_length = 0

        for signal in ordered_signals:
            block = self._format_signal_message_html(signal).strip()
            separator = "\n\n" if current_batch else ""
            projected_length = current_length + len(separator) + len(block)

            if current_batch and projected_length > max_length:
                batches.append("\n\n".join(current_batch))
                current_batch = [block]
                current_length = len(block)
                continue

            if separator:
                current_length += len(separator)
            current_batch.append(block)
            current_length += len(block)

        if current_batch:
            batches.append("\n\n".join(current_batch))

        return batches

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
                    text += "• ✅ Bot scanning setiap 10 menit\n"
                    text += "• ✅ Simulasi trade (no real money)\n"
                    text += "• 📊 Use `/autotrade_status` untuk detail\n"
                else:
                    text += "🔴 **REAL TRADING** - Aktif ⚠️\n"
                    text += "• 🚨 Bot scanning setiap 10 menit\n"
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
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def _generate_single_signal(pair):
            """Generate signal for single pair (runs in thread)"""
            signal = self._run_coroutine_in_private_loop(self._generate_signal_for_pair(pair))
            return pair, signal
        
        def _generate_signals_in_background():
            """Generate signals in background thread with parallel processing"""
            buy_signals = []
            sell_signals = []
            hold_signals = []
            
            # Use ThreadPoolExecutor for parallel signal generation (max 4 workers)
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_generate_single_signal, pair): pair for pair in watched_pairs}
                
                for future in as_completed(futures):
                    pair = futures[future]
                    try:
                        pair_result, signal = future.result()
                        
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
        buy_signal_dicts = [
            {"pair": pair, "price": price, "recommendation": rec, "ml_confidence": conf}
            for pair, price, rec, conf, _ in buy_signals
        ]
        sell_signal_dicts = [
            {"pair": pair, "price": price, "recommendation": rec, "ml_confidence": conf}
            for pair, price, rec, conf, _ in sell_signals
        ]
        hold_signal_dicts = [
            {"pair": pair, "price": price, "recommendation": rec, "ml_confidence": conf}
            for pair, price, rec, conf, _ in hold_signals
        ]

        signals_text = self._build_signal_overview_html(
            buy_signal_dicts,
            sell_signal_dicts,
            hold_signal_dicts,
            updated_at=datetime.now().strftime('%H:%M:%S'),
            include_hold=True,
            hold_limit=10,
        )

        signals_text += "\n\n<b>🤖 Auto-Trade Status</b>\n"
        if self.is_trading:
            is_dry = Config.AUTO_TRADE_DRY_RUN
            signals_text += "🧪 DRY RUN MODE - Aktif (Simulasi)\n" if is_dry else "🔴 REAL TRADING - Aktif\n"
        else:
            signals_text += "⚪ Auto-Trade: OFF\n"
        
        try:
            await self._send_signal_batch_with_actions(
                update,
                context,
                signals_text,
                buy_signal_dicts + sell_signal_dicts,
            )
        except Exception as e:
            logger.warning(f"Error sending /signals: {e}")
            await self._send_signal_batch_with_actions(
                update,
                context,
                signals_text,
                buy_signal_dicts + sell_signal_dicts,
            )
        
    async def _run_directional_signal_scan(self, update, context, watched_pairs, direction, log_prefix):
        """Background worker: scan watchlist and send directional (BUY/SELL) signals when ready."""
        try:
            signals = await self._collect_watchlist_signals(watched_pairs, log_prefix=log_prefix)

            if direction == "BUY":
                filtered = [s for s in signals if s.get('recommendation') in ['BUY', 'STRONG_BUY']]
            else:
                filtered = [s for s in signals if s.get('recommendation') in ['SELL', 'STRONG_SELL']]

            if not filtered:
                logger.info(
                    "%s scan produced no %s signal; Telegram output suppressed "
                    "to keep command output strictly %s-only (valid=%s/%s)",
                    log_prefix,
                    direction,
                    direction,
                    len(signals),
                    len(watched_pairs),
                )
                return

            for batch in self._build_detailed_signal_message_batches(filtered):
                await self._send_signal_batch_with_actions(update, context, batch, filtered)
        except Exception as e:
            logger.error(f"❌ {log_prefix} background scan error: {e}")
            try:
                await self._send_message(update, context, f"❌ Error generating {direction} signals: {e}")
            except Exception:
                pass

    async def signal_buy_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show only BUY/STRONG_BUY from latest saved watchlist signals; no new scan."""
        await self._send_saved_signal_filter(update, context, "BUY")

    async def signal_sell_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show only SELL/STRONG_SELL from latest saved watchlist signals; no new scan."""
        await self._send_saved_signal_filter(update, context, "SELL")

    async def _run_hold_signal_scan(self, update, context, watched_pairs):
        """Background worker: scan watchlist and send HOLD signals when ready."""
        try:
            signals = await self._collect_watchlist_signals(watched_pairs, log_prefix="/signal_hold")
            hold_signals = [s for s in signals if s.get('recommendation') == 'HOLD']

            if not hold_signals:
                logger.info(
                    "/signal_hold scan produced no HOLD signal; Telegram output suppressed "
                    "to keep command output strictly HOLD-only (valid=%s/%s)",
                    len(signals),
                    len(watched_pairs),
                )
                return

            result = self._build_signal_overview_html(
                [],
                [],
                hold_signals,
                updated_at=datetime.now().strftime('%H:%M:%S'),
                include_hold=True,
            )
            await self._send_message(update, context, result, parse_mode='HTML')
        except Exception as e:
            logger.error(f"❌ /signal_hold background scan error: {e}")
            try:
                await self._send_message(update, context, f"❌ Error generating HOLD signals: {e}")
            except Exception:
                pass

    async def signal_hold_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show only HOLD from latest saved watchlist signals; no new scan."""
        await self._send_saved_signal_filter(update, context, "HOLD")

    async def _run_buysell_signal_scan(self, update, context, watched_pairs):
        """Background worker: scan watchlist and send BUY+SELL signals when ready."""
        try:
            signals = await self._collect_watchlist_signals(watched_pairs, log_prefix="/signal_buysell")
            buy_signals = [s for s in signals if s.get('recommendation') in ['BUY', 'STRONG_BUY']]
            sell_signals = [s for s in signals if s.get('recommendation') in ['SELL', 'STRONG_SELL']]

            if not buy_signals and not sell_signals:
                logger.info(
                    "/signal_buysell scan produced no BUY/SELL signals; Telegram output suppressed "
                    "to keep command output strictly BUY/SELL-only (valid=%s/%s)",
                    len(signals),
                    len(watched_pairs),
                )
                return

            result = self._build_signal_overview_html(
                buy_signals,
                sell_signals,
                [],
                updated_at=datetime.now().strftime('%H:%M:%S'),
                include_hold=False,
            )
            await self._send_signal_batch_with_actions(update, context, result, buy_signals + sell_signals)
        except Exception as e:
            logger.error(f"❌ /signal_buysell background scan error: {e}")
            try:
                await self._send_message(update, context, f"❌ Error generating BUY/SELL signals: {e}")
            except Exception:
                pass

    async def signal_buysell(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show only BUY and SELL signals for all watched pairs (no HOLD)."""
        user_id = update.effective_user.id
        watched_pairs = self._get_watched_pairs_for_user(user_id)

        if not watched_pairs:
            await self._send_message(update, context, "No watched pairs. Use /watch <PAIR> to add.")
            return

        await self._send_message(
            update, context,
            f"🔄 Scanning {len(watched_pairs)} pairs for BUY/SELL signals...\n\n"
            f"⏳ Running in background - will send results when ready..."
        )

        self._create_background_task(
            self._run_buysell_signal_scan(update, context, watched_pairs)
        )
        return

    async def signal_near_miss(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show read-only near-miss BUY/SELL candidates from saved watchlist signals."""
        user_id = update.effective_user.id
        watched_pairs = self._get_watched_pairs_for_user(user_id)

        if not watched_pairs:
            await self._send_message(update, context, "No watched pairs. Use /watch <PAIR> to add.")
            return

        try:
            signals = self._get_latest_saved_watchlist_signals(watched_pairs)
        except Exception as e:
            logger.error(f"❌ /signal near saved-signal report error: {e}")
            await self._send_message(update, context, "❌ Gagal membaca signal tersimpan.")
            return

        summary = build_near_miss_summary(signals)
        text = format_near_miss_report_html(summary, watched_count=len(watched_pairs))
        await self._send_message(update, context, text, parse_mode='HTML')
        return

    async def _signal_buysell_legacy_unused(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Legacy implementation - no longer used (kept for safety, will be removed)."""
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
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def _generate_single_signal(pair):
            signal = self._run_coroutine_in_private_loop(self._generate_signal_for_pair(pair))
            return pair, signal
        
        def _scan_buysell_parallel():
            buy_results = []
            sell_results = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_generate_single_signal, pair): pair for pair in watched_pairs}
                for future in as_completed(futures):
                    pair = futures[future]
                    try:
                        pair_result, signal = future.result()
                        if signal:
                            rec = signal.get('recommendation')
                            if rec in ['BUY', 'STRONG_BUY']:
                                buy_results.append(signal)
                            elif rec in ['SELL', 'STRONG_SELL']:
                                sell_results.append(signal)
                    except Exception as e:
                        logger.debug(f"/signal_buysell scan error for {pair}: {e}")
            return buy_results, sell_results
        
        loop = asyncio.get_event_loop()
        buy_signals, sell_signals = await loop.run_in_executor(None, _scan_buysell_parallel)
        
        if not buy_signals and not sell_signals:
            result = f"⚪ No BUY/SELL signals found in {len(watched_pairs)} pairs. All are HOLD."
            await self._send_message(update, context, result)
            return

        result = self._build_signal_overview_html(
            buy_signals,
            sell_signals,
            [],
            updated_at=datetime.now().strftime('%H:%M:%S'),
            include_hold=False,
        )
        await self._send_message(update, context, result, parse_mode='HTML')

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

    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show advanced portfolio summary and risk metrics with visual indicators"""
        user_id = update.effective_user.id
        
        try:
            # Use the previously unused Portfolio module
            summary = self.portfolio_manager.get_portfolio_summary(user_id)
            # Use the previously unused RiskManager module
            risk_metrics = self.risk_manager.get_risk_metrics(user_id)
            
            # Performance trend indicators
            pnl_emoji = "🟢" if summary['unrealized_pnl'] >= 0 else "🔴"
            trend_icon = "🚀" if summary['unrealized_pnl'] > 0 else "📉" if summary['unrealized_pnl'] < 0 else "➡️"
            gain_icon = "✅" if summary['unrealized_pnl'] >= 0 else "⚠️"
            
            text = f"📊 <b>PORTFOLIO &amp; RISK METRICS</b> {trend_icon}\n\n"
            text += f"💰 <b>Total Value:</b> {summary['total_value']:,.0f} IDR {gain_icon}\n"
            text += f"💵 <b>Available Cash:</b> {summary['available_balance']:,.0f} IDR\n"
            text += f"📈 <b>Positions Value:</b> {summary['positions_value']:,.0f} IDR\n"
            text += f"{pnl_emoji} <b>Unrealized PnL:</b> {summary['unrealized_pnl']:,.0f} IDR\n\n"
            
            # Risk metrics with icons
            win_rate = risk_metrics['win_rate']
            win_rate_icon = "🎯" if win_rate >= 50 else "⚡" if win_rate >= 30 else "⏳"
            
            text += "🛡️ <b>RISK METRICS:</b>\n"
            text += f"{win_rate_icon} Win Rate: {win_rate:.1f}%\n"
            text += f"⚖️ Sharpe Ratio: {risk_metrics['sharpe_ratio']:.2f}\n"
            text += f"✅ Winning Trades: {risk_metrics['winning_trades']}\n"
            text += f"❌ Losing Trades: {risk_metrics['losing_trades']}\n\n"
            
            if summary['num_positions'] > 0:
                text += f"📦 <b>OPEN POSITIONS ({summary['num_positions']}):</b>\n"
                # FIX: Limit displayed positions to avoid "Message is too long" (Telegram max 4096 chars)
                MAX_POSITIONS_SHOWN = 20
                positions_to_show = summary['positions'][:MAX_POSITIONS_SHOWN]
                hidden_count = summary['num_positions'] - len(positions_to_show)
                
                for pos in positions_to_show:
                    pnl_pct = pos['unrealized_pnl_pct']
                    # Enhanced visual indicators per position
                    if pnl_pct >= 10:
                        icon = "🚀"  # Mooning
                        perf = "🔥"
                    elif pnl_pct >= 5:
                        icon = "🟢"  # Strong gain
                        perf = "💪"
                    elif pnl_pct >= 0:
                        icon = "🟡"  # Small gain
                        perf = "✅"
                    elif pnl_pct >= -5:
                        icon = "🟠"  # Small loss
                        perf = "⚠️"
                    elif pnl_pct >= -10:
                        icon = "🔴"  # Big loss
                        perf = "📉"
                    else:
                        icon = "⛔"  # Heavy loss
                        perf = "🚨"
                    
                    text += f"{icon} <b>{pos['pair']}</b> {perf}: {pnl_pct:+.2f}%\n"
                    text += f"   Value: {pos['value']:,.0f} IDR\n"
                    text += f"   Entry: {pos['entry_price']:,.0f} | Cur: {pos['current_price']:,.0f}\n"
                
                if hidden_count > 0:
                    text += f"\n<i>... and {hidden_count} more positions</i>\n"
            else:
                text += "📦 <i>No open positions.</i>\n"
            
            # FIX: Truncate if still too long (safety net)
            MAX_MESSAGE_LENGTH = 4000
            if len(text) > MAX_MESSAGE_LENGTH:
                text = text[:MAX_MESSAGE_LENGTH] + "\n\n<i>... message truncated</i>"
                
            await self._send_message(update, context, text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in portfolio command: {e}")
            await self._send_message(update, context, "❌ Failed to generate portfolio summary.")

    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_info = update.effective_user
        pair_filter = None
        if context.args:
            pair_filter = context.args[0].upper().replace('/', '')
            if not pair_filter.endswith('IDR'):
                pair_filter += 'IDR'
        text = "❌ Unknown error"

        if Config.AUTO_TRADE_DRY_RUN:
            try:
                db_balance = self.db.get_balance(user_id)
                user_name = getattr(user_info, 'first_name', None) or 'User'
                username = getattr(user_info, 'username', None) or 'N/A'

                # Get trade history for stats
                trade_history = self.db.get_trade_history(user_id, limit=1000)

                # Convert sqlite3.Row to dict for safe access
                closed_trades = []
                open_trades = self.db.get_open_trades(user_id)
                # Filter out broken trades with amount=0 (legacy bug)
                open_trades = [t for t in open_trades if float(t['amount'] if 'amount' in t.keys() else 0) > 0]
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
                        pair_key = str(pair).lower().replace('/', '').replace('_', '')
                        coin_name = pair_key[:-3] if pair_key.endswith('idr') else pair_key
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
            
            # Filter out invalid pairs — FIX #4: terima btcidr dan BTC/IDR
            valid_pairs = []
            for p in watched_pairs:
                p_norm = p.strip()
                # Terima format slash: BTC/IDR
                if '/' in p_norm and p_norm.upper().endswith('/IDR'):
                    valid_pairs.append(p_norm.upper())
                # Terima format tanpa slash: btcidr / BTCIDR
                elif p_norm.lower().endswith('idr') and len(p_norm) >= 4:
                    valid_pairs.append(p_norm.lower())
                else:
                    logger.warning(f"⚠️ Skipping invalid pair during sync: {p_norm}")
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
            
            # FIX #6: Wrap blocking requests.get dengan asyncio.to_thread
            url = f"{indodax.base_url}/api/tickers"
            response = await asyncio.to_thread(requests.get, url, timeout=10)
            
            if response.status_code == 200:
                tickers = response.json().get('tickers', {})
                
                # Analyze each pair
                opportunities = []
                
                for pair_id, data in tickers.items():
                    pair = pair_id.upper().replace('_', '/')
                    price = float(data.get('last', 0))
                    volume = float(data.get('vol_idr', 0))
                    open_price = float(data.get('open', 0))
                    high = float(data.get('high', 0))
                    low = float(data.get('low', 0))
                    
                    # Calculate change vs opening price so gainers/losers reflect
                    # actual direction, not distance from intraday low.
                    if open_price > 0:
                        change_24h = ((price - open_price) / open_price) * 100
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
                    
                    # Trending = top volume with positive change
                    trending = sorted([o for o in opportunities if o['change'] > 0], key=lambda x: x['volume'], reverse=True)[:5]
                    if trending:
                        text += "\n📈 **TRENDING**\n\n"
                        for o in trending:
                            text += f"• `{o['pair']}` - `{o['price']:,.0f}` IDR (`{o['change']:+.1f}%`)\n"
                            text += f"  Vol: `{Utils.format_currency(o['volume'])}`\n\n"
                    
                    # High volume (top 15 regardless of direction)
                    high_vol = sorted(opportunities, key=lambda x: x['volume'], reverse=True)[:15]
                    if high_vol:
                        text += "\n🚀 **HIGH VOLUME**\n\n"
                        for o in high_vol:
                            text += f"• `{o['pair']}` - `{Utils.format_currency(o['volume'])}`\n"
                    
                    text += "\n" + "=" * 40
                    text += "\n\nℹ️ Change vs open (24h)"
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

    async def pair_stats_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show pair performance ranking. Usage: /pair_stats [min_trades]"""
        user_id = update.effective_user.id
        min_trades = 5
        if context.args:
            try:
                min_trades = int(context.args[0])
            except ValueError:
                pass
        
        stats = self.db.get_all_pair_performance(min_trades=min_trades)
        if not stats:
            await self._send_message(
                update, context,
                f"📊 **Pair Performance Ranking**\n\n"
                f"No pairs with >= {min_trades} closed trades yet.\n"
                f"Trade more to build stats.",
                parse_mode='Markdown'
            )
            return
        
        text = f"📊 **Pair Performance Ranking** (min {min_trades} trades)\n\n"
        for i, row in enumerate(stats[:20], 1):
            pf = row['profit_factor']
            pf_str = f"{pf:.2f}" if pf != float('inf') else "∞"
            emoji = "🟢" if pf >= 2 else "🟡" if pf >= 1 else "🔴"
            text += (
                f"{emoji} #{i} `{row['pair'].upper()}`\n"
                f"   Trades: {row['total_trades']} | Wins: {row['win_count']} | Losses: {row['loss_count']}\n"
                f"   Profit Factor: {pf_str} | Avg Win: {row['avg_profit_pct']:.2f}% | Avg Loss: {row['avg_loss_pct']:.2f}%\n\n"
            )
        
        text += "💡 Pairs with profit factor < 1.0 are auto-skipped by autotrade/autohunter."
        await self._send_message(update, context, text, parse_mode='Markdown')

    async def trade_review_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trade review. Usage: /trade_review <trade_id>"""
        user_id = update.effective_user.id
        if not context.args:
            await self._send_message(
                update, context,
                "📝 **Trade Review**\n\n"
                "Usage: `/trade_review <TRADE_ID>`\n\n"
                "Example: `/trade_review 42`\n\n"
                "Or use `/trade_reviews` to see recent reviews.",
                parse_mode='Markdown'
            )
            return
        
        try:
            trade_id = int(context.args[0])
        except ValueError:
            await self._send_message(update, context, "❌ Trade ID must be a number!")
            return
        
        review = self.db.get_trade_review(trade_id)
        if not review:
            await self._send_message(
                update, context,
                f"📝 No review found for trade ID `{trade_id}`.\n"
                f"Trade may not be closed yet, or ID doesn't exist.",
                parse_mode='Markdown'
            )
            return
        
        r = review
        hold_h = r['hold_duration_minutes'] // 60 if r['hold_duration_minutes'] else 0
        hold_m = r['hold_duration_minutes'] % 60 if r['hold_duration_minutes'] else 0
        hold_str = f"{hold_h}h {hold_m}m" if hold_h > 0 else f"{hold_m}m"
        
        pnl_sign = "+" if r['pnl_pct'] and r['pnl_pct'] > 0 else ""
        pnl_emoji = "🟢" if r['pnl_pct'] and r['pnl_pct'] > 0 else "🔴"
        
        v4_line = ""
        if r['v4_prediction']:
            v4_safe = str(r['v4_prediction']).replace('_', ' ')
            v4_conf_str = f" ({r['v4_confidence']:.0%})" if r['v4_confidence'] else ""
            v4_line = f"\n🤖 V4 Prediction: `{v4_safe}`{v4_conf_str}\n"
        
        text = f"""📝 **Trade Review: #{r['trade_id']}**

📊 Pair: `{r['pair'].upper()}`
💰 Entry: `{r['entry_price']:,.0f}` IDR
💰 Exit: `{r['exit_price']:,.0f}` IDR
{pnl_emoji} P&L: `{pnl_sign}{r['pnl_pct']:.2f}%`

⏱️ Hold Duration: `{hold_str}`
📈 Max Profit During Hold: `+{r['max_profit_pct']:.2f}%`
📉 Max Loss During Hold: `{r['max_loss_pct']:.2f}%`

🤖 ML Confidence at Entry: `{r['ml_confidence']:.0%}`{v4_line}
🚪 Exit Reason: `{r['exit_reason'] or 'N/A'}`

💡 **Lesson:**
{r['lesson']}
"""
        await self._send_message(update, context, text, parse_mode='Markdown')

    async def trade_reviews_recent_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent trade reviews. Usage: /trade_reviews [pair] [limit]"""
        pair = None
        limit = 10
        if context.args:
            # Try to parse: /trade_reviews btcidr 5
            if len(context.args) >= 1:
                first_arg = context.args[0].lower().replace('/', '')
                if first_arg.isdigit():
                    limit = int(first_arg)
                else:
                    pair = first_arg
                    if not pair.endswith('idr'):
                        pair += 'idr'
            if len(context.args) >= 2:
                try:
                    limit = int(context.args[1])
                except ValueError:
                    pass
        
        reviews = self.db.get_recent_trade_reviews(pair=pair, limit=limit)
        if not reviews:
            filter_text = f" for `{pair.upper()}`" if pair else ""
            await self._send_message(
                update, context,
                f"📝 No trade reviews{filter_text} yet.\nClose some trades to generate reviews.",
                parse_mode='Markdown'
            )
            return
        
        text = f"📝 **Recent Trade Reviews**{' — ' + pair.upper() if pair else ''}\n\n"
        for r in reviews:
            pnl_sign = "+" if r['pnl_pct'] and r['pnl_pct'] > 0 else ""
            pnl_emoji = "🟢" if r['pnl_pct'] and r['pnl_pct'] > 0 else "🔴"
            hold_h = r['hold_duration_minutes'] // 60 if r['hold_duration_minutes'] else 0
            hold_m = r['hold_duration_minutes'] % 60 if r['hold_duration_minutes'] else 0
            hold_str = f"{hold_h}h{hold_m}m" if hold_h > 0 else f"{hold_m}m"
            text += (
                f"#{r['trade_id']} `{r['pair'].upper()}` {pnl_emoji} {pnl_sign}{r['pnl_pct']:.2f}% "
                f"({hold_str}) — {r['lesson'][:60]}{'...' if len(r['lesson']) > 60 else ''}\n\n"
            )
        
        text += "Use `/trade_review <id>` for full details."
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

            top_50 = self._select_top_volume_pairs(
                all_tickers,
                limit=50,
                min_volume_idr=500_000_000,
            )

            if not top_50:
                await msg.edit_text(
                    "❌ **Tidak ada pair IDR volume tinggi yang tersedia**\n\n"
                    "Belum ada pair dengan volume > 500M IDR pada snapshot saat ini."
                )
                return

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

            # FIX #7: Hapus klaim "auto-added" yang menyesatkan.
            # Config.WATCH_PAIRS hanya in-memory, bukan watchlist user/subscribers.
            # Tampilkan saran /watch saja.
            vol_msg += "\n\n💡 Untuk memantau pair di atas:\n"
            top_pairs_str = " ".join(t['pair'].lower() for t in top_50[:5])
            vol_msg += f"`/watch {top_pairs_str}`\n"
            vol_msg += "<i>Gunakan /watch untuk menambah ke watchlist Anda secara permanen.</i>"

            await msg.edit_text(vol_msg, parse_mode='HTML')

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
                    tp_label = f"📈 Take Profit: {Utils.format_price(take_profit_1)} IDR (buy back lower)"
                else:
                    sl_label = f"📉 Stop Loss: {Utils.format_price(stop_loss)} IDR (sell lower)"
                    tp_label = f"📈 Take Profit: {Utils.format_price(take_profit_1)} IDR (sell higher)"
                
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
            await self._send_message(update, context, "❌ Admin only!")
            return
        
        import psutil
        
        uptime_seconds = time.time() - self.start_time
        uptime_str = f"{uptime_seconds/3600:.1f}h" if uptime_seconds >= 3600 else f"{uptime_seconds/60:.1f}m"
        
        # Get system info
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Count active pairs
        watched_set = sorted(set(p for pairs in self.subscribers.values() for p in pairs))
        active_pairs = len(watched_set)
        watched_display = ", ".join(watched_set[:10]) if watched_set else "Belum ada"
        if len(watched_set) > 10:
            watched_display += f", +{len(watched_set) - 10} lagi"

        learning_counts = {"trade_outcomes": 0, "pair_performance": 0, "adaptive_thresholds": 0}
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                for table_name in learning_counts:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    learning_counts[table_name] = cursor.fetchone()[0]
        except Exception as e:
            logger.debug(f"Learning data status unavailable: {e}")
        
        text = f"""
🤖 <b>Status Bot</b> <code>{datetime.now().strftime('%H:%M:%S')}</code>

<b>Mode Trading</b>
• Auto-trade: <b>{'ON' if self.is_trading else 'OFF'}</b>
• Mode uang: <b>{'DRY RUN / simulasi' if Config.AUTO_TRADE_DRY_RUN else 'REAL / uang asli'}</b>
• API Indodax: <b>{'Siap' if Config.IS_API_KEY_CONFIGURED else 'Belum diset'}</b>
• Model ML: <b>{'Siap' if self.ml_model else 'Belum siap'}</b>

<b>Kesehatan Sistem</b>
• Uptime: <code>{uptime_str}</code>
• CPU: <code>{cpu_percent}%</code>
• Memory: <code>{memory.percent}%</code> ({memory.used/1024/1024:.0f}MB)
• Telegram: <b>Aktif</b>
• Database: <b>Aktif</b>
• Harga: <b>REST polling</b>

<b>Aktivitas</b>
• User terdaftar: <code>{len(self.subscribers)}</code>
• Pair dipantau: <code>{active_pairs}</code>
• Watchlist: <code>{watched_display}</code>

<b>Data Belajar Profit</b>
• Trade outcomes: <code>{learning_counts['trade_outcomes']}</code>
• Pair performance: <code>{learning_counts['pair_performance']}</code>
• Adaptive thresholds: <code>{learning_counts['adaptive_thresholds']}</code>

<b>Batas Risiko</b>
• Stop loss: <code>{Config.STOP_LOSS_PCT}%</code>
• Take profit: <code>{Config.TAKE_PROFIT_PCT}%</code>
• Daily loss limit: <code>{Config.MAX_DAILY_LOSS_PCT}%</code>
• Max drawdown: <code>{Config.MAX_DRAWDOWN_PCT:.0%}</code>
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
        
        await self._send_message(
            update,
            context,
            text, 
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enable auto-trading (admin only)"""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return

        self.is_trading = True
        self._save_auto_trade_mode(True)
        logger.info("🟢 Auto-trading ENABLED by admin in locked DRY RUN mode")

        await update.message.reply_text(
            "✅ **Auto-trading ENABLED — DRY RUN ONLY**\n\n"
            "🔒 Mode uang dikunci: **NO MONEY / SIMULATION**\n\n"
            "Bot will now:\n"
            "• Analyze markets every 5 minutes\n"
            "• Simulate trades when signals are strong\n"
            "• Apply stop-loss & take-profit in simulation\n"
            "• Enforce risk management rules\n\n"
            "Trading uang asli hanya lewat Scalper (`/s_buy`, `/s_sell`).\n"
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
                    pair_name = trade['pair'] if hasattr(trade, '__getitem__') else getattr(trade, 'get', lambda k, d: d)('pair', 'unknown')
                    errors.append(f"Error flattening {pair_name}: {e}")
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
        winning_trades = sum(1 for t in trade_history if (t['profit_loss'] or 0) > 0)
        losing_trades = sum(1 for t in trade_history if (t['profit_loss'] or 0) <= 0)
        win_rate = (winning_trades / max(total_trades, 1)) * 100
        total_pnl = sum((t['profit_loss'] or 0) for t in trade_history)

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
        queue_size = self.signal_queue.get_stats().get("pending", 0) if self.signal_queue.is_available() else 0

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
        """Toggle auto-trading mode (dryrun/real/off) dan sinkronisasi dengan watchlist.

        Perilaku:
        - /autotrade dryrun → enable DRY RUN + import semua pair di watchlist
          admin pemanggil ke auto_trade_pairs (tanpa perlu setting ulang).
        - /autotrade real   → real mode (tetap dilock ke DRY RUN jika config melarang).
        - /autotrade off    → matikan auto-trading.
        """
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        args = getattr(context, "args", []) or []
        mode = (args[0].lower() if args else "").strip()

        dry_run_supported = bool(getattr(Config, "AUTO_TRADE_DRY_RUN", True))
        real_supported = bool(getattr(Config, "AUTO_TRADE_REAL", False))

        # Help / usage ketika mode tidak dikenali
        if mode not in ("dryrun", "dry_run", "simulation", "real", "live", "normal", "off", "disable", "stop"):
            text = (
                "⚙️ **Auto-Trade Control**\n\n"
                "Gunakan perintah:\n"
                "• `/autotrade dryrun` - Simulasi (DRY RUN), pakai watchlist yang sudah ada\n"
                "• `/autotrade off`    - Matikan auto-trading\n\n"
                "Mode REAL trading saat ini dikunci untuk keamanan (hanya Scalper yang boleh memakai uang asli)."
            )
            await self._send_message(update, context, text, parse_mode='Markdown')
            return

        if mode in ['off', 'disable', 'stop']:
            self.is_trading = False
            logger.info("🔴 Auto-trading DISABLED via /autotrade off")
            text = (
                "⏸️ **AUTO-TRADING DISABLED**\n\n"
                "Bot tidak akan membuka posisi baru secara otomatis.\n\n"
                "Gunakan `/autotrade dryrun` untuk mengaktifkan simulasi."
            )
            await self._send_message(update, context, text, parse_mode='Markdown')
            return

        # Normalisasi alias ke mode kanonik
        if mode in ['dryrun', 'dry_run', 'simulation']:
            if not dry_run_supported:
                await self._send_message(update, context, "❌ Dry run mode dimatikan di konfigurasi.", parse_mode='Markdown')
                return
            is_dry_run = True
        else:
            # Semua varian 'real' tetap dilock ke DRY RUN untuk keamanan
            if not real_supported or not getattr(Config, 'IS_API_KEY_CONFIGURED', False):
                self._lock_no_money_automation("/autotrade real blocked")
                text = (
                    "🔒 **AUTO-TRADING REAL MODE DILOCK**\n\n"
                    "AutoTrade tidak boleh memakai uang asli.\n"
                    "Mode dipaksa tetap: **DRY RUN / NO MONEY**.\n\n"
                    "✅ Trading uang asli hanya boleh lewat **Scalper** dengan tombol/command:\n"
                    "• `/s_buy <pair> <price> <idr>`\n"
                    "• `/s_sell <pair> [price] [amount]`\n\n"
                    "Gunakan `/autotrade dryrun` untuk simulasi atau `/s_menu` untuk Scalper."
                )
                await self._send_message(update, context, text, parse_mode='Markdown')
                return
            is_dry_run = False

        # Aktifkan auto-trading
        self.is_trading = True
        self._save_auto_trade_mode(is_dry_run)
        logger.info("🟡 Auto-trading ENABLED in %s mode via /autotrade", 'DRY RUN' if is_dry_run else 'REAL')

        # Auto-enable signal notifications so DRY RUN signals appear in Telegram
        if not self._are_signal_notifications_enabled():
            self._set_signal_notifications_enabled(True)
            logger.info("🔔 Signal notifications auto-enabled for DRY RUN visibility")

        # Ambil user_id admin pemanggil dan existing watchlist
        user_id = update.effective_user.id
        imported_pairs = []
        if is_dry_run:
            # Refresh watchlist dari Indodax sebelum import — ambil top 33 volume > 500M
            refresh_result = None
            if getattr(self, 'indodax', None):
                try:
                    refresh_result = await self._refresh_watchlist_from_top_volume(
                        user_id=user_id,
                        limit=33,
                        min_volume_idr=500_000_000,
                    )
                    logger.info(
                        "🔄 Watchlist refreshed during autotrade dryrun: %d pairs active",
                        refresh_result.get("active_count", 0) if refresh_result else 0,
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Watchlist refresh failed during autotrade dryrun: {e}")
            
            # Ambil watchlist yang sudah di-refresh (dari DB)
            existing_watchlist = list(self.subscribers.get(user_id, []) or [])
            if not existing_watchlist:
                existing_watchlist = self.db.get_watchlist(user_id)
            
            # Build eligible set: hanya pair dari top volume (threshold 500M)
            eligible_watchlist_pairs = set()
            if existing_watchlist and getattr(self, 'indodax', None):
                try:
                    eligible_watchlist_pairs = {
                        item["pair"]
                        for item in self._select_top_volume_pairs(
                            self.indodax.get_all_tickers(),
                            limit=500,
                            min_volume_idr=500_000_000,
                        )
                    }
                except Exception as e:
                    logger.warning(f"⚠️ Failed to build dry-run eligible watchlist from top volume: {e}")

            if existing_watchlist:
                if not hasattr(self, 'auto_trade_pairs') or self.auto_trade_pairs is None:
                    self.auto_trade_pairs = {}

                current = list(self.auto_trade_pairs.get(user_id, []) or [])
                seen_norm = {self._normalize_pair_key(p) for p in current}
                for pair in existing_watchlist:
                    norm = self._normalize_pair_key(pair)
                    if eligible_watchlist_pairs and norm not in eligible_watchlist_pairs:
                        continue
                    if norm and norm not in seen_norm:
                        current.append(pair)
                        seen_norm.add(norm)
                        imported_pairs.append(pair)
                if current:
                    self.auto_trade_pairs[user_id] = current

        # Hitung ringkasan sederhana
        user_id_for_stats = list(self.subscribers.keys())[0] if self.subscribers else user_id
        closed_count = len(self.db.get_trade_history(user_id_for_stats, limit=10000))
        open_count = len(self.db.get_open_trades(user_id_for_stats))
        all_count = closed_count + open_count

        if is_dry_run:
            lines = [
                "🧪 **AUTO-TRADING: DRY RUN MODE** 🧪",
                "",
                "✅ **Simulation Mode ACTIVE**",
                "",
                "📊 **Current Status:**",
                f"• Total Trades Executed: `{all_count}`",
                f"• Open Positions: `{open_count}`",
                f"• Closed Trades: `{closed_count}`",
                "• Mode: SIMULATION (no real money)",
                "",
                "🤖 **Bot will simulate:**",
                "• Scanning watched pairs every 5 minutes",
                "• Generating BUY/SELL signals (confidence >65%)",
                "• Applying Stop Loss (-2%) & Take Profit (+5%)",
                "• Enforcing risk limits (max 5% daily loss)",
            ]
            if imported_pairs:
                pairs_str = ", ".join(sorted({p.upper() for p in imported_pairs}))
                lines.append("")
                lines.append("📌 Existing Watchlist Imported:")
                lines.append(pairs_str)
            lines.append("")
            lines.append("💡 Gunakan `/autotrade_status` untuk melihat riwayat harian.")
            lines.append("Gunakan `/trades` untuk melihat semua trade.")
            await self._send_message(update, context, "\n".join(lines), parse_mode='Markdown')
        else:
            text = (
                "🟢 Auto-trading ENABLED in REAL mode. Gunakan dengan sangat hati-hati.\n\n"
                "Pastikan Anda memahami semua risiko dan sudah menguji strategi di DRY RUN."
            )
            await self._send_message(update, context, text, parse_mode='Markdown')

    async def autotrade_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show auto-trading status dashboard"""
        try:
            await self._autotrade_status_impl(update, context)
        except Exception as e:
            logger.error(f"autotrade_status error: {e}")
            try:
                await self._send_message(update, context, f"❌ Error menampilkan autotrade status: {e}")
            except Exception:
                pass

    async def _autotrade_status_impl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Internal implementation for autotrade_status."""
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

        # If auto-trading is ON but there are no auto-trades today, give Markdown-safe guidance
        if self.is_trading and not today_trades:
            active_pairs = list(self.auto_trade_pairs.get(user_id, []) or [])
            if not active_pairs:
                active_pairs = list(self.subscribers.get(user_id, []) or [])
            if active_pairs:
                pairs_str = ", ".join(sorted({str(p).upper() for p in active_pairs}))
                text += f"\n📌 Pair aktif dari watchlist: {pairs_str}\n"
            else:
                text += "\n📌 Pair aktif dari watchlist: belum ada. Tambahkan dengan `/watch btcidr, ethidr`.\n"
            text += "\n💡 Auto-trading aktif, tapi belum ada trade otomatis hari ini.\n"
            text += "Kemungkinan penyebab: \n"
            text += "• Pair yang di-watch belum memberi sinyal BUY/STRONG_BUY yang valid\n"
            text += "• Gate risk management (drawdown harian, VAR, korelasi) memblokir eksekusi\n"
            text += "• Data historis belum cukup (butuh puluhan candle per pair)\n\n"

            block_reasons = getattr(self, '_autotrade_block_reasons', {}) or {}
            if block_reasons:
                sorted_reasons = sorted(
                    block_reasons.values(),
                    key=lambda item: item.get('timestamp') or datetime.min,
                    reverse=True,
                )
                bucket_counts = {}
                for item in sorted_reasons:
                    bucket = item.get('bucket') or 'OTHER'
                    bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

                text += "📎 **Ringkasan blokir entry DRY RUN terbaru:**\n"
                for bucket, count in sorted(bucket_counts.items(), key=lambda kv: (-kv[1], kv[0])):
                    text += f"• {bucket}: {count}\n"

                text += "\n🧱 **Contoh pair yang terakhir diblokir:**\n"
                for item in sorted_reasons[:3]:
                    pair_label = str(item.get('pair') or 'N/A').upper()
                    bucket = item.get('bucket') or 'OTHER'
                    reason = str(item.get('reason') or '-').replace('`', "'")
                    text += f"• {pair_label} [{bucket}] — {reason}\n"
                text += "\n"

            # Context-aware tips based on current state
            if active_pairs:
                text += f"📌 Watchlist sudah aktif ({len(active_pairs)} pair). "
                text += "Bot akan otomatis entry saat sinyal BUY valid muncul.\n"
                text += "💡 Cek `/trades` untuk hasil simulasi atau tunggu notifikasi entry DRY RUN.\n\n"
            else:
                text += "✅ **Langkah untuk memulai Auto-Trade DRY RUN:**\n"
                text += "1. Tambah pair ke watchlist: `/watch btcidr, ethidr`\n"
                text += "2. Pastikan mode: `/autotrade dryrun`\n"
                text += "3. Bot akan otomatis entry saat sinyal BUY valid muncul\n\n"

        if dry_run_trades:
            text += f"  - 🧪 Dry Run: {len(dry_run_trades)}\n"
        if real_trades:
            text += f"  - 🔴 Real: {len(real_trades)}\n"

        if today_trades:
            wins = sum(1 for t in today_trades if (t['profit_loss'] or 0) > 0)
            losses = len(today_trades) - wins
            total_pnl = sum((t['profit_loss'] or 0) for t in today_trades)

            text += f"• Wins: {wins} | Losses: {losses}\n"
            text += f"• P&L: `{Utils.format_currency(total_pnl)}` IDR\n"

            # Show recent trades
            text += "\n📋 **Recent Auto-Trades:**\n"
            for trade in today_trades[:5]:
                pair = trade['pair'] if 'pair' in trade.keys() else 'N/A'
                trade_type = trade['type'] if 'type' in trade.keys() else 'N/A'
                pnl = trade['profit_loss'] or 0
                pnl_sign = '+' if pnl >= 0 else ''
                status = "✅" if pnl > 0 else "❌" if pnl < 0 else "⏳"

                # Check if dry run
                notes = str(trade['notes'] or '').lower()
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
                # Skip broken trades with amount=0 (bug lama, sudah difix)
                if float(trade_dict.get('amount', 0) or 0) <= 0:
                    continue
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
        try:
            subs = self.subscribers.get(user_id)
            if subs:
                first_pair = list(subs)[0]
                last_scan = self.last_ml_update.get(first_pair, 'N/A')
                text += f"\n⏱️ **Last Scan:** {last_scan}\n"
            else:
                text += "\n⏱️ **Last Scan:** N/A\n"
        except Exception:
            text += "\n⏱️ **Last Scan:** N/A\n"

        text += "\n💡 **Commands:**\n"
        text += "• `/autotrade dryrun` - Enable simulation mode\n"
        text += "• `/autotrade real` - Enable real trading\n"
        text += "• `/autotrade off` - Disable auto-trading\n"
        text += "• `/trades` - View all trades\n"
        text += "• `/balance` - Check balance\n"

        try:
            await self._send_message(update, context, text, parse_mode='Markdown')
        except Exception:
            # Fallback: send without Markdown if parsing fails
            clean_text = text.replace('**', '').replace('`', '').replace('_', '')
            await self._send_message(update, context, clean_text)

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
                self._cleanup_pair_runtime_state(pair, remove_auto_trade=True, user_id=user_id)
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

            # Get status dari integrated smart_hunter & ultra_hunter
            hunter_status_data = self.smart_hunter.get_status()
            ultra_status_data = self.ultra_hunter.get_status()
            is_running = hunter_status_data.get('is_running', False)
            ultra_running = ultra_status_data.get('is_running', False)

            text = "🤖 **HUNTER STATUS DASHBOARD**\n\n"

            # Smart Hunter Status
            status_emoji = "🟢" if is_running else "⚪"
            status_text = "RUNNING" if is_running else "STOPPED"
            text += f"📊 **Smart Hunter:** {status_emoji} {status_text}\n"

            # Ultra Hunter Status
            ultra_emoji = "🟢" if ultra_running else "⚪"
            ultra_text = "RUNNING" if ultra_running else "STOPPED"
            text += f"🛡️ **Ultra Hunter:** {ultra_emoji} {ultra_text}\n"
            text += "🔗 **Mode:** Terintegrasi dengan bot utama\n\n"

            # Get today's trades
            all_trades = self.db.get_trade_history(user_id, limit=50)

            hunter_trades = []
            if all_trades:
                for trade in all_trades:
                    try:
                        if hasattr(trade, 'keys'):
                            trade_dict = {key: trade[key] for key in trade.keys()}
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

            # Open positions dari integrated hunters
            active_positions = hunter_status_data.get('active_trades', 0)
            daily_trades = hunter_status_data.get('daily_trades', 0)
            daily_pnl = hunter_status_data.get('daily_pnl', 0)
            hunter_balance = hunter_status_data.get('balance', 0)

            ultra_positions = ultra_status_data.get('active_trades', 0)
            ultra_daily = ultra_status_data.get('daily_trades', 0)
            ultra_pnl = ultra_status_data.get('daily_pnl', 0)
            ultra_balance = ultra_status_data.get('balance', 0)

            text += "\n📊 **Smart Hunter Stats:**\n"
            text += f"• Active Positions: {active_positions}\n"
            text += f"• Daily Trades: {daily_trades}\n"
            text += f"• Daily P&L: `{daily_pnl:,.0f}` IDR\n"
            text += f"• Balance: `{hunter_balance:,.0f}` IDR\n"

            text += "\n🛡️ **Ultra Hunter Stats:**\n"
            text += f"• Active Positions: {ultra_positions}\n"
            text += f"• Daily Trades: {ultra_daily}\n"
            text += f"• Daily P&L: `{ultra_pnl:,.0f}` IDR\n"
            text += f"• Balance: `{ultra_balance:,.0f}` IDR\n"

            # Open positions from database
            open_trades = self.db.get_open_trades(user_id)
            if open_trades:
                text += f"\n📊 **Open Positions ({len(open_trades)}):**\n"
                for trade in open_trades[:5]:
                    try:
                        if hasattr(trade, 'keys'):
                            trade_dict = {key: trade[key] for key in trade.keys()}
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

            # Commands
            text += "\n💡 **Kontrol Hunter:**\n"
            text += "• `/smarthunter on|off` - Smart Hunter\n"
            text += "• `/smarthunter_status` - Detail Smart Hunter\n"
            text += "• `/ultrahunter start|stop` - Ultra Hunter\n"
            text += "• `/ultrahunter status` - Detail Ultra Hunter\n"
            text += "\n💡 **Commands Lain:**\n"
            text += "• `/hunter_status` - Dashboard ini\n"
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

            self._lock_no_money_automation("/smarthunter start blocked")
            await self._send_message(
                update,
                context,
                "🔒 **Smart Hunter dikunci NO MONEY**\n\n"
                "Smart Hunter tidak dijalankan untuk eksekusi uang asli.\n"
                "Gunakan sinyal/analisa sebagai referensi, tetapi eksekusi hanya boleh lewat Scalper (`/s_buy`, `/s_sell`).\n\n"
                "Status AutoTrade tetap: **DRY RUN / OFF**.",
                parse_mode='Markdown',
            )
            return

        elif action in ['off', 'stop', 'disable']:
            if not self.smart_hunter.is_running:
                await self._send_message(update, context, "⚠️ Smart Hunter is not running")
                return

            success = await self.smart_hunter.stop()
            if success:
                await self._send_message(
                    update,
                    context,
                    "🛑 **Smart Hunter stop**\n\n"
                    "Monitoring background dimatikan.\n"
                    "Posisi yang sudah terbuka tetap perlu dipantau.\n\n"
                    "Nyalakan lagi dengan `/smarthunter on`.",
                    parse_mode='Markdown',
                )
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
        """Ultra Conservative Hunter control command — Integrated version with DB persistence."""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await self._send_message(update, context, "❌ Admin only!")
            return

        if not context.args or len(context.args) == 0:
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

ℹ️ **Note:**
• Ultra Hunter now runs INTEGRATED inside the main bot
• Trades are automatically saved to database
• Running both `/autotrade` and `/ultrahunter` may cause double positions

⚠️ **Risk Warning:**
• Trades use REAL money (unless DRY RUN)
• Start with small amounts
• Monitor regularly
            """
            await self._send_message(update, context, text, parse_mode='Markdown')
            return

        action = context.args[0].lower()

        if action in ('start', 'on', 'enable'):
            if self.ultra_hunter.is_running:
                await self._send_message(update, context,
                    "⚠️ **Ultra Hunter is ALREADY RUNNING**\n\n"
                    "Use `/ultrahunter stop` to stop it first.")
                return

            if self.is_trading:
                self._lock_no_money_automation("/ultrahunter start blocked while autotrade active")
                await self._send_message(update, context,
                    "🔒 **Ultra Hunter dikunci NO MONEY**\n\n"
                    "AutoTrade sedang aktif, jadi Ultra Hunter tidak akan dijalankan.\n"
                    "Mode uang dipaksa tetap **DRY RUN / NO MONEY**.\n\n"
                    "Trading uang asli hanya boleh lewat Scalper (`/s_buy`, `/s_sell`).",
                    parse_mode='Markdown')
                return

            self._lock_no_money_automation("/ultrahunter start blocked")
            await self._send_message(update, context,
                "🔒 **Ultra Hunter dikunci NO MONEY**\n\n"
                "Ultra Hunter tidak dijalankan untuk eksekusi uang asli.\n"
                "Trading uang asli hanya boleh lewat Scalper (`/s_buy`, `/s_sell`).\n\n"
                "Status AutoTrade tetap: **DRY RUN / OFF**.",
                parse_mode='Markdown')
            return

        elif action in ('stop', 'off', 'disable'):
            if not self.ultra_hunter.is_running:
                await self._send_message(update, context,
                    "ℹ️ **Ultra Hunter is not running**\n\n"
                    "Use `/ultrahunter start` to start it")
                return

            success = await self.ultra_hunter.stop()
            if success:
                await self._send_message(update, context,
                    "✅ **ULTRA HUNTER STOPPED**\n\n"
                    "📊 Open positions remain active and continue to be monitored.\n\n"
                    "Use `/ultrahunter start` to restart")
            else:
                await self._send_message(update, context, "❌ Failed to stop Ultra Hunter")

        elif action == 'status':
            status_text = await self.ultra_hunter.send_status_message(update, context)
            await self._send_message(update, context, status_text, parse_mode='Markdown')

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

    def _send_training_notification(self, text: str, is_success: bool = True):
        """Send training result to Telegram from background thread.
        Tries to edit the original message first, then falls back to sending a new message.
        """
        import asyncio
        try:
            chat_id = getattr(self, '_retrain_chat_id', None)
            msg = getattr(self, '_pending_train_msg', None)
            loop = getattr(self, '_retrain_loop', None)
            
            if not loop or not loop.is_running():
                logger.warning("⚠️ Cannot send retrain notification: event loop not available")
                return
            
            # Send a NEW message (not edit) — more visible + notification push
            if chat_id:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.app.bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            parse_mode='Markdown'
                        ),
                        loop
                    )
                    future.result(timeout=15)
                    logger.info("✅ Retrain result sent via new message")
                except Exception as send_err:
                    logger.warning(f"⚠️ Could not send new message with Markdown: {send_err}")
                    # FALLBACK: strip formatting and send as plain text
                    try:
                        import re
                        plain_text = re.sub(r'[*_`~]', '', text)
                        future = asyncio.run_coroutine_threadsafe(
                            self.app.bot.send_message(
                                chat_id=chat_id,
                                text=plain_text,
                            ),
                            loop
                        )
                        future.result(timeout=15)
                        logger.info("✅ Retrain result sent as plain text (Markdown fallback)")
                    except Exception as fallback_err:
                        logger.error(f"❌ Plain text fallback also failed: {fallback_err}")
            else:
                logger.warning("⚠️ Cannot send retrain notification: chat_id not available")

            # Also try to edit the original message as a record
            if msg:
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        msg.edit_text(
                            f"~~{msg.text}~~\n\n✅ *Training completed — see new message below*",
                            parse_mode='Markdown'
                        ),
                        loop
                    )
                    future.result(timeout=10)
                except Exception as edit_err:
                    logger.debug(f"Could not edit original message: {edit_err}")
                
        except Exception as notify_err:
            logger.error(f"❌ Failed to send retrain notification: {notify_err}")

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
            # Get ALL pairs from database/watchlists, then normalize pair-name variants
            # before showing the summary and passing data to ML.
            data_frames, pairs_with_data = self._collect_normalized_training_data(
                pairs_to_check=None,
                limit=2000,
                min_candles=100,
                include_small_groups=True,
                include_zero_summary=True,
            )

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
            self._retrain_chat_id = update.effective_chat.id
            self._retrain_loop = asyncio.get_running_loop()

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
        """Run ML training in background thread (non-blocking)
        FIX: Also trains V4 trade-outcome model so manual /retrain activates V4 filters.
        """
        try:
            logger.info(f"🤖 Background ML training started with {len(all_data)} candles")

            if self.ml_version == 'V2':
                success = self.ml_model.train(all_data, use_multi_class=False)
            else:
                success = self.ml_model.train(all_data)

            # --- V1/V2 metrics ---
            if success:
                accuracy = getattr(self.ml_model, 'last_accuracy', 'N/A')
                recall = getattr(self.ml_model, 'last_recall', 'N/A')
                precision = getattr(self.ml_model, 'last_precision', 'N/A')
                f1 = getattr(self.ml_model, 'last_f1', 'N/A')

                accuracy_str = f"{accuracy:.2%}" if isinstance(accuracy, (int, float)) else str(accuracy)
                recall_str = f"{recall:.2%}" if isinstance(recall, (int, float)) else str(recall)
                precision_str = f"{precision:.2%}" if isinstance(precision, (int, float)) else str(precision)
                f1_str = f"{f1:.2%}" if isinstance(f1, (int, float)) else str(f1)

                undersample_info = getattr(self.ml_model, 'last_undersample_info', None)
                undersample_text = ""
                if undersample_info and undersample_info.get('applied'):
                    # FIX: Use triple backticks for multiline code blocks instead of single backticks
                    # to avoid Telegram Markdown parse errors with multiline content
                    undersample_text = (
                        f"\n📊 **Undersampling Applied:**\n"
                        f"```\n{undersample_info['before']}\n```\n\n"
                        f"```\n{undersample_info['after']}\n```"
                    )
                elif undersample_info:
                    msg_text = undersample_info.get('message', 'Balanced')
                    # Escape backticks to prevent breaking inline code entity
                    msg_text = msg_text.replace('`', "'")
                    undersample_text = f"\n📊 **Class Balance:**\n`{msg_text}`"

                text_v12 = (
                    f"✅ **ML V1/V2 Retrained!**\n\n"
                    f"📊 Data used: `{len(all_data)}` candles\n"
                    f"🎯 Accuracy: `{accuracy_str}`\n"
                    f"🎯 Recall: `{recall_str}`\n"
                    f"🎯 Precision: `{precision_str}`\n"
                    f"🎯 F1 Score: `{f1_str}`\n"
                    f"{undersample_text}"
                )
            else:
                text_v12 = "❌ Failed to train V1/V2 model."

            # --- V4 trade-outcome model ---
            v4_text = ""
            try:
                logger.info("🤖 Training ML V4 (trade outcome based)...")
                from analysis.ml_signal_trainer import train_model_from_signals
                v4_success, v4_msg = train_model_from_signals(
                    self, tp_pct=3, sl_pct=2, window=10, days_back=30
                )
                if v4_success and getattr(self, '_last_signal_outcomes', None):
                    if not self.ml_model_v4:
                        from analysis.ml_model_v4 import MLTradingModelV4
                        self.ml_model_v4 = MLTradingModelV4()
                    v4_train_success = self.ml_model_v4.train_from_outcomes(
                        self._last_signal_outcomes
                    )
                    if v4_train_success:
                        v4_status = self.ml_model_v4.get_status()
                        v4_text = (
                            f"\n\n🤖 **ML V4 Trained (Trade Outcome)**\n"
                            f"🎯 Win Rate: `{v4_status.get('win_rate', 0):.1%}`\n"
                            f"📈 Profit Factor: `{v4_status.get('profit_factor', 0):.2f}`\n"
                            f"💰 Expectancy: `{v4_status.get('expectancy', 0):.2f}%`"
                        )
                        logger.info(
                            f"✅ ML V4 trained via manual /retrain: "
                            f"win_rate={v4_status.get('win_rate'):.1%}, "
                            f"profit_factor={v4_status.get('profit_factor'):.2f}"
                        )
                    else:
                        v4_text = "\n\n⏳ ML V4: training returned False (need more labeled signals)"
                else:
                    v4_text = f"\n\n⏳ ML V4: {v4_msg}"
            except Exception as v4_e:
                logger.warning(f"⚠️ V4 training skipped in manual /retrain: {v4_e}")
                v4_text = "\n\n⏳ ML V4: not available yet (need more signal history)"

            text = text_v12 + v4_text + "\n\n💡 Signals will now include ML confidence!\n\n🔔 **RETRAIN SELESAI**"

            # Send result via Telegram (edit old msg or send new msg to chat)
            self._send_training_notification(text, is_success=True)
            logger.info("✅ Background ML training completed (V1/V2 + V4)")

        except Exception as e:
            logger.error("❌ Background ML training failed: %s", e)
            import traceback
            logger.error(traceback.format_exc())
            error_text = f"❌ Training error: {str(e)}\n\n🔔 **RETRAIN SELESAI**"
            self._send_training_notification(error_text, is_success=False)

    # =====================================================================
    # MAX DRAWDOWN CIRCUIT BREAKER
    # =====================================================================

    def _calculate_equity(self, user_id):
        """Calculate total equity = cash balance + current value of open positions."""
        try:
            balance = self.db.get_balance(user_id)
            open_trades = self.db.get_open_trades(user_id)
            open_value = 0.0
            for trade in open_trades:
                pair = trade['pair']
                amount = float(trade['amount'])
                # Get current price from cache or API
                current_price = self.price_data.get(pair, {}).get('last')
                if not current_price:
                    try:
                        ticker = self.indodax.get_ticker(pair)
                        current_price = ticker['last'] if ticker else float(trade['price'])
                    except Exception:
                        current_price = float(trade['price'])
                open_value += current_price * amount
            return balance + open_value
        except Exception as e:
            logger.error(f"❌ Error calculating equity: {e}")
            return self.db.get_balance(user_id)

    def _check_max_drawdown(self, user_id):
        """
        Check if equity drawdown from peak exceeds limit.
        Returns (allowed: bool, message: str).
        If drawdown exceeds limit, auto-trade is stopped globally.
        """
        try:
            current_equity = self._calculate_equity(user_id)
            peak = self.db.get_equity_peak(user_id)

            # Initialize peak if not set or equity is higher
            if peak is None or current_equity > peak:
                self.db.set_equity_peak(user_id, current_equity)
                logger.info(f"📈 Equity peak updated for user {user_id}: {current_equity:,.0f}")
                return True, "Peak updated"

            drawdown = (peak - current_equity) / peak
            if drawdown >= Config.MAX_DRAWDOWN_PCT:
                self.is_trading = False
                msg = (
                    f"🚨 <b>CIRCUIT BREAKER TRIGGERED</b>\n\n"
                    f"📉 Drawdown: <code>{drawdown:.1%}</code> (limit <code>{Config.MAX_DRAWDOWN_PCT:.1%}</code>)\n"
                    f"💰 Peak: <code>{Utils.format_currency(peak)}</code>\n"
                    f"💰 Now: <code>{Utils.format_currency(current_equity)}</code>\n\n"
                    f"⛔ Auto-trade has been STOPPED.\n"
                    f"Use <code>/reset_drawdown</code> to re-enable after review."
                )
                logger.error(f"[CIRCUIT_BREAKER] {msg}")
                # Notify admins asynchronously
                # Sanitize HTML to prevent parse-entity errors (Bug Critical #4).
                msg_safe = sanitize_telegram_html(msg)
                for admin_id in Config.ADMIN_IDS:
                    try:
                        asyncio.create_task(
                            self.app.bot.send_message(chat_id=admin_id, text=msg_safe, parse_mode='HTML')
                        )
                    except Exception:
                        pass
                return False, f"Drawdown {drawdown:.1%} exceeds limit"

            return True, f"Drawdown {drawdown:.1%} (limit {Config.MAX_DRAWDOWN_PCT:.1%})"
        except Exception as e:
            logger.error(f"❌ Error in max drawdown check: {e}")
            return True, "Check error, allowing trade"

    async def cmd_reset_drawdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin command: reset equity peak and re-enable auto-trade."""
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Admin only!")
            return
        user_id = list(self.subscribers.keys())[0] if self.subscribers else update.effective_user.id
        current_equity = self._calculate_equity(user_id)
        self.db.set_equity_peak(user_id, current_equity)
        self.is_trading = True
        await update.message.reply_text(
            f"✅ <b>Drawdown Reset</b>\n\n"
            f"💰 New equity peak: <code>{Utils.format_currency(current_equity)}</code>\n"
            f"🔄 Auto-trade re-enabled.\n\n"
            f"⚠️ Review cause of drawdown before continuing.",
            parse_mode='HTML'
        )
        logger.info(f"✅ Drawdown reset by admin. New peak: {current_equity:,.0f}. Auto-trade re-enabled.")

    async def cmd_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Open Crypto Dashboard in browser."""
        # Determine dashboard URL (public URL must be set for Telegram button to work)
        dashboard_url = Config.DASHBOARD_URL if Config.DASHBOARD_URL else Config.WEBHOOK_URL
        
        if not dashboard_url:
            await update.message.reply_text(
                "⚠️ <b>Dashboard URL not configured</b>\n\n"
                "Please set <code>DASHBOARD_URL</code> in your <code>.env</code> file.\n\n"
                "Example:\n"
                "<code>DASHBOARD_URL=http://your-vps-ip:8080</code>\n\n"
                "Then restart the bot.",
                parse_mode='HTML'
            )
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 Open Dashboard", url=dashboard_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📱 <b>Crypto Bot Dashboard</b>\n\n"
            "View your portfolio, signals, and adaptive thresholds in real-time.\n\n"
            "Click the button below to open the dashboard in your browser.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    # =====================================================================
    # PENDING ORDER EXECUTION TRACKING
    # =====================================================================

    async def check_pending_orders(self):
        """Check status of pending limit orders. Called periodically."""
        try:
            pending = self.db.get_pending_orders(status='PENDING')
            if not pending:
                return

            logger.info(f"[PENDING_ORDER] Checking {len(pending)} pending orders")
            for order in pending:
                db_id = order['id']
                raw_order_id = order['order_id']
                order_id = "" if raw_order_id is None else str(raw_order_id)
                pair = order['pair']
                limit_price = order['limit_price']
                placed_at = order['placed_at']
                trade_id = order['trade_id'] if 'trade_id' in order.keys() else None

                # Calculate elapsed time
                try:
                    if isinstance(placed_at, str):
                        placed_dt = datetime.fromisoformat(placed_at.replace('Z', '+00:00'))
                    else:
                        placed_dt = placed_at
                    elapsed_minutes = (datetime.now() - placed_dt).total_seconds() / 60
                except Exception:
                    elapsed_minutes = 0

                # Timeout config (default 5 minutes)
                timeout_minutes = getattr(Config, 'LIMIT_ORDER_TIMEOUT_MINUTES', 5)

                is_dry_run = order_id.startswith('DRY-')

                if is_dry_run:
                    # DRY RUN realistic fill simulation:
                    # Use ASK price (not last) — limit BUY only fills when ask <= limit
                    current_price_data = self.price_data.get(pair, {})
                    market_price = None
                    try:
                        ticker = self.indodax.get_ticker(pair)
                        if ticker:
                            # Prefer ask (sell) for BUY fill realism
                            ask_price = ticker.get('sell') or ticker.get('ask')
                            last_price = ticker.get('last')
                            market_price = float(ask_price) if ask_price else (float(last_price) if last_price else None)
                    except Exception:
                        pass
                    if market_price is None:
                        market_price = current_price_data.get('last')

                    if market_price and market_price <= limit_price:
                        meta = {}
                        try:
                            raw_notes = order.get('notes') if hasattr(order, 'get') else None
                            if raw_notes:
                                meta = json.loads(raw_notes)
                        except Exception:
                            meta = {}
                        # Calculate realistic fill price with slippage for all cases
                        slippage_pct = float(getattr(Config, 'DRYRUN_SLIPPAGE_PCT', 0.001) or 0.001)
                        fill_price = float(limit_price) * (1 + slippage_pct)
                        if not trade_id:
                            fee_rate = float(getattr(Config, 'TRADING_FEE_RATE', 0.003) or 0.003)
                            amount = float(order.get('amount') or 0)
                            # Fee applied on fill (entry side)
                            fee = fill_price * amount * fee_rate
                            ml_conf = float(meta.get('ml_confidence', 0.5) or 0.5)
                            signal_source = str(meta.get('signal_source') or 'auto')
                            trade_id = self.db.add_trade(
                                user_id=order['user_id'],
                                pair=pair,
                                trade_type='BUY',
                                price=fill_price,
                                amount=amount,
                                total=fill_price * amount,
                                fee=fee,
                                signal_source=signal_source,
                                ml_confidence=ml_conf,
                                notes=f"[DRY RUN] Filled limit order_id: {order_id} @ {fill_price:,.0f} (limit={float(limit_price):,.0f}, slip={slippage_pct*100:.2f}%, fee={fee:,.0f})",
                            )
                            stop_loss = meta.get('stop_loss')
                            take_profit_1 = meta.get('take_profit_1')
                            take_profit_2 = meta.get('take_profit_2')
                            atr_value = meta.get('atr')
                            try:
                                tp_data = self.trading_engine.calculate_stop_loss_take_profit(fill_price, 'BUY', atr_value=atr_value)
                                stop_loss = tp_data.get('stop_loss', stop_loss)
                                take_profit_1 = tp_data.get('take_profit_1', take_profit_1)
                                take_profit_2 = tp_data.get('take_profit_2', take_profit_2)
                            except Exception:
                                pass
                            try:
                                if stop_loss and take_profit_1 and take_profit_2:
                                    self.price_monitor.set_price_level(order['user_id'], trade_id, pair, fill_price, float(stop_loss), float(take_profit_1), float(take_profit_2), amount)
                            except Exception:
                                pass
                        # Simulate fill with realistic price
                        self.db.update_pending_order_filled(
                            db_id,
                            fill_price=fill_price,
                            notes=f"[DRY RUN] Simulated fill @ {fill_price:,.0f} (limit={limit_price:,.0f}, market={market_price:,.0f}, slip={slippage_pct*100:.2f}%)",
                            trade_id=trade_id,
                        )
                        logger.info(f"[PENDING_ORDER] DRY RUN filled: {pair} @ {fill_price:,.0f} (limit={limit_price:,.0f}, market={market_price:,.0f})")
                    elif market_price and market_price >= limit_price * (1 + Config.LIMIT_ORDER_CANCEL_DISTANCE_PCT / 100.0):
                        self.db.update_pending_order_cancelled(
                            db_id,
                            notes=f"[DRY RUN] Cancelled chase: market {market_price:,.0f} > limit {limit_price:,.0f} by {Config.LIMIT_ORDER_CANCEL_DISTANCE_PCT:.2f}%"
                        )
                        if trade_id:
                            self.db.close_trade(trade_id=trade_id, sell_price=limit_price, sell_amount=order['amount'], order_id=order_id, reason="LIMIT_NOT_FILLED_CANCELLED")
                            self.price_monitor.remove_price_level(order['user_id'], trade_id)
                        logger.info(f"[PENDING_ORDER] DRY RUN chase-cancelled: {pair} order_id={order_id}")
                    elif elapsed_minutes >= timeout_minutes:
                        # Simulate cancel
                        self.db.update_pending_order_cancelled(
                            db_id,
                            notes=f"[DRY RUN] Cancelled after {elapsed_minutes:.0f}m (market {market_price:,.0f} > limit {limit_price:,.0f})"
                        )
                        if trade_id:
                            self.db.close_trade(trade_id=trade_id, sell_price=limit_price, sell_amount=order['amount'], order_id=order_id, reason="LIMIT_NOT_FILLED_TIMEOUT")
                            self.price_monitor.remove_price_level(order['user_id'], trade_id)
                        logger.info(f"[PENDING_ORDER] DRY RUN cancelled: {pair} after {elapsed_minutes:.0f}m")
                else:
                    # Real trading: check via API
                    try:
                        open_orders = self.indodax.get_open_orders(pair)
                        order_still_open = any(
                            str(o.get('order_id')) == str(order_id) for o in open_orders
                        )
                        if not order_still_open:
                            # Order no longer open = filled or cancelled
                            # Assume filled for simplicity (Indodax doesn't give easy fill history)
                            self.db.update_pending_order_filled(
                                db_id, fill_price=limit_price,
                                notes=f"Filled (order no longer in open orders)"
                            )
                            logger.info(f"[PENDING_ORDER] Real order filled: {pair} order_id={order_id}")
                        else:
                            try:
                                ticker = self.indodax.get_ticker(pair)
                                market_price = ticker['last'] if ticker else None
                            except Exception:
                                market_price = None
                            if market_price and market_price >= limit_price * (1 + Config.LIMIT_ORDER_CANCEL_DISTANCE_PCT / 100.0):
                                cancel_result = self.indodax.cancel_order(pair, order_id)
                                if cancel_result and cancel_result.get('success') == 1:
                                    self.db.update_pending_order_cancelled(
                                        db_id,
                                        notes=f"Cancelled chase: market {market_price:,.0f} > limit {limit_price:,.0f} by {Config.LIMIT_ORDER_CANCEL_DISTANCE_PCT:.2f}%"
                                    )
                                    if trade_id:
                                        self.db.close_trade(trade_id=trade_id, sell_price=limit_price, sell_amount=order['amount'], order_id=order_id, reason="LIMIT_NOT_FILLED_CANCELLED")
                                        self.price_monitor.remove_price_level(order['user_id'], trade_id)
                                    logger.info(f"[PENDING_ORDER] Real order chase-cancelled: {pair} order_id={order_id}")
                                else:
                                    logger.warning(f"[PENDING_ORDER] Chase cancel failed for {pair} order_id={order_id}: {cancel_result}")
                        if order_still_open and elapsed_minutes >= timeout_minutes:
                            # Cancel timeout order
                            cancel_result = self.indodax.cancel_order(pair, order_id)
                            if cancel_result and cancel_result.get('success') == 1:
                                self.db.update_pending_order_cancelled(
                                    db_id,
                                    notes=f"Cancelled by bot after {elapsed_minutes:.0f}m timeout"
                                )
                                if trade_id:
                                    self.db.close_trade(trade_id=trade_id, sell_price=limit_price, sell_amount=order['amount'], order_id=order_id, reason="LIMIT_NOT_FILLED_TIMEOUT")
                                    self.price_monitor.remove_price_level(order['user_id'], trade_id)
                                logger.info(f"[PENDING_ORDER] Real order cancelled: {pair} order_id={order_id} after {elapsed_minutes:.0f}m")
                            else:
                                logger.warning(f"[PENDING_ORDER] Cancel failed for {pair} order_id={order_id}: {cancel_result}")
                    except Exception as e:
                        logger.error(f"[PENDING_ORDER] Error checking order {order_id} for {pair}: {e}")
        except Exception as e:
            logger.error(f"❌ Error in check_pending_orders: {e}")

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

    def _estimate_candle_limit_for_days(
        self,
        days: int,
        interval_minutes: int = 15,
        warmup_candles: int = 200,
        hard_cap: int = 50000,
    ) -> int:
        """Estimate candle limit to avoid silently truncating long backtest periods."""
        safe_days = max(1, int(days))
        safe_interval = max(1, int(interval_minutes))
        candles_per_day = (24 * 60) // safe_interval
        required = (safe_days * candles_per_day) + max(0, int(warmup_candles))
        return min(max(required, 500), hard_cap)

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
            candle_limit = self._estimate_candle_limit_for_days(days)
            
            # Get price data
            df = self.db.get_price_history(pair, limit=candle_limit)
            
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
            df = self.db.get_price_history(pair, limit=2000)
            
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
            winning = [t for t in trades if (t['profit_loss'] or 0) > 0]
            losing = [t for t in trades if (t['profit_loss'] or 0) < 0]

            win_rate = len(winning) / len(trades) if trades else 0
            avg_win = sum((t['profit_loss'] or 0) for t in winning) / len(winning) if winning else 0
            avg_loss = abs(sum((t['profit_loss'] or 0) for t in losing) / len(losing)) if losing else 0
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
            from datetime import datetime, timedelta
            start_date = datetime.now() - timedelta(days=days)
            candle_limit = self._estimate_candle_limit_for_days(days)

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
                df = self.db.get_price_history(pair, limit=candle_limit)
                if df is not None and 'timestamp' in df.columns:
                    df = df[df['timestamp'] >= start_date]
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

        if text in ("📱 Menu", "Menu"):
            await self.menu(update, context)
            return

        if text in ("⚙️ Settings", "Settings"):
            await self.settings(update, context)
            return

        if text in ("📊 Market", "Market"):
            await self.market_scan(update, context)
            return

        if text in ("💼 Portfolio", "Portfolio"):
            await self.portfolio(update, context)
            return

        if text in ("🔔 Alerts", "Alerts"):
            await self.notifications(update, context)
            return

        if text in ("📈 Signal", "Signal"):
            context.args = []
            await self.signals(update, context)
            return

        if text in ("💰 Price", "Price"):
            context.user_data['pending_quick_action'] = 'price'
            await self._send_message(
                update,
                context,
                "💰 Harga pair apa?\nKetik contoh: <code>btcidr</code> atau gunakan <code>/price btcidr</code>.",
                parse_mode='HTML',
            )
            return

        if text in ("📘 Panduan", "Panduan", "Help"):
            await self.help(update, context)
            return

        if text in ("🤖 Auto-Trade", "Auto-Trade", "Autotrade"):
            await self._show_autotrade_quick_panel(update, context)
            return

        if text in ("⚙️ Admin", "Admin"):
            await self._show_admin_panel(update, context)
            return

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
                        result_text = self._run_coroutine_in_private_loop(
                            self.execute_manual_trade(user_id, order_data)
                        )

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
            pending_quick_action = context.user_data.pop('pending_quick_action', None)
            if pending_quick_action == 'price':
                context.args = [pair]
                await self.price(update, context)
                return
            if pending_quick_action == 'watch':
                context.args = [pair]
                await self.watch(update, context)
                return

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
• <code>/signal &lt;PAIR&gt;</code> - Signal lengkap 1 pair
• <code>/signals</code> - Semua signal di watchlist
• <code>/signal buy</code> - Tampilkan hanya pair BUY/STRONG_BUY
• <code>/signal sell</code> - Tampilkan hanya pair SELL/STRONG_SELL
• <code>/signal hold</code> - Tampilkan hanya pair HOLD
• <code>/signal buysell</code> - Tampilkan pair BUY + SELL tanpa HOLD
• <code>/signal on|off</code> - Kontrol notifikasi otomatis
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

        if data == 'menu_home':
            is_admin = user_id in Config.ADMIN_IDS
            text = build_main_menu_html(
                is_admin=is_admin,
                is_trading=self.is_trading,
                is_dry_run=Config.AUTO_TRADE_DRY_RUN,
                watch_count=len(self.subscribers.get(user_id, [])),
                autotrade_count=len(self.auto_trade_pairs.get(user_id, [])),
                dashboard_ready=bool(Config.DASHBOARD_URL),
            )
            await query.edit_message_text(
                text,
                parse_mode='HTML',
                reply_markup=self._build_quick_keyboard(is_admin),
            )
            return

        if data == 'help':
            try:
                await self.help(update, context)
            except Exception as e:
                logger.error(f"[CALLBACK] help error: {e}")
                await self._safe_callback_reply(query, f"❌ Help error: {e}")
            return

        if data.startswith('nav_'):
            section = data.replace('nav_', '', 1)
            is_admin = user_id in Config.ADMIN_IDS
            text = build_menu_section_html(
                section,
                is_admin=is_admin,
                dashboard_ready=bool(Config.DASHBOARD_URL),
            )
            await query.edit_message_text(
                text,
                parse_mode='HTML',
                reply_markup=self._build_menu_panel_keyboard(section, is_admin=is_admin),
            )
            return

        if data == 'market_scan_quick':
            await self._run_callback_command(query, update, context, self.market_scan, "📊 Market Scan")
            return

        if data == 'balance_quick':
            await self._run_callback_command(query, update, context, self.balance, "💰 Balance")
            return

        if data == 'portfolio_quick':
            await self._run_callback_command(query, update, context, self.portfolio, "💼 Portfolio")
            return

        if data == 'pair_stats_quick':
            await self._run_callback_command(query, update, context, self.pair_stats_cmd, "📊 Pair Stats")
            return

        if data == 'notifications_quick':
            await self._run_callback_command(query, update, context, self.notifications, "🔔 Notifications")
            return

        if data == 'signals_quick':
            context.args = []
            await self._run_callback_command(query, update, context, self.signals, "📈 Signals")
            return

        if data == 'status_quick':
            await self._run_callback_command(query, update, context, self.status, "⚙️ Status")
            return

        if data == 'autotrade_status_quick':
            await self._run_callback_command(query, update, context, self.autotrade_status, "🤖 Auto-Trade Status")
            return

        if data == 'autotrade_quick':
            try:
                await self._show_autotrade_quick_panel(update, context)
            except Exception as e:
                logger.error(f"[CALLBACK] autotrade_quick error: {e}")
                await self._safe_callback_reply(query, f"❌ Auto-Trade panel error: {e}")
            return

        if data == 'watch_quick':
            context.user_data['pending_quick_action'] = 'watch'
            await query.edit_message_text(
                "🔔 <b>Tambah Alerts</b>\n\n"
                "Ketik <code>btcidr</code> untuk mulai pantau 1 pair.\n"
                "Bisa juga pakai command: <code>/watch btcidr, ethidr</code>.",
                parse_mode='HTML',
                reply_markup=self._build_menu_panel_keyboard("alerts", is_admin=user_id in Config.ADMIN_IDS),
            )
            return

        # Watch pair callbacks
        if data.startswith('watch_'):
            pair = data.replace('watch_', '')
            context.args = [pair]
            try:
                await self.watch(update, context)
            except Exception as e:
                logger.error(f"[CALLBACK] watch_{pair} error: {e}")
                await self._safe_callback_reply(query, f"❌ Watch error: {e}")
            return

        # Signal callbacks
        elif data.startswith('signal_'):
            pair = data.replace('signal_', '')
            if pair in ('quick', 'default'):
                context.user_data['pending_quick_action'] = 'signal'
                await query.edit_message_text("🤖 Signal untuk pair apa?\nKetik nama pair, contoh: `pippinidr`", parse_mode='Markdown')
            else:
                context.args = [pair]
                try:
                    await self.get_signal(update, context)
                except Exception as e:
                    logger.error(f"[CALLBACK] signal_{pair} error: {e}")
                    await self._safe_callback_reply(query, f"❌ Signal error: {e}")
            return

        # Price callbacks
        elif data.startswith('price_'):
            pair = data.replace('price_', '')
            if pair in ('quick', 'default'):
                context.user_data['pending_quick_action'] = 'price'
                await query.edit_message_text("💰 Harga pair apa?\nKetik nama pair, contoh: `btcidr` atau `pippinidr`.")
            else:
                context.args = [pair]
                try:
                    await self.price(update, context)
                except Exception as e:
                    logger.error(f"[CALLBACK] price_{pair} error: {e}")
                    await self._safe_callback_reply(query, f"❌ Price error: {e}")
            return
        
        # Admin callbacks
        if data == 'admin_panel':
            try:
                await self._show_admin_panel(update, context)
            except Exception as e:
                logger.error(f"[CALLBACK] admin_panel error: {e}")
                await self._safe_callback_reply(query, f"❌ Admin panel error: {e}")
            return

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
            return

        if data == 'admin_logs':
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
            return

        if data == 'admin_backtest':
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
            return

        if data == 'admin_retrain':
            if user_id in Config.ADMIN_IDS:
                context.args = []
                try:
                    await self.retrain_ml(update, context)
                except Exception as e:
                    logger.error(f"[CALLBACK] admin_retrain error: {e}")
                    await self._safe_callback_reply(query, f"❌ Retrain error: {e}")
            return

        # Auto-trade pair addition from /start menu
        if data == 'autotrade_add_pair':
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
            return

        # Backtest plot callback
        if data.startswith('backtest_plot_'):
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
            return

        # Ultra Hunter callbacks
        if data == 'ultra_start_confirm':
            if user_id in Config.ADMIN_IDS:
                self._lock_no_money_automation("ultra_start_confirm blocked")
                context.user_data.pop('ultra_start_pending', None)
                await query.edit_message_text(
                    "🔒 **Ultra Hunter tetap dikunci NO MONEY**\n\n"
                    "Konfirmasi start diblokir oleh safety policy.\n"
                    "Trading uang asli hanya boleh lewat Scalper (`/s_buy`, `/s_sell`).",
                    parse_mode='Markdown'
                )
            return

        if data == 'ultra_cancel':
            if user_id in Config.ADMIN_IDS:
                context.user_data.pop('ultra_start_pending', None)
                await query.edit_message_text(
                    "❌ **Ultra Hunter start cancelled**\n\n"
                    "Use `/stop_trading` first if you want to run Ultra Hunter safely",
                    parse_mode='Markdown'
                )
            return

        # =====================================================================
        # Catch-all: unrecognized callback data
        # =====================================================================
        logger.warning(f"[CALLBACK] Unrecognized callback data: {data}")
        try:
            await query.edit_message_text(
                f"⚠️ <b>Tombol tidak dikenali</b>\n\n"
                f"Callback: <code>{data}</code>\n\n"
                f"Gunakan <code>/help</code> untuk melihat command yang tersedia.",
                parse_mode='HTML',
            )
        except Exception:
            await query.message.reply_text(
                f"⚠️ Tombol tidak dikenali: {data}\nGunakan /help untuk melihat menu.",
                parse_mode='HTML',
            )

    # =============================================================================
    # CORE TRADING LOGIC
    # =============================================================================
    
    def _subscribe_pair(self, pair):
        """Subscribe to WebSocket channel for a pair - DISABLED, using REST polling only"""
        # WebSocket subscription DISABLED - using REST API polling instead
        logger.info(f"📡 Watch request for {pair} (WebSocket disabled, will poll via REST API)")
        return
    
    async def _load_historical_data(self, pair, limit=None):
        """
        Load historical price data for ML analysis
        OPTIMIZED: Non-blocking async API calls
        Lookback default dari Config.HISTORICAL_DATA_LIMIT (default 500 tick).
        """
        if limit is None:
            limit = getattr(Config, 'HISTORICAL_DATA_LIMIT', 200)
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
        # Guard concurrent signal generation across /signals commands and background scans.
        start_wait = time.time()
        acquired = False
        while not acquired:
            acquired = self._signal_generation_semaphore.acquire(blocking=False)
            if acquired:
                break
            if time.time() - start_wait >= 60:
                logger.warning(f"⏱️ Signal generation semaphore timeout for {pair}")
                return None
            await asyncio.sleep(0.05)
        try:
            return await generate_signal_for_pair(self, pair)
        finally:
            self._signal_generation_semaphore.release()
    
    def _format_signal_message(self, signal):
        return format_signal_message(signal)

    def _generate_strength_bar(self, strength):
        return generate_strength_bar(strength)

    def _format_signal_message_html(self, signal):
        return format_signal_message_html(signal)

    def _format_market_scan_signal(self, signal):
        return format_market_scan_signal(signal)

    def _generate_strength_bar_html(self, strength):
        return generate_strength_bar_html(strength)

    def _signal_visual(self, recommendation):
        return signal_visual(recommendation)

    def _format_signal_list_price(self, price):
        return format_signal_list_price(price)

    def _format_signal_scan_line_html(self, signal):
        return format_signal_scan_line_html(signal)

    def _format_signal_section_html(self, title, signals):
        return format_signal_section_html(title, signals)

    def _build_signal_overview_html(
        self,
        buy_signals,
        sell_signals,
        hold_signals,
        updated_at=None,
        include_hold=True,
        hold_limit=None,
    ):
        return build_signal_overview_html(
            buy_signals,
            sell_signals,
            hold_signals,
            updated_at=updated_at,
            include_hold=include_hold,
            hold_limit=hold_limit,
        )

    async def _monitor_strong_signal(self, pair, signal=None):
        return await monitor_strong_signal(self, pair, signal=signal)

    async def _check_trading_opportunity(self, pair, signal=None):
        return await check_trading_opportunity(self, pair, signal=signal)

    async def _analyze_market_intelligence(self, pair, current_price):
        return await analyze_market_intelligence(self, pair, current_price)

    async def _get_support_resistance_for_pair(self, pair):
        return await get_support_resistance_for_pair(self, pair)

    def _detect_market_regime(self, pair):
        return detect_market_regime(self, pair)

    async def _execute_auto_sell(self, pair, signal, current_price, user_id, is_dry_run):
        return await execute_auto_sell(self, pair, signal, current_price, user_id, is_dry_run)

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
        return detect_spoofing(self, pair, bids, asks)

    def _update_heatmap(self, pair: str, bids: list, asks: list):
        update_heatmap(self, pair, bids, asks)

    def _find_liquidity_zones(self, pair: str) -> list:
        return find_liquidity_zones(self, pair)

    def _smart_order_routing(self, pair: str, side: str, total_size: float, 
                              bids: list, asks: list) -> list:
        return smart_order_routing(pair, side, total_size, bids, asks)

    def _elite_signal(self, df, bids, asks, zones) -> tuple:
        return elite_signal(df, bids, asks, zones)

    def _split_order(self, pair: str, side: str, total_size: float,
                     bids: list, asks: list) -> list:
        return split_order(self, pair, side, total_size, bids, asks)

    def _execute_single_order(self, pair: str, side: str, price: float, size: float) -> dict:
        return execute_single_order(self, pair, side, price, size)

    def _fee_aware_net_price(self, price: float, side: str) -> tuple:
        return fee_aware_net_price(price, side)

    async def _broadcast_to_subscribers(self, pair, message):
        """Send message to all users watching this pair"""
        # FIX #8: Normalize pair sebelum compare — WS kirim BTC/IDR, subscribers simpan btcidr
        pair_normalized = pair.replace('/', '').lower()
        pair_escaped = self._escape_markdown(pair)
        message_escaped = message.replace(f"`{pair}`", f"`{pair_escaped}`").replace(f"**{pair}**", f"**{pair_escaped}**")

        for user_id, pairs in self.subscribers.items():
            # Normalize setiap entry di subscribers juga sebelum compare
            if any(p.replace('/', '').lower() == pair_normalized for p in pairs):
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
            ohlcv = {
                'timestamp': price_data['timestamp'],
                'open': current_price,
                'high': current_price,
                'low': current_price,
                'close': current_price,
                'volume': price_data.get('volume', 0)
            }
            
            # Update historical data for ML
            self._update_historical_data(pair, price_data)

            # Save to database in background so hot price ticks do not block the event loop
            self._create_background_task(self._save_price_history_background(pair, ohlcv))

            # Check SL/TP levels for notifications
            self._create_background_task(self.price_monitor.check_price_levels(pair, current_price))

            # Process signal-related tasks once per tick to avoid duplicate signal generation
            self._create_background_task(process_price_update_signal_tasks(self, pair))

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
        # Each pair keeps ~HISTORICAL_DATA_LIMIT candles × ~6 columns × 8 bytes
        # = ~24KB per pair @ 500 cap. 100 pairs = ~2.4MB total, safe for 4GB VPS
        MAX_TRACKED_PAIRS = 100  # Increased from 50 to support more pairs
        IN_MEMORY_CAP = getattr(Config, 'HISTORICAL_DATA_LIMIT', 200)

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
            df = self.historical_data[pair]
            df.loc[len(df)] = new_candle

            if len(df) > IN_MEMORY_CAP:
                self.historical_data[pair] = df.tail(IN_MEMORY_CAP).reset_index(drop=True)
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
