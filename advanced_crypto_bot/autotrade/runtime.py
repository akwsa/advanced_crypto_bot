#!/usr/bin/env python3
# Tujuan: Runtime helpers for signal monitoring, autotrade execution, and market-intelligence gating.
# Caller: bot.AdvancedCryptoBot price-update flow and Telegram-triggered autotrade flow.
# Dependensi: core.config, core.utils, core.profit_optimizer, signals.signal_pipeline, pandas, requests.
# Main Functions: process_price_update_signal_tasks, monitor_strong_signal, check_trading_opportunity, analyze_market_intelligence, detect_market_regime, execute_auto_sell.
# Side Effects: HTTP calls to Telegram/Indodax, DB reads/writes via bot dependencies, trade execution, notifications.
"""Runtime helpers extracted from bot.py for signal monitoring and auto-trading."""

import asyncio
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


def _signal_notifications_enabled(bot):
    """Return whether automatic Telegram signal notifications are enabled."""
    return getattr(bot, "signal_notifications_enabled", True)


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
    """Return DRY RUN nominal based on pair price tier.

    Rules:
    - price < 10,000  => price * 1000
    - 10,000..100,000 => price * 100
    - price > 100,000 => price * 10
    """
    price_value = _to_positive_float(price)
    if price_value is None:
        return None
    if price_value < 10_000:
        multiplier = 1000
    elif price_value <= 100_000:
        multiplier = 100
    else:
        multiplier = 10
    return float(price_value * multiplier)


async def _get_cached_signal(bot, pair):
    now = datetime.now()
    cache = getattr(bot, "_signal_result_cache", {})
    cached = cache.get(pair)
    if cached and (now - cached["timestamp"]).total_seconds() < 2:
        return cached["signal"]

    in_flight = getattr(bot, "_signal_inflight_tasks", {}).get(pair)
    if in_flight:
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
        # Auto-promote: in DRY RUN, watched pairs with BUY signal get promoted
        if Config.AUTO_TRADE_DRY_RUN and _is_watched(bot, pair):
            _auto_promote_pair(bot, pair)
        else:
            logger.debug(f"⏭️ Skipping {pair}: Not in auto-trade list (only in watchlist)")
            if _is_watched(bot, pair):
                await monitor_strong_signal(bot, pair, signal=signal)
            return

    pair_key = _normalize_pair(pair)
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
    # For autotrade, use pre-SR recommendation if available. SR_VALIDATION is
    # designed for Telegram notification filtering; autotrade has its own entry
    # gates (market intelligence, R/R, profit optimizer) that are more appropriate.
    effective_rec = signal.get("pre_sr_recommendation") or signal["recommendation"]
    if effective_rec not in ["STRONG_BUY", "BUY", "STRONG_SELL", "SELL"]:
        logger.debug(f"⏸️ Skipping {pair}: Weak signal ({effective_rec})")
        return
    # Override recommendation with pre-SR for autotrade execution path
    signal["recommendation"] = effective_rec
    if cooldown_active and signal["recommendation"] not in ["STRONG_SELL", "SELL"]:
        logger.debug(f"⏭️ Skipping {pair}: scan cooldown active and signal is not SELL")
        return
    if cooldown_active:
        logger.debug(f"⏭️ Bypassing auto-trade scan cooldown for {pair}: open position needs SELL monitoring")
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
                await bot.app.bot.send_message(**kwargs)
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
            return

        market_conditions = await analyze_market_intelligence(bot, pair, current_price)
        regime = detect_market_regime(bot, pair)
        if not market_conditions.get("passes_entry_filter", True) and not is_dry_run:
            logger.info(f"🚫 Entry blocked for {pair}: MI filter failed (Signal={market_conditions['overall_signal']})")
            return
        elif not market_conditions.get("passes_entry_filter", True):
            logger.info(f"⚠️ [DRY RUN] MI filter would block {pair} (Signal={market_conditions['overall_signal']}), proceeding anyway")

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
                current_price = fresh_ticker["last"]
                logger.info(f"🔄 Fresh execution price for {pair}: {current_price}")
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
                    logger.info(f"🚫 [V4_FILTER] Entry blocked for {pair}: predicted bad outcome ({v4_pred})")
                    return

                if v4_pred.startswith('GOOD') and v4_conf >= 0.65:
                    logger.info(f"📈 [V4_FILTER] Boost position for {pair}: good outcome predicted")
                    # Will apply boost after position size calc
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
            logger.info(f"🚫 Trade blocked for {pair}: {optimization.reason}")
            return

        amount *= optimization.position_multiplier
        total *= optimization.position_multiplier

        # Apply V4 boost (if GOOD prediction with high confidence)
        if 'v4_boost' in locals() and v4_boost > 1.0:
            amount *= v4_boost
            total *= v4_boost
            logger.info(f"📈 [V4_BOOST] Position size boosted {v4_boost:.0%} for {pair}")

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
            logger.info(
                f"🚫 Trade blocked for {pair}: optimized R/R after fees too low "
                f"({rr_after_fees:.2f} < {optimization.min_rr_required:.2f})"
            )
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
            logger.info(
                f"🚫 Entry blocked for {pair}: maker edge too small "
                f"({price_diff_pct:.2f}% < {Config.LIMIT_ORDER_MIN_EDGE_PCT:.2f}%)"
            )
            return
        logger.info(
            f"🎯 [ENTRY_ZONE] {pair}: Limit order @ {entry_zone_price:,.0f} "
            f"({price_diff_pct:.2f}% below market {current_price:,.0f})"
        )

        if is_dry_run:
            simulated_order_id = f"DRY-{random.randint(100000, 999999)}"
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
                notes=f"[DRY RUN] Simulated limit order_id: {simulated_order_id} @ {entry_zone_price:,.0f}",
            )
            bot.price_monitor.set_price_level(user_id, trade_id, pair, entry_zone_price, stop_loss, take_profit_1, take_profit_2, amount)
            # Register pending order for execution tracking
            try:
                bot.db.add_pending_order(
                    order_id=simulated_order_id,
                    pair=pair,
                    user_id=user_id,
                    trade_type="BUY",
                    limit_price=entry_zone_price,
                    amount=amount,
                    total=total,
                    notes="[DRY RUN] Simulated limit order",
                    trade_id=trade_id
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
💵 Total: `{Utils.format_currency(total)}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR (-2%)
🎯 Take Profit: `{Utils.format_price(take_profit_1)}` IDR

🤖 Confidence: {confidence:.0%}
🆔 Trade ID: `{trade_id}`
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
        "volume_ratio": 1.0,
        "orderbook_pressure": "NEUTRAL",
        "buy_sell_ratio": 1.0,
        "overall_signal": "NEUTRAL",
    }
    try:
        if pair in bot.historical_data and not bot.historical_data[pair].empty:
            df = bot.historical_data[pair]
            if len(df) >= 20:
                current_volume = df["volume"].iloc[-1]
                avg_volume = df["volume"].iloc[-20:].mean()
                if avg_volume > 0:
                    volume_ratio = current_volume / avg_volume
                    result["volume_ratio"] = round(volume_ratio, 2)
                    if volume_ratio >= Config.MI_VOLUME_SPIKE_MIN:
                        result["volume_spike"] = True
                        logger.info(f"📊 Volume spike detected for {pair}: {volume_ratio:.2f}x")

        try:
            orderbook = bot.indodax.get_orderbook(pair, limit=20)
            if orderbook:
                raw_bids = orderbook.get("bids", [])
                raw_asks = orderbook.get("asks", [])
                bot._update_heatmap(pair, raw_bids, raw_asks)
                cleaned_bids, cleaned_asks, spoof_detected = bot._detect_spoofing(pair, raw_bids, raw_asks)
                result["spoof_detected"] = spoof_detected
                bids = cleaned_bids if cleaned_bids else raw_bids[:10]
                asks = cleaned_asks if cleaned_asks else raw_asks[:10]
                total_bid_volume = sum(bid[0] * bid[1] for bid in bids) if bids else 0
                total_ask_volume = sum(ask[0] * ask[1] for ask in asks) if asks else 0
                if total_bid_volume > 0 and total_ask_volume > 0:
                    buy_sell_ratio = total_bid_volume / total_ask_volume
                    result["buy_sell_ratio"] = round(buy_sell_ratio, 2)
                    if buy_sell_ratio >= Config.MI_ORDERBOOK_BULLISH_MIN:
                        result["orderbook_pressure"] = "BULLISH"
                    elif buy_sell_ratio <= (1 / Config.MI_ORDERBOOK_BULLISH_MIN if Config.MI_ORDERBOOK_BULLISH_MIN > 0 else 0.7):
                        result["orderbook_pressure"] = "BEARISH"
                    logger.info(f"📊 Orderbook pressure for {pair}: {result['orderbook_pressure']} ({buy_sell_ratio:.2f}x)")
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
            result["passes_entry_filter"] = result["overall_signal"] in ["BULLISH", "MODERATE"]
        else:
            result["passes_entry_filter"] = True

        logger.info(
            f"📊 Market intelligence for {pair}: Volume={result['volume_ratio']}x, "
            f"OB={result['orderbook_pressure']}, Signal={result['overall_signal']}, "
            f"Filter={'PASS' if result['passes_entry_filter'] else 'FAIL'}"
        )
    except Exception as e:
        logger.error(f"❌ Error in market intelligence analysis for {pair}: {e}")
        result["passes_entry_filter"] = True

    return result


def _calculate_entry_zone(current_price, support=None, signal_price=None):
    """Tier 2: Calculate limit-order entry zone for scalping-style auto-trade.
    Returns entry_zone_price (limit price to place order).
    Logic: buy near support or slightly below current price to avoid chasing.
    """
    if support and support > 0:
        # Entry slightly above support, but not more than 1% below current
        entry_from_support = support * 1.003
        entry_from_current = current_price * 0.995
        entry_zone = max(entry_from_support, entry_from_current)
    else:
        # No support data: use 0.5% below current as default entry zone
        entry_zone = current_price * 0.995

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

            pnl = (sell_price - entry_price) * amount
            pnl_pct = ((sell_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

            if is_dry_run:
                simulated_order_id = f"DRY-SELL-{random.randint(100000, 999999)}"
                bot.db.close_trade(trade_id=trade_id, sell_price=sell_price, sell_amount=amount, order_id=simulated_order_id, reason=f"Auto-SELL ({signal['recommendation']})")
                bot.price_monitor.remove_price_level(user_id, trade_id)
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
