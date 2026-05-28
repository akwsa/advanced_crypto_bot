from datetime import datetime, timedelta

from signals.signal_decision_layer import (
    BELI,
    BELI_BERTAHAP,
    BELI_KUAT,
    PANTAU,
    classify_buy_signal_label,
    should_reject_duplicate_buy_signal,
)


def _base_buy_signal(**overrides):
    signal = {
        "recommendation": "STRONG_BUY",
        "ml_confidence": 0.83,
        "combined_strength": 0.28,
        "risk_reward_ratio": 8.5,
        "price_zone": "IN_SUPPORT",
        "distance_to_support_pct": 0.52,
        "distance_to_resistance_pct": 4.37,
        "arima_direction": "FLAT",
        "indicators": {
            "rsi": "OVERSOLD",
            "macd": "BEARISH",
            "ma_trend": "NEUTRAL",
            "volume": "NORMAL",
        },
    }
    signal.update(overrides)
    return signal


def test_classify_buy_signal_downgrades_early_reversal_to_pantau():
    result = classify_buy_signal_label(_base_buy_signal())
    assert result.label == PANTAU
    assert "momentum belum konfirmasi" in result.reason


def test_classify_buy_signal_allows_beli_bertahap_for_rebound_candidate():
    result = classify_buy_signal_label(
        _base_buy_signal(
            combined_strength=0.20,
            ml_confidence=0.61,
            risk_reward_ratio=1.32,
            indicators={
                "rsi": "OVERSOLD",
                "macd": "BULLISH_CROSS",
                "ma_trend": "NEUTRAL",
                "volume": "NORMAL",
            },
            distance_to_resistance_pct=1.9,
        )
    )
    assert result.label == BELI_BERTAHAP


def test_classify_buy_signal_allows_buy_on_confirmed_setup():
    result = classify_buy_signal_label(
        _base_buy_signal(
            combined_strength=0.24,
            ml_confidence=0.66,
            risk_reward_ratio=1.42,
            indicators={
                "rsi": "NEUTRAL",
                "macd": "BULLISH_CROSS",
                "ma_trend": "NEUTRAL",
                "volume": "NORMAL",
            },
            distance_to_resistance_pct=1.8,
        )
    )
    assert result.label == BELI


def test_classify_buy_signal_requires_full_confirmation_for_strong_buy():
    result = classify_buy_signal_label(
        _base_buy_signal(
            combined_strength=0.36,
            ml_confidence=0.76,
            risk_reward_ratio=1.74,
            indicators={
                "rsi": "NEUTRAL",
                "macd": "BULLISH_CROSS",
                "ma_trend": "BULLISH",
                "volume": "NORMAL",
            },
            arima_direction="UP",
            distance_to_resistance_pct=2.7,
        )
    )
    assert result.label == BELI_KUAT


def test_duplicate_buy_signal_rejected_when_no_meaningful_improvement():
    now = datetime(2026, 5, 27, 16, 30, 0)
    previous = {
        "display_recommendation": BELI_KUAT,
        "ml_confidence": 0.83,
        "combined_strength": 0.28,
        "risk_reward_ratio": 8.5,
        "timestamp": now - timedelta(minutes=8),
    }
    current = {
        "display_recommendation": BELI_KUAT,
        "ml_confidence": 0.82,
        "combined_strength": 0.29,
        "risk_reward_ratio": 8.4,
        "timestamp": now,
    }
    reason = should_reject_duplicate_buy_signal(current, previous, now=now)
    assert reason is not None
    assert "duplicate buy signal" in reason


def test_duplicate_buy_signal_allowed_when_quality_improves_materially():
    now = datetime(2026, 5, 27, 16, 30, 0)
    previous = {
        "display_recommendation": BELI_BERTAHAP,
        "ml_confidence": 0.64,
        "combined_strength": 0.21,
        "risk_reward_ratio": 1.40,
        "timestamp": now - timedelta(minutes=12),
    }
    current = {
        "display_recommendation": BELI,
        "ml_confidence": 0.73,
        "combined_strength": 0.34,
        "risk_reward_ratio": 1.95,
        "timestamp": now,
    }
    assert should_reject_duplicate_buy_signal(current, previous, now=now) is None
