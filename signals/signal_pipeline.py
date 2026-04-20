#!/usr/bin/env python3
"""Signal generation pipeline extracted from bot.py."""

import logging
import os
from datetime import datetime

from analysis.technical_analysis import TechnicalAnalysis

logger = logging.getLogger("crypto_bot")

ACTIONABLE_SIGNALS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}
BUY_SIGNALS = {"BUY", "STRONG_BUY"}
SELL_SIGNALS = {"SELL", "STRONG_SELL"}


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


async def generate_signal_for_pair(bot, pair):
    """Generate comprehensive trading signal using bot dependencies."""
    if pair not in bot.historical_data:
        await bot._load_historical_data(pair)

    if pair not in bot.historical_data or bot.historical_data[pair].empty:
        logger.warning(f"⚠️ No data available for {pair} yet (waiting for WebSocket)")
        return None

    df = bot.historical_data[pair].copy()
    if len(df) < 60:
        logger.warning(f"⚠️ Not enough data for {pair}: {len(df)} candles (need 60+)")
        return None

    real_time_price = None
    try:
        from api.indodax_api import IndodaxAPI

        indodax = IndodaxAPI()
        ticker = indodax.get_ticker(pair)
        if ticker:
            real_time_price = ticker["last"]
            logger.info(f"🌐 API price for {pair}: {real_time_price}")
    except Exception as e:
        logger.error(f"❌ Failed to get API price for {pair}: {e}")

    if real_time_price is None and pair in bot.price_data and bot.price_data[pair]:
        ws_price = bot.price_data[pair].get("last")
        ws_timestamp = bot.price_data[pair].get("timestamp")
        if ws_timestamp and (datetime.now() - ws_timestamp).total_seconds() < 60:
            real_time_price = ws_price
            logger.info(f"📡 WebSocket price for {pair}: {ws_price} (fresh)")
        else:
            logger.warning(f"⚠️ WebSocket price stale for {pair}")

    if real_time_price is None:
        real_time_price = df["close"].iloc[-1]
        logger.warning(f"⚠️ Using historical price for {pair}: {real_time_price}")

    logger.info(f"✅ Final price for {pair}: {real_time_price}")

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

    signal = bot.trading_engine.generate_signal(
        pair=pair,
        ta_signals=ta_signals,
        ml_prediction=ml_prediction_bool,
        ml_confidence=ml_confidence,
        ml_signal_class=ml_signal_class,
    )

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

    last_signal_info = previous_signal_info
    last_signal_time = last_signal_info.get("timestamp")
    last_recommendation = last_signal_info.get("recommendation", "HOLD")
    ml_signal_class_for_engine = signal["recommendation"]

    is_volatile_safe, vol_reason = (True, "OK")
    regime = "UNKNOWN"
    position_multiplier = 1.0
    try:
        is_volatile_safe, vol_reason = bot.signal_quality_engine.check_volatility_filter(df)
        regime, position_multiplier = bot.signal_quality_engine.detect_market_regime(df)
    except Exception:
        pass

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

    quality_signal = bot.signal_quality_engine.generate_signal(
        pair=pair,
        ta_signals=ta_signals,
        ml_prediction=ml_prediction_bool if ml_prediction is not None else False,
        ml_confidence=ml_confidence,
        ml_signal_class=ml_signal_class_for_engine,
        last_signal_time=last_signal_time,
        last_recommendation=last_recommendation,
        combined_strength=signal.get("combined_strength", 0.0),
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
        signal["quality_approved"] = True
        signal["confluence_score"] = quality_signal.get("confluence", 0)
        logger.info(f"✅ [QUALITY ENGINE] {pair}: {signal['recommendation']} approved (confluence: {quality_signal.get('confluence', 0)})")

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

    try:
        sr_validation_enabled = os.getenv("ENABLE_SR_VALIDATION", "true").lower() == "true"
        if sr_validation_enabled:
            support_1 = signal.get("support_1", 0)
            resistance_1 = signal.get("resistance_1", 0)
            risk_reward = signal.get("risk_reward_ratio", 0)
            recommendation = signal.get("recommendation", "HOLD")
            rr_threshold = float(os.getenv("SR_MIN_RR_RATIO", "0.8"))
            sl_min_pct = float(os.getenv("SR_MIN_SL_PCT", "0.3"))
            near_support_pct = float(os.getenv("SR_NEAR_SUPPORT_PCT", "2.0"))
            near_resistance_pct = float(os.getenv("SR_NEAR_RESISTANCE_PCT", "2.0"))

            if recommendation in ACTIONABLE_SIGNALS:
                sl_distance_pct = signal.get("sr_stop_distance_pct")
                if sl_distance_pct is None:
                    sl_distance_pct = 999

                reject_signal = False
                reject_reason = ""
                if recommendation in BUY_SIGNALS and resistance_1 > 0:
                    if real_time_price >= resistance_1 * (1 - near_resistance_pct / 100):
                        ml_conf = signal.get("ml_confidence", 0)
                        if ml_conf > 0.70:
                            logger.info(
                                f"⚠️ [S/R VALIDATION] {pair}: BUY near resistance but high ML confidence ({ml_conf:.0%}) - allowing"
                            )
                        else:
                            reject_signal = True
                            reject_reason = f"BUY signal rejected: Price at/near resistance (R1: {resistance_1:,.0f})"
                elif recommendation in SELL_SIGNALS and support_1 > 0:
                    if real_time_price <= support_1 * (1 + near_support_pct / 100):
                        ml_conf = signal.get("ml_confidence", 0)
                        if ml_conf > 0.70:
                            logger.info(
                                f"⚠️ [S/R VALIDATION] {pair}: SELL near support but high ML confidence ({ml_conf:.0%}) - allowing"
                            )
                        else:
                            reject_signal = True
                            reject_reason = f"SELL signal rejected: Price at/near support (S1: {support_1:,.0f})"

                if not reject_signal and risk_reward > 0 and risk_reward < rr_threshold:
                    reject_signal = True
                    reject_reason = f"Signal rejected: Risk/Reward ratio too low ({risk_reward:.2f} < {rr_threshold:.2f})"
                if not reject_signal and sl_distance_pct < sl_min_pct:
                    reject_signal = True
                    reject_reason = f"Signal rejected: Stop Loss distance too small ({sl_distance_pct:.2f}% < {sl_min_pct:.1f}%)"

                if reject_signal:
                    logger.warning(f"🛡️ [S/R VALIDATION] {pair}: {recommendation} → HOLD | {reject_reason}")
                    signal["recommendation"] = "HOLD"
                    signal["reason"] = reject_reason
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
                volume_24h = ticker.get("vol_idr", 0) or ticker.get("vol_btc", 0) * ticker.get("last", 0)
        except Exception:
            pass

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

    hold_flags = []
    for flag, name in [
        ("volatility_filtered", "volatility_filter"),
        ("regime_filtered", "regime_filter"),
        ("quality_filtered", "quality_engine"),
        ("sr_filtered", "sr_validation"),
        ("enhancement_filtered", "enhancement"),
    ]:
        if signal.get(flag):
            hold_flags.append(name)
    if signal.get("recommendation") == "HOLD":
        hold_source = ", ".join(hold_flags) if hold_flags else "upstream_signal"
        logger.warning(f"🧭 [HOLD TRACE] {pair}: source={hold_source} | reason={signal.get('reason', 'No reason provided')}")

    bot.previous_signals[pair] = {
        "recommendation": signal["recommendation"],
        "timestamp": datetime.now(),
    }

    if bot._signal_db is None:
        return signal

    final_confidence = signal.get("ml_confidence", ml_confidence)
    signal_data = {
        "symbol": pair.upper(),
        "price": str(real_time_price),
        "rec": signal["recommendation"],
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
        "analysis": signal.get("reason", ""),
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
