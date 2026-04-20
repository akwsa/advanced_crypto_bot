#!/usr/bin/env python3
"""Runtime helpers extracted from bot.py for signal monitoring and auto-trading."""

import asyncio
import logging
import random
from datetime import datetime, timedelta

import pandas as pd
import requests

from core.config import Config
from core.utils import Utils
from signals.signal_pipeline import generate_signal_for_pair

logger = logging.getLogger("crypto_bot")


def _is_watched(bot, pair):
    return any(pair in pairs for pairs in bot.subscribers.values())


def _is_auto_trade_pair(bot, pair):
    return any(pair in pairs for pairs in bot.auto_trade_pairs.values())


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

    if watched:
        await monitor_strong_signal(bot, pair)


async def monitor_strong_signal(bot, pair, signal=None):
    """Monitor watched pairs and send strong-signal alerts."""
    if not _is_watched(bot, pair):
        return

    if not hasattr(bot, "_last_signal_checks"):
        bot._last_signal_checks = {}

    last_check = bot._last_signal_checks.get(pair)
    if last_check and datetime.now() - last_check < timedelta(minutes=5):
        return
    bot._last_signal_checks[pair] = datetime.now()

    if signal is None:
        signal = await _get_cached_signal(bot, pair)
    if not signal or "recommendation" not in signal:
        if signal is not None and "recommendation" not in signal:
            logger.warning(f"⚠️ Signal for {pair} missing 'recommendation' key, skipping")
        return

    recommendation = signal.get("recommendation", "HOLD")
    confidence = signal.get("ml_confidence", 0)
    if recommendation not in ["STRONG_BUY", "STRONG_SELL", "BUY", "SELL"]:
        return

    signal_key = f"{pair}_{recommendation}"
    if not hasattr(bot, "_notification_cooldown"):
        bot._notification_cooldown = {}

    last_sent = bot._notification_cooldown.get(signal_key, datetime.min)
    if datetime.now() - last_sent < timedelta(minutes=5):
        logger.debug(f"⏳ Notification cooldown: {signal_key}")
        return
    bot._notification_cooldown[signal_key] = datetime.now()

    signal_text = bot._format_signal_message_html(signal)
    signal_emoji = {
        "STRONG_BUY": "🚀",
        "BUY": "📈",
        "SELL": "📉",
        "STRONG_SELL": "🔻",
    }.get(recommendation, "🔔")

    if recommendation in ["BUY", "STRONG_BUY"]:
        rec_colored = f"🟢 {recommendation}"
    elif recommendation in ["SELL", "STRONG_SELL"]:
        rec_colored = f"🔴 {recommendation}"
    else:
        rec_colored = f"⚪ {recommendation}"

    signal_text = f"{signal_emoji} <b>Signal Alert — {rec_colored}</b>\n\n{signal_text}"
    loop = asyncio.get_event_loop()
    for admin_id in Config.ADMIN_IDS:
        try:
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": admin_id, "text": signal_text, "parse_mode": "HTML"}
            response = await loop.run_in_executor(None, lambda: requests.post(url, json=payload, timeout=10))
            if response.status_code == 200:
                logger.info("📢 Signal alert sent to admin %s for %s: %s (%.1f%%)", admin_id, pair, recommendation, confidence * 100)
            else:
                logger.error("❌ Failed to send signal alert: HTTP %s - %s", response.status_code, response.text)
        except Exception as e:
            logger.error("❌ Failed to send signal alert via HTTP: %s", e)


async def check_trading_opportunity(bot, pair, signal=None):
    """Check and execute trading opportunity (auto-trading)."""
    if not bot.is_trading:
        return

    if not _is_auto_trade_pair(bot, pair):
        logger.debug(f"⏭️ Skipping {pair}: Not in auto-trade list (only in watchlist)")
        if _is_watched(bot, pair):
            await monitor_strong_signal(bot, pair, signal=signal)
        return

    if pair in bot.last_ml_update:
        if datetime.now() - bot.last_ml_update[pair] < timedelta(minutes=bot.auto_trade_interval_minutes):
            return
    bot.last_ml_update[pair] = datetime.now()

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
    if signal["recommendation"] not in ["STRONG_BUY", "BUY", "STRONG_SELL", "SELL"]:
        logger.debug(f"⏸️ Skipping {pair}: Weak signal ({signal['recommendation']})")
        return

    user_id = list(bot.subscribers.keys())[0] if bot.subscribers else 1
    signal_text = f"{mode_label}\n\n{bot._format_signal_message_html(signal)}"
    for admin_id in Config.ADMIN_IDS:
        try:
            await bot.app.bot.send_message(chat_id=admin_id, text=signal_text, parse_mode="HTML")
            logger.info(f"📢 Signal notification sent to admin {admin_id} for {pair}")
        except Exception as e:
            logger.error(f"❌ Failed to send signal notification: {e}")

    can_trade, reason = bot.risk_manager.check_daily_loss_limit(user_id)
    if not can_trade:
        logger.warning(f"⚠️ Trading blocked for {pair}: {reason}")
        return

    current_price = signal["price"]
    confidence = signal["ml_confidence"]

    if signal["recommendation"] in ["BUY", "STRONG_BUY"]:
        market_conditions = await analyze_market_intelligence(bot, pair, current_price)
        regime = detect_market_regime(bot, pair)
        if not market_conditions.get("passes_entry_filter", True):
            logger.info(f"🚫 Entry blocked for {pair}: MI filter failed (Signal={market_conditions['overall_signal']})")
            return

        if regime["is_high_vol"]:
            logger.info(f"⚠️ HIGH VOLATILITY regime detected for {pair} - proceeding with caution")
            amount, total = bot.trading_engine.calculate_position_size(1, current_price)
            amount *= 0.5
            total *= 0.5
            logger.info(f"📊 Position size reduced 50% due to high volatility: {amount}")
        elif regime["is_trending"] and regime["trend_direction"] == "DOWN":
            logger.info(f"⚠️ DOWNTREND detected for {pair} - reducing position size")
            amount, total = bot.trading_engine.calculate_position_size(1, current_price)
            amount *= 0.75
            total *= 0.75
            logger.info(f"📊 Position size reduced 25% due to downtrend: {amount}")
        else:
            amount, total = bot.trading_engine.calculate_position_size(1, current_price)

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

        tp_data = bot.trading_engine.calculate_stop_loss_take_profit(current_price, "BUY")
        stop_loss = tp_data["stop_loss"]
        take_profit_1 = tp_data["take_profit_1"]
        take_profit_2 = tp_data["take_profit_2"]

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
        if rr_after_fees < Config.RISK_REWARD_RATIO * 0.8:
            logger.info(f"🚫 Trade blocked for {pair}: R/R after fees too low ({rr_after_fees:.2f})")
            return

        logger.info(f"💰 Fee-aware: Entry={net_entry:,.0f}, TP={effective_tp:,.0f}, SL={effective_sl:,.0f}, R/R={rr_after_fees:.2f}")

        if is_dry_run:
            simulated_order_id = f"DRY-{random.randint(100000, 999999)}"
            trade_id = bot.db.add_trade(
                user_id=user_id,
                pair=pair,
                trade_type="BUY",
                price=current_price,
                amount=amount,
                total=total,
                fee=0,
                signal_source="auto",
                ml_confidence=confidence,
                notes=f"[DRY RUN] Simulated order_id: {simulated_order_id}",
            )
            bot.price_monitor.set_price_level(user_id, trade_id, pair, current_price, stop_loss, take_profit_1, take_profit_2, amount)
            text = f"""
🧪 **DRY RUN: SIMULATED TRADE** 🧪

📊 Pair: `{pair}`
💡 Action: **BUY** (SIMULATED)
💰 Price: `{Utils.format_price(current_price)}` IDR
📦 Amount: `{amount}`
💵 Total: `{Utils.format_currency(total)}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR (-2%)
🎯 Take Profit: `{Utils.format_price(take_profit_1)}` IDR

🤖 Confidence: {confidence:.0%}
🆔 Trade ID: `{trade_id}`
📋 Order ID: `{simulated_order_id}`
"""
            await bot._broadcast_to_subscribers(pair, text)
            logger.info(f"🧪 [DRY RUN] Simulated BUY for {pair}: {amount} @ {current_price}")
        else:
            if not Config.IS_API_KEY_CONFIGURED:
                logger.error(f"❌ Cannot execute real trade for {pair}: API keys not configured")
                await bot._broadcast_to_subscribers(pair, f"❌ **AUTO-TRADE BLOCKED**\n\nCannot execute real trade for {pair}.")
                return

            if Config.SMART_ROUTING_ENABLED and ob:
                routing_results = bot._split_order(pair, "buy", amount, ob.get("bids", []), ob.get("asks", []))
                if routing_results:
                    total_filled = sum(r.get("filled", 0) for r in routing_results if r)
                    avg_price = sum(r.get("avg_price", 0) * r.get("filled", 0) for r in routing_results if r) / total_filled if total_filled > 0 else current_price
                    order_id = routing_results[0].get("order_id", "SPLIT-ORDER")
                    current_price = avg_price
                    amount = total_filled
                    total = total_filled * avg_price
                else:
                    result = bot.indodax.create_order(pair, "buy", current_price, amount)
                    order_id = result.get("return", {}).get("order_id", "N/A") if result and result.get("success") == 1 else "N/A"
            else:
                result = bot.indodax.create_order(pair, "buy", current_price, amount)
                order_id = result.get("return", {}).get("order_id", "N/A") if result and result.get("success") == 1 else "N/A"

            if order_id and order_id != "N/A":
                trade_id = bot.db.add_trade(
                    user_id=user_id,
                    pair=pair,
                    trade_type="BUY",
                    price=current_price,
                    amount=amount,
                    total=total,
                    fee=0,
                    signal_source="auto",
                    ml_confidence=confidence,
                    notes=f"Auto-trade order_id: {order_id}",
                )
                bot.price_monitor.set_price_level(user_id, trade_id, pair, current_price, stop_loss, take_profit_1, take_profit_2, amount)
                text = f"""
🚨 **AUTO-TRADE EXECUTED** 🟢

📊 Pair: `{pair}`
💡 Action: **BUY**
💰 Price: `{Utils.format_price(current_price)}` IDR
📦 Amount: `{amount}`
💵 Total: `{Utils.format_currency(total)}`

🛡️ Stop Loss: `{Utils.format_price(stop_loss)}` IDR (-2%)
🎯 Take Profit: `{Utils.format_price(take_profit_1)}` IDR

🤖 Confidence: {confidence:.0%}
🆔 Trade ID: `{trade_id}`
📋 Order ID: `{order_id}`
"""
                await bot._broadcast_to_subscribers(pair, text)
                logger.info(f"✅ Auto-BUY executed for {pair}: {amount} @ {current_price}")
            else:
                logger.error(f"❌ Auto-trade order failed for {pair}: order_id={order_id}")

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
            total_exposure = sum(t["total"] for t in open_trades if hasattr(t, "get") or isinstance(t, dict))
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
                    if volume_ratio > 1.5:
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
                    if buy_sell_ratio > 1.3:
                        result["orderbook_pressure"] = "BULLISH"
                    elif buy_sell_ratio < 0.7:
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
                else:
                    logger.error(f"❌ Auto-sell order failed for {pair}: {result}")
    except Exception as e:
        logger.error(f"❌ Auto-sell execution error for {pair}: {e}")
