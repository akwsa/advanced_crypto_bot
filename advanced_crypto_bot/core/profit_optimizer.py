# Tujuan: Shared profit-optimization helpers for autotrade and autohunter decisions.
# Caller: autotrade.runtime, autohunter.smart_profit_hunter.
# Dependensi: core.config only.
# Main Functions: evaluate_autotrade_setup, evaluate_hunter_setup, scale_take_profit_targets.
# Side Effects: none; pure computation only.

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from core.config import Config


@dataclass(frozen=True)
class ProfitOptimizationDecision:
    edge_score: float
    position_multiplier: float
    tp1_multiplier: float
    tp2_multiplier: float
    stop_loss_multiplier: float
    min_rr_required: float
    should_skip: bool
    reason: str


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_confidence(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return _clamp(float(value), 0.0, 1.0)


def _as_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _liquidity_bonus(liquidity_zones: Optional[Iterable[Tuple[float, float]]]) -> float:
    if not liquidity_zones:
        return 0.0
    top_zone = next(iter(liquidity_zones), None)
    if not top_zone:
        return 0.0
    zone_volume = _as_float(top_zone[1], 0.0)
    if zone_volume <= 0:
        return 0.0
    if zone_volume >= 1_000_000:
        return 6.0
    if zone_volume >= 250_000:
        return 4.0
    return 2.0


def scale_take_profit_targets(
    take_profit_1: Optional[float],
    take_profit_2: Optional[float],
    tp1_multiplier: float,
    tp2_multiplier: float,
    entry_price: float,
    trade_type: str,
) -> Tuple[Optional[float], Optional[float]]:
    if not take_profit_1 or not take_profit_2 or entry_price <= 0:
        return take_profit_1, take_profit_2

    is_buy = trade_type in {"BUY", "STRONG_BUY"}
    tp1_distance = abs(take_profit_1 - entry_price)
    tp2_distance = abs(take_profit_2 - entry_price)

    if is_buy:
        scaled_tp1 = entry_price + (tp1_distance * tp1_multiplier)
        scaled_tp2 = entry_price + (tp2_distance * tp2_multiplier)
        scaled_tp2 = max(scaled_tp2, scaled_tp1 * 1.002)
    else:
        scaled_tp1 = entry_price - (tp1_distance * tp1_multiplier)
        scaled_tp2 = entry_price - (tp2_distance * tp2_multiplier)
        scaled_tp2 = min(scaled_tp2, scaled_tp1 * 0.998)

    return scaled_tp1, scaled_tp2


def evaluate_autotrade_setup(
    *,
    signal: Dict,
    market_conditions: Dict,
    regime: Dict,
    rr_after_fees: float,
    liquidity_zones: Optional[Iterable[Tuple[float, float]]] = None,
    elite_signal: Optional[str] = None,
) -> ProfitOptimizationDecision:
    confidence = _normalize_confidence(signal.get("ml_confidence"))
    combined_strength = abs(_as_float(signal.get("combined_strength")))
    volume_ratio = _as_float(market_conditions.get("volume_ratio"), 1.0)
    buy_sell_ratio = _as_float(market_conditions.get("buy_sell_ratio"), 1.0)

    edge_score = 0.0
    edge_score += confidence * 35.0
    edge_score += min(combined_strength, 1.0) * 20.0
    edge_score += min(max(volume_ratio - 1.0, 0.0), 2.0) * 9.0
    edge_score += min(max(buy_sell_ratio - 1.0, 0.0), 1.5) * 8.0
    edge_score += min(max(rr_after_fees - 1.0, 0.0), 3.0) * 7.0
    edge_score += _liquidity_bonus(liquidity_zones)

    if market_conditions.get("overall_signal") == "BULLISH":
        edge_score += 8.0
    elif market_conditions.get("overall_signal") == "MODERATE":
        edge_score += 4.0

    if elite_signal == "BUY":
        edge_score += 8.0
    elif elite_signal == "SELL":
        edge_score -= 14.0

    if regime.get("is_high_vol"):
        edge_score -= 18.0
    elif regime.get("is_trending") and regime.get("trend_direction") == "UP":
        edge_score += 7.0
    elif regime.get("is_trending") and regime.get("trend_direction") == "DOWN":
        edge_score -= 9.0
    elif regime.get("is_choppy"):
        edge_score -= 5.0

    edge_score = _clamp(edge_score, 0.0, 100.0)
    min_rr_required = max(Config.RISK_REWARD_RATIO * 0.75, 1.35)

    if rr_after_fees < min_rr_required:
        return ProfitOptimizationDecision(
            edge_score=edge_score,
            position_multiplier=0.0,
            tp1_multiplier=1.0,
            tp2_multiplier=1.0,
            stop_loss_multiplier=1.0,
            min_rr_required=min_rr_required,
            should_skip=True,
            reason=f"R/R after fees below dynamic floor ({rr_after_fees:.2f} < {min_rr_required:.2f})",
        )

    if edge_score < Config.PROFIT_AUTOTRADE_MIN_EDGE_SCORE:
        return ProfitOptimizationDecision(
            edge_score=edge_score,
            position_multiplier=0.0,
            tp1_multiplier=1.0,
            tp2_multiplier=1.0,
            stop_loss_multiplier=1.0,
            min_rr_required=min_rr_required,
            should_skip=True,
            reason=f"Edge score too low ({edge_score:.1f} < {Config.PROFIT_AUTOTRADE_MIN_EDGE_SCORE:.1f})",
        )

    normalized_edge = edge_score / 100.0
    position_multiplier = _clamp(
        0.55 + (normalized_edge * Config.PROFIT_AUTOTRADE_MAX_POSITION_BOOST),
        0.45,
        Config.PROFIT_AUTOTRADE_MAX_POSITION_BOOST,
    )
    tp1_multiplier = _clamp(0.95 + (normalized_edge * 0.35), 0.90, 1.25)
    tp2_multiplier = _clamp(1.00 + (normalized_edge * Config.PROFIT_TP2_EXPANSION_MAX), 1.0, 1.45)
    stop_loss_multiplier = _clamp(1.0 - (normalized_edge * 0.10), 0.90, 1.0)

    return ProfitOptimizationDecision(
        edge_score=edge_score,
        position_multiplier=position_multiplier,
        tp1_multiplier=tp1_multiplier,
        tp2_multiplier=tp2_multiplier,
        stop_loss_multiplier=stop_loss_multiplier,
        min_rr_required=min_rr_required,
        should_skip=False,
        reason="autotrade setup approved",
    )


def evaluate_hunter_setup(
    *,
    score: float,
    rsi: float,
    volume_ratio: float,
    trend: str,
    volatility: float,
    price_change: float,
    risk_reward: float,
) -> ProfitOptimizationDecision:
    edge_score = 0.0
    edge_score += _clamp(score, 0.0, 100.0) * 0.45
    edge_score += _clamp(volume_ratio, 0.0, 3.0) * 12.0
    edge_score += 12.0 if trend == "BULLISH" else -8.0

    if 35 <= rsi <= 55:
        edge_score += 14.0
    elif 30 <= rsi < 35 or 55 < rsi <= 62:
        edge_score += 8.0
    else:
        edge_score -= 10.0

    if 2.0 <= price_change <= 7.0:
        edge_score += 10.0
    elif price_change > 10.0:
        edge_score -= 8.0

    if volatility >= 14.0:
        edge_score -= 10.0
    elif volatility <= 8.0:
        edge_score += 6.0

    edge_score += min(max(risk_reward - 1.0, 0.0), 3.0) * 8.0
    edge_score = _clamp(edge_score, 0.0, 100.0)

    if risk_reward < Config.PROFIT_HUNTER_MIN_RR or edge_score < Config.PROFIT_HUNTER_MIN_EDGE_SCORE:
        reason = (
            f"Hunter edge too low ({edge_score:.1f})"
            if edge_score < Config.PROFIT_HUNTER_MIN_EDGE_SCORE
            else f"Hunter R/R too low ({risk_reward:.2f})"
        )
        return ProfitOptimizationDecision(
            edge_score=edge_score,
            position_multiplier=0.0,
            tp1_multiplier=1.0,
            tp2_multiplier=1.0,
            stop_loss_multiplier=1.0,
            min_rr_required=Config.PROFIT_HUNTER_MIN_RR,
            should_skip=True,
            reason=reason,
        )

    normalized_edge = edge_score / 100.0
    position_multiplier = _clamp(
        0.60 + (normalized_edge * Config.PROFIT_HUNTER_MAX_POSITION_BOOST),
        0.50,
        Config.PROFIT_HUNTER_MAX_POSITION_BOOST,
    )
    tp1_multiplier = _clamp(0.95 + (normalized_edge * 0.30), 0.90, 1.20)
    tp2_multiplier = _clamp(1.05 + (normalized_edge * 0.35), 1.0, 1.35)
    stop_loss_multiplier = _clamp(1.0 - (normalized_edge * 0.08), 0.92, 1.0)

    return ProfitOptimizationDecision(
        edge_score=edge_score,
        position_multiplier=position_multiplier,
        tp1_multiplier=tp1_multiplier,
        tp2_multiplier=tp2_multiplier,
        stop_loss_multiplier=stop_loss_multiplier,
        min_rr_required=Config.PROFIT_HUNTER_MIN_RR,
        should_skip=False,
        reason="hunter setup approved",
    )
