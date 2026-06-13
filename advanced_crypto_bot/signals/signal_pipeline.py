#!/usr/bin/env python3
# Tujuan: Pipeline end-to-end pembentukan signal per pair.
# Caller: bot.py _generate_signal_for_pair dan background monitor.
# Dependensi: TechnicalAnalysis, ML models, SignalQualityEngine, DB/cache.
# Main Functions: generate_signal_for_pair.
# Side Effects: DB read/write signal, cache reads, CPU-heavy analysis.
"""Signal generation pipeline extracted from bot.py."""

import logging
import os
from datetime import datetime

from analysis.technical_analysis import TechnicalAnalysis
from signals.signal_rules import (
    get_final_actionable_rejection_reason,
    is_buy_support_entry_zone,
    min_confidence_for,
    should_block_actionable_on_stale_price,
)
from signals.signal_decision_layer import (
    classify_buy_signal_label,
    should_reject_duplicate_buy_signal,
)

logger = logging.getLogger("crypto_bot")

ACTIONABLE_SIGNALS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}
BUY_SIGNALS = {"BUY", "STRONG_BUY"}
SELL_SIGNALS = {"SELL", "STRONG_SELL"}

# FIX #4: In-memory cache per pair untuk GARCH/VaR/ARIMA (TTL 5 menit)
_quant_cache: dict = {}


def _pct_distance(reference_price, level):
    """Return percentage distance from price to a level."""
    if reference_price <= 0 or level <= 0:
        return None
    return abs(level - reference_price) / reference_price * 100


def _compute_directional_sr_metrics(recommendation, price, support_1, resistance_1):
    """Compute support/resistance metrics using the active trade direction."""
    distance_to_support_pct = _pct_distance(price, support_1)
    distance_to_resistance_pct = _pct_distance(price, resistance_1)
    stop_distance_pct = None
    risk_reward_ratio = 0.0

    if recommendation in BUY_SIGNALS and support_1 > 0 and resistance_1 > 0:
        risk = price - support_1
        reward = resistance_1 - price
        stop_distance_pct = distance_to_support_pct
        if risk > 0 and reward > 0:
            risk_reward_ratio = reward / risk
    elif recommendation in SELL_SIGNALS and support_1 > 0 and resistance_1 > 0:
        risk = resistance_1 - price
        reward = price - support_1
        stop_distance_pct = distance_to_resistance_pct
        if risk > 0 and reward > 0:
            risk_reward_ratio = reward / risk

    return {
        "distance_to_support_pct": distance_to_support_pct,
        "distance_to_resistance_pct": distance_to_resistance_pct,
        "stop_distance_pct": stop_distance_pct,
        "risk_reward_ratio": risk_reward_ratio,
    }


def _apply_directional_confidence_adjustment(recommendation, confidence, raw_adjustment):
    """Apply enhancement confidence in the same direction as the active signal."""
    if raw_adjustment == 0 or recommendation not in ACTIONABLE_SIGNALS:
        return confidence, 0.0

    applied_adjustment = raw_adjustment if recommendation in BUY_SIGNALS else -raw_adjustment
    adjusted_confidence = max(0.0, min(1.0, confidence + applied_adjustment))
    return adjusted_confidence, applied_adjustment


def _apply_final_rejection(signal, source, reason):
    """Apply a standardized final rejection to HOLD."""
    signal["recommendation"] = "HOLD"
    signal["reason"] = f"[{source}] {reason}"
    signal["final_gate_source"] = source


async def generate_signal_for_pair(bot, pair):
    """Generate comprehensive trading signal using bot dependencies."""
    # FIX 2026-06-13: Guard against under-filled in-memory cache.
    # Polling thread bisa append 1-N tick ke historical_data[pair] sebelum bootstrap
    # dari DB sempat jalan. Akibatnya: pipeline pakai df pendek (5-10 row) → HTF
    # resample 1h → 5 candle → INSUFFICIENT_DATA permanen walau DB punya 800+ tick.
    # Re-load dari DB kalau cache kurang dari setengah target supaya HTF SMA slow=10
    # (butuh ≥11 candle 1h ≈ ≥660 tick @ 64s cadence) bisa jalan.
    cache_target = getattr(__import__('core.config', fromlist=['Config']).Config,
                           'HISTORICAL_DATA_LIMIT', 800)
    cache_min = cache_target // 2  # 400 tick = ~7 jam, masih kurang tapi best effort

    if pair not in bot.historical_data:
        if hasattr(bot, '_load_historical_data'):
            await bot._load_historical_data(pair)
    elif len(bot.historical_data[pair]) < cache_min and hasattr(bot, '_load_historical_data'):
        logger.info(
            f"📚 [REFILL] {pair}: cache only {len(bot.historical_data[pair])} rows "
            f"(< {cache_min}), reloading from DB"
        )
        await bot._load_historical_data(pair)

    if pair not in bot.historical_data or bot.historical_data[pair].empty:
        logger.warning(f"⚠️ No data available for {pair} yet (waiting for WebSocket)")
        return None

    df = bot.historical_data[pair].copy()
    if len(df) < 60:
        logger.warning(f"⚠️ Not enough data for {pair}: {len(df)} candles (need 60+)")
        return None

    real_time_price = None
    price_source = "UNKNOWN"
    stale_price_fallback = False
    stale_realtime_price = False
    ws_price = None
    ws_timestamp = None
    try:
        from api.indodax_api import IndodaxAPI

        indodax = IndodaxAPI()
        ticker = indodax.get_ticker(pair)
        if ticker:
            real_time_price = ticker["last"]
            price_source = "API"
            logger.info(f"🌐 API price for {pair}: {real_time_price}")
    except Exception as e:
        logger.error(f"❌ Failed to get API price for {pair}: {e}")

    if real_time_price is None and pair in bot.price_data and bot.price_data[pair]:
        ws_price = bot.price_data[pair].get("last")
        ws_timestamp = bot.price_data[pair].get("timestamp")
        if ws_timestamp and (datetime.now() - ws_timestamp).total_seconds() < 60:
            real_time_price = ws_price
            price_source = "WEBSOCKET_FRESH"
            logger.info(f"📡 WebSocket price for {pair}: {ws_price} (fresh)")
        else:
            stale_realtime_price = True
            logger.warning(f"⚠️ WebSocket price stale for {pair}")

    # Only flag stale_realtime_price if we are actually relying on a stale WS cache.
    # If API provided a fresh price, the WS cache age is irrelevant.
    if real_time_price is not None and price_source not in ("API", "WEBSOCKET_FRESH") and pair in bot.price_data and bot.price_data[pair]:
        ws_price = bot.price_data[pair].get("last")
        ws_timestamp = bot.price_data[pair].get("timestamp")
        if ws_timestamp and (datetime.now() - ws_timestamp).total_seconds() >= 60:
            stale_realtime_price = True
            logger.warning(
                f"⚠️ Cached realtime price stale for {pair}: age={(datetime.now() - ws_timestamp).total_seconds():.0f}s"
            )

    if real_time_price is None:
        real_time_price = df["close"].iloc[-1]
        price_source = "HISTORICAL_FALLBACK"
        stale_price_fallback = True
        logger.warning(f"⚠️ Using historical price for {pair}: {real_time_price}")

    logger.info(f"✅ Final price for {pair}: {real_time_price} (source={price_source})")

    ta = TechnicalAnalysis(df)
    ta_signals = ta.get_signals()

    ml_prediction = None
    try:
        predict_result = bot.ml_model.predict(df)
        if len(predict_result) == 3:
            ml_prediction, ml_confidence, ml_signal_class = predict_result
        elif len(predict_result) == 2:
            ml_prediction, ml_confidence = predict_result
            ml_signal_class = "BUY" if ml_prediction else "SELL"
        else:
            logger.warning(f"⚠️ Unexpected predict result format: {len(predict_result)} values")
            ml_prediction, ml_confidence, ml_signal_class = None, 0.5, "HOLD"

        if ml_signal_class:
            logger.info(f"✅ ML prediction successful for {pair}: {ml_confidence:.2%} ({ml_signal_class})")
        else:
            logger.info(f"✅ ML prediction successful for {pair}: {ml_confidence:.2%}")

        if isinstance(ml_prediction, bool):
            ml_prediction_bool = ml_prediction
        elif isinstance(ml_prediction, int) and bot.ml_version == "V2":
            ml_prediction_bool = ml_prediction >= 3
        else:
            ml_prediction_bool = ml_prediction

        if ml_prediction is None:
            logger.info(f"⏳ ML model not trained yet for {pair} — using TA-only signal")
    except Exception as e:
        logger.warning(f"⚠️ ML prediction failed for {pair}: {e}")
        import traceback

        logger.debug(f"ML Error: {traceback.format_exc()}")
        logger.info(f"💡 Using TA-only signal for {pair}")
        ml_prediction = None
        ml_prediction_bool = None
        ml_confidence = 0.65
        ml_signal_class = None

    # [FALLBACK GUARD] Jika primary model tidak fitted atau return default HOLD+0.65
    # (tanda silent failure mis. sklearn version mismatch), coba gunakan V2 sebagai fallback.
    # Ini memastikan ML tetap berkontribusi ke combined_strength di trading_engine.
    _primary_is_fitted = getattr(bot.ml_model, '_is_fitted', True)
    _primary_default_hold = (ml_signal_class in (None, 'HOLD') and abs(ml_confidence - 0.65) < 0.001)

    if not _primary_is_fitted or _primary_default_hold:
        _fb_result = None
        _fb_source = None

        # Fallback ke V2 jika primary bukan V2
        if getattr(bot, 'ml_version', 'V2') != 'V2':
            try:
                from analysis.ml_model_v2 import MLTradingModelV2
                if not hasattr(bot, '_ml_fallback_v2'):
                    bot._ml_fallback_v2 = MLTradingModelV2()
                if getattr(bot._ml_fallback_v2, '_is_fitted', False):
                    _fb_result = bot._ml_fallback_v2.predict(df)
                    _fb_source = 'V2'
            except Exception as _fe:
                logger.debug(f"[ML FALLBACK] V2 attempt failed for {pair}: {_fe}")

        if _fb_result and len(_fb_result) == 3:
            _fb_pred, _fb_conf, _fb_class = _fb_result
            # Gunakan fallback jika primary tidak fitted (selalu), atau jika fallback
            # memberikan sinyal lebih informatif dari HOLD default.
            if not _primary_is_fitted or _fb_class not in (None, 'HOLD'):
                ml_prediction = _fb_pred
                ml_confidence = _fb_conf
                ml_signal_class = _fb_class
                if isinstance(ml_prediction, bool):
                    ml_prediction_bool = ml_prediction
                elif isinstance(ml_prediction, int):
                    ml_prediction_bool = ml_prediction >= 3
                else:
                    ml_prediction_bool = bool(ml_prediction) if ml_prediction is not None else None
                logger.info(
                    f"🔄 [ML FALLBACK] {pair}: primary {'not fitted' if not _primary_is_fitted else 'HOLD default'}"
                    f" → using {_fb_source}: {_fb_class} ({_fb_conf:.2%})"
                )
        elif not _primary_is_fitted:
            logger.warning(
                f"⚠️ [ML FALLBACK] {pair}: primary not fitted, no fallback available "
                f"— proceeding TA-only"
            )

    # NEW: V4 Trade Outcome prediction (if available)
    v4_prediction = None
    v4_confidence = None
    try:
        if hasattr(bot, 'ml_model_v4') and bot.ml_model_v4 and bot.ml_model_v4.is_fitted:
            v4_features = {
                'signal_price': real_time_price,
                'ml_confidence': float(ml_confidence) if ml_confidence else 0.5,
                'recommendation': str(ml_signal_class) if ml_signal_class else 'HOLD',
                'hour': datetime.now().hour,
                'dayofweek': datetime.now().weekday(),
                'symbol': pair,
            }
            v4_prediction, v4_confidence = bot.ml_model_v4.predict(v4_features)
            logger.info(f"🤖 V4 outcome prediction for {pair}: {v4_prediction} ({v4_confidence:.2%})")
        elif hasattr(bot, 'ml_model_v4') and bot.ml_model_v4 and not bot.ml_model_v4.is_fitted:
            logger.debug(f"V4 model loaded but not fitted for {pair}, skipping prediction")
        else:
            logger.debug(f"V4 model not available for {pair}, skipping prediction")
    except Exception as e:
        logger.warning(f"⚠️ V4 prediction failed for {pair}: {e}")

    signal = bot.trading_engine.generate_signal(
        pair=pair,
        ta_signals=ta_signals,
        ml_prediction=ml_prediction_bool,
        ml_confidence=ml_confidence,
        ml_signal_class=ml_signal_class,
    )
    # Preserve raw ML confidence (pre enhancement adjustments) for UI transparency.
    signal["ml_confidence_raw"] = ml_confidence

    logger.info(f"📊 Signal for {pair}: {signal['recommendation']}")
    logger.info(f"📊 ML Confidence: {ml_confidence:.2%}")
    logger.info(f"📊 TA Strength: {ta_signals.get('strength', 0):.2f}")
    logger.info(f"📊 Combined Strength: {signal.get('combined_strength', 0):.2f}")
    logger.info(
        "🔎 [PIPELINE BASE] %s | ml_class=%s | base_rec=%s | ml_conf=%.2f | ta_strength=%+.2f | combined=%+.2f",
        pair,
        ml_signal_class or "NONE",
        signal["recommendation"],
        ml_confidence,
        ta_signals.get("strength", 0),
        signal.get("combined_strength", 0),
    )
    signal["price_source"] = price_source
    signal["stale_price_fallback"] = stale_price_fallback
    signal["stale_realtime_price"] = stale_realtime_price

    original_rec = signal["recommendation"]
    stabilization_applied = False
    previous_signal_info = bot.previous_signals.get(pair, {}).copy()

    if pair in bot.previous_signals:
        prev = bot.previous_signals[pair]
        prev_rec = prev.get("recommendation", "HOLD")
        prev_timestamp = prev.get("timestamp", datetime.now())
        time_diff = (datetime.now() - prev_timestamp).total_seconds()
        signal_levels = {
            "STRONG_BUY": 3,
            "BUY": 2,
            "HOLD": 1,
            "SELL": -2,
            "STRONG_SELL": -3,
        }

        current_level = signal_levels.get(signal["recommendation"], 0)
        prev_level = signal_levels.get(prev_rec, 0)
        jump = abs(current_level - prev_level)

        if jump >= 7:
            if signal["recommendation"] == "STRONG_BUY":
                logger.info(f"🛡️ [STABILIZE] Extreme jump detected: {pair} {prev_rec} → {original_rec}")
                logger.info(f"   → Downgrading STRONG_BUY → BUY (extreme jump: {jump})")
                signal["recommendation"] = "BUY"
                signal["reason"] = f"Signal stabilized from {prev_rec}. Extreme jump ({jump}). Downgraded to BUY."
                stabilization_applied = True
            elif signal["recommendation"] == "STRONG_SELL":
                logger.info(f"🛡️ [STABILIZE] Extreme jump detected: {pair} {prev_rec} → {original_rec}")
                logger.info(f"   → Downgrading STRONG_SELL → SELL (extreme jump: {jump})")
                signal["recommendation"] = "SELL"
                signal["reason"] = f"Signal stabilized from {prev_rec}. Extreme jump ({jump}). Downgraded to SELL."
                stabilization_applied = True
        elif jump >= 5:
            confidence = signal.get("ml_confidence", 0)
            if signal["recommendation"] == "STRONG_BUY" and confidence > 0.70:
                logger.info(f"✅ [ALLOW] HOLD → STRONG_BUY with high confidence: {pair} ({confidence:.1%})")
            elif signal["recommendation"] == "STRONG_BUY":
                logger.info(f"🛡️ [STABILIZE] Moderate jump: {pair} {prev_rec} → {original_rec}")
                logger.info(f"   → Downgrading STRONG_BUY → BUY (moderate jump: {jump}, conf: {confidence:.1%})")
                signal["recommendation"] = "BUY"
                signal["reason"] = f"Signal stabilized from {prev_rec}. Moderate jump ({jump}). Downgraded to BUY."
                stabilization_applied = True
            elif signal["recommendation"] == "STRONG_SELL":
                if prev_rec in ["SELL", "HOLD"]:
                    logger.info(f"✅ [ALLOW] Signal strengthening: {pair} {prev_rec} → {original_rec} (trend continuation)")
                else:
                    logger.info(f"🛡️ [STABILIZE] Moderate jump: {pair} {prev_rec} → {original_rec}")
                    logger.info(f"   → Downgrading STRONG_SELL → SELL (moderate jump: {jump})")
                    signal["recommendation"] = "SELL"
                    signal["reason"] = f"Signal stabilized from {prev_rec}. Moderate jump ({jump}). Downgraded to SELL."
                    stabilization_applied = True
            elif signal["recommendation"] in ["BUY", "SELL"]:
                logger.info(f"✅ [ALLOW] Keeping {signal['recommendation']} for {pair} (no downgrade)")
        elif time_diff > 1800:
            logger.info(f"✅ [ALLOW] Large time gap ({time_diff/60:.0f}m), allowing signal change: {pair} {prev_rec} → {original_rec}")

    if stabilization_applied:
        logger.warning(f"⚠️ [FINAL] Signal for {pair}: {original_rec} → {signal['recommendation']} (STABILIZED)")
    else:
        logger.info(f"📊 [FINAL] Signal for {pair}: {signal['recommendation']} (no stabilization)")

    # Batch 3: hard reject actionable signal when only stale historical fallback price is available.
    if should_block_actionable_on_stale_price(
        stale_price_fallback,
        signal["recommendation"],
        stale_realtime_price=stale_realtime_price,
    ):
        if stale_price_fallback:
            reject_reason = (
                f"Actionable signal blocked due to stale realtime price "
                f"(using historical fallback={real_time_price:,.0f})"
            )
        else:
            cache_age = (datetime.now() - ws_timestamp).total_seconds() if ws_timestamp else None
            reject_reason = (
                "Actionable signal blocked due to stale realtime cache "
                f"(price_source={price_source}, cache_age={cache_age:.0f}s)"
                if cache_age is not None
                else f"Actionable signal blocked due to stale realtime cache (price_source={price_source})"
            )
        logger.warning(f"🛡️ [PRICE VALIDATION] {pair}: {signal['recommendation']} → HOLD | {reject_reason}")
        _apply_final_rejection(signal, "PRICE_VALIDATION", reject_reason)
        signal["price_filtered"] = True

    last_signal_info = previous_signal_info
    last_signal_time = last_signal_info.get("timestamp")
    last_recommendation = last_signal_info.get("recommendation", "HOLD")
    ml_signal_class_for_engine = signal["recommendation"]

    is_volatile_safe, vol_reason = (True, "OK")
    regime = "UNKNOWN"
    position_multiplier = 1.0
    try:
        is_volatile_safe, vol_reason = bot.signal_quality_engine.check_volatility_filter(df, pair=pair)
        regime, position_multiplier = bot.signal_quality_engine.detect_market_regime(df)
    except Exception as e:
        logger.warning(f"⚠️ [{pair}] Volatility/regime checks failed: {e}")

    if not is_volatile_safe:
        signal["recommendation"] = "HOLD"
        signal["reason"] = f"Volatility filter: {vol_reason}"
        signal["volatility_filtered"] = True
        logger.warning(f"🛡️ [VOLATILITY] {pair}: {vol_reason}")
    elif position_multiplier == 0.0:
        signal["recommendation"] = "HOLD"
        signal["reason"] = f"Market regime: {regime} - too volatile for trading"
        signal["regime_filtered"] = True
        logger.warning(f"🛡️ [REGIME] {pair}: {regime} - no trading")
    else:
        signal["market_regime"] = regime
        signal["position_multiplier"] = position_multiplier
        if position_multiplier < 1.0:
            logger.info(f"📊 [{pair}] Regime: {regime}, Position size: {position_multiplier*100:.0f}%")

    # Snapshot recommendation BEFORE Quality Engine + SR Validation run.
    # Autotrade execution path uses this to bypass the filter pipeline:
    # - Quality Engine V3 + SR Validation are designed for Telegram
    #   notification filtering (avoid spam, enforce confluence rules).
    # - Autotrade has its own 17 entry gates (MI, V4, chase prevention,
    #   correlation, R/R-after-fees, profit optimizer, etc.) that are
    #   more appropriate for execution decisions.
    # Field name kept as `pre_sr_recommendation` for backward compat with
    # autotrade/runtime.py:514 (renaming would touch multiple call sites).
    # Regime filter (above) intentionally NOT bypassed — it represents
    # genuine "market unsafe to trade" verdict, not a filter heuristic.
    signal["pre_sr_recommendation"] = signal.get("recommendation", "HOLD")

    quality_signal = bot.signal_quality_engine.generate_signal(
        pair=pair,
        ta_signals=ta_signals,
        ml_prediction=ml_prediction_bool if ml_prediction is not None else False,
        ml_confidence=ml_confidence,
        ml_signal_class=ml_signal_class_for_engine,
        last_signal_time=last_signal_time,
        last_recommendation=last_recommendation,
        combined_strength=signal.get("combined_strength", 0.0),
        df=df,  # NEW: pass price data for quant mean reversion analysis
        market_regime=regime,  # NEW: pass regime for z-score alignment check
        current_price=real_time_price,
    )

    if quality_signal and quality_signal.get("type") == "HOLD":
        original_rec = signal["recommendation"]
        signal["recommendation"] = "HOLD"
        signal["reason"] = quality_signal.get("reason", f"Signal rejected by Quality Engine V3 (was {original_rec})")
        signal["quality_filtered"] = True
        logger.warning(
            f"🛡️ [QUALITY ENGINE] {pair}: {original_rec} → HOLD | "
            f"Reason: {quality_signal.get('reason', 'Unknown')}"
        )
    elif quality_signal:
        # ROUND 6: Merge Quality Engine result back into runtime signal.
        # This is required for graceful downgrades (STRONG_BUY→BUY / STRONG_SELL→SELL)
        # and for downstream S/R smart gate to see the correct confluence value.
        original_rec = signal.get("recommendation", "HOLD")
        approved_rec = quality_signal.get("recommendation") or quality_signal.get("type") or original_rec
        signal["quality_approved"] = True
        signal["recommendation"] = approved_rec
        signal["type"] = approved_rec
        signal["confluence_score"] = quality_signal.get("confluence", 0)
        signal["confluence"] = quality_signal.get("confluence", 0)
        if quality_signal.get("reason"):
            signal["quality_reason"] = quality_signal.get("reason")
        if approved_rec != original_rec:
            logger.info(
                f"⬇️ [QUALITY ENGINE] {pair}: runtime recommendation adjusted "
                f"{original_rec} → {approved_rec} (confluence: {quality_signal.get('confluence', 0)})"
            )
        logger.info(f"✅ [QUALITY ENGINE] {pair}: {signal['recommendation']} approved (confluence: {quality_signal.get('confluence', 0)})")

    # NEW: Enrich signal with Quant Mean Reversion z-score data
    try:
        mr_data = bot.signal_quality_engine.analyze_mean_reversion(
            df=df,
            pair=pair,
            market_regime=regime,
            current_price=real_time_price,
        )
        if mr_data:
            signal["mean_reversion"] = mr_data
            # Apply confidence boost if MR aligns with signal direction
            mr_signal = mr_data.get("mr_signal", "NEUTRAL")
            mr_boost = mr_data.get("mr_confidence_boost", 0.0)
            rec = signal.get("recommendation", "HOLD")
            if mr_boost > 0 and rec in ACTIONABLE_SIGNALS:
                is_buy = rec in BUY_SIGNALS
                mr_is_buy = mr_signal in ("BUY", "STRONG_BUY")
                if (is_buy and mr_is_buy) or (not is_buy and not mr_is_buy and mr_signal != "NEUTRAL"):
                    old_conf = signal.get("ml_confidence", 0.5)
                    new_conf = min(1.0, old_conf + mr_boost)
                    signal["ml_confidence"] = new_conf
                    logger.info(
                        f"📈 [QUANT MR BOOST] {pair}: Confidence {old_conf:.1%} → {new_conf:.1%} "
                        f"(+{mr_boost:.1%} from z={mr_data.get('z_score_composite', 0):+.2f})"
                    )
    except Exception as e:
        logger.debug(f"[QUANT MR] {pair}: Enrichment skipped: {e}")

    signal["price"] = real_time_price
    support_1 = 0
    resistance_1 = 0
    risk_reward = 0
    distance_to_support_pct = None
    distance_to_resistance_pct = None

    try:
        sr_levels = bot.sr_detector.detect_levels(
            df=df,
            levels=2,
            current_price=real_time_price,
            method="auto",
            pair=pair,
        )
        signal.update(sr_levels)
        support_1 = sr_levels.get("support_1", 0)
        resistance_1 = sr_levels.get("resistance_1", 0)
        raw_risk_reward = sr_levels.get("risk_reward_ratio", 0)
        directional_sr = _compute_directional_sr_metrics(
            signal["recommendation"],
            real_time_price,
            support_1,
            resistance_1,
        )
        distance_to_support_pct = directional_sr["distance_to_support_pct"]
        distance_to_resistance_pct = directional_sr["distance_to_resistance_pct"]
        signal["sr_raw_risk_reward_ratio"] = raw_risk_reward
        signal["sr_stop_distance_pct"] = directional_sr["stop_distance_pct"]
        signal["distance_to_support_pct"] = distance_to_support_pct or 0
        signal["distance_to_resistance_pct"] = distance_to_resistance_pct or 0
        if signal["recommendation"] in ACTIONABLE_SIGNALS:
            risk_reward = directional_sr["risk_reward_ratio"]
            signal["risk_reward_ratio"] = risk_reward
        else:
            risk_reward = raw_risk_reward

        logger.info(
            f"📊 [S/R] {pair}: S1={sr_levels.get('support_1', 0):,.0f} | "
            f"R1={sr_levels.get('resistance_1', 0):,.0f} | "
            f"Zone={sr_levels.get('price_zone', 'UNKNOWN')} | "
            f"R/R={risk_reward:.2f}"
        )
        logger.info(
            "🔎 [PIPELINE BASE] %s | final_pre_sr=%s | s1=%s | r1=%s | dist_s1=%s | dist_r1=%s | rr=%.2f",
            pair,
            signal["recommendation"],
            f"{support_1:,.0f}" if support_1 > 0 else "n/a",
            f"{resistance_1:,.0f}" if resistance_1 > 0 else "n/a",
            f"{distance_to_support_pct:.2f}%" if distance_to_support_pct is not None else "n/a",
            f"{distance_to_resistance_pct:.2f}%" if distance_to_resistance_pct is not None else "n/a",
            risk_reward,
        )
    except Exception as e:
        logger.warning(f"⚠️ [S/R] Failed to detect levels for {pair}: {e}")
        signal["support_1"] = 0
        signal["support_2"] = 0
        signal["resistance_1"] = 0
        signal["resistance_2"] = 0
        signal["price_zone"] = "UNKNOWN"
        signal["risk_reward_ratio"] = 0

    # NOTE: signal["pre_sr_recommendation"] sudah di-snapshot di atas
    # (sebelum Quality Engine, line ~399). Itu adalah recommendation yang
    # autotrade pakai untuk bypass Quality Engine + SR Validation.
    # Field di sini sengaja TIDAK di-overwrite supaya autotrade dapat
    # melihat keadaan pre-filter, bukan post-Quality-Engine.

    # Final runtime gate for actionable signals (authoritative path).
    try:
        from core.config import Config
        sr_validation_enabled = getattr(Config, 'ENABLE_SR_VALIDATION', True)
        if sr_validation_enabled:
            support_1 = signal.get("support_1", 0)
            resistance_1 = signal.get("resistance_1", 0)
            risk_reward = signal.get("risk_reward_ratio", 0)
            recommendation = signal.get("recommendation", "HOLD")
            rr_threshold = getattr(Config, 'SR_MIN_RR_RATIO', 1.5)
            sl_min_pct = getattr(Config, 'SR_MIN_SL_PCT', 0.3)
            near_support_pct = getattr(Config, 'SR_NEAR_SUPPORT_PCT', 2.0)
            near_resistance_pct = getattr(Config, 'SR_NEAR_RESISTANCE_PCT', 2.0)

            if recommendation in ACTIONABLE_SIGNALS:
                sl_distance_pct = signal.get("sr_stop_distance_pct")
                if sl_distance_pct is None:
                    sl_distance_pct = 999

                reject_signal = False
                reject_reason = ""

                sr_confidence = float(signal.get("ml_confidence") or ml_confidence or 0)
                sr_confluence = int(signal.get("confluence", 0) or 0)

                if recommendation in BUY_SIGNALS and resistance_1 > 0 and real_time_price > 0:
                    # Guard: S/R validation hanya valid bila R1 dan harga
                    # real-time keduanya valid. Sebelum guard ini, pair dengan
                    # data orderbook corrupt (R1=0, price=0) tetap masuk
                    # validation dan auto-reject karena `0 >= 0 * (1 - X)`.
                    if real_time_price >= resistance_1 * (1 - near_resistance_pct / 100):
                        reject_reason = (
                            f"BUY at/near resistance "
                            f"(price={real_time_price:,.0f}, R1={resistance_1:,.0f}, "
                            f"conf={sr_confidence:.2f}, confluence={sr_confluence})"
                        )
                        reject_signal = True
                        reject_reason = "BUY rejected: " + reject_reason

                if not reject_signal and recommendation in BUY_SIGNALS and support_1 > 0:
                    support_floor = signal.get("support_2", 0) or support_1 * (1 - near_support_pct / 100)
                    support_ceiling = support_1 * (1 + near_support_pct / 100)
                    if not is_buy_support_entry_zone(
                        real_time_price,
                        support_1,
                        signal.get("support_2", 0),
                        near_support_pct,
                    ):
                        reject_signal = True
                        reject_reason = (
                            "BUY rejected: outside support entry zone "
                            f"(price={real_time_price:,.0f}, S2={support_floor:,.0f}, "
                            f"S1={support_1:,.0f}, max_entry={support_ceiling:,.0f}, "
                            f"zone={signal.get('price_zone', 'UNKNOWN')}, "
                            f"conf={sr_confidence:.2f}, confluence={sr_confluence})"
                        )

                if not reject_signal and recommendation in SELL_SIGNALS and support_1 > 0:
                    if real_time_price <= support_1 * (1 + near_support_pct / 100):
                        reject_reason = (
                            f"SELL at/near support "
                            f"(price={real_time_price:,.0f}, S1={support_1:,.0f}, "
                            f"conf={sr_confidence:.2f}, confluence={sr_confluence})"
                        )
                        reject_signal = True
                        reject_reason = "SELL rejected: " + reject_reason

                if not reject_signal and risk_reward > 0 and risk_reward < rr_threshold:
                    reject_reason = (
                        f"risk/reward low "
                        f"(rr={risk_reward:.2f} < min={rr_threshold:.2f}, "
                        f"conf={sr_confidence:.2f}, confluence={sr_confluence})"
                    )
                    reject_signal = True
                    reject_reason = "Signal rejected: " + reject_reason
                if not reject_signal and sl_distance_pct < sl_min_pct:
                    reject_reason = (
                        f"stop distance tight "
                        f"(sl={sl_distance_pct:.2f}% < min={sl_min_pct:.1f}%, "
                        f"conf={sr_confidence:.2f}, confluence={sr_confluence})"
                    )
                    reject_signal = True
                    reject_reason = "Signal rejected: " + reject_reason

                if reject_signal:
                    logger.warning(f"🛡️ [S/R VALIDATION] {pair}: {recommendation} → HOLD | {reject_reason}")
                    _apply_final_rejection(signal, "SR_VALIDATION", reject_reason)
                    signal["sr_filtered"] = True
    except Exception as e:
        logger.warning(f"⚠️ [S/R VALIDATION] Failed for {pair}: {e}")

    if ml_signal_class_for_engine in ["BUY", "STRONG_BUY"] and signal["recommendation"] != ml_signal_class_for_engine:
        logger.warning(
            "🟡 [BUY TRACE] %s | requested=%s | final=%s | reason=%s | confluence=%s | combined=%+.2f | ml_conf=%.2f | s1=%s | r1=%s | dist_s1=%s | dist_r1=%s | rr=%.2f",
            pair,
            ml_signal_class_for_engine,
            signal["recommendation"],
            signal.get("reason", "Unknown"),
            quality_signal.get("confluence", "n/a") if quality_signal else "n/a",
            signal.get("combined_strength", 0),
            signal.get("ml_confidence", ml_confidence),
            f"{support_1:,.0f}" if support_1 > 0 else "n/a",
            f"{resistance_1:,.0f}" if resistance_1 > 0 else "n/a",
            f"{distance_to_support_pct:.2f}%" if distance_to_support_pct is not None else "n/a",
            f"{distance_to_resistance_pct:.2f}%" if distance_to_resistance_pct is not None else "n/a",
            risk_reward,
        )

    try:
        volume_24h = None
        try:
            ticker = bot.indodax.get_ticker(pair)
            if ticker:
                # get_ticker returns 'volume' (in IDR for sorting) from Indodax API
                volume_24h = float(ticker.get("volume", 0) or 0)
                if volume_24h <= 0:
                    # Fallback: try vol_idr or compute from vol_btc * last
                    volume_24h = float(ticker.get("vol_idr", 0) or 0)
                if volume_24h <= 0:
                    vol_btc = float(ticker.get("vol_btc", 0) or 0)
                    last = float(ticker.get("last", 0) or 0)
                    if vol_btc > 0 and last > 0:
                        volume_24h = vol_btc * last
        except Exception:
            pass

        # Attach volume to signal for Telegram display
        if volume_24h and volume_24h > 0:
            signal["volume_24h"] = volume_24h

        enhancement_result = bot.signal_enhancement.analyze(
            df=df,
            current_price=real_time_price,
            volume_24h=volume_24h,
            base_recommendation=signal["recommendation"],
        )

        signal["enhancement"] = {
            "enabled_features": enhancement_result.get("enabled_features", []),
            "adjustments": enhancement_result.get("adjustments", []),
            "vwap": enhancement_result.get("vwap", {}),
            "ichimoku": enhancement_result.get("ichimoku", {}),
            "divergence": enhancement_result.get("divergence", {}),
            "candlestick": enhancement_result.get("candlestick", {}),
            "volume": enhancement_result.get("volume", {}),
        }

        raw_confidence_adjustment = enhancement_result.get("final_confidence_adjustment", 0)
        # Cap negative adjustment to -0.05 max (prevent enhancement from killing signals)
        if raw_confidence_adjustment < -0.03:
            raw_confidence_adjustment = -0.03
        old_confidence = signal.get("ml_confidence", 0.5)
        adjusted_confidence, applied_adjustment = _apply_directional_confidence_adjustment(
            signal.get("recommendation", "HOLD"),
            old_confidence,
            raw_confidence_adjustment,
        )
        if applied_adjustment != 0:
            signal["ml_confidence"] = adjusted_confidence
            logger.info(
                f"📈 [ENHANCEMENT] {pair}: Confidence adjusted {old_confidence:.1%} → {signal['ml_confidence']:.1%} "
                f"(adjustment: {applied_adjustment:+.2f}, features: {enhancement_result.get('enabled_features', [])})"
            )

        if enhancement_result.get("should_override"):
            signal["recommendation"] = "HOLD"
            signal["reason"] = enhancement_result.get("override_reason", "Enhancement rejected signal")
            signal["enhancement_filtered"] = True
            logger.warning(f"🛡️ [ENHANCEMENT] {pair}: Signal overridden to HOLD | {signal['reason']}")
    except Exception as e:
        logger.warning(f"⚠️ [ENHANCEMENT] Failed for {pair}: {e}")

    # ── Quant enrichment: GARCH / VaR / ARIMA ────────────────────────────
    # FIX #1: Dipindahkan ke SINI — sebelum ARIMA filter dan sebelum DB save.
    # FIX #2: GARCH regime di-set ke trading_engine di sini (bukan setelah return).
    # FIX #4: Cache per pair dengan TTL 5 menit untuk hindari recompute tiap sinyal.
    try:
        from quant.volatility_models import GARCHModel
        from quant.risk_metrics import RiskMetrics
        from quant.forecasting import ARIMAModel
        from datetime import timedelta

        _now = datetime.now()
        _cache = _quant_cache.get(pair, {})
        _cache_age = (_now - _cache.get("ts", _now - timedelta(minutes=10))).total_seconds()
        _cache_valid = _cache_age < 300  # TTL 5 menit

        close_prices = df["close"].tolist()
        returns_pct = (df["close"].pct_change().dropna() * 100).tolist()

        if _cache_valid:
            # Gunakan hasil cache
            signal.update({k: v for k, v in _cache.items() if k != "ts"})
            logger.debug(f"[QUANT CACHE] {pair}: hit (age={_cache_age:.0f}s)")
        else:
            _new_cache = {"ts": _now}

            # GARCH(1,1)
            if len(returns_pct) >= 30:
                _gr = GARCHModel().fit(returns_pct[-200:])
                if _gr:
                    _new_cache.update({
                        "garch_current_vol": round(_gr.current_vol, 4),
                        "garch_forecast_vol": round(_gr.forecast_vol_1d, 4),
                        "garch_regime": _gr.regime,
                        "garch_persistence": round(_gr.persistence, 4),
                        "garch_has_clustering": _gr.has_clustering,
                    })

            # VaR / CVaR — dari return candle (per-candle scale)
            if len(returns_pct) >= 20:
                _rr = RiskMetrics(mc_simulations=500, random_seed=42).calculate(
                    returns_pct[-100:], confidence=0.95
                )
                if _rr:
                    _new_cache.update({
                        "var_historical": round(_rr.var_historical, 4),
                        "var_parametric": round(_rr.var_parametric, 4),
                        "cvar_historical": round(_rr.cvar_historical, 4),
                    })

            # ARIMA forecast
            if len(close_prices) >= 30:
                _ar = ARIMAModel(p=1, d=1, q=1).fit_forecast(close_prices[-100:], steps=3)
                if _ar:
                    _new_cache.update({
                        "arima_direction": _ar.direction,
                        "arima_change_pct": round(_ar.expected_change_pct, 4),
                        "arima_forecast_1": round(_ar.forecast[0], 2) if _ar.forecast else None,
                    })

            _quant_cache[pair] = _new_cache
            signal.update({k: v for k, v in _new_cache.items() if k != "ts"})
            logger.debug(f"[QUANT CACHE] {pair}: computed & cached")

        # FIX #2: Set GARCH regime ke trading_engine SEKARANG (sebelum filter & DB save)
        if hasattr(bot, 'trading_engine') and "garch_regime" in signal:
            bot.trading_engine._last_garch_regime = signal["garch_regime"]

    except Exception as _qe:
        logger.debug(f"[QUANT ENRICH] {pair}: skipped — {_qe}")
    # ── End quant enrichment ──────────────────────────────────────────────

    # V4 Validation for Actionable Signals
    if v4_prediction and signal["recommendation"] in ACTIONABLE_SIGNALS:
        direction = "BUY" if signal["recommendation"] in BUY_SIGNALS else "SELL"
        if v4_prediction == f"BAD_{direction}":
            reject_reason = f"V4 predicted bad outcome ({v4_prediction})"
            logger.warning(f"🛡️ [V4 VALIDATION] {pair}: {signal['recommendation']} → HOLD | {reject_reason}")
            _apply_final_rejection(signal, "V4_VALIDATION", reject_reason)
            signal["v4_filtered"] = True
        # Soft veto for SELL-side bias: when V4 is neutral, keep trading flow
        # but avoid forcing aggressive bearish actions.
        elif direction == "SELL" and str(v4_prediction).startswith("NEUTRAL"):
            current_rec = signal["recommendation"]
            ml_conf = float(signal.get("ml_confidence", 0.0) or 0.0)
            neutral_floor = min_confidence_for(current_rec) + 0.03

            if current_rec == "STRONG_SELL":
                signal["recommendation"] = "SELL"
                signal["type"] = "SELL"
                signal["v4_soft_filtered"] = True
                signal["reason"] = (
                    f"V4 neutral outcome ({v4_prediction}) → downgrade STRONG_SELL to SELL"
                )
                logger.info(
                    f"🧭 [V4 SOFT FILTER] {pair}: STRONG_SELL → SELL | "
                    f"prediction={v4_prediction} conf={float(v4_confidence or 0.0):.1%}"
                )
            elif current_rec == "SELL" and ml_conf < neutral_floor:
                reject_reason = (
                    f"V4 neutral outcome ({v4_prediction}) and SELL confidence weak "
                    f"({ml_conf:.1%} < {neutral_floor:.1%})"
                )
                logger.warning(f"🛡️ [V4 SOFT FILTER] {pair}: SELL → HOLD | {reject_reason}")
                _apply_final_rejection(signal, "V4_SOFT_FILTER", reject_reason)
                signal["v4_filtered"] = True

    # Adaptive Threshold Validation (per-pair learning)
    try:
        if signal["recommendation"] in ACTIONABLE_SIGNALS and hasattr(bot, '_adaptive_engine') and bot._adaptive_engine:
            thresholds = bot._adaptive_engine.get_adaptive_thresholds(pair)
            if thresholds.get('skip_pair'):
                reject_reason = f"Pair {pair} skipped by adaptive learning (PF={thresholds.get('profit_factor_7d', 0):.2f} < 1.0)"
                logger.warning(f"🛡️ [ADAPTIVE] {pair}: {signal['recommendation']} → HOLD | {reject_reason}")
                _apply_final_rejection(signal, "ADAPTIVE_SKIP", reject_reason)
                signal["adaptive_filtered"] = True
            else:
                # Apply adaptive confidence threshold.
                # DB stores per-pair overrides in `confidence_threshold_{buy,strong_buy}`
                # keys (legacy naming, but logically applied per direction).
                # Fallback to the static per-direction minimum when no DB row exists.
                rec = signal["recommendation"]
                is_strong = rec.startswith("STRONG_")
                db_key = 'confidence_threshold_strong_buy' if is_strong else 'confidence_threshold_buy'
                fallback_conf = min_confidence_for(rec)
                required_conf = thresholds.get(db_key, fallback_conf)
                ml_conf = float(signal.get("ml_confidence", 0.0) or 0.0)
                if ml_conf < required_conf:
                    reject_reason = (
                        f"{rec} rejected: adaptive confidence too low "
                        f"({ml_conf:.1%} < {required_conf:.1%})"
                    )
                    logger.warning(f"🛡️ [ADAPTIVE] {pair}: {rec} → HOLD | {reject_reason}")
                    _apply_final_rejection(signal, "ADAPTIVE_CONF", reject_reason)
                    signal["adaptive_filtered"] = True
    except Exception as e:
        logger.debug(f"⚠️ [ADAPTIVE] Threshold check skipped for {pair}: {e}")

    # ── ARIMA direction filter (Integrasi #4) ────────────────────────────
    # Blokir BUY jika ARIMA memprediksi DOWN dengan keyakinan kuat.
    # Hanya aktif jika ARIMA sudah dihitung (ada di signal dict).
    # Tidak memblokir SELL atau HOLD.
    try:
        arima_dir = signal.get("arima_direction")
        arima_pct = signal.get("arima_change_pct", 0.0)
        if (
            signal["recommendation"] in BUY_SIGNALS
            and arima_dir == "DOWN"
            and arima_pct is not None
            and arima_pct < -1.0  # Hanya blokir jika prediksi turun > 1%
        ):
            _arima_reason = f"ARIMA prediksi turun {arima_pct:+.2f}% — konfirmasi arah berlawanan dengan BUY"
            logger.warning(f"🛡️ [ARIMA FILTER] {pair}: {signal['recommendation']} → HOLD | {_arima_reason}")
            _apply_final_rejection(signal, "ARIMA_FILTER", _arima_reason)
            signal["arima_filtered"] = True
    except Exception as _ae:
        logger.debug(f"[ARIMA FILTER] {pair}: skipped — {_ae}")
    # ── End ARIMA filter ──────────────────────────────────────────────────

    # ── Sentiment enrichment (NEW 2026-06-06 — adapted from Meridian-main) ──
    # Fetches crypto news sentiment and adjusts confidence.
    # Bullish sentiment + BUY signal → confidence boost
    # Bearish sentiment + BUY signal → confidence penalty
    # Concept source: Meridian-main/agent.py get_crypto_sentiment()
    try:
        from signals.sentiment_analysis import get_sentiment_for_pair
        from core.config import Config as _SentCfg

        if getattr(_SentCfg, 'SENTIMENT_ENABLED', False):
            _sent_result = get_sentiment_for_pair(pair)
            signal["sentiment"] = {
                "sentiment": _sent_result.sentiment,
                "score": _sent_result.score,
                "summary": _sent_result.summary,
                "source": _sent_result.source,
                "headline_count": _sent_result.headline_count,
            }

            # Apply confidence adjustment based on sentiment alignment
            _sent_rec = signal.get("recommendation", "HOLD")
            if _sent_rec in ACTIONABLE_SIGNALS:
                _old_conf = signal.get("ml_confidence", 0.5)
                _boost = getattr(_SentCfg, 'SENTIMENT_CONFIDENCE_BOOST', 0.05)
                _penalty = getattr(_SentCfg, 'SENTIMENT_CONFIDENCE_PENALTY', 0.03)
                _is_buy = _sent_rec in BUY_SIGNALS
                _sent_bullish = _sent_result.sentiment == "BULLISH"
                _sent_bearish = _sent_result.sentiment == "BEARISH"

                _adjustment = 0.0
                if _is_buy and _sent_bullish:
                    _adjustment = _boost
                elif _is_buy and _sent_bearish:
                    _adjustment = -_penalty
                elif not _is_buy and _sent_bearish:  # SELL + bearish = aligned
                    _adjustment = _boost
                elif not _is_buy and _sent_bullish:  # SELL + bullish = misaligned
                    _adjustment = -_penalty

                if _adjustment != 0:
                    _new_conf = max(0.0, min(1.0, _old_conf + _adjustment))
                    signal["ml_confidence"] = _new_conf
                    logger.info(
                        f"📰 [SENTIMENT] {pair}: {_sent_result.sentiment} ({_sent_result.score:+.1f}) "
                        f"→ confidence {_old_conf:.1%} → {_new_conf:.1%} ({_adjustment:+.2f})"
                    )
    except Exception as _se:
        logger.debug(f"[SENTIMENT] {pair}: enrichment skipped — {_se}")
    # ── End sentiment enrichment ────────────────────────────────────────────

    final_policy_reason = get_final_actionable_rejection_reason(signal)
    if final_policy_reason:
        logger.warning(
            f"🛡️ [FINAL POLICY] {pair}: {signal['recommendation']} → HOLD | {final_policy_reason}"
        )
        _apply_final_rejection(signal, "FINAL_POLICY", final_policy_reason)
        signal["final_policy_filtered"] = True

    hold_flags = []
    for flag, name in [
        ("volatility_filtered", "volatility_filter"),
        ("regime_filtered", "regime_filter"),
        ("quality_filtered", "quality_engine"),
        ("sr_filtered", "sr_validation"),
        ("enhancement_filtered", "enhancement"),
        ("v4_filtered", "v4_validation"),
        ("arima_filtered", "arima_filter"),
        ("final_policy_filtered", "final_policy"),
    ]:
        if signal.get(flag):
            hold_flags.append(name)
    if signal.get("recommendation") == "HOLD":
        hold_source = ", ".join(hold_flags) if hold_flags else "upstream_signal"
        logger.warning(f"🧭 [HOLD TRACE] {pair}: source={hold_source} | reason={signal.get('reason', 'No reason provided')}")

    display_recommendation = signal.get("recommendation", "HOLD")
    if display_recommendation in BUY_SIGNALS:
        display_decision = classify_buy_signal_label(signal)
        signal["display_recommendation"] = display_decision.label
        signal["display_reason"] = display_decision.reason
        signal["reason"] = f"{signal.get('reason', '')} | Decision layer: {display_decision.reason}".strip(" |")

        duplicate_reason = should_reject_duplicate_buy_signal(
            signal,
            previous_signal_info,
            now=datetime.now(),
        )
        if duplicate_reason:
            logger.warning(f"🛡️ [DECISION DUPLICATE] {pair}: {display_decision.label} → HOLD | {duplicate_reason}")
            signal["duplicate_filtered"] = True
            signal["duplicate_filtered_reason"] = duplicate_reason
            signal["display_recommendation"] = "HOLD"
            _apply_final_rejection(signal, "DECISION_DUPLICATE", duplicate_reason)
    else:
        signal["display_recommendation"] = display_recommendation

    bot.previous_signals[pair] = {
        "recommendation": signal["recommendation"],
        "display_recommendation": signal.get("display_recommendation", signal["recommendation"]),
        "ml_confidence": signal.get("ml_confidence", 0.0),
        "combined_strength": signal.get("combined_strength", 0.0),
        "risk_reward_ratio": signal.get("risk_reward_ratio", 0.0),
        "timestamp": datetime.now(),
    }

    if bot._signal_db is None:
        return signal

    final_confidence = signal.get("ml_confidence", ml_confidence)
    signal_data = {
        "symbol": pair.upper(),
        "price": str(real_time_price),
        "rec": signal.get("display_recommendation", signal["recommendation"]),
        "rsi": str(ta_signals.get("indicators", {}).get("rsi", "—")),
        "macd": str(ta_signals.get("indicators", {}).get("macd_signal", "—")),
        "ma": str(ta_signals.get("indicators", {}).get("ma_trend", "—")),
        "bollinger": str(ta_signals.get("indicators", {}).get("bb", "—")),
        "volume": str(ta_signals.get("indicators", {}).get("volume", "—")),
        "confidence": f"{final_confidence:.1%}",
        "strength": f"{signal.get('combined_strength', 0):.2f}",
        "support_1": f"{signal.get('support_1', 0):,.0f}" if signal.get("support_1", 0) > 0 else "—",
        "support_2": f"{signal.get('support_2', 0):,.0f}" if signal.get("support_2", 0) > 0 else "—",
        "resistance_1": f"{signal.get('resistance_1', 0):,.0f}" if signal.get("resistance_1", 0) > 0 else "—",
        "resistance_2": f"{signal.get('resistance_2', 0):,.0f}" if signal.get("resistance_2", 0) > 0 else "—",
        "price_zone": signal.get("price_zone", "UNKNOWN"),
        "risk_reward": f"{signal.get('risk_reward_ratio', 0):.2f}",
        "analysis": signal.get("reason", "") + (f" [V4:{v4_prediction}]" if v4_prediction else ""),
        "final_gate_source": signal.get("final_gate_source"),
        "price_source": signal.get("price_source"),
        "signal_time": datetime.now().strftime("%H:%M:%S"),
    }

    try:
        signal_id = bot._signal_db.insert_signal(signal_data, datetime.now(), retries=3)
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
