"""Contract tests for Story 2.3: Deterministic Simulator Lifecycle."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.market import (
    InstrumentRules,
    MarketQuality,
    MarketSnapshot,
    OrderBookLevel,
    OrderBookSide,
    UniverseMembership,
)
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
        execution_side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0),
        rules=InstrumentRules(
            version="rules:btc-idr:7",
            min_order_size=ScaledInteger(1, 0),
            price_scale=2,
            quantity_scale=0,
            price_tick=ScaledInteger(1, 2),
            quantity_step=ScaledInteger(1, 0),
            metadata_qualified=True,
        ),
        membership=UniverseMembership(
            universe_version="universe:2026-08-29",
            effective_at_utc=event_time,
            is_member=True,
            proof_id="membership:btc-idr:2026-08-29",
        ),
        quality=MarketQuality(
            freshness_micros=1_000_000,
            max_freshness_micros=3_000_000,
            current_spread_ratio_bps=10,
            max_spread_ratio_bps=50,
            source_integrity_qualified=True,
            authority_scope_id="indodax-public-market",
            evidence_id="l2:btc-idr:1001",
        ),
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
    assert snapshot.calculate_executable_price(OrderBookSide.ASK) == (
        ScaledInteger(10, 0),
        ScaledInteger(10000, 2),
    )


def test_order_simulator_fills_economically_equal_mixed_scale_quantity():
    event_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    snapshot = MarketSnapshot.create(
        instrument_id="BTC-IDR",
        event_at_utc=event_time,
        received_at_utc=event_time,
        venue_cursor="1002",
        ingest_cursor="2002",
        bids=(OrderBookLevel(ScaledInteger(9900, 2), ScaledInteger(5, 0)),),
        asks=(OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(5, 0)),),
        execution_side=OrderBookSide.ASK,
        requested_size=ScaledInteger(500, 2),
        rules=InstrumentRules(
            version="rules:btc-idr:8",
            min_order_size=ScaledInteger(1, 0),
            price_scale=2,
            quantity_scale=2,
            price_tick=ScaledInteger(1, 2),
            quantity_step=ScaledInteger(1, 2),
            metadata_qualified=True,
        ),
        membership=UniverseMembership(
            universe_version="universe:2026-08-29",
            effective_at_utc=event_time,
            is_member=True,
            proof_id="membership:btc-idr:2026-08-29",
        ),
        quality=MarketQuality(
            freshness_micros=0,
            max_freshness_micros=3_000_000,
            current_spread_ratio_bps=10,
            max_spread_ratio_bps=50,
            source_integrity_qualified=True,
            authority_scope_id="indodax-public-market",
            evidence_id="l2:btc-idr:1002",
        ),
    )

    event = OrderSimulator(seed=42).simulate_execution(
        order_id="ord-mixed-scale",
        side=OrderBookSide.ASK,
        requested_size=ScaledInteger(5, 0),
        snapshot=snapshot,
        evaluated_at_utc=event_time,
    )

    assert event.status is OrderStatus.FILLED
    assert event.filled_quantity == ScaledInteger(500, 2)
    assert event.remaining_quantity == ScaledInteger(0, 2)
    assert event.fills[0].quantity == ScaledInteger(500, 2)
    assert event.fills[0].fee == ScaledInteger(10000, 4)


def test_order_simulator_dry_run_no_live_imports():
    # Verify that live submission modules cannot be imported or accessed
    with pytest.raises(ModuleNotFoundError):
        import autotrade_next.adapters.indodax.live_submit  # type: ignore
