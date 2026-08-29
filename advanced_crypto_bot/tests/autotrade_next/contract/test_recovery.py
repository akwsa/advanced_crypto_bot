"""Contract tests for Story 2.6: Lifecycle Recovery."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.accounting import PositionAccount
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.recovery import LifecycleRecoveryManager, RecoveryAction, RecoveryState
from autotrade_next.domain.simulator import OrderStatus


def test_lifecycle_recovery_query_venue_on_unknown():
    account = PositionAccount(
        instrument_id="BTC-IDR",
        cash_balance=ScaledInteger(10000000, 2),
        position_quantity=ScaledInteger(0, 4),
        processed_fill_ids=(),
    )
    state = RecoveryState(
        last_processed_sequence=100,
        account_snapshot=account,
        pending_order_ids=("ord-001",),
        unreconciled_unknown_orders=("ord-001",),
    )

    action, targets = LifecycleRecoveryManager.evaluate_recovery(
        state=state,
        order_statuses={"ord-001": OrderStatus.UNKNOWN},
    )

    assert action is RecoveryAction.QUERY_VENUE
    assert targets == ("ord-001",)


def test_lifecycle_recovery_no_action_when_clean():
    account = PositionAccount(
        instrument_id="BTC-IDR",
        cash_balance=ScaledInteger(10000000, 2),
        position_quantity=ScaledInteger(0, 4),
        processed_fill_ids=(),
    )
    state = RecoveryState(
        last_processed_sequence=100,
        account_snapshot=account,
        pending_order_ids=(),
        unreconciled_unknown_orders=(),
    )

    action, targets = LifecycleRecoveryManager.evaluate_recovery(
        state=state,
        order_statuses={},
    )

    assert action is RecoveryAction.NO_ACTION
    assert targets == ()
