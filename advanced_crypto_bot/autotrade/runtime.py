#!/usr/bin/env python3
# Tujuan: Runtime helpers for signal monitoring, autotrade execution, and market-intelligence gating.
# Caller: bot.AdvancedCryptoBot price-update flow and Telegram-triggered autotrade flow.
# Dependensi: core.config, core.utils, core.profit_optimizer, signals.signal_pipeline, pandas, requests.
# Main Functions: process_price_update_signal_tasks, monitor_strong_signal, check_trading_opportunity, analyze_market_intelligence, detect_market_regime, execute_auto_sell.
# Side Effects: HTTP calls to Telegram/Indodax, DB reads/writes via bot dependencies, trade execution, notifications.
"""Runtime helpers extracted from bot.py for signal monitoring and auto-trading."""

import asyncio
import json
import logging
import random
import threading
from datetime import datetime, timedelta

import pandas as pd
import requests

from core.config import Config
from core.profit_optimizer import evaluate_autotrade_setup, scale_take_profit_targets
from core.utils import Utils
from signals.signal_pipeline import generate_signal_for_pair

logger = logging.getLogger("crypto_bot")


def _classify_autotrade_block_reason(reason):
    """Classify a blocked entry reason into a compact diagnostic bucket."""
    text = str(reason or "").upper()
    if "V4_FILTER" in text or "BAD_BUY" in text or "BAD_SELL" in text:
        return "V4_FILTER"
    if ("R/R AFTER FEES" in text) or ("R/R" in text and "DYNAMIC FLOOR" in text):
        return "R/R_FLOOR"
    if "CVAR" in text:
        return "CVAR"
    if "CORREL" in text:
        return "CORRELATION"
    if "CHASE" in text:
        return "CHASE_PREVENTION"
    if "DRAWDOWN" in text:
        return "DRAWDOWN"
    if "DAILY LOSS" in text or "MAX_DAILY_LOSS" in text:
        return "DAILY_LOSS"
    if "MAKER EDGE" in text or "ENTRY ZONE" in text:
        return "ENTRY_EDGE"
    if "PAIR_FILTER" in text or "PROFIT_FACTOR" in text:
        return "PAIR_FILTER"
    if "MI FILTER" in text or "MARKET INTELLIGENCE" in text:
        return "MARKET_INTELLIGENCE"
    return "OTHER"


def _remember_autotrade_block_reason(bot, pair, reason):
    """Store the latest blocked-entry reason per pair for status diagnostics."""
    pair_key = _normalize_pair(pair)
    bucket = _classify_autotrade_block_reason(reason)
    store = getattr(bot, "_autotrade_block_reasons", None)
    if store is None:
        store = {}
        bot._autotrade_block_reasons = store
    store[pair_key] = {
        "pair": str(pair or "").upper(),
        "reason": str(reason or "").strip(),
        "bucket": bucket,
        "timestamp": datetime.now().astimezone() if datetime.now().astimezone else datetime.now(),
    }


# =============================================================================
# TELEGRAM SIGNAL ALERT COOLDOWNS (Prioritas 1 — 2026-05-22)
# =============================================================================
# Cooldown ini menahan spam notifikasi Telegram TANPA mempengaruhi auto-trade
# execution. Diturunkan dari 5 menit → 3 menit untuk timeframe crypto intraday
# yang sering flip BUY↔SELL dalam 5-10 menit. Tetap mencegah duplikasi tapi
# lebih responsif terhadap setup baru.
# - SIGNAL_CHECK_COOLDOWN_MINUTES: cooldown per pair (semua recommendation)
# - SIGNAL_NOTIFICATION_COOLDOWN_MINUTES: cooldown per (pair, recommendation)
SIGNAL_CHECK_COOLDOWN_MINUTES = 3
SIGNAL_NOTIFICATION_COOLDOWN_MINUTES = 3


# =============================================================================
# QUANT MODULE LAZY INITIALIZATION
# =============================================================================

def _get_quant_kelly(bot):
    """Lazy-init Bayesian Kelly engine on bot instance."""
    if not hasattr(bot, '_quant_kelly_engine'):
        try:
            from quant.bayesian_kelly import BayesianKellyEngine
            bot._quant_kelly_engine = BayesianKellyEngine()
            logger.info("✅ [QUANT] Bayesian Kelly Engine initialized in runtime")
        except Exception as e:
            logger.debug(f"[QUANT] Kelly engine not available: {e}")
            bot._quant_kelly_engine = None
    return bot._quant_kelly_engine


def _get_quant_momentum(bot):
    """Lazy-init Momentum Factor engine on bot instance."""
    if not hasattr(bot, '_quant_momentum_engine'):
        try:
            from quant.momentum_factor import MomentumFactorEngine
            bot._quant_momentum_engine = MomentumFactorEngine()
            logger.info("✅ [QUANT] Momentum Factor Engine initialized in runtime")
        except Exception as e:
            logger.debug(f"[QUANT] Momentum engine not available: {e}")
            bot._quant_momentum_engine = None
    return bot._quant_momentum_engine


def _get_quant_correlation(bot):
    """Lazy-init Dynamic Correlation engine on bot instance."""
    if not hasattr(bot, '_quant_corr_engine'):
        try:
            from quant.dynamic_correlation import DynamicCorrelationEngine
            bot._quant_corr_engine = DynamicCorrelationEngine()
            logger.info("✅ [QUANT] Dynamic Correlation Engine initialized in runtime")
        except Exception as e:
            logger.debug(f"[QUANT] Correlation engine not available: {e}")
            bot._quant_corr_engine = None
    return bot._quant_corr_engine


def _get_quant_perf(bot):
    """Lazy-init Performance Analytics engine on bot instance."""
    if not hasattr(bot, '_quant_perf_engine'):
        try:
            from quant.performance_analytics import PerformanceAnalytics
            bot._quant_perf_engine = PerformanceAnalytics()
            logger.info("✅ [QUANT] Performance Analytics Engine initialized in runtime")
        except Exception as e:
            logger.debug(f"[QUANT] Performance engine not available: {e}")
            bot._quant_perf_engine = None
    return bot._quant_perf_engine


def _normalize_pair(pair):
    return str(pair or "").lower().replace("/", "").replace("_", "")


def _get_runtime_state_lock(bot):
    """Return a shared lock for compound runtime-state checks/mutations."""
    lock = getattr(bot, "_runtime_state_lock", None)
    if lock is None:
        lock = threading.RLock()
        bot._runtime_state_lock = lock
    return lock


def _is_watched(bot, pair):
    pair_norm = _normalize_pair(pair)
    return any(
        pair_norm == _normalize_pair(watched_pair)
        for pairs in bot.subscribers.values()
        for watched_pair in pairs
    )


def _is_auto_trade_pair(bot, pair):
    pair_norm = _normalize_pair(pair)
    return any(
        pair_norm == _normalize_pair(auto_pair)
        for pairs in bot.auto_trade_pairs.values()
        for auto_pair in pairs
    )


def _get_autotrade_liquidity_blacklist(bot):
    store = getattr(bot, "_autotrade_liquidity_blacklist", None)
    if store is None:
        store = {}
        bot._autotrade_liquidity_blacklist = store
    return store


def _is_autotrade_liquidity_blacklisted(bot, pair):
    pair_key = _normalize_pair(pair)
    store = _get_autotrade_liquidity_blacklist(bot)
    entry = store.get(pair_key)
    if not entry:
        return False
    expires_at = entry.get("expires_at")
    if expires_at and datetime.now() > expires_at:
        store.pop(pair_key, None)
        return False
    return True


def _blacklist_autotrade_pair(bot, pair, reason):
    pair_key = _normalize_pair(pair)
    ttl_minutes = int(getattr(Config, "AUTOTRADE_LIQUIDITY_BLACKLIST_TTL_MINUTES", 180) or 180)
    expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
    store = _get_autotrade_liquidity_blacklist(bot)
    store[pair_key] = {
        "pair": str(pair or "").upper(),
        "reason": str(reason or "").strip(),
        "expires_at": expires_at,
        "timestamp": datetime.now(),
    }
    logger.info(f"🚫 [LIQUIDITY_BLACKLIST] {pair}: {reason} (ttl={ttl_minutes}m)")
    _remember_autotrade_block_reason(bot, pair, f"LIQUIDITY_BLACKLIST: {reason}")


def _extract_bid_ask_from_ticker(ticker):
    if not ticker:
        return None, None, None
    bid = _to_positive_float(ticker.get("bid"))
    if bid is None:
        bid = _to_positive_float(ticker.get("buy"))
    ask = _to_positive_float(ticker.get("ask"))
    if ask is None:
        ask = _to_positive_float(ticker.get("sell"))
    last = _to_positive_float(ticker.get("last"))
    return bid, ask, last



def _signal_notifications_enabled(bot):
    """Return whether automatic Telegram signal notifications are enabled."""
    return bot._are_signal_notifications_enabled() if hasattr(bot, '_are_signal_notifications_enabled') else getattr(bot, 'signal_notifications_enabled', True)


def _signal_passes_filter(bot, recommendation):
    """Apply Telegram automatic signal alert filter.

    /signal on enables actionable automatic alerts: BUY/STRONG_BUY and
    SELL/STRONG_SELL. HOLD/neutral signals are suppressed.
    """
    rec = (recommendation or '').upper()
    return rec in ('BUY', 'STRONG_BUY', 'SELL', 'STRONG_SELL')


def _to_positive_float(value):
    """Convert value to positive float or None when invalid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _is_valid_position_size(amount, total):
    """Return True when position sizing output is usable for order placement."""
    try:
        return float(amount) > 0 and float(total) > 0
    except (TypeError, ValueError):
        return False


def _calculate_dry_run_total_from_price(price):
    """Return DRY RUN total IDR based on pair price.

    Target: 1.000.000 - 2.000.000 IDR per trade, capped at 2.000.000:
    - Price < 1000 IDR   → min 10.000 koin, cap 2.000.000
    - 1000-10000 IDR     → min 100 koin, cap 2.000.000
    - > 10000 IDR        → cap 2.000.000

    FIX 2026-06-07: MAX_TOTAL dinaikkan ke 2.000.000 dan di-hard-cap
    (sebelumnya 1.500.000). Semua pair termasuk BTC tidak boleh melebihi
    2.000.000 IDR.
    """
    TARGET_TOTAL = 1_250_000
    MIN_TOTAL = 1_000_000
    MAX_TOTAL = 2_000_000  # FIX: hard cap 2.000.000 for all pairs

    price_value = _to_positive_float(price)
    if price_value is None:
        return None

    total = TARGET_TOTAL

    # Pastikan amount koin masuk akal untuk harga rendah
    amount_coins = total / price_value

    if price_value < 1000:
        min_amount = 10000
        if amount_coins < min_amount:
            amount_coins = min_amount
            total = amount_coins * price_value
    elif price_value <= 10000:
        min_amount = 100
        if amount_coins < min_amount:
            amount_coins = min_amount
            total = amount_coins * price_value

    # Hard cap: never exceed MAX_TOTAL even for expensive coins like BTC
    return max(MIN_TOTAL, min(MAX_TOTAL, total))


async def _get_cached_signal(bot, pair):
    now = datetime.now()
    cache = getattr(bot, "_signal_result_cache", {})
    cached = cache.get(pair)
    if cached and (now - cached["timestamp"]).total_seconds() < 2:
        return cached["signal"]

    in_flight = getattr(bot, "_signal_inflight_tasks", {}).get(pair)
    if in_flight:
        # FIX 2026-06-07 v2: Validate event-loop compatibility before awaiting.
        # If the stored task was created on a different event loop (e.g., main
        # Telegram loop vs SignalQueue worker loop), we must not await it —
        # asyncio will raise "attached to a different loop". Instead, clear
        # the stale entry and create a fresh task on the current loop.
        try:
            task_loop = in_flight.get_loop() if hasattr(in_flight, 'get_loop') else None
        except Exception:
            task_loop = None
        if task_loop is not None:
            import asyncio as _asyncio
            try:
                current_loop = _asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if task_loop is not current_loop:
                logger.debug(
                    "_get_cached_signal: stale inflight task for %s (task_loop != current), clearing",
                    pair
                )
                bot._signal_inflight_tasks.pop(pair, None)
                in_flight = None
            else:
                return await in_flight

    task = asyncio.create_task(generate_signal_for_pair(bot, pair))
    bot._signal_inflight_tasks[pair] = task
    try:
        signal = await task
        if signal is not None:
            bot._signal_result_cache[pair] = {"timestamp": datetime.now(), "signal": signal}
        return signal
    finally:
        bot._signal_inflight_tasks.pop(pair, None)


async def process_price_update_signal_tasks(bot, pair):
    """Process signal-related tasks once per price tick to avoid duplicate signal computation."""
    watched = _is_watched(bot, pair)
    auto_trade_pair = bot.is_trading and _is_auto_trade_pair(bot, pair)

    if auto_trade_pair:
        await check_trading_opportunity(bot, pair)
        return

    if watched and bot.is_trading and Config.AUTO_TRADE_DRY_RUN:
        # Auto-promote: generate signal, if BUY/STRONG_BUY (pre-SR) → add to auto_trade_pairs and execute
        signal = await _get_cached_signal(bot, pair)
        if signal:
            # Use pre-SR recommendation: SR_VALIDATION may convert BUY→HOLD for
            # notification purposes, but autotrade has its own entry gates (R/R,
            # market intelligence, etc.) so we let it through.
            pre_sr_rec = signal.get("pre_sr_recommendation") or signal.get("recommendation", "HOLD")
            if pre_sr_rec in ("BUY", "STRONG_BUY"):
                _auto_promote_pair(bot, pair)
                await check_trading_opportunity(bot, pair, signal=signal)
                return
            else:
                logger.info(f"⏭️ [AUTO-PROMOTE] {pair}: pre_sr_rec={pre_sr_rec}, final_rec={signal.get('recommendation')}, skipping")
        # Still send notification for non-BUY actionable signals
        await monitor_strong_signal(bot, pair, signal=signal)
    elif watched:
        await monitor_strong_signal(bot, pair)


def _auto_promote_pair(bot, pair):
    """Auto-add a watched pair to auto_trade_pairs on BUY/STRONG_BUY signal."""
    pair_norm = _normalize_pair(pair)
    if Config.AUTOTRADE_LIQUIDITY_WHITELIST and pair_norm not in set(Config.AUTOTRADE_LIQUIDITY_WHITELIST):
        return
    if _is_autotrade_liquidity_blacklisted(bot, pair):
        return
    if getattr(Config, "AUTOTRADE_LIQUIDITY_PROMOTE_REQUIRE_BIDASK", True):
        # In DRY RUN mode, skip strict bid/ask check at promote stage.
        # The MI spread gate inside check_trading_opportunity will still
        # block entry if spread is truly invalid. This ensures DRY RUN
        # can actually generate trades for evaluation purposes.
        if Config.AUTO_TRADE_DRY_RUN:
            logger.debug(f"⏭️ [AUTO-PROMOTE] {pair}: DRY RUN mode, skipping strict bid/ask check at promote")
        else:
            try:
                ticker = bot.indodax.get_ticker(pair)
                bid, ask, last = _extract_bid_ask_from_ticker(ticker)
                if bid is None or ask is None:
                    _blacklist_autotrade_pair(bot, pair, "bid/ask missing or invalid")
                    return
                mid = (bid + ask) / 2 if (bid and ask) else None
                if mid is None or mid <= 0:
                    _blacklist_autotrade_pair(bot, pair, f"invalid mid price (bid={bid}, ask={ask})")
                    return
                spread_pct = (ask - bid) / mid
                max_spread = float(getattr(Config, "AUTOTRADE_LIQUIDITY_PROMOTE_MAX_SPREAD_PCT", 0.03) or 0.03)
                if spread_pct > max_spread:
                    _blacklist_autotrade_pair(bot, pair, f"spread too wide for autotrade promote ({spread_pct*100:.3f}% > {max_spread*100:.2f}%)")
                    return
            except Exception as e:
                logger.debug(f"⚠️ Liquidity promote check skipped for {pair}: {e}")
    user_id = list(bot.subscribers.keys())[0] if bot.subscribers else None
    if user_id is None:
        return
    if user_id not in bot.auto_trade_pairs:
        bot.auto_trade_pairs[user_id] = []
    if not any(_normalize_pair(p) == pair_norm for p in bot.auto_trade_pairs[user_id]):
        bot.auto_trade_pairs[user_id].append(pair)
        logger.info(f"🚀 [AUTO-PROMOTE] {pair} added to auto_trade_pairs on BUY signal (DRY RUN)")


async def monitor_strong_signal(bot, pair, signal=None):
    """Monitor watched pairs and send strong-signal alerts."""
    if not _is_watched(bot, pair):
        return

    pair_key = _normalize_pair(pair)

    if signal is None:
        signal = await _get_cached_signal(bot, pair)
    if not signal or "recommendation" not in signal:
        if signal is not None and "recommendation" not in signal:
            logger.warning(f"⚠️ Signal for {pair} missing 'recommendation' key, skipping")
        return
    signal = dict(signal)
    signal.setdefault("pair", pair)
    signal.setdefault("indicators", {})
    signal.setdefault("reason", "Signal alert generated from watched pair")

    recommendation = signal.get("recommendation", "HOLD")
    confidence = signal.get("ml_confidence", 0)
    if recommendation not in ["STRONG_BUY", "STRONG_SELL", "BUY", "SELL"]:
        return

    if not _signal_passes_filter(bot, recommendation):
        logger.info(
            f"🎯 Watched signal alert filtered out for {pair}: {recommendation} "
            f"(auto Telegram alerts are BUY-only)"
        )
        return

    now = datetime.now()
    with _get_runtime_state_lock(bot):
        if not hasattr(bot, "_last_signal_checks"):
            bot._last_signal_checks = {}

        last_check = bot._last_signal_checks.get(pair_key)
        if last_check and now - last_check < timedelta(minutes=SIGNAL_CHECK_COOLDOWN_MINUTES):
            return
        bot._last_signal_checks[pair_key] = now

    signal_key = f"{pair_key}_{recommendation}"
    with _get_runtime_state_lock(bot):
        if not hasattr(bot, "_notification_cooldown"):
            bot._notification_cooldown = {}

        last_sent = bot._notification_cooldown.get(signal_key, datetime.min)
        if now - last_sent < timedelta(minutes=SIGNAL_NOTIFICATION_COOLDOWN_MINUTES):
            logger.debug(f"⏳ Notification cooldown: {signal_key}")
            return
        bot._notification_cooldown[signal_key] = now

    signal_text = bot._format_signal_message_html(signal)

    # Build safe Scalper-only action buttons (BUY/SELL) bila pair officially listed
    # di Indodax dan memenuhi safety policy balance/scalper-position.
    # Lihat docs/telegram-scalper-signal-safety.md.
    try:
        action_markup = bot._build_signal_action_markup(signal)
    except Exception as e:  # noqa: BLE001
        action_markup = None
        logger.debug(f"⚠️ Failed to build signal action markup for {pair}: {e}")
    action_markup_dict = action_markup.to_dict() if action_markup is not None else None

    if not _signal_notifications_enabled(bot):
        logger.info(f"🔕 Watched signal alert NOT pushed for {pair}: notifications OFF (signal still processed)")
        return

    loop = asyncio.get_event_loop()
    for admin_id in Config.ADMIN_IDS:
        try:
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": admin_id, "text": signal_text, "parse_mode": "HTML"}
            if action_markup_dict is not None:
                payload["reply_markup"] = action_markup_dict
            response = await loop.run_in_executor(None, lambda: requests.post(url, json=payload, timeout=10))
            if response.status_code == 200:
                logger.info("📢 Signal alert sent to admin %s for %s: %s (%.1f%%)", admin_id, pair, recommendation, confidence * 100)
            else:
                logger.error("❌ Failed to send signal alert: HTTP %s - %s", response.status_code, response.text)
        except Exception as e:
            logger.error("❌ Failed to send signal alert via HTTP: %s", e)


def _get_pair_correlation_group(pair):
    """Return the correlation group key for a given pair, or None."""
    p = pair.lower().replace('/', '')
    for group, members in Config.CORRELATION_GROUPS.items():
        if p in [m.lower().replace('/', '') for m in members]:
            return group
    return None


def _check_correlated_exposure(bot, user_id, pair, balance):
    """Check exposure in the same correlation group.
    
    Uses Quant Dynamic Correlation engine if available (rolling real-time correlation),
    falls back to hardcoded Config.CORRELATION_GROUPS.
    
    Returns (allowed, reduction_factor, reason).
    """
    if not Config.CORRELATION_AVOIDANCE_ENABLED:
        return True, 1.0, "Correlation check disabled"

    # Try Quant Dynamic Correlation first
    try:
        corr_engine = _get_quant_correlation(bot)
        if corr_engine is not None:
            # Feed latest prices
            for p, df in bot.historical_data.items():
                if df is not None and not df.empty and len(df) >= 15:
                    corr_engine.update_prices(p, df['close'].astype(float).tolist())

            open_trades = bot.db.get_open_trades(user_id)
            check = corr_engine.check_correlation_limit(pair, open_trades, balance=balance)

            if not check.allowed:
                return False, 0.0, f"[QUANT] {check.reason}"
            elif check.correlation_value >= 0.60:
                # High but not blocking — reduce size
                return True, 0.6, f"[QUANT] High correlation ({check.correlation_value:.2f}) with {', '.join(check.correlated_pairs)}"
            else:
                return True, 1.0, f"[QUANT] Correlation OK (max={check.correlation_value:.2f})"
    except Exception as e:
        logger.debug(f"[QUANT CORR] Fallback to static groups: {e}")

    # Fallback: static correlation groups from Config
    group = _get_pair_correlation_group(pair)
    if not group:
        return True, 1.0, "No correlation group"
    open_trades = bot.db.get_open_trades(user_id)
    group_members = [m.lower().replace('/', '') for m in Config.CORRELATION_GROUPS[group]]
    correlated_exposure = sum(
        t["total"] for t in open_trades
        if t["pair"].lower().replace('/', '') in group_members
    )
    exposure_pct = (correlated_exposure / balance) if balance > 0 else 0
    max_pct = Config.PORTFOLIO_MAX_CORRELATED_EXPOSURE_PCT
    if exposure_pct >= max_pct:
        return False, 0.0, f"Correlated exposure {exposure_pct:.1%} >= limit {max_pct:.1%}"
    elif exposure_pct >= max_pct * 0.75:
        return True, 0.5, f"Correlated exposure high ({exposure_pct:.1%}), reducing size 50%"
    return True, 1.0, f"Correlated exposure OK ({exposure_pct:.1%})"


async def check_trading_opportunity(bot, pair, signal=None):
    """Check and execute trading opportunity (auto-trading)."""
    if not bot.is_trading:
        return

    if not _is_auto_trade_pair(bot, pair):
        # DRY RUN auto-promote: if pair is in watchlist and signal is BUY/STRONG_BUY,
        # promote it to auto_trade_pairs and proceed with trade logic.
        if Config.AUTO_TRADE_DRY_RUN and _is_watched(bot, pair) and signal:
            pre_sr = signal.get("pre_sr_recommendation") or signal.get("recommendation", "HOLD")
            if pre_sr in ("BUY", "STRONG_BUY"):
                _auto_promote_pair(bot, pair)
                # Re-check after promote
                if not _is_auto_trade_pair(bot, pair):
                    await monitor_strong_signal(bot, pair, signal=signal)
                    return
            else:
                await monitor_strong_signal(bot, pair, signal=signal)
                return
        else:
            logger.debug(f"⏭️ Skipping {pair}: Not in auto-trade list (only in watchlist)")
            if _is_watched(bot, pair):
                await monitor_strong_signal(bot, pair, signal=signal)
            return

    pair_key = _normalize_pair(pair)

    # ── Per-pair execution lock ──────────────────────────────────────────
    # Prevent parallel execution for the same pair from different code paths
    # (e.g. WebSocket handler vs SignalQueue worker). Without this lock, two
    # concurrent calls to check_trading_opportunity for the same pair can both
    # pass position/cooldown checks and create duplicate trades.
    # Uses asyncio.Lock stored on the bot object; released automatically when
    # the 'async with' block exits (including on exception).
    if not hasattr(bot, '_pair_execution_locks'):
        bot._pair_execution_locks = {}
    if pair_key not in bot._pair_execution_locks:
        bot._pair_execution_locks[pair_key] = asyncio.Lock()
    pair_lock = bot._pair_execution_locks[pair_key]
    # ─────────────────────────────────────────────────────────────────────

    async with pair_lock:
        return await _check_trading_opportunity_locked(bot, pair, pair_key, signal)

async def _check_trading_opportunity_locked(bot, pair, pair_key, signal):
    """Core trading logic — must be called while holding the per-pair lock."""
    user_id = list(bot.subscribers.keys())[0] if bot.subscribers else 1
    open_trades_for_pair = []
    try:
        open_trades_for_pair = [
            t for t in bot.db.get_open_trades(user_id)
            if _normalize_pair(t.get("pair") if hasattr(t, "get") else t["pair"]) == pair_key
        ]
    except Exception as e:
        logger.debug(f"⚠️ Could not inspect open trades before auto-trade cooldown for {pair}: {e}")

    cooldown_active = False
    now = datetime.now()
    with _get_runtime_state_lock(bot):
        last_ml_update = getattr(bot, "last_ml_update", {})
        last_update = last_ml_update.get(pair_key)
        cooldown_active = bool(last_update and now - last_update < timedelta(minutes=bot.auto_trade_interval_minutes))
        if cooldown_active and not open_trades_for_pair:
            return

    is_dry_run = Config.AUTO_TRADE_DRY_RUN
    mode_label = "🧪 DRY RUN" if is_dry_run else "🔴 REAL"
    logger.info(f"{mode_label} Scanning {pair} for auto-trade opportunity...")

    if signal is None:
        signal = await _get_cached_signal(bot, pair)
    if not signal:
        return
    if "recommendation" not in signal:
        logger.warning(f"⚠️ Signal for {pair} missing 'recommendation' key, skipping")
        return
    signal = dict(signal)
    signal.setdefault("pair", pair)
    signal.setdefault("indicators", {})
    signal.setdefault("reason", "Signal alert generated from auto-trade queue")
    # For autotrade, use pre-pipeline-filter recommendation if available.
    # `pre_sr_recommendation` is snapshot BEFORE Quality Engine V3 + SR
    # Validation run (signal_pipeline.py ~line 399). Both filters are
    # designed for Telegram notification filtering (avoid spam, enforce
    # confluence rules). Autotrade has 17 of its own entry gates (market
    # intelligence, V4 filter, chase prevention, correlation, R/R after
    # fees, profit optimizer) that are more appropriate for execution.
    #
    # Without this bypass, e.g. STRONG_BUY signals with confluence=2 are
    # downgraded to HOLD by Quality Engine ("STRONG_BUY requirements not
    # met"), and autotrade then skips them as "Weak signal". Result: 0
    # entries despite strong ML+TA agreement.
    effective_rec = signal.get("pre_sr_recommendation") or signal["recommendation"]
    if effective_rec not in ["STRONG_BUY", "BUY", "STRONG_SELL", "SELL"]:
        # Promoted DEBUG → INFO supaya setiap scan yang berakhir tanpa entry
        # tetap punya audit trail. Sebelum patch ini, ~73% scan DRY RUN
        # berakhir silent karena log skip-nya di level DEBUG.
        logger.info(f"⏸️ Skipping {pair}: Weak signal ({effective_rec})")
        return
    # FIX 2026-06-11: Explicit veto checks sebelum pre_sr override.
    # Beberapa flag dari pipeline upstream menandakan bahwa signal TIDAK
    # boleh dieksekusi walau pre_sr-nya kuat:
    #   - duplicate_filtered: signal ini duplikat dari alert sebelumnya
    #     (cooldown anti-spam alert) — execution akan trigger dari alert
    #     pertama yang asli, bukan dari yang ini.
    #   - execution_allowed=False: decision layer (signal_pipeline V4 outcome
    #     filter, dll) sudah menolak signal ini secara eksplisit.
    #   - display_recommendation=PANTAU: pipeline final-nya watch-only.
    # Sebelum override pre_sr ada, flag-flag ini incidentally diblokir karena
    # signal["recommendation"] = HOLD. Sekarang kita perlu cek eksplisit.
    if signal.get("duplicate_filtered"):
        logger.info(
            f"⏸️ Skipping {pair}: duplicate_filtered=True "
            f"({signal.get('duplicate_filtered_reason', 'no reason')})"
        )
        return
    if signal.get("execution_allowed") is False:
        logger.info(
            f"⏸️ Skipping {pair}: execution_allowed=False "
            f"({signal.get('decision_reason', 'no reason')})"
        )
        return
    if signal.get("display_recommendation") == "PANTAU":
        logger.info(
            f"⏸️ Skipping {pair}: display_recommendation=PANTAU "
            f"({signal.get('display_reason', 'no reason')})"
        )
        return
    # FIX 2026-06-11: Apply pre_sr override on signal['recommendation']
    # so downstream gates (DRY RUN open-position check, MI filter, V4,
    # execution path) see the autotrade-relevant recommendation. Without
    # this, BUY/STRONG_BUY signals downgraded to HOLD by SR_VALIDATION
    # pass the weak-signal gate (via effective_rec) but then fail every
    # subsequent `signal["recommendation"]` check at L762, so
    # `analyze_market_intelligence` and `should_execute_trade` are never
    # called. CHANGELOG noted this fix at 2026-05-29 ("Fix 3") but the
    # override line was lost during merge of branches scalper-sltp +
    # autotrade-dryrun-no-entry-vm-20260609.
    if signal["recommendation"] != effective_rec:
        logger.info(
            f"📝 [autotrade] {pair}: recommendation override "
            f"{signal['recommendation']} → {effective_rec} (pre-SR snapshot)"
        )
        signal["recommendation"] = effective_rec
    # NOTE: DRY RUN now allows both BUY and STRONG_BUY for realistic validation.
    # Previously only STRONG_BUY was allowed, making DRY RUN results misleading.
    if is_dry_run and open_trades_for_pair and signal["recommendation"] in ["BUY", "STRONG_BUY"]:
        logger.info(f"⏭️ Skipping {pair}: open DRY RUN position already exists; waiting for SELL")
        return
    if cooldown_active and signal["recommendation"] not in ["STRONG_SELL", "SELL"]:
        logger.info(f"⏭️ Skipping {pair}: scan cooldown active and signal is not SELL")
        return
    if cooldown_active:
        logger.info(f"⏭️ Bypassing auto-trade scan cooldown for {pair}: open position needs SELL monitoring")
    with _get_runtime_state_lock(bot):
        last_ml_update = getattr(bot, "last_ml_update", {})
        last_ml_update[pair_key] = now
        bot.last_ml_update = last_ml_update
    signal_text = bot._format_signal_message_html(signal)
    notif_filter_pass = _signal_passes_filter(bot, signal["recommendation"])
    if not notif_filter_pass:
        logger.info(
            f"🎯 Auto-trade signal notification filtered out for {pair}: {signal['recommendation']} "
            f"(filter={getattr(bot, 'signal_notification_filter', 'all')}); trade logic still proceeds"
        )
    if _signal_notifications_enabled(bot) and notif_filter_pass:
        # Build safe Scalper-only action buttons (BUY/SELL) for auto-trade signal alerts.
        # See docs/telegram-scalper-signal-safety.md.
        try:
            action_markup = bot._build_signal_action_markup(signal)
        except Exception as e:  # noqa: BLE001
            action_markup = None
            logger.debug(f"⚠️ Failed to build signal action markup for {pair}: {e}")

        for admin_id in Config.ADMIN_IDS:
            try:
                kwargs = {
                    "chat_id": admin_id,
                    "text": signal_text,
                    "parse_mode": "HTML",
                }
                if action_markup is not None:
                    kwargs["reply_markup"] = action_markup

                # FIX 2026-06-07 v2: Detect event-loop mismatch and reschedule
                # on main Telegram loop. When check_trading_opportunity runs
                # inside the SignalQueue worker's asyncio event loop, the PTB
                # bot HTTP client is bound to the main loop — await fails with
                # "bound to a different event loop".
                try:
                    await bot.app.bot.send_message(**kwargs)
                except RuntimeError as runtime_err:
                    if 'different event loop' in str(runtime_err).lower() or \
                       'different loop' in str(runtime_err).lower():
                        # Reschedule on main Telegram loop (fire-and-forget for notification)
                        import asyncio as _asyncio
                        _loop = getattr(bot, '_telegram_loop', None)
                        if _loop and not _loop.is_closed():
                            _asyncio.run_coroutine_threadsafe(
                                bot.app.bot.send_message(**kwargs),
                                _loop
                            )
                            logger.info(
                                "📢 Signal notification rescheduled on main loop for admin %s (%s)",
                                admin_id, pair
                            )
                            continue
                    raise
                logger.info(f"📢 Signal notification sent to admin {admin_id} for {pair}")
            except Exception as e:
                logger.error(f"❌ Failed to send signal notification: {e}")
    else:
        logger.info(f"🔕 Auto-trade signal notification skipped for {pair}: notifications OFF")

    can_trade, reason = bot.risk_manager.check_daily_loss_limit(user_id)
    if not can_trade:
        logger.warning(f"⚠️ Trading blocked for {pair}: {reason}")
        return

    # Max drawdown circuit breaker
    dd_allowed, dd_reason = bot._check_max_drawdown(user_id)
    if not dd_allowed:
        logger.error(f"🚫 [CIRCUIT_BREAKER] Trading blocked for {pair}: {dd_reason}")
        return

    # Pair performance filter
    try:
        pp = bot.db.get_pair_performance(pair)
        if pp and pp['profit_factor'] is not None and pp['profit_factor'] < 1.0 and pp['total_trades'] >= 5:
            logger.info(
                f"🚫 [PAIR_FILTER] Entry blocked for {pair}: "
                f"profit_factor={pp['profit_factor']:.2f} (min 1.0) over {pp['total_trades']} trades"
            )
            return
    except Exception as e:
        logger.debug(f"⚠️ Pair performance check skipped for {pair}: {e}")

    current_price = _to_positive_float(signal.get("price"))
    if current_price is None:
        current_price = _to_positive_float(getattr(bot, "price_data", {}).get(pair, {}).get("last"))
        if current_price is not None:
            logger.info(f"🔄 Using cached WebSocket price for {pair}: {current_price}")
    if current_price is None:
        try:
            ticker = bot.indodax.get_ticker(pair)
            current_price = _to_positive_float(ticker.get("last") if ticker else None)
            if current_price is not None:
                logger.info(f"🔄 Using fresh API price for {pair}: {current_price}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch fallback price for {pair}: {e}")
    if current_price is None:
        logger.warning(f"⚠️ Skipping {pair}: signal price missing/invalid and no fallback available")
        return

    confidence = float(signal.get("ml_confidence", 0.5) or 0.5)

    if signal["recommendation"] in ["BUY", "STRONG_BUY"]:
        # Authoritative pre-entry gate. Previously this runtime bypassed
        # TradingEngine.should_execute_trade(), so real entries could ignore
        # duplicate-position, max-daily-trade, min-balance, trading-hours, and
        # correlation-cooldown checks.
        should_trade, gate_reason = bot.trading_engine.should_execute_trade(user_id, signal, current_price)
        if not should_trade:
            logger.info(f"🚫 Entry blocked for {pair}: {gate_reason}")
            _remember_autotrade_block_reason(bot, pair, gate_reason)
            return

        market_conditions = await analyze_market_intelligence(bot, pair, current_price)
        regime = detect_market_regime(bot, pair)
        if not market_conditions.get("passes_entry_filter", True):
            # Apply MI filter consistently in both DRY RUN and real trading
            # so validation results are representative.
            log_fn = logger.warning if is_dry_run else logger.info
            prefix = "🧪 [DRY RUN]" if is_dry_run else "🚫"
            block_reason = market_conditions.get("block_reason", "")
            if block_reason == "SPREAD_INVALID":
                bid = market_conditions.get("best_bid")
                ask = market_conditions.get("best_ask")
                log_fn(f"{prefix} Entry blocked for {pair}: SPREAD_INVALID (bid={bid}, ask={ask})")
            elif block_reason == "SPREAD_TOO_WIDE":
                spread_pct = market_conditions.get("spread_pct", 0)
                log_fn(
                    f"{prefix} Entry blocked for {pair}: SPREAD_TOO_WIDE "
                    f"({spread_pct*100:.3f}% > max {Config.MI_SPREAD_MAX_PCT*100:.1f}%)"
                )
            elif block_reason == "NO_BID_LIQUIDITY":
                # Pair illiquid (bid side empty / harga 0). Lebih tepat di-skip
                # daripada menunggu spread menyempit. Diagnosa harus jelas:
                # ini BUKAN spread terlalu lebar, ini ketiadaan likuiditas.
                best_bid = market_conditions.get("best_bid", 0) or 0
                best_ask = market_conditions.get("best_ask", 0) or 0
                log_fn(
                    f"{prefix} Entry blocked for {pair}: NO_BID_LIQUIDITY "
                    f"(bid={best_bid:,.0f} ask={best_ask:,.0f}; pair illiquid)"
                )
            else:
                log_fn(f"{prefix} Entry blocked for {pair}: MI filter failed (Signal={market_conditions['overall_signal']})")
            return

        if regime["is_high_vol"]:
            logger.info(f"⚠️ HIGH VOLATILITY regime detected for {pair} - proceeding with caution")
            v4_status = None
            if hasattr(bot, 'ml_model_v4') and bot.ml_model_v4 and bot.ml_model_v4.is_fitted:
                v4_status = bot.ml_model_v4.get_status()
            
            amount, total = bot.trading_engine.calculate_position_size(
                user_id, current_price, kelly_win_rate=v4_status.get('win_rate') if v4_status else None
            )
            if not _is_valid_position_size(amount, total):
                logger.warning(f"⚠️ Position sizing failed for {pair} in high-volatility regime")
                return
            amount *= 0.5
            total *= 0.5
            logger.info(f"📊 Position size reduced 50% due to high volatility: {amount}")
        elif regime["is_trending"] and regime["trend_direction"] == "DOWN":
            logger.info(f"⚠️ DOWNTREND detected for {pair} - reducing position size")
            v4_status = None
            if hasattr(bot, 'ml_model_v4') and bot.ml_model_v4 and bot.ml_model_v4.is_fitted:
                v4_status = bot.ml_model_v4.get_status()
            
            amount, total = bot.trading_engine.calculate_position_size(
                user_id, current_price, kelly_win_rate=v4_status.get('win_rate') if v4_status else None
            )
            if not _is_valid_position_size(amount, total):
                logger.warning(f"⚠️ Position sizing failed for {pair} in downtrend regime")
                return
            amount *= 0.75
            total *= 0.75
            logger.info(f"📊 Position size reduced 25% due to downtrend: {amount}")
        else:
            v4_status = None
            if hasattr(bot, 'ml_model_v4') and bot.ml_model_v4 and bot.ml_model_v4.is_fitted:
                v4_status = bot.ml_model_v4.get_status()
            amount, total = bot.trading_engine.calculate_position_size(
                user_id, current_price, kelly_win_rate=v4_status.get('win_rate') if v4_status else None
            )
            if not _is_valid_position_size(amount, total):
                logger.warning(f"⚠️ Position sizing failed for {pair}")
                return

        if is_dry_run:
            dry_run_total = _calculate_dry_run_total_from_price(current_price)
            if dry_run_total is None or dry_run_total <= 0:
                logger.warning(f"⚠️ DRY RUN nominal sizing failed for {pair} at price {current_price}")
                return
            total = dry_run_total
            amount = total / current_price
            logger.info(
                f"🧪 [DRY RUN SIZE] {pair}: using tier nominal {total:,.0f} IDR at price {current_price:,.0f} "
                f"=> amount={amount:.8f}"
            )

        # Exploration mode: reduce position to configured factor for PANTAU signals (data collection only)
        if signal.get("_exploration_mode"):
            exploration_factor = float(signal.get("_exploration_factor_override") or getattr(Config, "DRYRUN_EXPLORATION_POSITION_FACTOR", 0.20) or 0.20)
            amount *= exploration_factor
            total *= exploration_factor
            logger.info(
                f"🔬 [EXPLORATION SIZE] {pair}: reduced to {exploration_factor*100:.0f}% "
                f"=> total={total:,.0f} IDR, amount={amount:.8f}"
            )

        # =====================================================================
        # QUANT: Bayesian Kelly Position Sizing Override
        # If Bayesian Kelly engine has enough data, use its adaptive sizing
        # instead of the simple Kelly above. Falls back gracefully.
        # =====================================================================
        try:
            kelly_engine = _get_quant_kelly(bot)
            if kelly_engine is not None:
                balance = bot.db.get_balance(user_id)
                vol_pct = regime.get("volatility", 2.0) if isinstance(regime.get("volatility"), (int, float)) else 2.0
                dd_pct = 0.0
                try:
                    dd_allowed, dd_reason = bot._check_max_drawdown(user_id)
                    # Extract drawdown % from reason if available
                    if 'drawdown' in dd_reason.lower():
                        import re
                        dd_match = re.search(r'(\d+\.?\d*)%', dd_reason)
                        if dd_match:
                            dd_pct = float(dd_match.group(1))
                except Exception:
                    pass

                kelly_result = kelly_engine.calculate_position_size(
                    pair=pair,
                    balance=balance,
                    entry_price=current_price,
                    ml_confidence=confidence,
                    volatility_pct=vol_pct,
                    current_drawdown_pct=dd_pct,
                )
                if kelly_result.position_value > 0 and kelly_result.method != 'negative_edge':
                    old_total = total
                    total = kelly_result.position_value
                    amount = kelly_result.position_amount
                    logger.info(
                        f"📊 [QUANT KELLY] {pair}: Bayesian Kelly override | "
                        f"{old_total:,.0f} → {total:,.0f} IDR | "
                        f"fraction={kelly_result.kelly_fraction:.2%} | "
                        f"method={kelly_result.method}"
                    )
        except Exception as e:
            logger.debug(f"[QUANT KELLY] {pair}: Fallback to standard sizing: {e}")

        # =====================================================================
        # QUANT: Momentum Factor — log momentum context for trade decision
        # =====================================================================
        try:
            momentum_engine = _get_quant_momentum(bot)
            if momentum_engine is not None and pair in bot.historical_data:
                df_mom = bot.historical_data[pair]
                mom_result = momentum_engine.analyze(df_mom, pair=pair)
                if mom_result and mom_result.direction == 'BEARISH' and mom_result.strength == 'STRONG':
                    # Strong bearish momentum opposing BUY → reduce size
                    amount *= 0.7
                    total *= 0.7
                    logger.info(
                        f"📉 [QUANT MOMENTUM] {pair}: Strong bearish momentum ({mom_result.momentum_score:+.0f}), "
                        f"reducing BUY size 30%"
                    )
                elif mom_result and mom_result.direction == 'BULLISH' and mom_result.strength == 'STRONG':
                    logger.info(
                        f"📈 [QUANT MOMENTUM] {pair}: Strong bullish momentum ({mom_result.momentum_score:+.0f}), "
                        f"confirming BUY direction"
                    )
        except Exception as e:
            logger.debug(f"[QUANT MOMENTUM] {pair}: Skipped: {e}")

        try:
            from api.indodax_api import IndodaxAPI

            indodax = IndodaxAPI()
            fresh_ticker = indodax.get_ticker(pair)
            if fresh_ticker:
                fresh_price = _to_positive_float(fresh_ticker.get("last"))
                if fresh_price is not None:
                    # FIX 2026-06-07: Validate fresh price against signal price.
                    # Reject if the fresh price deviates >50% from signal price
                    # (prevents test data contamination like BTC price=100).
                    signal_entry_price = _to_positive_float(signal.get("price")) or current_price
                    if signal_entry_price and signal_entry_price > 0:
                        deviation = abs(fresh_price - signal_entry_price) / signal_entry_price
                        if deviation > 0.50:
                            logger.warning(
                                f"⚠️ [PRICE VALIDATION] Fresh price {fresh_price:,.0f} deviates "
                                f"{deviation*100:.0f}% from signal price {signal_entry_price:,.0f} for {pair} — "
                                f"REJECTED (possible data contamination). Using signal price instead."
                            )
                        else:
                            current_price = fresh_price
                            logger.info(f"🔄 Fresh execution price for {pair}: {current_price}")
                    else:
                        current_price = fresh_price
                        logger.info(f"🔄 Fresh execution price for {pair}: {current_price}")
                else:
                    logger.warning(f"⚠️ Fresh ticker missing 'last' price for {pair}, using signal price")
            else:
                logger.warning(f"⚠️ Failed to get fresh price for {pair}, using signal price")
        except Exception as e:
            logger.error(f"❌ Error fetching fresh price: {e}")

        # Chase prevention: abort if price spiked too far from original signal price
        signal_entry_price = _to_positive_float(signal.get("price")) or current_price
        if signal_entry_price and signal_entry_price > 0:
            chase_pct = (current_price - signal_entry_price) / signal_entry_price
            if chase_pct > (Config.AUTOTRADE_CHASE_THRESHOLD_PCT / 100.0):
                logger.info(
                    f"🚫 Chase prevention: {pair} price moved +{chase_pct*100:.2f}% from signal price "
                    f"({Utils.format_price(current_price)} vs signal {Utils.format_price(signal_entry_price)}), skipping entry"
                )
                return

        # Portfolio heat / correlation limit check
        try:
            balance = bot.db.get_balance(user_id)
            corr_allowed, corr_factor, corr_reason = _check_correlated_exposure(bot, user_id, pair, balance)
            if not corr_allowed:
                logger.info(f"🚫 Entry blocked for {pair}: {corr_reason}")
                return
            if corr_factor < 1.0:
                amount *= corr_factor
                total *= corr_factor
                logger.info(f"📊 {corr_reason} for {pair}: new amount={amount:.4f}")
        except Exception as e:
            logger.warning(f"⚠️ Correlation check failed for {pair}: {e}")

        # V4 Trade Outcome check
        try:
            if hasattr(bot, 'ml_model_v4') and bot.ml_model_v4 and bot.ml_model_v4.is_fitted:
                v4_features = {
                    'signal_price': float(current_price),
                    'ml_confidence': float(confidence) if confidence else 0.5,
                    'recommendation': str(signal.get('recommendation', 'HOLD')),
                    'hour': datetime.now().hour,
                    'dayofweek': datetime.now().weekday(),
                    'symbol': pair,
                }
                v4_pred, v4_conf = bot.ml_model_v4.predict(v4_features)
                logger.info(f"🤖 [V4_FILTER] {pair}: {v4_pred} ({v4_conf:.1%})")

                if v4_pred.startswith('BAD'):
                    if is_dry_run:
                        # DRY RUN: V4 BAD prediction → reduce position size instead of blocking
                        # This allows data collection while still respecting the signal
                        signal["_v4_bad_prediction"] = True
                        v4_boost = 0.5  # Half size for BAD prediction in DRY RUN
                        logger.info(f"⚠️ [V4_FILTER] {pair}: BAD prediction in DRY RUN → size reduced 50% (not blocked)")
                    else:
                        reason = f"[V4_FILTER] Entry blocked for {pair}: predicted bad outcome ({v4_pred})"
                        logger.info(f"🚫 {reason}")
                        _remember_autotrade_block_reason(bot, pair, reason)
                        return
                elif v4_pred.startswith('GOOD') and v4_conf >= 0.65:
                    logger.info(f"📈 [V4_FILTER] Boost position for {pair}: good outcome predicted")
                    v4_boost = 1.2
                else:
                    v4_boost = 1.0
            else:
                v4_boost = 1.0
        except Exception as e:
            logger.debug(f"⚠️ V4 filter skipped for {pair}: {e}")
            v4_boost = 1.0

        indicators = signal.get('indicators', {})
        atr_value = indicators.get('atr')
        tp_data = bot.trading_engine.calculate_stop_loss_take_profit(current_price, "BUY", atr_value=atr_value)
        stop_loss = tp_data["stop_loss"]
        take_profit_1 = tp_data["take_profit_1"]
        take_profit_2 = tp_data["take_profit_2"]
        
        # Log R/R ratio for transparency
        rr_ratio = tp_data.get('rr_ratio', 0)
        method = tp_data.get('method', 'unknown')
        logger.info(f"📊 SL/TP Method: {method}, R/R Ratio: {rr_ratio:.2f}")

        sr_data = await get_support_resistance_for_pair(bot, pair)
        if sr_data:
            if sr_data.get("nearest_resistance") and take_profit_1 > sr_data["nearest_resistance"]:
                take_profit_1 = sr_data["nearest_resistance"] * 0.98
                logger.info(f"📊 TP1 adjusted to S/R: {take_profit_1:,.0f}")
            if sr_data.get("nearest_support") and stop_loss < sr_data["nearest_support"]:
                stop_loss = sr_data["nearest_support"] * 0.98
                logger.info(f"📊 SL adjusted to S/R: {stop_loss:,.0f}")

        if Config.RL_ENABLED:
            mi_signal = market_conditions.get("overall_signal", "NEUTRAL")
            state = bot._rl_get_state(confidence, regime.get("regime", "RANGE"), mi_signal)
            rl_action = bot._rl_choose_action(state)
            logger.info(f"🧠 RL action for {pair}: {rl_action} (state={state})")
            if rl_action == "SELL":
                logger.info(f"🧠 RL vetoed BUY for {pair}, suggests SELL instead")
                amount *= 0.5
                total *= 0.5

        ob = None
        elite_signal = None
        if Config.SMART_ROUTING_ENABLED:
            try:
                ob = bot.indodax.get_orderbook(pair, limit=20)
                if ob:
                    routing_orders = bot._smart_order_routing(pair, "buy", total, ob.get("bids", []), ob.get("asks", []))
                    logger.info(f"📊 Smart routing for {pair}: {len(routing_orders)} chunks")
            except Exception as e:
                logger.warning(f"⚠️ Smart routing failed for {pair}: {e}")

        liquidity_zones = bot._find_liquidity_zones(pair)
        if liquidity_zones:
            top_zone = liquidity_zones[0]
            logger.info(f"📊 Top liquidity zone for {pair}: {top_zone[0]:,.0f} (vol={top_zone[1]:,.0f})")

        try:
            ob = ob or bot.indodax.get_orderbook(pair, limit=20)
            raw_bids = ob.get("bids", []) if ob else []
            raw_asks = ob.get("asks", []) if ob else []
            elite_signal, elite_prob, elite_imb = bot._elite_signal(bot.historical_data.get(pair, pd.DataFrame()), raw_bids, raw_asks, liquidity_zones)
            logger.info(f"🎯 Elite signal for {pair}: {elite_signal} (prob={elite_prob}, imb={elite_imb})")
            if elite_signal == "SELL":
                logger.warning(f"⚠️ Elite signal conflicts with ML signal for {pair}")
                amount *= 0.5
                total *= 0.5
        except Exception as e:
            logger.warning(f"⚠️ Elite signal failed for {pair}: {e}")

        net_entry, _, _ = bot._fee_aware_net_price(current_price, "BUY")
        effective_tp = take_profit_1 * (1 - Config.TRADING_FEE_RATE)
        effective_sl = stop_loss * (1 + Config.TRADING_FEE_RATE)
        potential_profit = (effective_tp - net_entry) / net_entry * 100
        potential_loss = (net_entry - effective_sl) / net_entry * 100
        rr_after_fees = potential_profit / potential_loss if potential_loss > 0 else 0

        optimization = evaluate_autotrade_setup(
            signal=signal,
            market_conditions=market_conditions,
            regime=regime,
            rr_after_fees=rr_after_fees,
            liquidity_zones=liquidity_zones,
            elite_signal=elite_signal if 'elite_signal' in locals() else None,
        )
        if optimization.should_skip:
            if is_dry_run:
                # DRY RUN: profit optimizer skip → proceed with minimum size for data collection
                logger.info(
                    f"⚠️ [DRY RUN] {pair}: profit optimizer would skip ({optimization.reason}) "
                    f"— proceeding with 25% size for data collection"
                )
                signal["_optimizer_skip_override"] = True
                signal.setdefault("_exploration_mode", True)
                signal.setdefault("_exploration_factor_override", 0.25)
            else:
                logger.info(f"🚫 Trade blocked for {pair}: {optimization.reason}")
                _remember_autotrade_block_reason(bot, pair, optimization.reason)
                return

        if optimization.should_skip and is_dry_run:
            # DRY RUN: profit optimizer returned should_skip=True dengan
            # position_multiplier=0.0. Jangan apply multiplier 0 — pakai 1.0
            # agar amount tidak jadi 0. Eksplorasi size sudah diatur oleh
            # exploration_factor_override di atas (25%).
            logger.debug(f"🧪 [DRY RUN] {pair}: skipping position_multiplier=0 (optimizer skip override)")
        else:
            amount *= optimization.position_multiplier
            total *= optimization.position_multiplier

        # Apply V4 boost/reduction
        if 'v4_boost' in locals() and v4_boost != 1.0:
            amount *= v4_boost
            total *= v4_boost
            if v4_boost < 1.0:
                logger.info(f"📉 [V4] {pair}: position reduced to {v4_boost*100:.0f}% (BAD prediction in DRY RUN)")
            else:
                logger.info(f"📈 [V4_BOOST] Position size boosted {v4_boost:.0%} for {pair}")

        # FIX 2026-06-07: Final safety guard — cap DRY RUN total at MAX 2.000.000 IDR
        # and ensure amount/total are positive. This guards against:
        # - Multiple reduction multipliers making amount near-zero
        # - Bayesian Kelly override inflating position beyond the cap
        # - Any other mutation that produces invalid position size
        DRY_RUN_MAX_TOTAL = 2_000_000  # Hard cap for all pairs including BTC
        if is_dry_run:
            if amount <= 0 or total <= 0 or total > DRY_RUN_MAX_TOTAL:
                original_amount = amount
                original_total = total
                total = min(max(total, 1_000_000), DRY_RUN_MAX_TOTAL) if total > 0 else DRY_RUN_MAX_TOTAL
                amount = total / current_price if current_price > 0 else 0
                logger.warning(
                    f"🛡️ [DRY RUN GUARD] {pair}: amount={original_amount:.4f}, "
                    f"total={original_total:,.0f} → corrected to total={total:,.0f}, "
                    f"amount={amount:.4f}"
                )

        stop_loss = current_price - ((current_price - stop_loss) * optimization.stop_loss_multiplier)
        take_profit_1, take_profit_2 = scale_take_profit_targets(
            take_profit_1,
            take_profit_2,
            optimization.tp1_multiplier,
            optimization.tp2_multiplier,
            current_price,
            "BUY",
        )

        effective_tp = take_profit_1 * (1 - Config.TRADING_FEE_RATE)
        effective_sl = stop_loss * (1 + Config.TRADING_FEE_RATE)
        potential_profit = (effective_tp - net_entry) / net_entry * 100
        potential_loss = (net_entry - effective_sl) / net_entry * 100
        rr_after_fees = potential_profit / potential_loss if potential_loss > 0 else 0
        if rr_after_fees < optimization.min_rr_required:
            if is_dry_run:
                # DRY RUN: allow entry with reduced size for data collection
                logger.info(
                    f"⚠️ [DRY RUN] {pair}: R/R after fees low ({rr_after_fees:.2f} < {optimization.min_rr_required:.2f}) "
                    f"— proceeding with 30% size for data collection"
                )
                signal["_rr_reduced"] = True
                signal.setdefault("_exploration_mode", True)
                signal.setdefault("_exploration_factor_override", 0.30)
            else:
                reason = (
                    f"optimized R/R after fees too low "
                    f"({rr_after_fees:.2f} < {optimization.min_rr_required:.2f})"
                )
                logger.info(f"🚫 Trade blocked for {pair}: {reason}")
                _remember_autotrade_block_reason(bot, pair, reason)
                return

        logger.info(
            f"💰 Fee-aware: Entry={net_entry:,.0f}, TP={effective_tp:,.0f}, SL={effective_sl:,.0f}, "
            f"R/R={rr_after_fees:.2f}, Edge={optimization.edge_score:.1f}, SizeX={optimization.position_multiplier:.2f}"
        )

        # Tier 2: Calculate entry zone for limit order (scalping model)
        nearest_support = sr_data.get("nearest_support") if sr_data else None
        signal_entry_price = _to_positive_float(signal.get("price")) or current_price
        entry_zone_price = _calculate_entry_zone(current_price, support=nearest_support, signal_price=signal_entry_price)
        price_diff_pct = ((current_price - entry_zone_price) / current_price) * 100 if current_price > 0 else 0
        if price_diff_pct < Config.LIMIT_ORDER_MIN_EDGE_PCT:
            reason = (
                f"maker edge too small "
                f"({price_diff_pct:.2f}% < {Config.LIMIT_ORDER_MIN_EDGE_PCT:.2f}%)"
            )
            logger.info(f"🚫 Entry blocked for {pair}: {reason}")
            _remember_autotrade_block_reason(bot, pair, reason)
            return
        logger.info(
            f"🎯 [ENTRY_ZONE] {pair}: Limit order @ {entry_zone_price:,.0f} "
            f"({price_diff_pct:.2f}% below market {current_price:,.0f})"
        )

        if is_dry_run:
            simulated_order_id = f"DRY-{random.randint(100000, 999999)}"
            fill_price = None
            try:
                fill_ticker = bot.indodax.get_ticker(pair)
                _, ask, last = _extract_bid_ask_from_ticker(fill_ticker)
                fill_price = ask or last or current_price
            except Exception:
                fill_price = current_price

            # DRY RUN realism: apply simulated slippage to fill price (BUY pays more)
            slippage_pct = float(getattr(Config, "DRYRUN_SLIPPAGE_PCT", 0.001) or 0.001)
            fill_price_raw = fill_price
            fill_price = fill_price * (1 + slippage_pct)
            logger.debug(
                f"🧪 [DRY RUN SLIPPAGE] {pair}: raw={fill_price_raw:,.0f} → "
                f"slipped={fill_price:,.0f} (+{slippage_pct*100:.2f}%)"
            )

            # DRY RUN fill logic: fill immediately if market price is within
            # reasonable distance of entry zone (simulates realistic limit fill).
            # In real trading, limit orders near market typically fill quickly.
            # Threshold: fill if ask is within 1% above entry_zone_price.
            # This is generous to ensure DRY RUN generates enough trades for evaluation.
            fill_threshold_pct = 0.01  # 1% tolerance for immediate fill in DRY RUN
            fill_distance = (fill_price - entry_zone_price) / entry_zone_price if entry_zone_price > 0 else 999
            can_fill_immediately = fill_price <= entry_zone_price or fill_distance <= fill_threshold_pct

            if fill_price is not None and can_fill_immediately:
                if amount <= 0 or total <= 0:
                    logger.warning(f"🛡️ [DRY RUN] {pair}: amount={amount} atau total={total} <= 0, skip fill")
                    return
                fee_rate = float(getattr(Config, "TRADING_FEE_RATE", 0.0) or 0.0)
                # DRY RUN realism: fee applied on both entry and exit (round-trip)
                fee = float(fill_price) * float(amount) * fee_rate
                tp_fill = bot.trading_engine.calculate_stop_loss_take_profit(fill_price, "BUY", atr_value=atr_value)
                stop_loss = tp_fill["stop_loss"]
                take_profit_1 = tp_fill["take_profit_1"]
                take_profit_2 = tp_fill["take_profit_2"]
                trade_id = bot.db.add_trade(
                    user_id=user_id,
                    pair=pair,
                    trade_type="BUY",
                    price=float(fill_price),
                    amount=amount,
                    total=float(fill_price) * float(amount),
                    fee=fee,
                    signal_source="auto",
                    ml_confidence=confidence,
                    notes=f"[DRY RUN] Filled limit order_id: {simulated_order_id} @ {float(fill_price):,.0f}",
                )
                bot.price_monitor.set_price_level(user_id, trade_id, pair, float(fill_price), stop_loss, take_profit_1, take_profit_2, amount)
                text = f"""
🧪 **DRY RUN: FILLED LIMIT BUY** 🧪

📊 Pair: `{pair}`
💡 Action: **BUY** (SIMULATED)
💰 Fill Price: `{Utils.format_price(fill_price)}` IDR
📊 Limit Price: `{Utils.format_price(entry_zone_price)}` IDR
📦 Amount: `{amount}`
💵 Total: `{Utils.format_currency(float(fill_price) * float(amount))}`
💸 Fee: `{Utils.format_currency(fee)}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR
🎯 Take Profit: `{Utils.format_price(take_profit_1)}` IDR

🤖 Confidence: {confidence:.0%}
🆔 Trade ID: `{trade_id}`
📋 Order ID: `{simulated_order_id}`
"""
                await bot._broadcast_to_subscribers(pair, text)
                logger.info(f"🧪 [DRY RUN] Filled LIMIT BUY for {pair}: {amount} @ {float(fill_price):,.0f} (limit {entry_zone_price:,.0f})")
                return

            meta = {
                "ml_confidence": confidence,
                "atr": atr_value,
                "stop_loss": stop_loss,
                "take_profit_1": take_profit_1,
                "take_profit_2": take_profit_2,
                "signal_source": "auto",
            }
            try:
                existing = bot.db.get_pending_orders(pair=pair, status="PENDING")
                for pending in existing or []:
                    try:
                        if str(pending.get("trade_type") or pending.get("type") or "").upper() == "BUY":
                            return
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                bot.db.add_pending_order(
                    order_id=simulated_order_id,
                    pair=pair,
                    user_id=user_id,
                    trade_type="BUY",
                    limit_price=entry_zone_price,
                    amount=amount,
                    total=float(entry_zone_price) * float(amount),
                    notes=json.dumps(meta, separators=(",", ":")),
                    trade_id=None
                )
                logger.info(f"[PENDING_ORDER] Registered simulated limit order {simulated_order_id} for {pair}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to register pending order: {e}")
            text = f"""
🧪 **DRY RUN: SIMULATED LIMIT ORDER** 🧪

📊 Pair: `{pair}`
💡 Action: **BUY LIMIT** (SIMULATED)
💰 Entry Zone: `{Utils.format_price(entry_zone_price)}` IDR
📊 Market Price: `{Utils.format_price(current_price)}` IDR
📦 Amount: `{amount}`
💵 Total: `{Utils.format_currency(float(entry_zone_price) * float(amount))}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR (-2%)
🎯 Take Profit: `{Utils.format_price(take_profit_1)}` IDR

🤖 Confidence: {confidence:.0%}
📋 Order ID: `{simulated_order_id}`
"""
            await bot._broadcast_to_subscribers(pair, text)
            logger.info(f"🧪 [DRY RUN] Simulated LIMIT BUY for {pair}: {amount} @ {entry_zone_price:,.0f} (market was {current_price:,.0f})")
        else:
            if not Config.IS_API_KEY_CONFIGURED:
                logger.error(f"❌ Cannot execute real trade for {pair}: API keys not configured")
                await bot._broadcast_to_subscribers(pair, f"❌ **AUTO-TRADE BLOCKED**\n\nCannot execute real trade for {pair}.")
                return

            if Config.SMART_ROUTING_ENABLED and ob:
                # Note: smart routing uses current market; for Tier 2 we keep routing at market
                # but log the entry zone for future improvement
                routing_results = bot._split_order(pair, "buy", amount, ob.get("bids", []), ob.get("asks", []))
                if routing_results:
                    total_filled = sum(r.get("filled", 0) for r in routing_results if r)
                    avg_price = sum(r.get("avg_price", 0) * r.get("filled", 0) for r in routing_results if r) / total_filled if total_filled > 0 else current_price
                    order_id = routing_results[0].get("order_id", "SPLIT-ORDER")
                    current_price = avg_price
                    amount = total_filled
                    total = total_filled * avg_price
                else:
                    result = bot.indodax.create_order(pair, "buy", entry_zone_price, amount)
                    order_id = result.get("return", {}).get("order_id", "N/A") if result and result.get("success") == 1 else "N/A"
            else:
                result = bot.indodax.create_order(pair, "buy", entry_zone_price, amount)
                order_id = result.get("return", {}).get("order_id", "N/A") if result and result.get("success") == 1 else "N/A"

            if order_id and order_id != "N/A":
                trade_id = bot.db.add_trade(
                    user_id=user_id,
                    pair=pair,
                    trade_type="BUY",
                    price=entry_zone_price,
                    amount=amount,
                    total=total,
                    fee=0,
                    signal_source="auto",
                    ml_confidence=confidence,
                    notes=f"Auto-trade limit order_id: {order_id} @ {entry_zone_price:,.0f}",
                )
                bot.price_monitor.set_price_level(user_id, trade_id, pair, entry_zone_price, stop_loss, take_profit_1, take_profit_2, amount)
                # Register pending order for execution tracking
                try:
                    bot.db.add_pending_order(
                        order_id=order_id,
                        pair=pair,
                        user_id=user_id,
                        trade_type="BUY",
                        limit_price=entry_zone_price,
                        amount=amount,
                        total=total,
                        notes=f"Auto-trade limit order_id: {order_id}",
                        trade_id=trade_id
                    )
                    logger.info(f"[PENDING_ORDER] Registered real limit order {order_id} for {pair}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to register pending order: {e}")
                text = f"""
🚨 **AUTO-TRADE LIMIT ORDER PLACED** 🟢

📊 Pair: `{pair}`
💡 Action: **BUY LIMIT**
💰 Entry Zone: `{Utils.format_price(entry_zone_price)}` IDR
📊 Market Price: `{Utils.format_price(current_price)}` IDR
📦 Amount: `{amount}`
💵 Total: `{Utils.format_currency(total)}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR (-2%)
🎯 Take Profit: `{Utils.format_price(take_profit_1)}` IDR

🤖 Confidence: {confidence:.0%}
🆔 Trade ID: `{trade_id}`
📋 Order ID: `{order_id}`
"""
                await bot._broadcast_to_subscribers(pair, text)
                logger.info(f"✅ Auto-BUY limit placed for {pair}: {amount} @ {entry_zone_price:,.0f} (market {current_price:,.0f})")
            else:
                logger.error(f"❌ Auto-trade limit order failed for {pair}: order_id={order_id}")

    elif signal["recommendation"] in ["SELL", "STRONG_SELL"]:
        open_trades = bot.db.get_open_trades(user_id)
        pair_trades = [t for t in open_trades if t["pair"] == pair]
        if pair_trades:
            logger.info(f"🔴 SELL signal for {pair} - {len(pair_trades)} open position(s) found, executing auto-sell")
            await execute_auto_sell(bot, pair, signal, current_price, user_id, is_dry_run)
            if Config.RL_ENABLED and Config.RL_UPDATE_REWARD:
                for trade in pair_trades:
                    trade_dict = dict(trade) if hasattr(trade, "keys") else trade
                    entry = trade_dict.get("price", 0)
                    if entry > 0:
                        pnl_pct = ((current_price - entry) / entry) * 100
                        reward = pnl_pct / 100
                        regime_data = detect_market_regime(bot, pair)
                        state = bot._rl_get_state(signal["ml_confidence"], regime_data.get("regime", "RANGE"), "NEUTRAL")
                        bot._rl_update(state, "SELL", reward)
        else:
            logger.info(f"⏸️ SELL signal for {pair} - no open position to sell")

    if Config.PORTFOLIO_RISK_ADJUSTED:
        open_trades = bot.db.get_open_trades(user_id)
        if open_trades:
            total_exposure = sum(t["total"] for t in open_trades)
            balance = bot.db.get_balance(user_id)
            exposure_pct = (total_exposure / balance * 100) if balance > 0 else 0
            logger.info(f"📊 Portfolio exposure: {total_exposure:,.0f} IDR ({exposure_pct:.1f}%)")


async def analyze_market_intelligence(bot, pair, current_price):
    result = {
        "volume_spike": False,
        "volume_ratio": 0.0,  # 0.0 = no data (bukan 1.0 yang misleading)
        "orderbook_pressure": "NEUTRAL",
        "buy_sell_ratio": 1.0,
        "overall_signal": "NEUTRAL",
    }
    try:
        if pair in bot.historical_data and not bot.historical_data[pair].empty:
            df = bot.historical_data[pair]
            # 2026-06-10: volume_ratio fix.
            # Field `volume` di historical_data adalah volume_24h dari ticker
            # (rolling 24h window) yang di-append berulang per poll. Akibatnya
            # 20 candle terakhir punya volume ~sama → ratio ≈ 1.0 (palsu).
            # Solusi: pakai DELTA volume_24h antar candle = trade baru dalam
            # window poll. Volume_24h kadang turun (trade lama drop out window)
            # → clip ke 0 supaya tidak negatif.
            if len(df) >= 21:  # need 21 = 20 deltas + 1 anchor
                volume_delta = df["volume"].diff().clip(lower=0).dropna()
                if len(volume_delta) >= 20:
                    current_volume = float(volume_delta.iloc[-1])
                    avg_volume = float(volume_delta.iloc[-20:].mean())
                    if avg_volume > 0:
                        volume_ratio = current_volume / avg_volume
                        result["volume_ratio"] = round(volume_ratio, 2)
                        if volume_ratio >= Config.MI_VOLUME_SPIKE_MIN:
                            result["volume_spike"] = True
                            logger.info(f"📊 Volume spike detected for {pair}: {volume_ratio:.2f}x")
                    else:
                        logger.debug(f"📊 Volume data for {pair}: avg_delta=0 (no recent trades)")
                else:
                    logger.debug(f"📊 Volume data for {pair}: only {len(volume_delta)} deltas (need 20+)")
            else:
                logger.debug(f"📊 Volume data for {pair}: only {len(df)} candles (need 21+ for delta)")
        else:
            logger.debug(f"📊 Volume data for {pair}: no historical data in memory")

        try:
            orderbook = bot.indodax.get_orderbook(pair, limit=20)
            if orderbook:
                raw_bids = orderbook.get("bids", [])
                raw_asks = orderbook.get("asks", [])
                bot._update_heatmap(pair, raw_bids, raw_asks)
                cleaned_bids, cleaned_asks, spoof_detected = bot._detect_spoofing(pair, raw_bids, raw_asks)
                result["spoof_detected"] = spoof_detected
                # BUG FIX 2026-06-10: detect_spoofing return prices yang sudah
                # di-round ke ribuan (round(price, -3)), merusak presisi harga
                # untuk pair low-cap. Ini menyebabkan spread negatif (bid > ask)
                # karena best_bid jadi ribuan terdekat ke ATAS, sementara ask asli
                # tetap presisi. Contoh: bid=571 -> round=1000, best_ask=574 ->
                # spread -54%.
                #
                # Solusi: spread calculation tetap pakai RAW orderbook (cuma
                # filter price <= 0). Spoof detection tetap jalan untuk logging
                # dan alert tapi tidak mempengaruhi entry decision.
                raw_bids_clean = raw_bids[:10]
                raw_asks_clean = raw_asks[:10]
                # Filter out invalid prices (harga ≤ 0) dari raw data
                # Pattern sama dengan spread guard di bawah: try/except float
                def _price_valid(level):
                    try:
                        return float(level[0]) > 0
                    except (TypeError, ValueError, IndexError):
                        return False
                raw_bids_clean = [lv for lv in raw_bids_clean if _price_valid(lv)]
                raw_asks_clean = [lv for lv in raw_asks_clean if _price_valid(lv)]
                if raw_bids_clean and raw_asks_clean:
                    bids = raw_bids_clean
                    asks = raw_asks_clean
                else:
                    # Fallback: cleaned data (mungkin tidak ada data raw yang valid)
                    bids = cleaned_bids if cleaned_bids else raw_bids[:10]
                    asks = cleaned_asks if cleaned_asks else raw_asks[:10]

                def _orderbook_notional(levels):
                    total = 0.0
                    for level in levels or []:
                        try:
                            price = float(level[0])
                            amount = float(level[1])
                        except (TypeError, ValueError, IndexError):
                            continue
                        total += price * amount
                    return total

                total_bid_volume = _orderbook_notional(bids)
                total_ask_volume = _orderbook_notional(asks)
                if total_bid_volume > 0 and total_ask_volume > 0:
                    buy_sell_ratio = total_bid_volume / total_ask_volume
                    result["buy_sell_ratio"] = round(buy_sell_ratio, 2)
                    if buy_sell_ratio >= Config.MI_ORDERBOOK_BULLISH_MIN:
                        result["orderbook_pressure"] = "BULLISH"
                    elif buy_sell_ratio <= (1 / Config.MI_ORDERBOOK_BULLISH_MIN if Config.MI_ORDERBOOK_BULLISH_MIN > 0 else 0.7):
                        result["orderbook_pressure"] = "BEARISH"
                    logger.info(f"📊 Orderbook pressure for {pair}: {result['orderbook_pressure']} ({buy_sell_ratio:.2f}x)")

                # Spread guard: calculate best bid/ask and spread percentage
                #
                # Indodax kadang mengembalikan level dengan harga 0 (atau bid
                # kosong sama sekali) untuk pair low-cap / illiquid. Bila itu
                # tidak difilter, `max(bid_prices)` jadi 0 → spread terhitung
                # 100%/200%, dan bot meng-attribute ini ke SPREAD_TOO_WIDE.
                # Itu menyesatkan: penyebabnya bukan spread lebar, melainkan
                # tidak ada bid liquidity sama sekali. Kita pisahkan dua kasus:
                #  (a) NO_BID_LIQUIDITY  — bid kosong / semua harga ≤ 0
                #  (b) SPREAD_TOO_WIDE   — kedua sisi ada, gap > batas
                try:
                    bid_prices = []
                    ask_prices = []
                    for level in bids or []:
                        try:
                            price = float(level[0])
                        except (TypeError, ValueError, IndexError):
                            continue
                        if price > 0:  # filter level harga ≤ 0 (sentinel)
                            bid_prices.append(price)
                    for level in asks or []:
                        try:
                            price = float(level[0])
                        except (TypeError, ValueError, IndexError):
                            continue
                        if price > 0:
                            ask_prices.append(price)

                    has_bid = bool(bid_prices)
                    has_ask = bool(ask_prices)

                    if not has_bid or not has_ask:
                        # Liquidity hilang di salah satu sisi. Block entry tapi
                        # dengan label yang akurat — bukan "spread terlalu
                        # lebar". Skipping pair lebih tepat dari menunggu spread
                        # menyempit (bid kosong tidak akan menyempit).
                        if has_ask:
                            result["best_ask"] = min(ask_prices)
                        if has_bid:
                            result["best_bid"] = max(bid_prices)
                        result["spread_too_wide"] = True
                        result["block_reason"] = "NO_BID_LIQUIDITY"
                        bid_repr = f"{min(bid_prices):,.0f}" if has_bid else "EMPTY"
                        ask_repr = f"{min(ask_prices):,.0f}" if has_ask else "EMPTY"
                        logger.warning(
                            f"⚠️ No bid/ask liquidity for {pair}: "
                            f"bid={bid_repr} ask={ask_repr} "
                            f"(orderbook one-sided; pair illiquid)"
                        )
                    else:
                        best_bid = max(bid_prices)
                        best_ask = min(ask_prices)
                        mid_price = (best_bid + best_ask) / 2
                        if mid_price > 0:
                            spread_pct = (best_ask - best_bid) / mid_price
                            result["best_bid"] = best_bid
                            result["best_ask"] = best_ask
                            result["mid_price"] = mid_price
                            result["spread_pct"] = round(spread_pct, 6)
                            if spread_pct > Config.MI_SPREAD_MAX_PCT:
                                result["spread_too_wide"] = True
                                result["block_reason"] = "SPREAD_TOO_WIDE"
                                logger.warning(
                                    f"⚠️ Spread too wide for {pair}: {spread_pct*100:.3f}% "
                                    f">(max {Config.MI_SPREAD_MAX_PCT*100:.1f}%) "
                                    f"bid={best_bid:,.0f} ask={best_ask:,.0f}"
                                )
                            else:
                                result["spread_too_wide"] = False
                                logger.info(
                                    f"📊 Spread OK for {pair}: {spread_pct*100:.3f}% "
                                    f"bid={best_bid:,.0f} ask={best_ask:,.0f}"
                                )
                        else:
                            result["spread_too_wide"] = True
                            result["block_reason"] = "SPREAD_INVALID"
                            result["best_bid"] = best_bid
                            result["best_ask"] = best_ask
                            result["mid_price"] = mid_price
                except Exception as spread_err:
                    logger.debug(f"Spread calc skipped for {pair}: {spread_err}")
        except Exception as e:
            logger.warning(f"⚠️ Orderbook analysis failed for {pair}: {e}")

        bullish_signals = int(result["volume_spike"]) + int(result["orderbook_pressure"] == "BULLISH")
        if bullish_signals == 2:
            result["overall_signal"] = "BULLISH"
        elif bullish_signals == 1:
            result["overall_signal"] = "MODERATE"

        if Config.MI_REQUIRE_BULLISH_FOR_ENTRY:
            result["passes_entry_filter"] = result["overall_signal"] == "BULLISH"
        elif Config.MI_ALLOW_MODERATE_ENTRY:
            # FIX 2026-06-06: Also allow NEUTRAL if MI_ALLOW_NEUTRAL_ENTRY is True
            allow_neutral = getattr(Config, "MI_ALLOW_NEUTRAL_ENTRY", False)
            if allow_neutral:
                result["passes_entry_filter"] = result["overall_signal"] in ["BULLISH", "MODERATE", "NEUTRAL"]
            else:
                result["passes_entry_filter"] = result["overall_signal"] in ["BULLISH", "MODERATE"]
        else:
            result["passes_entry_filter"] = True

        # Spread hard gate: override passes_entry_filter if spread too wide
        if result.get("spread_too_wide"):
            result["passes_entry_filter"] = False

        spread_info = ""
        if result.get("spread_pct") is not None:
            block = " SPREAD_TOO_WIDE" if result.get("spread_too_wide") else ""
            spread_info = f", Spread={result['spread_pct']*100:.3f}%{block}"

        logger.info(
            f"📊 Market intelligence for {pair}: Volume={result['volume_ratio']}x, "
            f"OB={result['orderbook_pressure']}, Signal={result['overall_signal']}, "
            f"Filter={'PASS' if result['passes_entry_filter'] else 'FAIL'}{spread_info}"
        )
    except Exception as e:
        logger.error(f"❌ Error in market intelligence analysis for {pair}: {e}")
        result["passes_entry_filter"] = True

    return result


def _calculate_entry_zone(current_price, support=None, signal_price=None):
    """Tier 2: Calculate limit-order entry zone for scalping-style auto-trade.
    Returns entry_zone_price (limit price to place order).
    Logic: buy near support or slightly below current price to avoid chasing.

    FIX 2026-06-06: Uses Config.ENTRY_ZONE_DISTANCE_PCT (default 0.2%) instead of
    hardcoded 0.5%. Closer to market = more instant fills in trending markets.
    """
    entry_distance = getattr(Config, 'ENTRY_ZONE_DISTANCE_PCT', 0.002)

    if support and support > 0:
        # Entry slightly above support, but not more than entry_distance below current
        entry_from_support = support * 1.003
        entry_from_current = current_price * (1 - entry_distance)
        entry_zone = max(entry_from_support, entry_from_current)
    else:
        # No support data: use configurable distance below current as default entry zone
        entry_zone = current_price * (1 - entry_distance)

    if signal_price and signal_price > 0:
        # Never enter above signal price + 0.5% (chase prevention)
        max_entry = signal_price * 1.005
        if entry_zone > max_entry:
            entry_zone = max(signal_price * 0.998, current_price * 0.992)

    return round(entry_zone, 0)


async def get_support_resistance_for_pair(bot, pair):
    try:
        if pair not in bot.historical_data or bot.historical_data[pair].empty:
            return None
        df = bot.historical_data[pair]
        if len(df) < 50:
            return None
        sr_data = bot.sr_detector.detect_levels(df)
        if sr_data:
            logger.info(f"📊 S/R for {pair}: Support={sr_data.get('nearest_support')}, Resistance={sr_data.get('nearest_resistance')}")
        return sr_data
    except Exception as e:
        logger.error(f"❌ Error getting S/R for {pair}: {e}")
        return None


def detect_market_regime(bot, pair):
    result = {
        "regime": "UNKNOWN",
        "volatility": 0.0,
        "trend_strength": 0.0,
        "trend_direction": "NEUTRAL",
        "is_trending": False,
        "is_choppy": False,
        "is_high_vol": False,
    }
    try:
        if pair not in bot.historical_data or bot.historical_data[pair].empty:
            return result
        df = bot.historical_data[pair]
        if len(df) < 30:
            return result
        returns = df["close"].pct_change().dropna()
        volatility = returns.std()
        result["volatility"] = round(volatility, 4)
        current_price = df["close"].iloc[-1]
        lookback_price = df["close"].iloc[-20]
        trend_change = (current_price - lookback_price) / lookback_price
        result["trend_strength"] = round(trend_change, 4)
        if volatility > Config.REGIME_VOLATILITY_THRESHOLD:
            result["regime"] = "HIGH_VOLATILITY"
            result["is_high_vol"] = True
            result["trend_direction"] = "UP" if trend_change > 0 else "DOWN"
        elif abs(trend_change) > Config.REGIME_TREND_THRESHOLD:
            result["regime"] = "TREND"
            result["is_trending"] = True
            result["trend_direction"] = "UP" if trend_change > 0 else "DOWN"
        else:
            result["regime"] = "RANGE"
            result["is_choppy"] = True
        logger.info(f"📊 Regime for {pair}: {result['regime']} (vol={volatility:.4f}, trend={trend_change:.4f})")
    except Exception as e:
        logger.error(f"❌ Error detecting regime for {pair}: {e}")
    return result


async def execute_auto_sell(bot, pair, signal, current_price, user_id, is_dry_run):
    try:
        open_trades = bot.db.get_open_trades(user_id)
        pair_trades = [t for t in open_trades if t["pair"] == pair]
        if not pair_trades:
            logger.debug(f"⏸️ No open position for {pair}, skipping SELL")
            return

        for trade in pair_trades:
            trade_dict = dict(trade) if hasattr(trade, "keys") else trade
            trade_id = trade_dict.get("id")
            entry_price = trade_dict.get("price", 0)
            amount = trade_dict.get("amount", 0)
            if amount <= 0:
                logger.warning(f"⚠️ Invalid amount for trade {trade_id}: {amount}")
                continue

            sell_price = current_price
            try:
                fresh_ticker = bot.indodax.get_ticker(pair)
                if fresh_ticker:
                    sell_price = fresh_ticker["bid"]
                    logger.info(f"🔄 Fresh sell price for {pair}: {sell_price}")
            except Exception:
                logger.warning(f"⚠️ Failed to get fresh sell price for {pair}, using signal price")

            fee_rate = float(getattr(Config, "TRADING_FEE_RATE", 0.0) or 0.0)
            slippage_pct = float(getattr(Config, "DRYRUN_SLIPPAGE_PCT", 0.0) or 0.0)
            slippage_cap = float(getattr(Config, "SLIPPAGE_MAX_PCT", 0.0) or 0.0)
            effective_slippage = min(max(0.0, slippage_pct), max(0.0, slippage_cap))
            if is_dry_run and sell_price is not None:
                sell_price = float(sell_price) * (1 - effective_slippage)

            entry_fee = float(trade_dict.get("fee") or 0)
            if entry_fee <= 0 and entry_price and amount:
                entry_fee = float(entry_price) * float(amount) * fee_rate
            exit_fee = float(sell_price) * float(amount) * fee_rate if sell_price and amount else 0.0

            pnl = (float(sell_price) - float(entry_price)) * float(amount) - entry_fee - exit_fee
            invested = float(entry_price) * float(amount) if entry_price and amount else 0.0
            pnl_pct = ((pnl / invested) * 100) if invested > 0 else 0.0

            if is_dry_run:
                simulated_order_id = f"DRY-SELL-{random.randint(100000, 999999)}"
                bot.db.close_trade(
                    trade_id=trade_id,
                    sell_price=sell_price,
                    sell_amount=amount,
                    order_id=simulated_order_id,
                    reason=f"Auto-SELL ({signal['recommendation']})",
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                )
                bot.price_monitor.remove_price_level(user_id, trade_id)
                text = f"""
🧪 **DRY RUN: SIMULATED SELL** 🧪

📊 Pair: `{pair}`
💡 Action: **SELL** (SIMULATED)
💰 Price: `{Utils.format_price(sell_price)}` IDR
📦 Amount: `{amount}`

📈 Entry: `{Utils.format_price(entry_price)}` IDR
📊 P&L: `{Utils.format_currency(pnl)}` ({pnl_pct:+.2f}%)
💸 Fee (entry+exit): `{Utils.format_currency(entry_fee + exit_fee)}`

🤖 Signal: {signal['recommendation']}
🆔 Trade ID: `{trade_id}`
"""
                await bot._broadcast_to_subscribers(pair, text)
                logger.info(f"🧪 [DRY RUN] Simulated SELL for {pair}: {amount} @ {sell_price}, P&L={pnl_pct:+.2f}%")
                _record_trade_outcome_to_kelly(bot, pair, pnl_pct)
            else:
                if not Config.IS_API_KEY_CONFIGURED:
                    logger.error(f"❌ Cannot execute real sell for {pair}: API keys not configured")
                    return
                result = bot.indodax.create_order(pair, "sell", sell_price, amount)
                if result and result.get("success") == 1:
                    order_id = result.get("return", {}).get("order_id", "N/A")
                    bot.db.close_trade(trade_id=trade_id, sell_price=sell_price, sell_amount=amount, order_id=order_id, reason=f"Auto-SELL ({signal['recommendation']})")
                    bot.price_monitor.remove_price_level(user_id, trade_id)
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
                    await bot._broadcast_to_subscribers(pair, text)
                    logger.info(f"✅ Auto-SELL executed for {pair}: {amount} @ {sell_price}, P&L={pnl_pct:+.2f}%")
                    _record_trade_outcome_to_kelly(bot, pair, pnl_pct)
                else:
                    logger.error(f"❌ Auto-sell order failed for {pair}: {result}")
    except Exception as e:
        logger.error(f"❌ Auto-sell execution error for {pair}: {e}")


def _record_trade_outcome_to_kelly(bot, pair, pnl_pct):
    """Record trade outcome to Bayesian Kelly engine for adaptive learning."""
    try:
        kelly_engine = _get_quant_kelly(bot)
        if kelly_engine is not None:
            won = pnl_pct > 0
            kelly_engine.update_trade_outcome(pair, won=won, pnl_pct=pnl_pct)
            logger.info(
                f"📊 [QUANT KELLY] Recorded {pair} outcome: "
                f"{'WIN' if won else 'LOSS'} {pnl_pct:+.2f}%"
            )
    except Exception as e:
        logger.debug(f"[QUANT KELLY] Failed to record outcome: {e}")
