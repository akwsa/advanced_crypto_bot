"""Contract tests for Story 3.2 atomic portfolio allocation."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.portfolio_allocation import (
    AllocationProposal,
    AllocationRejectCode,
    ConstituentCheckpoint,
    PortfolioConsistencyCut,
    ReservationBucket,
    ReservationConsumption,
    ReservationLifecycle,
    ReservationVector,
    RiskReservation,
    build_portfolio_allocation,
)


NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


def amount(units: int, scale: int = 2) -> ScaledInteger:
    return ScaledInteger(units, scale)


def ref(kind: str, value: str) -> ContentRef:
    return ContentRef.v2("autotrade-next", kind, {"value": value})


def bucket(initial: int, *, scale: int = 2) -> ReservationBucket:
    return ReservationBucket(
        initial=amount(initial, scale),
        consumed=amount(0, scale),
        active_remainder=amount(initial, scale),
        released=amount(0, scale),
    )


def vector(notional: int = 4_000) -> ReservationVector:
    return ReservationVector(
        notional=bucket(notional),
        planned_loss=bucket(200),
        fees=bucket(40),
        slippage_impact=bucket(60),
        turnover=bucket(notional),
    )


def reservation(pair: str = "BTC-IDR", horizon: str = "H1",
                reservation_id: str = "res-btc") -> RiskReservation:
    return RiskReservation(
        reservation_id=reservation_id,
        instrument_id=pair,
        pair_id=pair,
        horizon=horizon,
        balances=vector(),
    )


def checkpoints(sequence: int = 7) -> tuple[ConstituentCheckpoint, ...]:
    return (
        ConstituentCheckpoint(
            "opportunity-set", "portfolio", 1, ref("OpportunitySet", "frozen"),
        ),
        ConstituentCheckpoint(
            "market-cutoff", "portfolio", 1, ref("MarketCutoff", "t0"),
        ),
        ConstituentCheckpoint(
            "journal-high-water", "portfolio", 91,
            ContentRef.v2("autotrade-next", "JournalHighWater", {"sequence": 91}),
        ),
        ConstituentCheckpoint("positions", "portfolio", sequence, ref("Positions", str(sequence))),
        ConstituentCheckpoint("working-orders", "portfolio", 3, ref("Orders", "3")),
        ConstituentCheckpoint("risk-state", "portfolio", 11, ref("RiskState", "11")),
    )


def cut() -> PortfolioConsistencyCut:
    return PortfolioConsistencyCut(
        cutoff_at_utc=NOW,
        total_equity=amount(10_000),
        opportunity_set_ref=ref("OpportunitySet", "frozen"),
        market_cutoff_ref=ref("MarketCutoff", "t0"),
        journal_high_water=91,
        positions_ref=ref("Positions", "7"),
        working_orders_ref=ref("Orders", "3"),
        risk_state_ref=ref("RiskState", "11"),
        constituents=checkpoints(),
    )


def proposal(pair: str = "BTC-IDR", horizon: str = "H1",
             reservation_id: str = "res-btc") -> AllocationProposal:
    return AllocationProposal(
        decision_ref=ref("Decision", reservation_id),
        pair_id=pair,
        instrument_id=pair,
        horizon=horizon,
        risk_increasing=True,
        reservation=reservation(pair, horizon, reservation_id),
    )


def test_bucket_conservation_uses_common_scale_and_rejects_false_conservation() -> None:
    valid = ReservationBucket(
        initial=amount(100, 0),
        consumed=amount(3_000, 2),
        active_remainder=amount(500, 1),
        released=amount(2_000, 2),
    )
    assert valid.initial == amount(100, 0)

    with pytest.raises(DecisionError, match="RESERVATION_CONSERVATION_BREACH"):
        ReservationBucket(
            initial=amount(100, 0),
            consumed=amount(100, 2),
            active_remainder=amount(0, 2),
            released=amount(0, 2),
        )


def test_partial_multiple_fill_preserves_remainder_and_duplicate_is_content_bound() -> None:
    original = reservation()
    first_consumption = ReservationConsumption(
        amount(1_000), amount(50), amount(10), amount(15), amount(1_000),
    )
    second_consumption = ReservationConsumption(
        amount(500), amount(25), amount(5), amount(5), amount(500),
    )
    first = original.apply_fill(fill_id="fill-1", consumption=first_consumption)
    second = first.apply_fill(fill_id="fill-2", consumption=second_consumption)

    assert second.lifecycle is ReservationLifecycle.PARTIAL
    assert second.balances.notional.active_remainder == amount(2_500)
    assert second.balances.notional.released == amount(0)
    assert second.apply_fill(fill_id="fill-2", consumption=second_consumption) is second
    with pytest.raises(DecisionError, match="FILL_IDENTITY_CONFLICT"):
        second.apply_fill(
            fill_id="fill-2",
            consumption=ReservationConsumption(
                amount(1), amount(1), amount(1), amount(1), amount(1),
            ),
        )


def test_zero_notional_or_turnover_cannot_forge_a_partial_fill() -> None:
    with pytest.raises(DecisionError, match="EMPTY_FILL_CONSUMPTION"):
        ReservationConsumption(
            amount(0), amount(0), amount(0), amount(0), amount(0),
        )
    with pytest.raises(DecisionError, match="EMPTY_FILL_CONSUMPTION"):
        ReservationConsumption(
            amount(1), amount(0), amount(0), amount(0), amount(0),
        )


def test_unknown_and_partial_never_release_rounding_residual_until_terminal() -> None:
    partial = reservation().apply_fill(
        fill_id="fill-1",
        consumption=ReservationConsumption(
            amount(3_999), amount(199), amount(39), amount(59), amount(3_999),
        ),
    )
    unknown = partial.mark_unknown(ref("VenueEvidence", "unknown"))
    assert unknown.lifecycle is ReservationLifecycle.UNKNOWN
    assert unknown.balances.notional.active_remainder == amount(1)
    assert unknown.balances.notional.released == amount(0)

    terminal = unknown.terminalize(
        ReservationLifecycle.EXPIRED, ref("VenueEvidence", "expired"),
    )
    assert terminal.balances.notional.active_remainder == amount(0)
    assert terminal.balances.notional.released == amount(1)

    with pytest.raises(DecisionError, match="TERMINAL_RESERVATION_HAS_REMAINDER"):
        RiskReservation(
            "forged", "BTC-IDR", "BTC-IDR", "H1", vector(),
            ReservationLifecycle.FILLED, (), ref("VenueEvidence", "forged"),
        )

    with pytest.raises(DecisionError, match="FILLED_RESERVATION_WITHOUT_FILL"):
        reservation().terminalize(
            ReservationLifecycle.FILLED, ref("VenueEvidence", "filled"),
        )


def test_accepted_batch_is_scan_order_independent_and_content_bound() -> None:
    btc = proposal()
    eth = proposal("ETH-IDR", "H4", "res-eth")
    first = build_portfolio_allocation(
        consistency_cut=cut(), proposals=(btc, eth),
        observed_constituents=checkpoints(), expected_sequence=4,
        next_risk_state_ref=ref("RiskState", "12"),
    )
    reversed_order = build_portfolio_allocation(
        consistency_cut=cut(), proposals=(eth, btc),
        observed_constituents=tuple(reversed(checkpoints())), expected_sequence=4,
        next_risk_state_ref=ref("RiskState", "12"),
    )
    assert first.executable and reversed_order.executable
    assert first.batch_ref == reversed_order.batch_ref
    assert first.event_ref == reversed_order.event_ref
    assert first.outbox_ref == reversed_order.outbox_ref
    assert first.pair_horizon_ownership == (("BTC-IDR", "H1"), ("ETH-IDR", "H4"))
    with pytest.raises(DecisionError, match="ALLOCATION_CONTENT_REFERENCE_MISMATCH"):
        replace(first, event_ref=ref("ForgedEvent", "caller-supplied"))


def test_stale_constituent_rejects_entire_risk_increasing_batch() -> None:
    stale = list(checkpoints())
    stale[3] = ConstituentCheckpoint(
        "positions", "portfolio", 8, ref("Positions", "8"),
    )
    result = build_portfolio_allocation(
        consistency_cut=cut(), proposals=(proposal(), proposal("ETH-IDR", "H4", "res-eth")),
        observed_constituents=tuple(stale), expected_sequence=4,
        next_risk_state_ref=ref("RiskState", "12"),
    )
    assert not result.executable
    assert result.rejection is not None
    assert result.rejection.code is AllocationRejectCode.STALE_CONSTITUENT
    assert result.proposals == () and result.event_ref is None and result.outbox_ref is None


@pytest.mark.parametrize("checkpoint_index", (0, 1, 2))
def test_frozen_opportunity_market_and_journal_cut_are_observed(
    checkpoint_index: int,
) -> None:
    stale = list(checkpoints())
    original = stale[checkpoint_index]
    stale[checkpoint_index] = ConstituentCheckpoint(
        original.kind,
        original.constituent_id,
        original.sequence + 1,
        ref("StaleCheckpoint", original.kind),
    )
    result = build_portfolio_allocation(
        consistency_cut=cut(), proposals=(proposal(),),
        observed_constituents=tuple(stale), expected_sequence=4,
        next_risk_state_ref=ref("RiskState", "12"),
    )
    assert result.rejection is not None
    assert result.rejection.code is AllocationRejectCode.STALE_CONSTITUENT


def test_duplicate_observed_checkpoint_is_not_silently_collapsed() -> None:
    duplicated = (*checkpoints(), checkpoints()[0])
    with pytest.raises(DecisionError, match="DUPLICATE_OBSERVED_CHECKPOINT"):
        build_portfolio_allocation(
            consistency_cut=cut(), proposals=(proposal(),),
            observed_constituents=duplicated, expected_sequence=4,
            next_risk_state_ref=ref("RiskState", "12"),
        )


def test_duplicate_pair_horizon_ownership_rejects_without_partial_batch() -> None:
    result = build_portfolio_allocation(
        consistency_cut=cut(),
        proposals=(proposal(), proposal("BTC-IDR", "H4", "res-btc-h4")),
        observed_constituents=checkpoints(), expected_sequence=4,
        next_risk_state_ref=ref("RiskState", "12"),
    )
    assert result.rejection is not None
    assert result.rejection.code is AllocationRejectCode.DUPLICATE_PAIR_OWNERSHIP
    assert result.proposals == ()


def test_case_alias_cannot_bypass_unique_pair_ownership() -> None:
    result = build_portfolio_allocation(
        consistency_cut=cut(),
        proposals=(proposal(), proposal("btc-idr", "H4", "res-btc-case")),
        observed_constituents=checkpoints(), expected_sequence=4,
        next_risk_state_ref=ref("RiskState", "12"),
    )
    assert result.rejection is not None
    assert result.rejection.code is AllocationRejectCode.DUPLICATE_PAIR_OWNERSHIP


def test_risk_reducing_proposal_cannot_smuggle_a_new_reservation() -> None:
    base = proposal()
    with pytest.raises(DecisionError, match="RISK_REDUCING_PROPOSAL_HAS_RESERVATION"):
        replace(base, risk_increasing=False)


def test_equity_cap_is_common_scale_and_fail_closed() -> None:
    base = proposal()
    oversized = AllocationProposal(
        decision_ref=base.decision_ref,
        pair_id=base.pair_id,
        instrument_id=base.instrument_id,
        horizon=base.horizon,
        risk_increasing=True,
        reservation=RiskReservation(
            "res-large", "BTC-IDR", "BTC-IDR", "H1", vector(10_001),
        ),
    )
    result = build_portfolio_allocation(
        consistency_cut=cut(), proposals=(oversized,),
        observed_constituents=checkpoints(), expected_sequence=4,
        next_risk_state_ref=ref("RiskState", "12"),
    )
    assert result.rejection is not None
    assert result.rejection.code is AllocationRejectCode.EQUITY_CAP_EXCEEDED
