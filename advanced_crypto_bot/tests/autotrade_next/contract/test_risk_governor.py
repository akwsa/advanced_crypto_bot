"""Contract tests for Story 3.3 versioned portfolio RiskGovernor."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.risk_governor import (
    AdjustmentKind,
    CanonicalEquitySnapshot,
    EntryRiskRequest,
    QuantityAdjustment,
    RiskCheckReason,
    RiskGovernor,
    RiskPolicy,
    RiskPortfolioState,
)


NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


def amount(units: int, scale: int = 2) -> ScaledInteger:
    return ScaledInteger(units, scale)


def ref(kind: str, value: str) -> ContentRef:
    return ContentRef.v2("autotrade-next", kind, {"value": value})


def policy() -> RiskPolicy:
    return RiskPolicy.canonical("risk-policy-v1")


def equity(*, current: int = 1_000_000, daily_start: int = 1_000_000,
           peak: int = 1_000_000, high_water: int = 20) -> CanonicalEquitySnapshot:
    return CanonicalEquitySnapshot(
        equity=amount(current),
        daily_start_equity=amount(daily_start),
        peak_equity=amount(peak),
        observed_at_utc=NOW,
        journal_high_water=high_water,
        evidence_ref=ref("EquityEvidence", str(current)),
    )


def state(*, position: int = 0, exposure: int = 100_000,
          planned_loss: int = 0, turnover: int = 0,
          high_water: int = 20) -> RiskPortfolioState:
    return RiskPortfolioState(
        current_position_notional=amount(position),
        current_portfolio_exposure=amount(exposure),
        current_planned_loss=amount(planned_loss),
        rolling_entry_turnover=amount(turnover),
        journal_high_water=high_water,
        state_ref=ref("RiskState", f"{position}:{exposure}:{planned_loss}:{turnover}"),
    )


def adjustments(bps: int = 10_000) -> tuple[QuantityAdjustment, ...]:
    return tuple(
        QuantityAdjustment(kind, bps, ref("RiskAdjustment", kind.value))
        for kind in AdjustmentKind
    )


def request(*, quantity: int = 5_000, price: int = 100_000,
            planned_loss: int | None = None,
            mark_at: datetime = NOW, requested_at: datetime = NOW,
            stop_price: ScaledInteger | None = amount(95_000),
            depth: ScaledInteger | None = amount(10_000, 4),
            exit_capacity: ScaledInteger | None = amount(10_000, 4),
            minimum: ScaledInteger = amount(100, 4),
            high_water: int = 20,
            quantity_adjustments: tuple[QuantityAdjustment, ...] | None = None,
            ) -> EntryRiskRequest:
    return EntryRiskRequest(
        requested_quantity=amount(quantity, 4),
        minimum_quantity=minimum,
        mark_price=amount(price),
        mark_observed_at_utc=mark_at,
        requested_at_utc=requested_at,
        stop_price=stop_price,
        available_depth_quantity=depth,
        exit_capacity_quantity=exit_capacity,
        requested_planned_loss=amount(quantity // 2 if planned_loss is None else planned_loss),
        expected_journal_high_water=high_water,
        adjustments=(adjustments() if quantity_adjustments is None
                     else quantity_adjustments),
        market_evidence_ref=ref("MarketEvidence", str(mark_at)),
    )


def evaluate(**request_overrides):
    return RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(), state=state(),
        request=request(**request_overrides),
    )


def test_entry_is_approved_with_content_bound_policy_and_context() -> None:
    result = evaluate()
    assert result.allowed
    assert result.final_quantity == amount(5_000, 4)
    assert result.reasons == (RiskCheckReason.APPROVED,)
    assert result.policy_ref == policy().reference
    with pytest.raises(DecisionError, match="RISK_RESULT_REFERENCE_MISMATCH"):
        replace(result, result_ref=ref("ForgedRiskResult", "caller"))
    with pytest.raises(DecisionError, match="ALLOWED_RISK_RESULT_HAS_REJECTION"):
        replace(result, reasons=(RiskCheckReason.DAILY_LOSS_LIMIT,))


def test_planned_loss_cannot_understate_exact_mark_to_stop_loss() -> None:
    with pytest.raises(DecisionError, match="UNDERSTATED_PLANNED_LOSS"):
        request(planned_loss=2_499)
    with pytest.raises(DecisionError, match="RISK_POLICY_LIMIT_CAN_ONLY_TIGHTEN"):
        replace(policy(), max_position_bps=1_001)


def test_position_and_exposure_caps_use_exact_mixed_scale_and_only_reduce() -> None:
    position_limited = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(), state=state(exposure=0),
        request=request(quantity=20_000),
    )
    assert position_limited.allowed
    assert position_limited.final_quantity == amount(10_000, 4)
    assert RiskCheckReason.POSITION_QUANTITY_REDUCED in position_limited.reasons

    mixed_state = RiskPortfolioState(
        current_position_notional=amount(0, 0),
        current_portfolio_exposure=amount(3_900, 0),
        current_planned_loss=amount(0, 0),
        rolling_entry_turnover=amount(0, 0),
        journal_high_water=20,
        state_ref=ref("RiskState", "mixed-scale"),
    )
    exposure_limited = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(), state=mixed_state,
        request=request(quantity=5_000),
    )
    assert exposure_limited.final_quantity == amount(1_000, 4)
    assert RiskCheckReason.EXPOSURE_QUANTITY_REDUCED in exposure_limited.reasons


def test_daily_loss_and_hard_drawdown_are_derived_not_caller_attested() -> None:
    daily = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(current=979_900), state=state(), request=request(),
    )
    drawdown = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(current=899_900), state=state(), request=request(),
    )
    assert not daily.allowed and daily.reasons == (RiskCheckReason.DAILY_LOSS_LIMIT,)
    assert not drawdown.allowed and drawdown.reasons == (RiskCheckReason.HARD_DRAWDOWN_LIMIT,)
    exact_trigger = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(current=900_000), state=state(), request=request(),
    )
    assert exact_trigger.reasons == (RiskCheckReason.HARD_DRAWDOWN_LIMIT,)


def test_stale_equity_is_rejected_even_when_mark_is_current() -> None:
    stale_equity = replace(equity(), observed_at_utc=NOW - timedelta(seconds=6))
    result = RiskGovernor.evaluate_entry(
        policy=policy(), equity=stale_equity, state=state(), request=request(),
    )
    assert not result.allowed
    assert result.reasons == (RiskCheckReason.STALE_EQUITY,)


def test_planned_loss_and_turnover_capacity_reduce_quantity() -> None:
    planned = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(), state=state(planned_loss=4_900),
        request=request(quantity=5_000),
    )
    assert planned.allowed and planned.final_quantity == amount(200, 4)
    assert RiskCheckReason.PLANNED_LOSS_QUANTITY_REDUCED in planned.reasons

    turnover = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity(), state=state(turnover=399_000),
        request=request(quantity=5_000),
    )
    assert turnover.allowed and turnover.final_quantity == amount(100, 4)
    assert RiskCheckReason.TURNOVER_QUANTITY_REDUCED in turnover.reasons


@pytest.mark.parametrize(
    ("equity_value", "state_value", "request_value", "reason"),
    (
        (equity(), state(), request(mark_at=NOW - timedelta(seconds=6)), RiskCheckReason.STALE_MARK),
        (equity(), state(), request(mark_at=NOW + timedelta(microseconds=1)), RiskCheckReason.CLOCK_ANOMALY),
        (equity(), state(), request(stop_price=None), RiskCheckReason.MISSING_STOP),
        (equity(), state(), request(exit_capacity=None), RiskCheckReason.MISSING_EXIT_CAPACITY),
        (equity(), state(), request(depth=amount(99, 4)), RiskCheckReason.INSUFFICIENT_DEPTH),
        (equity(), state(high_water=19), request(), RiskCheckReason.HIGH_WATER_MISMATCH),
    ),
)
def test_missing_or_stale_risk_evidence_rejects_without_fabricated_quantity(
    equity_value, state_value, request_value, reason,
) -> None:
    result = RiskGovernor.evaluate_entry(
        policy=policy(), equity=equity_value, state=state_value, request=request_value,
    )
    assert not result.allowed
    assert result.final_quantity == amount(0, 4)
    assert result.reasons == (reason,)


def test_adjustments_have_fixed_order_and_can_only_reduce_quantity() -> None:
    reduced = evaluate(quantity_adjustments=adjustments(9_000))
    assert reduced.allowed
    assert reduced.final_quantity.units < request().requested_quantity.units
    assert reduced.final_quantity.units >= 0
    with pytest.raises(DecisionError, match="INVALID_ADJUSTMENT_BPS"):
        QuantityAdjustment(AdjustmentKind.LIQUIDITY, 10_001, ref("Adjustment", "bad"))


def test_risk_reducing_exit_is_turnover_exempt_and_position_bounded() -> None:
    result = RiskGovernor.evaluate_risk_reducing_exit(
        policy=policy(), requested_quantity=amount(20_000, 4),
        position_quantity=amount(10_000, 4),
    )
    assert result.allowed
    assert result.final_quantity == amount(10_000, 4)
    assert result.reasons == (RiskCheckReason.EXIT_POSITION_CLAMP,)
