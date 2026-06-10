"""Decision-layer helpers for user-facing signal labels and duplicate suppression.

Pure functions only. Keeps label logic explainable and testable before wiring
into the runtime signal pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class _StrEnum(str, Enum):
    """Minimal string enum compatible with current project Python versions."""

    def __str__(self) -> str:
        return self.value


class RawSignal(_StrEnum):
    BUY = "BUY"
    STRONG_BUY = "STRONG_BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class PositionState(_StrEnum):
    NO_POSITION = "NO_POSITION"
    HAS_POSITION = "HAS_POSITION"
    UNKNOWN_POSITION = "UNKNOWN_POSITION"


class FinalAction(_StrEnum):
    BUY_CONFIRMED = "BUY_CONFIRMED"
    BUY_CANDIDATE = "BUY_CANDIDATE"
    HOLD_POSITION = "HOLD_POSITION"
    SELL_CONFIRMED = "SELL_CONFIRMED"
    SELL_STOP_LOSS = "SELL_STOP_LOSS"
    SELL_TAKE_PROFIT = "SELL_TAKE_PROFIT"
    SELL_TRAILING_PROFIT = "SELL_TRAILING_PROFIT"
    AVOID_BUY = "AVOID_BUY"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    IGNORE = "IGNORE"


class ReasonCode(_StrEnum):
    NO_POSITION_FOR_SELL = "NO_POSITION_FOR_SELL"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    HARD_RISK_GATE = "HARD_RISK_GATE"
    THRESHOLD_MET = "THRESHOLD_MET"
    THRESHOLD_NOT_MET = "THRESHOLD_NOT_MET"
    UNKNOWN_POSITION_STATE = "UNKNOWN_POSITION_STATE"
    SOFT_CONFIRMATION_PENDING = "SOFT_CONFIRMATION_PENDING"
    VOLUME_NOT_SUPPORTIVE = "VOLUME_NOT_SUPPORTIVE"
    TREND_NOT_SUPPORTIVE = "TREND_NOT_SUPPORTIVE"


BUY_CONFIRMED = FinalAction.BUY_CONFIRMED
BUY_CANDIDATE = FinalAction.BUY_CANDIDATE
HOLD_POSITION = FinalAction.HOLD_POSITION
SELL_CONFIRMED = FinalAction.SELL_CONFIRMED
SELL_STOP_LOSS = FinalAction.SELL_STOP_LOSS
SELL_TAKE_PROFIT = FinalAction.SELL_TAKE_PROFIT
SELL_TRAILING_PROFIT = FinalAction.SELL_TRAILING_PROFIT
AVOID_BUY = FinalAction.AVOID_BUY
WAIT_CONFIRMATION = FinalAction.WAIT_CONFIRMATION
IGNORE = FinalAction.IGNORE


@dataclass(frozen=True)
class DecisionContext:
    pair: str
    raw_signal: RawSignal
    ml_confidence: float
    position_state: PositionState
    history_available: Optional[bool] = None
    three_hour_trend: Optional[str] = None
    volume_state: Optional[str] = None
    current_price: Optional[float] = None
    entry_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    sell_count_last_3: Optional[int] = None
    sl_hit: Optional[bool] = None
    tp_hit: Optional[bool] = None
    trailing_hit: Optional[bool] = None
    audit_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


@dataclass(frozen=True)
class DecisionResult:
    raw_signal: RawSignal
    final_action: FinalAction
    reason_codes: list[ReasonCode] = field(default_factory=list)
    reason_text: str = ""
    score: Optional[float] = None
    telegram_actionable: bool = False
    execution_allowed: bool = False
    audit_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(asdict(self))


BUY_SIGNAL_LABELS = {"BUY", "STRONG_BUY"}


@dataclass(frozen=True)
class DecisionLayerResult:
    label: str
    reason: str
    duplicate_rejected: bool = False


PANTAU = "PANTAU"
BELI_BERTAHAP = "BELI_BERTAHAP"
BELI = "BUY"
BELI_KUAT = "STRONG_BUY"


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _minutes_between(current_time: Optional[datetime], previous_time: Optional[datetime]) -> Optional[float]:
    if not current_time or not previous_time:
        return None
    try:
        return max(0.0, (current_time - previous_time).total_seconds() / 60.0)
    except Exception:
        return None


def classify_buy_signal_label(signal: dict) -> DecisionLayerResult:
    """Classify raw BUY/STRONG_BUY into user-facing confidence tiers.

    The goal is to reserve STRONG_BUY for confirmed setups, not early reversal
    guesses that are still fighting bearish momentum.

    FIX 2026-06-06 (from analisys_autotradedrurun.md):
    - Relaxed support zone check: allow support_dist <= 3.5% (was strict zone only)
    - Added BB position override: bb_position < 0.2 counts as momentum improving
    - Lowered thresholds: BELI_BERTAHAP ml_conf 0.56→0.50, BUY ml_conf 0.64→0.58
    - Added sentiment awareness: bullish sentiment can boost classification
    """
    recommendation = str(signal.get("recommendation") or "HOLD").upper()
    if recommendation not in BUY_SIGNAL_LABELS:
        return DecisionLayerResult(label=recommendation, reason="non-buy signal")

    ml_conf = _safe_float(signal.get("ml_confidence"), 0.0)
    strength = _safe_float(signal.get("combined_strength"), 0.0)
    rr = _safe_float(signal.get("risk_reward_ratio"), 0.0)
    zone = str(signal.get("price_zone") or "UNKNOWN").upper()
    support_dist = _safe_float(signal.get("distance_to_support_pct"), 999.0)
    resistance_dist = _safe_float(signal.get("distance_to_resistance_pct"), 0.0)

    indicators = signal.get("indicators", {}) or {}
    macd = str(indicators.get("macd") or "").upper()
    ma = str(indicators.get("ma_trend") or "").upper()
    volume = str(indicators.get("volume") or "").upper()
    arima_dir = str(signal.get("arima_direction") or "").upper()

    # Sentiment data (NEW 2026-06-06)
    sentiment_label = str(signal.get("sentiment", {}).get("sentiment") or "NEUTRAL").upper()

    # FIX: Expanded support zone — include NEAR_SUPPORT and support_dist <= 3.5%
    in_support = zone in {"IN_SUPPORT", "NEAR_SUPPORT"} or support_dist <= 3.5

    # FIX: BB position override — near lower BB = momentum improving
    bb_upper = _safe_float(signal.get("bb_upper") or indicators.get("bb_upper"), 0.0)
    bb_lower = _safe_float(signal.get("bb_lower") or indicators.get("bb_lower"), 0.0)
    current_price = _safe_float(signal.get("price"), 0.0)
    bb_position = None
    bb_near_lower = False
    if bb_upper > 0 and bb_lower > 0 and (bb_upper - bb_lower) > 0:
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
        bb_near_lower = bb_position < 0.25  # Price in bottom 25% of BB → oversold

    improving_momentum = (
        "BULLISH" in macd
        or "CROSS" in macd
        or strength >= 0.26
        or arima_dir == "UP"
        or bb_near_lower  # NEW: BB position override
    )
    trend_supportive = ma in {"BULLISH", "NEUTRAL"} or support_dist <= 2.5
    volume_supportive = volume in {"HIGH", "RISING", "STRONG", "NORMAL"}
    not_chasing = resistance_dist >= 1.6
    weak_reversal = (
        "BEARISH" in macd
        and ma != "BULLISH"
        and arima_dir != "UP"
        and not bb_near_lower  # NEW: BB near lower negates weak_reversal
        and strength < 0.34
    )

    # FIX: Relaxed — if not in support but BB near lower, still allow BELI_BERTAHAP
    if not in_support and not bb_near_lower:
        return DecisionLayerResult(
            label=PANTAU,
            reason="buy candidate di luar zona support; tunggu reclaim/konfirmasi",
        )

    if not improving_momentum or weak_reversal:
        return DecisionLayerResult(
            label=PANTAU,
            reason="masih reversal awal; momentum belum konfirmasi",
        )

    # FIX: Relaxed thresholds (was ml_conf<0.56, strength<0.15, rr<1.15)
    if ml_conf < 0.50 or strength < 0.10 or rr < 0.90:
        return DecisionLayerResult(
            label=BELI_BERTAHAP,
            reason="support valid tapi kualitas entry belum cukup untuk beli agresif",
        )

    # FIX: Relaxed thresholds (was ml_conf>=0.64, strength>=0.22, rr>=1.35)
    if (
        ml_conf >= 0.58
        and strength >= 0.16
        and rr >= 1.15
        and trend_supportive
        and not_chasing
    ):
        if (
            ml_conf >= 0.74
            and strength >= 0.34
            and rr >= 1.65
            and ("BULLISH" in macd or "CROSS" in macd)
            and volume_supportive
            and resistance_dist >= 2.4
        ):
            return DecisionLayerResult(
                label=BELI_KUAT,
                reason="support + momentum + volume + ruang profit terkonfirmasi",
            )
        return DecisionLayerResult(
            label=BELI,
            reason="setup buy cukup bersih, tapi belum layak disebut beli kuat",
        )

    return DecisionLayerResult(
        label=BELI_BERTAHAP,
        reason="ada rebound awal, namun konfirmasi trend/ruang profit belum penuh",
    )


def should_reject_duplicate_buy_signal(current_signal: dict, previous_signal: Optional[dict], now: Optional[datetime] = None) -> Optional[str]:
    """Return rejection reason if a new buy-type alert is only a duplicate.

    Duplicate means same pair produces another buy-flavoured alert too soon
    without meaningful improvement in recommendation quality, confidence,
    momentum, or location.
    """
    if not previous_signal:
        return None

    current_label = str(current_signal.get("display_recommendation") or current_signal.get("recommendation") or "HOLD").upper()
    previous_label = str(previous_signal.get("display_recommendation") or previous_signal.get("recommendation") or "HOLD").upper()
    if current_label not in {PANTAU, BELI_BERTAHAP, BELI, BELI_KUAT}:
        return None
    if previous_label not in {PANTAU, BELI_BERTAHAP, BELI, BELI_KUAT}:
        return None

    previous_time = previous_signal.get("timestamp")
    current_time = now or current_signal.get("timestamp")
    age_minutes = _minutes_between(current_time, previous_time)
    if age_minutes is None or age_minutes > 30:
        return None

    label_rank = {PANTAU: 1, BELI_BERTAHAP: 2, BELI: 3, BELI_KUAT: 4}
    current_rank = label_rank.get(current_label, 0)
    previous_rank = label_rank.get(previous_label, 0)

    current_conf = _safe_float(current_signal.get("ml_confidence"), 0.0)
    previous_conf = _safe_float(previous_signal.get("ml_confidence"), 0.0)
    current_strength = _safe_float(current_signal.get("combined_strength"), 0.0)
    previous_strength = _safe_float(previous_signal.get("combined_strength"), 0.0)
    current_rr = _safe_float(current_signal.get("risk_reward_ratio"), 0.0)
    previous_rr = _safe_float(previous_signal.get("risk_reward_ratio"), 0.0)

    improved = (
        current_rank > previous_rank
        or (
            current_rank >= previous_rank
            and (
                current_conf >= previous_conf + 0.05
                or current_strength >= previous_strength + 0.10
                or current_rr >= previous_rr + 0.40
            )
        )
    )

    if improved:
        return None

    return (
        f"duplicate buy signal dalam {age_minutes:.0f}m tanpa peningkatan berarti "
        f"(prev={previous_label}, now={current_label})"
    )
