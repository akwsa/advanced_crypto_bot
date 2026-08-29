"""Contract tests for Story 3.2: Portfolio Allocation and Risk Reservation."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.portfolio_allocation import PortfolioAllocation, RiskReservation


def test_risk_reservation_conservation_equation():
    # Valid: initial 100 == 30 + 50 + 20
    reservation = RiskReservation(
        reservation_id="res-001",
        instrument_id="BTC-IDR",
        initial_notional=ScaledInteger(10000, 2),
        consumed_notional=ScaledInteger(3000, 2),
        active_remainder_notional=ScaledInteger(5000, 2),
        released_notional=ScaledInteger(2000, 2),
    )
    assert reservation.reservation_id == "res-001"

    # Invalid: initial 100 != 30 + 50 + 10 (Breach)
    with pytest.raises(DecisionError) as exc_info:
        RiskReservation(
            reservation_id="res-002",
            instrument_id="BTC-IDR",
            initial_notional=ScaledInteger(10000, 2),
            consumed_notional=ScaledInteger(3000, 2),
            active_remainder_notional=ScaledInteger(5000, 2),
            released_notional=ScaledInteger(1000, 2),  # Missing 10
        )
    assert exc_info.value.code == "RESERVATION_CONSERVATION_BREACH"
