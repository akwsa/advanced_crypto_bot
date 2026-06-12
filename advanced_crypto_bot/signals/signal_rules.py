"""Lightweight signal rule helpers for runtime gates and unit tests."""

ACTIONABLE_SIGNALS = {"BUY", "STRONG_BUY", "SELL", "STRONG_SELL"}
BUY_SIGNALS = {"BUY", "STRONG_BUY"}
SELL_SIGNALS = {"SELL", "STRONG_SELL"}

# Asymmetric confidence thresholds (profit-oriented):
# Keep BUY relatively permissive, but make SELL stricter to reduce bear bias.
# 2026-06-12: Raised BUY 0.50→0.65 and STRONG_BUY 0.64→0.70 after trade-outcome
# analysis showed <60% confidence trades lose 80% of the time (5 trades: 4 BAD).
BUY_MIN_CONFIDENCE = 0.65
STRONG_BUY_MIN_CONFIDENCE = 0.70
SELL_MIN_CONFIDENCE = 0.65
STRONG_SELL_MIN_CONFIDENCE = 0.70

# Legacy aliases kept for backward compatibility with external callers.
BUY_SELL_MIN_CONFIDENCE = SELL_MIN_CONFIDENCE
STRONG_MIN_CONFIDENCE = STRONG_SELL_MIN_CONFIDENCE

SELL_CONFLICT_MAX_COMBINED_STRENGTH = 0.20


def min_confidence_for(recommendation):
    """Return per-direction minimum ML confidence for actionable signals."""
    if recommendation == "STRONG_BUY":
        return STRONG_BUY_MIN_CONFIDENCE
    if recommendation == "BUY":
        return BUY_MIN_CONFIDENCE
    if recommendation == "STRONG_SELL":
        return STRONG_SELL_MIN_CONFIDENCE
    if recommendation == "SELL":
        return SELL_MIN_CONFIDENCE
    return BUY_SELL_MIN_CONFIDENCE


# Backward-compatibility alias.
_min_confidence_for = min_confidence_for


def should_block_actionable_on_stale_price(stale_price_fallback, recommendation, stale_realtime_price=False):
    """Return True when actionable signal must be blocked due to stale realtime pricing."""
    return recommendation in ACTIONABLE_SIGNALS and (
        bool(stale_price_fallback) or bool(stale_realtime_price)
    )


def is_buy_support_entry_zone(price, support_1, support_2=0, near_support_pct=2.0):
    """Return True when BUY entry is inside the S2-S1 support-entry area."""
    try:
        price = float(price)
        support_1 = float(support_1)
        support_2 = float(support_2 or 0)
        near_support_pct = float(near_support_pct)
    except (TypeError, ValueError):
        return False

    if price <= 0 or support_1 <= 0:
        return False

    support_floor = support_2 if support_2 > 0 else support_1 * (1 - near_support_pct / 100)
    support_ceiling = support_1 * (1 + near_support_pct / 100)
    return support_floor <= price <= support_ceiling


def get_final_actionable_rejection_reason(signal):
    """Return policy rejection reason for an actionable signal, or None when valid."""
    recommendation = signal.get("recommendation", "HOLD")
    if recommendation not in ACTIONABLE_SIGNALS:
        return None

    ml_confidence = float(signal.get("ml_confidence", 0.0) or 0.0)
    combined_strength = float(signal.get("combined_strength", 0.0) or 0.0)

    min_confidence = _min_confidence_for(recommendation)
    if ml_confidence < min_confidence:
        return (
            f"{recommendation} rejected: final ML confidence too low "
            f"({ml_confidence:.1%} < {min_confidence:.0%})"
        )

    if recommendation in BUY_SIGNALS and combined_strength < 0:
        return (
            f"{recommendation} rejected: combined_strength negative "
            f"({combined_strength:.2f})"
        )

    if recommendation in SELL_SIGNALS and combined_strength > SELL_CONFLICT_MAX_COMBINED_STRENGTH:
        return (
            f"{recommendation} rejected: combined_strength too positive "
            f"({combined_strength:.2f} > {SELL_CONFLICT_MAX_COMBINED_STRENGTH:.2f})"
        )

    return None
