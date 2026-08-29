"""Contract tests for Story 2.4: Fill-authoritative accounting."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.accounting import CashLedgerEntry, MovementType, PositionAccount
from autotrade_next.domain.numeric import ScaledInteger


def test_position_account_apply_fill_buy():
    account = PositionAccount(
        instrument_id="BTC-IDR",
        cash_balance=ScaledInteger(10000000, 2),  # 100,000.00 cash
        position_quantity=ScaledInteger(0, 4),
        processed_fill_ids=(),
    )
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)

    # Buy 1.0 BTC @ 50,000.00 with 10.00 fee
    updated_account, entry = account.apply_fill(
        fill_id="fill-001",
        is_buy=True,
        quantity=ScaledInteger(10000, 4),  # 1.0000 BTC
        price=ScaledInteger(5000000, 2),  # 50,000.00
        fee=ScaledInteger(1000, 2),       # 10.00
        recorded_at_utc=now,
    )

    assert updated_account.position_quantity == ScaledInteger(10000, 4)
    # Cash: 100,000 - 50,000 - 10 = 49,990.00 -> units 4999000, scale 2
    assert updated_account.cash_balance == ScaledInteger(4999000, 2)
    assert entry.fill_id == "fill-001"
    assert entry.movement_type is MovementType.FILL_BUY
    assert "fill-001" in updated_account.processed_fill_ids


def test_position_account_duplicate_fill_idempotent():
    account = PositionAccount(
        instrument_id="BTC-IDR",
        cash_balance=ScaledInteger(10000000, 2),
        position_quantity=ScaledInteger(0, 4),
        processed_fill_ids=("fill-001",),
    )
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)

    # Try applying fill-001 again
    updated_account, entry = account.apply_fill(
        fill_id="fill-001",
        is_buy=True,
        quantity=ScaledInteger(10000, 4),
        price=ScaledInteger(5000000, 2),
        fee=ScaledInteger(1000, 2),
        recorded_at_utc=now,
    )

    # Balance and position should remain unchanged
    assert updated_account.cash_balance == ScaledInteger(10000000, 2)
    assert updated_account.position_quantity == ScaledInteger(0, 4)
    assert entry.amount.units == 0
