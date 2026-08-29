"""Contract tests for Story 2.2: Executable MarketSnapshot and Instrument Eligibility."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.market import (
    OrderBookLevel,
    OrderBookSide,
    MarketSnapshot,
    InstrumentEligibility,
    EligibilityStatus,
    EligibilityReason,
)
from autotrade_next.domain.errors import MarketEvidenceError


def test_order_book_level_creation():
    price = ScaledInteger(100000, 2)  # 1000.00
    quantity = ScaledInteger(5000, 3)   # 5.000
    level = OrderBookLevel(price=price, quantity=quantity)
    assert level.price == price
    assert level.quantity == quantity
    assert level.to_canonical_value() == {
        "price": {"units": 100000, "scale": 2},
        "quantity": {"units": 5000, "scale": 3},
    }


def test_market_snapshot_ordering_and_executable_capacity():
    event_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    receive_time = datetime(2026, 8, 29, 12, 0, 1, tzinfo=UTC)
    
    # Bids descending: 100, 99
    bids = (
        OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(10, 0)),
        OrderBookLevel(ScaledInteger(9900, 2), ScaledInteger(10, 0)),
    )
    # Asks ascending: 101, 102
    asks = (
        OrderBookLevel(ScaledInteger(10100, 2), ScaledInteger(10, 0)),
        OrderBookLevel(ScaledInteger(10200, 2), ScaledInteger(10, 0)),
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

    assert snapshot.instrument_id == "BTC-IDR"
    assert snapshot.event_at_utc == event_time
    assert snapshot.received_at_utc == receive_time
    assert snapshot.venue_cursor == "1001"
    assert snapshot.ingest_cursor == "2001"
    assert len(snapshot.bids) == 2
    assert len(snapshot.asks) == 2

    # Check capacity & executable price
    cap_asks, avg_price_asks = snapshot.calculate_executable_price(
        side=OrderBookSide.ASK, requested_size=ScaledInteger(15, 0)
    )
    assert cap_asks == ScaledInteger(20, 0)
    assert avg_price_asks.units == 10133
    assert avg_price_asks.scale == 2


def test_market_snapshot_unordered_bids_rejected():
    event_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    receive_time = datetime(2026, 8, 29, 12, 0, 1, tzinfo=UTC)
    
    # Bids ascending instead of descending: 99, 100
    bids = (
        OrderBookLevel(ScaledInteger(9900, 2), ScaledInteger(10, 0)),
        OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(10, 0)),
    )
    asks = (
        OrderBookLevel(ScaledInteger(10100, 2), ScaledInteger(10, 0)),
    )

    with pytest.raises(MarketEvidenceError) as exc_info:
        MarketSnapshot.create(
            instrument_id="BTC-IDR",
            event_at_utc=event_time,
            received_at_utc=receive_time,
            venue_cursor="1001",
            ingest_cursor="2001",
            bids=bids,
            asks=asks,
        )
    assert exc_info.value.code == "UNORDERED_BIDS"


def test_instrument_eligibility_evaluation():
    eligibility = InstrumentEligibility.evaluate(
        instrument_id="BTC-IDR",
        min_order_size=ScaledInteger(1, 0),
        max_spread_ratio_bps=50,
        freshness_micros=1000000,
        max_freshness_micros=3000000,
        is_universe_member=True,
        current_spread_ratio_bps=10,
        depth_capacity=ScaledInteger(10, 0),
        requested_size=ScaledInteger(5, 0),
    )
    assert eligibility.status is EligibilityStatus.ELIGIBLE
    assert eligibility.reason is EligibilityReason.QUALIFIED

    # Check stale freshness
    stale_eligibility = InstrumentEligibility.evaluate(
        instrument_id="BTC-IDR",
        min_order_size=ScaledInteger(1, 0),
        max_spread_ratio_bps=50,
        freshness_micros=4000000,
        max_freshness_micros=3000000,
        is_universe_member=True,
        current_spread_ratio_bps=10,
        depth_capacity=ScaledInteger(10, 0),
        requested_size=ScaledInteger(5, 0),
    )
    assert stale_eligibility.status is EligibilityStatus.INELIGIBLE
    assert stale_eligibility.reason is EligibilityReason.STALE_EVIDENCE
