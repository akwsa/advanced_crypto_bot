from datetime import datetime, timedelta

from signals.signal_decision_layer import BELI_KUAT, PANTAU, should_reject_duplicate_buy_signal


def test_pipeline_duplicate_rule_rejects_same_strength_reentry_within_30_minutes():
    now = datetime(2026, 5, 27, 18, 0, 0)
    previous_signal_info = {
        "recommendation": "STRONG_BUY",
        "display_recommendation": BELI_KUAT,
        "ml_confidence": 0.83,
        "combined_strength": 0.28,
        "risk_reward_ratio": 8.5,
        "timestamp": now - timedelta(minutes=9),
    }
    current_signal = {
        "recommendation": "STRONG_BUY",
        "display_recommendation": BELI_KUAT,
        "ml_confidence": 0.82,
        "combined_strength": 0.29,
        "risk_reward_ratio": 8.4,
        "timestamp": now,
    }

    reason = should_reject_duplicate_buy_signal(current_signal, previous_signal_info, now=now)

    assert reason is not None
    assert "duplicate buy signal" in reason


def test_pipeline_duplicate_rule_does_not_reject_if_label_quality_improves():
    now = datetime(2026, 5, 27, 18, 0, 0)
    previous_signal_info = {
        "recommendation": "BUY",
        "display_recommendation": PANTAU,
        "ml_confidence": 0.61,
        "combined_strength": 0.19,
        "risk_reward_ratio": 1.28,
        "timestamp": now - timedelta(minutes=11),
    }
    current_signal = {
        "recommendation": "BUY",
        "display_recommendation": "BUY",
        "ml_confidence": 0.67,
        "combined_strength": 0.30,
        "risk_reward_ratio": 1.70,
        "timestamp": now,
    }

    assert should_reject_duplicate_buy_signal(current_signal, previous_signal_info, now=now) is None
