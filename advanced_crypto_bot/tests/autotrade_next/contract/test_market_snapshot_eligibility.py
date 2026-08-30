"""Negative-first contracts for Story 2.2 market remediation."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from autotrade_next.domain.errors import MarketEvidenceError
from autotrade_next.domain.market import (
    EligibilityReason, EligibilityStatus, InstrumentEligibility, InstrumentRules,
    MarketQuality, MarketSnapshot, OrderBookLevel, OrderBookSide, UniverseMembership,
)
from autotrade_next.domain.numeric import ScaledInteger


EVENT = datetime(2026, 8, 29, 12, tzinfo=UTC)
RECEIVED = datetime(2026, 8, 29, 12, 0, 1, tzinfo=UTC)


def rules(**changes):
    values = dict(version="rules:7", min_order_size=ScaledInteger(10, 2),
                  price_scale=2, quantity_scale=2,
                  price_tick=ScaledInteger(1, 2), quantity_step=ScaledInteger(5, 2),
                  metadata_qualified=True)
    values.update(changes)
    return InstrumentRules(**values)


def membership(**changes):
    values = dict(universe_version="universe:7", effective_at_utc=EVENT,
                  is_member=True, proof_id="membership:btc-idr:7")
    values.update(changes)
    return UniverseMembership(**values)


def quality(**changes):
    values = dict(freshness_micros=1_000_000, max_freshness_micros=3_000_000,
                  current_spread_ratio_bps=10, max_spread_ratio_bps=50,
                  source_integrity_qualified=True,
                  authority_scope_id="indodax-public", evidence_id="l2:1001")
    values.update(changes)
    return MarketQuality(**values)


def snapshot(**changes):
    values = dict(
        instrument_id="BTC-IDR", event_at_utc=EVENT, received_at_utc=RECEIVED,
        venue_cursor="1001", ingest_cursor="2001",
        bids=(OrderBookLevel(ScaledInteger(1000, 1), ScaledInteger(50, 2)),
              OrderBookLevel(ScaledInteger(9995, 2), ScaledInteger(500, 3))),
        asks=(OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(50, 2)),
              OrderBookLevel(ScaledInteger(1001, 1), ScaledInteger(500, 3))),
        execution_side=OrderBookSide.ASK,
        requested_size=ScaledInteger(100, 2), rules=rules(),
        membership=membership(), quality=quality(),
    )
    values.update(changes)
    return MarketSnapshot.create(**values)


@pytest.mark.parametrize("price,quantity,code", [
    (ScaledInteger(0, 2), ScaledInteger(1, 2), "NONPOSITIVE_PRICE"),
    (ScaledInteger(-1, 2), ScaledInteger(1, 2), "NONPOSITIVE_PRICE"),
    (ScaledInteger(1, 2), ScaledInteger(0, 2), "NONPOSITIVE_QUANTITY"),
    (ScaledInteger(1, 2), ScaledInteger(-1, 2), "NONPOSITIVE_QUANTITY"),
    (1, ScaledInteger(1, 2), "INVALID_ORDERBOOK_LEVEL"),
])
def test_level_rejects_malformed_and_nonpositive(price, quantity, code):
    with pytest.raises(MarketEvidenceError) as error:
        OrderBookLevel(price, quantity)
    assert error.value.code == code
    assert error.value.partial_result is None


def test_book_rejects_mixed_scale_unordered_crossed_and_empty_side():
    with pytest.raises(MarketEvidenceError, match="UNORDERED_BIDS"):
        snapshot(bids=(OrderBookLevel(ScaledInteger(999, 1), ScaledInteger(1, 0)),
                       OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(1, 0))))
    with pytest.raises(MarketEvidenceError, match="CROSSED_BOOK"):
        snapshot(bids=(OrderBookLevel(ScaledInteger(1001, 1), ScaledInteger(1, 0)),),
                 asks=(OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(1, 0)),))
    with pytest.raises(MarketEvidenceError, match="EMPTY_EXECUTION_SIDE"):
        snapshot(asks=())


def test_snapshot_freezes_lists_and_content_binds_decision_inputs():
    bids = [OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(1, 0))]
    asks = [OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(1, 0))]
    base = snapshot(bids=bids, asks=asks)
    bids.clear(); asks.clear()
    assert len(base.bids) == len(base.asks) == 1
    assert base.snapshot_ref.verify(base.binding_value())
    with pytest.raises(FrozenInstanceError):
        base.requested_size = ScaledInteger(2, 0)
    assert snapshot(requested_size=ScaledInteger(105, 2)).snapshot_ref != base.snapshot_ref
    assert snapshot(rules=rules(version="rules:8")).snapshot_ref != base.snapshot_ref
    assert snapshot(membership=membership(proof_id="membership:new")).snapshot_ref != base.snapshot_ref


def test_mixed_scale_exact_walk_and_conservative_wap():
    snap = snapshot(
        asks=(OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(5, 1)),
              OrderBookLevel(ScaledInteger(1001, 1), ScaledInteger(500, 3))),
        bids=(OrderBookLevel(ScaledInteger(1000, 1), ScaledInteger(5, 1)),
              OrderBookLevel(ScaledInteger(9995, 2), ScaledInteger(500, 3))),
    )
    assert snap.calculate_executable_price(OrderBookSide.ASK) == (
        ScaledInteger(100, 2), ScaledInteger(10008, 2))
    bid_snap = snapshot(
        execution_side=OrderBookSide.BID,
        asks=snap.asks,
        bids=snap.bids,
    )
    assert bid_snap.calculate_executable_price(OrderBookSide.BID) == (
        ScaledInteger(100, 2), ScaledInteger(9997, 2))


def test_requested_size_binding_step_and_lossless_precision():
    with pytest.raises(MarketEvidenceError, match="REQUESTED_SIZE_MISMATCH"):
        snapshot().calculate_executable_price(OrderBookSide.ASK, ScaledInteger(95, 2))
    result = InstrumentEligibility.evaluate(
        snapshot=snapshot(requested_size=ScaledInteger(101, 2)))
    assert result.reason is EligibilityReason.QUANTITY_STEP_BREACH
    precision_result = InstrumentEligibility.evaluate(
        snapshot=snapshot(requested_size=ScaledInteger(1001, 3)))
    assert precision_result.reason is EligibilityReason.QUANTITY_PRECISION_BREACH


def test_precision_failures_are_pair_local_and_side_is_frozen():
    price_precision = snapshot(asks=(
        OrderBookLevel(ScaledInteger(100051, 3), ScaledInteger(1, 0)),))
    assert InstrumentEligibility.evaluate(
        snapshot=price_precision).reason is EligibilityReason.PRICE_PRECISION_BREACH

    quantity_precision = snapshot(asks=(
        OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(1001, 3)),))
    assert InstrumentEligibility.evaluate(
        snapshot=quantity_precision).reason is EligibilityReason.QUANTITY_PRECISION_BREACH

    bid_snapshot = snapshot(
        execution_side=OrderBookSide.BID,
        bids=(OrderBookLevel(ScaledInteger(10000, 2), ScaledInteger(1, 0)),),
        asks=(OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(10, 2)),),
    )
    assert InstrumentEligibility.evaluate(snapshot=bid_snapshot).status is EligibilityStatus.ELIGIBLE
    with pytest.raises(MarketEvidenceError, match="EXECUTION_SIDE_MISMATCH"):
        bid_snapshot.calculate_executable_price(OrderBookSide.ASK)


def test_direct_snapshot_construction_cannot_bypass_invariants():
    base = snapshot()
    with pytest.raises(MarketEvidenceError, match="NONPOSITIVE_REQUESTED_SIZE"):
        replace(base, requested_size=ScaledInteger(0, 2))


def test_market_scales_are_bounded_before_common_scale_arithmetic():
    with pytest.raises(MarketEvidenceError, match="SCALE_OUT_OF_RANGE"):
        OrderBookLevel(ScaledInteger(1, 19), ScaledInteger(1, 0))
    with pytest.raises(MarketEvidenceError, match="INVALID_PRICE_SCALE"):
        rules(price_scale=19)


def test_eligibility_result_rejects_contradictory_direct_construction():
    with pytest.raises(MarketEvidenceError, match="INVALID_ELIGIBILITY_RESULT"):
        InstrumentEligibility(
            "BTC-IDR", EligibilityStatus.ELIGIBLE,
            EligibilityReason.INSUFFICIENT_DEPTH,
        )
    with pytest.raises(MarketEvidenceError, match="INVALID_ELIGIBILITY_RESULT"):
        InstrumentEligibility(
            "BTC-IDR", EligibilityStatus.INELIGIBLE,
            EligibilityReason.SYSTEMIC_INTEGRITY_FAILURE,
        )


@pytest.mark.parametrize("changes,reason", [
    ({"membership": membership(is_member=False)}, EligibilityReason.NOT_UNIVERSE_MEMBER),
    ({"quality": quality(freshness_micros=3_000_001)}, EligibilityReason.STALE_EVIDENCE),
    ({"quality": quality(current_spread_ratio_bps=51)}, EligibilityReason.EXCEEDS_MAX_SPREAD),
    ({"rules": rules(metadata_qualified=False)}, EligibilityReason.UNQUALIFIED_METADATA),
    ({"rules": rules(price_tick=ScaledInteger(5, 2)), "asks": (
        OrderBookLevel(ScaledInteger(10006, 2), ScaledInteger(1, 0)),)},
     EligibilityReason.PRICE_TICK_BREACH),
    ({"requested_size": ScaledInteger(5, 2)}, EligibilityReason.MIN_SIZE_BREACH),
    ({"requested_size": ScaledInteger(15, 2), "asks": (
        OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(10, 2)),)},
     EligibilityReason.INSUFFICIENT_DEPTH),
])
def test_pair_local_failures_are_specific(changes, reason):
    result = InstrumentEligibility.evaluate(snapshot=snapshot(**changes))
    assert (result.status, result.reason) == (EligibilityStatus.INELIGIBLE, reason)
    assert result.entry_freeze_signal is None
    assert result.recovery_allowed and result.protective_allowed


def test_exact_coverage_is_eligible_and_systemic_failure_emits_signal():
    exact = snapshot(asks=(OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(1, 0)),))
    assert InstrumentEligibility.evaluate(snapshot=exact).status is EligibilityStatus.ELIGIBLE
    systemic = InstrumentEligibility.evaluate(
        snapshot=snapshot(quality=quality(source_integrity_qualified=False)))
    assert systemic.reason is EligibilityReason.SYSTEMIC_INTEGRITY_FAILURE
    assert systemic.entry_freeze_signal.signal_ref.verify(
        systemic.entry_freeze_signal.binding_value())
    assert systemic.entry_freeze_signal.cause_snapshot_ref == snapshot(
        quality=quality(source_integrity_qualified=False)).snapshot_ref
    assert systemic.recovery_allowed and systemic.protective_allowed


def test_aggregate_capacity_overflow_fails_as_market_evidence():
    maximum = (1 << 2048) - 1
    oversized = snapshot(asks=(
        OrderBookLevel(ScaledInteger(10005, 2), ScaledInteger(maximum, 2)),
        OrderBookLevel(ScaledInteger(10010, 2), ScaledInteger(maximum, 2)),
    ))
    with pytest.raises(MarketEvidenceError, match="CAPACITY_OUT_OF_RANGE"):
        oversized.calculate_executable_price(OrderBookSide.ASK)


def test_identical_input_is_deterministic_for_100_runs():
    outputs = []
    for _ in range(100):
        snap = snapshot()
        outputs.append((snap.snapshot_ref.key,
                        snap.calculate_executable_price(OrderBookSide.ASK),
                        InstrumentEligibility.evaluate(snapshot=snap)))
    assert all(value == outputs[0] for value in outputs)
