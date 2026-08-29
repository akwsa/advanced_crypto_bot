"""Contract tests for Story 2.5: Unified Exit Evaluation and Position Protection."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.exit_protection import ExitDecision, ExitEvaluator, ExitReason, ProtectionState
from autotrade_next.domain.numeric import ScaledInteger


def test_exit_evaluator_stop_loss():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    protection = ProtectionState(
        stop_loss_price=ScaledInteger(4500000, 2),  # 45,000.00
        take_profit_price=ScaledInteger(5500000, 2), # 55,000.00
        trailing_high_water=None,
        expiration_at_utc=None,
    )

    # Current price dropped to 44,000.00 -> trigger Stop Loss
    decision = ExitEvaluator.evaluate(
        current_position_quantity=ScaledInteger(10000, 4),  # 1.0000 BTC
        current_price=ScaledInteger(4400000, 2),
        protection=protection,
        evaluated_at_utc=now,
    )

    assert decision.should_exit is True
    assert decision.reason is ExitReason.STOP_LOSS
    assert decision.target_quantity == ScaledInteger(10000, 4)


def test_exit_evaluator_no_exit_when_flat():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    protection = ProtectionState(
        stop_loss_price=ScaledInteger(4500000, 2),
        take_profit_price=ScaledInteger(5500000, 2),
        trailing_high_water=None,
        expiration_at_utc=None,
    )

    decision = ExitEvaluator.evaluate(
        current_position_quantity=ScaledInteger(0, 4),
        current_price=ScaledInteger(4400000, 2),
        protection=protection,
        evaluated_at_utc=now,
    )

    assert decision.should_exit is False
    assert decision.reason is ExitReason.NO_EXIT
