"""Contract tests for Story 2.3: Deterministic Simulator Lifecycle."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.market import MarketSnapshot, OrderBookLevel, OrderBookSide
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.simulator import FeeType, OrderSimulator, OrderStatus, SimulatedFill, SimulatorEvent


def test_order_simulator_filled():
    event_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    receive_time = datetime(2026, 8, 29, 12, 0, 1, tzinfo=UTC)
    
    asks = (
        OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(10, 0)),
    )
    bids = (
        OrderBookLevel(ScaledInteger(9900, 2), ScaledInteger(10, 0)),
    )

    snapshot = MarketSnapshot.create(
        instrument_id="BTC-IDR",
        event_at_utc=event_time,
        received_at_utc=receive_time,
        venue_cursor="1001",
        ingest_cursor="2001",
        bids=bids,
        asks=asks,
    )

    simulator = OrderSimulator(seed=42)
    evt = simulator.simulate_execution(
        order_id="ord-123",
        side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0),
        snapshot=snapshot,
        evaluated_at_utc=event_time,
    )

    assert evt.order_id == "ord-123"
    assert evt.status is OrderStatus.FILLED
    assert evt.filled_quantity == ScaledInteger(5, 0)
    assert evt.remaining_quantity == ScaledInteger(0, 0)
    assert len(evt.fills) == 1
    assert evt.fills[0].price == ScaledInteger(10000, 2)
    assert evt.fills[0].fee_type is FeeType.TAKER


def test_order_simulator_dry_run_no_live_imports():
    # Verify that live submission modules cannot be imported or accessed
    with pytest.raises(ModuleNotFoundError):
        import autotrade_next.adapters.indodax.live_submit  # type: ignore
