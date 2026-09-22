"""Market Phase Engine — 4-phase classification (adapted from Cryptoiz)."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
class MarketPhase(Enum):
    ACCUMULATION = "ACCUMULATION"; MARKUP = "MARKUP"; DISTRIBUTION = "DISTRIBUTION"; MARKDOWN = "MARKDOWN"; UNKNOWN = "UNKNOWN"
@dataclass
class PhaseResult:
    phase: MarketPhase; confidence: float; reasons: list
def detect_market_phase(tier_signal, tier_confidence, price_change_pct, volume_ratio, rsi=None):
    reasons = []; phase = MarketPhase.UNKNOWN
    tf = tier_confidence * 0.4 if tier_signal == "ACCUMULATION" else (-tier_confidence * 0.4 if tier_signal == "DISTRIBUTION" else 0)
    pf = 0.35 if price_change_pct > 3.0 else (0.15 if price_change_pct > 1.0 else (-0.35 if price_change_pct < -3.0 else (-0.15 if price_change_pct < -1.0 else 0)))
    vf = 0.15 if volume_ratio > 2.0 else (0.08 if volume_ratio > 1.3 else (-0.05 if volume_ratio < 0.7 else 0))
    rf = 0.10 if (rsi is not None and rsi < 30) else (-0.10 if (rsi is not None and rsi > 70) else 0)
    if price_change_pct > 3.0: reasons.append(f"Strong uptrend: +{price_change_pct:.1f}%")
    elif price_change_pct < -3.0: reasons.append(f"Strong downtrend: {price_change_pct:.1f}%")
    ts = tf + pf + vf + rf
    if ts > 0.35: phase = MarketPhase.MARKUP if (price_change_pct > 2.0 or volume_ratio > 1.5) else MarketPhase.ACCUMULATION; confidence = min(1.0, ts)
    elif ts < -0.35: phase = MarketPhase.MARKDOWN if (price_change_pct < -2.0 or volume_ratio > 1.5) else MarketPhase.DISTRIBUTION; confidence = min(1.0, abs(ts))
    else: confidence = max(0.0, 1.0 - abs(ts))
    return PhaseResult(phase=phase, confidence=confidence, reasons=reasons)
def phase_recommendation(phase):
    return {MarketPhase.ACCUMULATION: "BUY_ZONE", MarketPhase.MARKUP: "HOLD_OR_TRAIL", MarketPhase.DISTRIBUTION: "CAUTION", MarketPhase.MARKDOWN: "AVOID_BUY"}.get(phase, "NEUTRAL")
