"""Versioned, fail-closed portfolio risk envelope and quantity governor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from .content import ContentRef
from .errors import DecisionError
from .numeric import ScaledInteger


MAX_RISK_SCALE = 18


def _text(value: object, code: str) -> None:
    if type(value) is not str or not value.strip():
        raise DecisionError(code)


def _amount(value: object, code: str, *, positive: bool = False) -> ScaledInteger:
    if type(value) is not ScaledInteger:
        raise DecisionError(code)
    if value.scale > MAX_RISK_SCALE:
        raise DecisionError("RISK_SCALE_EXCEEDED")
    if value.units < 0 or (positive and value.units == 0):
        raise DecisionError(code)
    return value


def _utc(value: object, code: str) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != UTC.utcoffset(value)):
        raise DecisionError(code)
    return value


def _aligned(left: ScaledInteger, right: ScaledInteger) -> tuple[int, int, int]:
    target = max(left.scale, right.scale)
    if target > MAX_RISK_SCALE:
        raise DecisionError("RISK_SCALE_EXCEEDED")
    return (
        target,
        left.units * (10 ** (target - left.scale)),
        right.units * (10 ** (target - right.scale)),
    )


def _compare(left: ScaledInteger, right: ScaledInteger) -> int:
    _, left_units, right_units = _aligned(left, right)
    return (left_units > right_units) - (left_units < right_units)


def _positive_difference(left: ScaledInteger, right: ScaledInteger) -> ScaledInteger:
    target, left_units, right_units = _aligned(left, right)
    return ScaledInteger(max(left_units - right_units, 0), target)


def _bps(value: ScaledInteger, basis_points: int) -> ScaledInteger:
    return ScaledInteger((value.units * basis_points) // 10_000, value.scale)


def _rescale_floor(value: ScaledInteger, target_scale: int) -> ScaledInteger:
    if target_scale > MAX_RISK_SCALE:
        raise DecisionError("RISK_SCALE_EXCEEDED")
    if target_scale >= value.scale:
        return ScaledInteger(value.units * (10 ** (target_scale - value.scale)),
                             target_scale)
    return ScaledInteger(value.units // (10 ** (value.scale - target_scale)),
                         target_scale)


def _min_quantity(left: ScaledInteger, right: ScaledInteger,
                  target_scale: int) -> ScaledInteger:
    selected = left if _compare(left, right) <= 0 else right
    return _rescale_floor(selected, target_scale)


def _quantity_cap_for_notional(
    quantity: ScaledInteger,
    price: ScaledInteger,
    capacity: ScaledInteger,
) -> ScaledInteger:
    if capacity.units <= 0:
        return ScaledInteger(0, quantity.scale)
    numerator = capacity.units * (10 ** (price.scale + quantity.scale))
    denominator = price.units * (10 ** capacity.scale)
    if denominator <= 0:
        raise DecisionError("INVALID_MARK_PRICE")
    cap_units = numerator // denominator
    return ScaledInteger(min(quantity.units, cap_units), quantity.scale)


def _amount_value(value: ScaledInteger) -> dict[str, int]:
    return {"units": value.units, "scale": value.scale}


class AdjustmentKind(str, Enum):
    LIQUIDITY = "LIQUIDITY"
    CORRELATION = "CORRELATION"
    STOP_DISTANCE = "STOP_DISTANCE"
    VOLATILITY = "VOLATILITY"
    COST = "COST"
    UNCERTAINTY = "UNCERTAINTY"


class RiskCheckReason(str, Enum):
    APPROVED = "APPROVED"
    POSITION_QUANTITY_REDUCED = "POSITION_QUANTITY_REDUCED"
    EXPOSURE_QUANTITY_REDUCED = "EXPOSURE_QUANTITY_REDUCED"
    PLANNED_LOSS_QUANTITY_REDUCED = "PLANNED_LOSS_QUANTITY_REDUCED"
    TURNOVER_QUANTITY_REDUCED = "TURNOVER_QUANTITY_REDUCED"
    DEPTH_QUANTITY_REDUCED = "DEPTH_QUANTITY_REDUCED"
    EXIT_CAPACITY_QUANTITY_REDUCED = "EXIT_CAPACITY_QUANTITY_REDUCED"
    ADJUSTMENT_QUANTITY_REDUCED = "ADJUSTMENT_QUANTITY_REDUCED"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    HARD_DRAWDOWN_LIMIT = "HARD_DRAWDOWN_LIMIT"
    STALE_MARK = "STALE_MARK"
    STALE_EQUITY = "STALE_EQUITY"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"
    MISSING_STOP = "MISSING_STOP"
    MISSING_EXIT_CAPACITY = "MISSING_EXIT_CAPACITY"
    INSUFFICIENT_DEPTH = "INSUFFICIENT_DEPTH"
    INSUFFICIENT_EXIT_CAPACITY = "INSUFFICIENT_EXIT_CAPACITY"
    HIGH_WATER_MISMATCH = "HIGH_WATER_MISMATCH"
    QUANTITY_BELOW_MINIMUM = "QUANTITY_BELOW_MINIMUM"
    EXIT_POSITION_CLAMP = "EXIT_POSITION_CLAMP"
    NO_POSITION = "NO_POSITION"


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    version: str
    max_position_bps: int
    max_portfolio_exposure_bps: int
    max_daily_loss_bps: int
    max_planned_loss_bps: int
    hard_drawdown_bps: int
    rolling_entry_turnover_bps: int
    max_mark_age_microseconds: int

    def __post_init__(self) -> None:
        _text(self.version, "INVALID_RISK_POLICY_VERSION")
        limits = (
            (self.max_position_bps, 1_000),
            (self.max_portfolio_exposure_bps, 4_000),
            (self.max_daily_loss_bps, 200),
            (self.max_planned_loss_bps, 50),
            (self.hard_drawdown_bps, 1_000),
            (self.rolling_entry_turnover_bps, 4_000),
        )
        if any(type(value) is not int or value <= 0 or value > ceiling
               for value, ceiling in limits):
            raise DecisionError("RISK_POLICY_LIMIT_CAN_ONLY_TIGHTEN")
        if (type(self.max_mark_age_microseconds) is not int
                or self.max_mark_age_microseconds <= 0):
            raise DecisionError("INVALID_MARK_AGE_LIMIT")

    @classmethod
    def canonical(cls, version: str) -> RiskPolicy:
        return cls(version, 1_000, 4_000, 200, 50, 1_000, 4_000, 5_000_000)

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "version": self.version,
            "max_position_bps": self.max_position_bps,
            "max_portfolio_exposure_bps": self.max_portfolio_exposure_bps,
            "max_daily_loss_bps": self.max_daily_loss_bps,
            "max_planned_loss_bps": self.max_planned_loss_bps,
            "hard_drawdown_bps": self.hard_drawdown_bps,
            "rolling_entry_turnover_bps": self.rolling_entry_turnover_bps,
            "max_mark_age_microseconds": self.max_mark_age_microseconds,
        }

    @property
    def reference(self) -> ContentRef:
        return ContentRef.v2("autotrade-next", "RiskPolicy", self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class CanonicalEquitySnapshot:
    equity: ScaledInteger
    daily_start_equity: ScaledInteger
    peak_equity: ScaledInteger
    observed_at_utc: datetime
    journal_high_water: int
    evidence_ref: ContentRef

    def __post_init__(self) -> None:
        _amount(self.equity, "INVALID_CANONICAL_EQUITY", positive=True)
        _amount(self.daily_start_equity, "INVALID_DAILY_START_EQUITY", positive=True)
        _amount(self.peak_equity, "INVALID_PEAK_EQUITY", positive=True)
        _utc(self.observed_at_utc, "INVALID_EQUITY_TIMESTAMP")
        if type(self.journal_high_water) is not int or self.journal_high_water < 0:
            raise DecisionError("INVALID_EQUITY_HIGH_WATER")
        if type(self.evidence_ref) is not ContentRef:
            raise DecisionError("INVALID_EQUITY_EVIDENCE")

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "equity": _amount_value(self.equity),
            "daily_start_equity": _amount_value(self.daily_start_equity),
            "peak_equity": _amount_value(self.peak_equity),
            "observed_at_utc": self.observed_at_utc,
            "journal_high_water": self.journal_high_water,
            "evidence_ref": self.evidence_ref.to_canonical_value(),
        }


@dataclass(frozen=True, slots=True)
class RiskPortfolioState:
    current_position_notional: ScaledInteger
    current_portfolio_exposure: ScaledInteger
    current_planned_loss: ScaledInteger
    rolling_entry_turnover: ScaledInteger
    journal_high_water: int
    state_ref: ContentRef

    def __post_init__(self) -> None:
        for value in (self.current_position_notional,
                      self.current_portfolio_exposure,
                      self.current_planned_loss,
                      self.rolling_entry_turnover):
            _amount(value, "INVALID_RISK_PORTFOLIO_STATE")
        if type(self.journal_high_water) is not int or self.journal_high_water < 0:
            raise DecisionError("INVALID_RISK_HIGH_WATER")
        if type(self.state_ref) is not ContentRef:
            raise DecisionError("INVALID_RISK_STATE_REFERENCE")

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "current_position_notional": _amount_value(self.current_position_notional),
            "current_portfolio_exposure": _amount_value(self.current_portfolio_exposure),
            "current_planned_loss": _amount_value(self.current_planned_loss),
            "rolling_entry_turnover": _amount_value(self.rolling_entry_turnover),
            "journal_high_water": self.journal_high_water,
            "state_ref": self.state_ref.to_canonical_value(),
        }


@dataclass(frozen=True, slots=True)
class QuantityAdjustment:
    kind: AdjustmentKind
    basis_points: int
    evidence_ref: ContentRef

    def __post_init__(self) -> None:
        if type(self.kind) is not AdjustmentKind:
            raise DecisionError("INVALID_ADJUSTMENT_KIND")
        if (type(self.basis_points) is not int
                or not 0 <= self.basis_points <= 10_000):
            raise DecisionError("INVALID_ADJUSTMENT_BPS")
        if type(self.evidence_ref) is not ContentRef:
            raise DecisionError("INVALID_ADJUSTMENT_EVIDENCE")

    def to_canonical_value(self) -> dict[str, object]:
        return {"kind": self.kind.value, "basis_points": self.basis_points,
                "evidence_ref": self.evidence_ref.to_canonical_value()}


@dataclass(frozen=True, slots=True)
class EntryRiskRequest:
    requested_quantity: ScaledInteger
    minimum_quantity: ScaledInteger
    mark_price: ScaledInteger
    mark_observed_at_utc: datetime
    requested_at_utc: datetime
    stop_price: ScaledInteger | None
    available_depth_quantity: ScaledInteger | None
    exit_capacity_quantity: ScaledInteger | None
    requested_planned_loss: ScaledInteger
    expected_journal_high_water: int
    adjustments: tuple[QuantityAdjustment, ...]
    market_evidence_ref: ContentRef

    def __post_init__(self) -> None:
        _amount(self.requested_quantity, "INVALID_REQUESTED_QUANTITY", positive=True)
        _amount(self.minimum_quantity, "INVALID_MINIMUM_QUANTITY", positive=True)
        _amount(self.mark_price, "INVALID_MARK_PRICE", positive=True)
        _utc(self.mark_observed_at_utc, "INVALID_MARK_TIMESTAMP")
        _utc(self.requested_at_utc, "INVALID_REQUEST_TIMESTAMP")
        if self.stop_price is not None:
            _amount(self.stop_price, "INVALID_STOP_PRICE", positive=True)
            if _compare(self.stop_price, self.mark_price) >= 0:
                raise DecisionError("INVALID_STOP_PRICE")
        if self.available_depth_quantity is not None:
            _amount(self.available_depth_quantity, "INVALID_DEPTH_QUANTITY")
        if self.exit_capacity_quantity is not None:
            _amount(self.exit_capacity_quantity, "INVALID_EXIT_CAPACITY")
        _amount(self.requested_planned_loss, "INVALID_REQUESTED_PLANNED_LOSS")
        if self.stop_price is not None:
            stop_distance = _positive_difference(self.mark_price, self.stop_price)
            product_scale = self.requested_quantity.scale + stop_distance.scale
            planned_scale = self.requested_planned_loss.scale
            product_units = (self.requested_quantity.units * stop_distance.units
                             * (10 ** planned_scale))
            planned_units = (self.requested_planned_loss.units
                             * (10 ** product_scale))
            if product_units > planned_units:
                raise DecisionError("UNDERSTATED_PLANNED_LOSS")
        if (type(self.expected_journal_high_water) is not int
                or self.expected_journal_high_water < 0):
            raise DecisionError("INVALID_EXPECTED_HIGH_WATER")
        if (type(self.adjustments) is not tuple
                or tuple(item.kind for item in self.adjustments) != tuple(AdjustmentKind)
                or any(type(item) is not QuantityAdjustment for item in self.adjustments)):
            raise DecisionError("INVALID_ADJUSTMENT_SET")
        if type(self.market_evidence_ref) is not ContentRef:
            raise DecisionError("INVALID_MARKET_EVIDENCE")
        if _compare(self.minimum_quantity, self.requested_quantity) > 0:
            raise DecisionError("MINIMUM_EXCEEDS_REQUESTED_QUANTITY")

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "requested_quantity": _amount_value(self.requested_quantity),
            "minimum_quantity": _amount_value(self.minimum_quantity),
            "mark_price": _amount_value(self.mark_price),
            "mark_observed_at_utc": self.mark_observed_at_utc,
            "requested_at_utc": self.requested_at_utc,
            "stop_price": (None if self.stop_price is None
                           else _amount_value(self.stop_price)),
            "available_depth_quantity": (
                None if self.available_depth_quantity is None
                else _amount_value(self.available_depth_quantity)),
            "exit_capacity_quantity": (
                None if self.exit_capacity_quantity is None
                else _amount_value(self.exit_capacity_quantity)),
            "requested_planned_loss": _amount_value(self.requested_planned_loss),
            "expected_journal_high_water": self.expected_journal_high_water,
            "adjustments": tuple(item.to_canonical_value() for item in self.adjustments),
            "market_evidence_ref": self.market_evidence_ref.to_canonical_value(),
        }


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    allowed: bool
    requested_quantity: ScaledInteger
    final_quantity: ScaledInteger
    reasons: tuple[RiskCheckReason, ...]
    policy_ref: ContentRef
    context_ref: ContentRef
    result_ref: ContentRef

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise DecisionError("INVALID_RISK_RESULT")
        _amount(self.requested_quantity, "INVALID_REQUESTED_QUANTITY", positive=True)
        _amount(self.final_quantity, "INVALID_FINAL_QUANTITY")
        if _compare(self.final_quantity, self.requested_quantity) > 0:
            raise DecisionError("RISK_GOVERNOR_INCREASED_QUANTITY")
        if (type(self.reasons) is not tuple or not self.reasons
                or any(type(item) is not RiskCheckReason for item in self.reasons)):
            raise DecisionError("INVALID_RISK_REASONS")
        if any(type(value) is not ContentRef for value in (
                self.policy_ref, self.context_ref, self.result_ref)):
            raise DecisionError("INVALID_RISK_RESULT_REFERENCE")
        if (self.policy_ref.domain != "autotrade-next"
                or self.policy_ref.kind != "RiskPolicy"
                or self.context_ref.domain != "autotrade-next"
                or self.context_ref.kind not in {
                    "EntryRiskContext", "RiskReducingExitContext"}):
            raise DecisionError("INVALID_RISK_RESULT_REFERENCE")
        if self.allowed != (self.final_quantity.units > 0):
            raise DecisionError("RISK_RESULT_ALLOWANCE_MISMATCH")
        rejection_reasons = {
            RiskCheckReason.DAILY_LOSS_LIMIT,
            RiskCheckReason.HARD_DRAWDOWN_LIMIT,
            RiskCheckReason.STALE_MARK,
            RiskCheckReason.STALE_EQUITY,
            RiskCheckReason.CLOCK_ANOMALY,
            RiskCheckReason.MISSING_STOP,
            RiskCheckReason.MISSING_EXIT_CAPACITY,
            RiskCheckReason.INSUFFICIENT_DEPTH,
            RiskCheckReason.INSUFFICIENT_EXIT_CAPACITY,
            RiskCheckReason.HIGH_WATER_MISMATCH,
            RiskCheckReason.QUANTITY_BELOW_MINIMUM,
            RiskCheckReason.NO_POSITION,
        }
        if self.allowed:
            if any(reason in rejection_reasons for reason in self.reasons):
                raise DecisionError("ALLOWED_RISK_RESULT_HAS_REJECTION")
            if RiskCheckReason.APPROVED in self.reasons:
                if (self.reasons != (RiskCheckReason.APPROVED,)
                        or self.final_quantity != self.requested_quantity):
                    raise DecisionError("INVALID_APPROVED_RISK_RESULT")
        elif (len(self.reasons) != 1 or self.reasons[0] not in rejection_reasons):
            raise DecisionError("DENIED_RISK_RESULT_MISSING_REJECTION")
        expected = ContentRef.v2(
            "autotrade-next", "RiskEvaluationResult",
            {
                "allowed": self.allowed,
                "requested_quantity": _amount_value(self.requested_quantity),
                "final_quantity": _amount_value(self.final_quantity),
                "reasons": tuple(item.value for item in self.reasons),
                "policy_ref": self.policy_ref.to_canonical_value(),
                "context_ref": self.context_ref.to_canonical_value(),
            },
        )
        if self.result_ref != expected:
            raise DecisionError("RISK_RESULT_REFERENCE_MISMATCH")


def _result(*, requested: ScaledInteger, final: ScaledInteger,
            reasons: tuple[RiskCheckReason, ...], policy_ref: ContentRef,
            context_ref: ContentRef) -> RiskEvaluationResult:
    allowed = final.units > 0
    value = {
        "allowed": allowed,
        "requested_quantity": _amount_value(requested),
        "final_quantity": _amount_value(final),
        "reasons": tuple(item.value for item in reasons),
        "policy_ref": policy_ref.to_canonical_value(),
        "context_ref": context_ref.to_canonical_value(),
    }
    return RiskEvaluationResult(
        allowed, requested, final, reasons, policy_ref, context_ref,
        ContentRef.v2("autotrade-next", "RiskEvaluationResult", value),
    )


def _entry_context(policy: RiskPolicy, equity: CanonicalEquitySnapshot,
                   state: RiskPortfolioState, request: EntryRiskRequest) -> ContentRef:
    return ContentRef.v2(
        "autotrade-next", "EntryRiskContext",
        {"policy": policy.to_canonical_value(),
         "equity": equity.to_canonical_value(),
         "state": state.to_canonical_value(),
         "request": request.to_canonical_value()},
    )


class RiskGovernor:
    @staticmethod
    def evaluate_entry(
        *, policy: RiskPolicy, equity: CanonicalEquitySnapshot,
        state: RiskPortfolioState, request: EntryRiskRequest,
    ) -> RiskEvaluationResult:
        if type(policy) is not RiskPolicy or type(equity) is not CanonicalEquitySnapshot:
            raise DecisionError("INVALID_RISK_CONTEXT")
        if type(state) is not RiskPortfolioState or type(request) is not EntryRiskRequest:
            raise DecisionError("INVALID_RISK_CONTEXT")
        policy_ref = policy.reference
        context_ref = _entry_context(policy, equity, state, request)
        zero = ScaledInteger(0, request.requested_quantity.scale)

        def rejected(reason: RiskCheckReason) -> RiskEvaluationResult:
            return _result(requested=request.requested_quantity, final=zero,
                           reasons=(reason,), policy_ref=policy_ref,
                           context_ref=context_ref)

        if not (equity.journal_high_water == state.journal_high_water
                == request.expected_journal_high_water):
            return rejected(RiskCheckReason.HIGH_WATER_MISMATCH)
        age = request.requested_at_utc - request.mark_observed_at_utc
        age_microseconds = ((age.days * 86_400 + age.seconds) * 1_000_000
                            + age.microseconds)
        if age_microseconds < 0:
            return rejected(RiskCheckReason.CLOCK_ANOMALY)
        if age_microseconds > policy.max_mark_age_microseconds:
            return rejected(RiskCheckReason.STALE_MARK)
        equity_age = request.requested_at_utc - equity.observed_at_utc
        equity_age_microseconds = (
            (equity_age.days * 86_400 + equity_age.seconds) * 1_000_000
            + equity_age.microseconds
        )
        if equity_age_microseconds < 0:
            return rejected(RiskCheckReason.CLOCK_ANOMALY)
        if equity_age_microseconds > policy.max_mark_age_microseconds:
            return rejected(RiskCheckReason.STALE_EQUITY)
        if request.stop_price is None:
            return rejected(RiskCheckReason.MISSING_STOP)
        if request.exit_capacity_quantity is None:
            return rejected(RiskCheckReason.MISSING_EXIT_CAPACITY)
        if request.available_depth_quantity is None or _compare(
                request.available_depth_quantity, request.minimum_quantity) < 0:
            return rejected(RiskCheckReason.INSUFFICIENT_DEPTH)
        if _compare(request.exit_capacity_quantity, request.minimum_quantity) < 0:
            return rejected(RiskCheckReason.INSUFFICIENT_EXIT_CAPACITY)

        drawdown = _positive_difference(equity.peak_equity, equity.equity)
        if _compare(drawdown, _bps(equity.peak_equity,
                                   policy.hard_drawdown_bps)) >= 0:
            return rejected(RiskCheckReason.HARD_DRAWDOWN_LIMIT)
        daily_loss = _positive_difference(equity.daily_start_equity, equity.equity)
        if _compare(daily_loss, _bps(equity.daily_start_equity,
                                     policy.max_daily_loss_bps)) > 0:
            return rejected(RiskCheckReason.DAILY_LOSS_LIMIT)

        quantity = request.requested_quantity
        reductions: list[RiskCheckReason] = []

        def apply_cap(cap: ScaledInteger, reason: RiskCheckReason) -> None:
            nonlocal quantity
            capped = _min_quantity(quantity, cap, request.requested_quantity.scale)
            if _compare(capped, quantity) < 0:
                if reason not in reductions:
                    reductions.append(reason)
                quantity = capped

        position_capacity = _positive_difference(
            _bps(equity.equity, policy.max_position_bps),
            state.current_position_notional,
        )
        apply_cap(_quantity_cap_for_notional(
            quantity, request.mark_price, position_capacity),
            RiskCheckReason.POSITION_QUANTITY_REDUCED)

        exposure_capacity = _positive_difference(
            _bps(equity.equity, policy.max_portfolio_exposure_bps),
            state.current_portfolio_exposure,
        )
        apply_cap(_quantity_cap_for_notional(
            quantity, request.mark_price, exposure_capacity),
            RiskCheckReason.EXPOSURE_QUANTITY_REDUCED)

        planned_capacity = _positive_difference(
            _bps(equity.equity, policy.max_planned_loss_bps),
            state.current_planned_loss,
        )
        if request.requested_planned_loss.units > 0:
            _, remaining_units, requested_loss_units = _aligned(
                planned_capacity, request.requested_planned_loss)
            planned_cap = ScaledInteger(
                (request.requested_quantity.units * remaining_units)
                // requested_loss_units,
                request.requested_quantity.scale,
            )
            apply_cap(planned_cap, RiskCheckReason.PLANNED_LOSS_QUANTITY_REDUCED)

        turnover_capacity = _positive_difference(
            _bps(equity.equity, policy.rolling_entry_turnover_bps),
            state.rolling_entry_turnover,
        )
        apply_cap(_quantity_cap_for_notional(
            quantity, request.mark_price, turnover_capacity),
            RiskCheckReason.TURNOVER_QUANTITY_REDUCED)
        apply_cap(request.available_depth_quantity,
                  RiskCheckReason.DEPTH_QUANTITY_REDUCED)
        apply_cap(request.exit_capacity_quantity,
                  RiskCheckReason.EXIT_CAPACITY_QUANTITY_REDUCED)

        for adjustment in request.adjustments:
            adjusted = ScaledInteger(
                (quantity.units * adjustment.basis_points) // 10_000,
                quantity.scale,
            )
            if adjusted.units < quantity.units:
                if RiskCheckReason.ADJUSTMENT_QUANTITY_REDUCED not in reductions:
                    reductions.append(RiskCheckReason.ADJUSTMENT_QUANTITY_REDUCED)
                quantity = adjusted

        if _compare(quantity, request.minimum_quantity) < 0:
            return rejected(RiskCheckReason.QUANTITY_BELOW_MINIMUM)
        reasons = tuple(reductions) if reductions else (RiskCheckReason.APPROVED,)
        return _result(requested=request.requested_quantity, final=quantity,
                       reasons=reasons, policy_ref=policy_ref,
                       context_ref=context_ref)

    @staticmethod
    def evaluate_risk_reducing_exit(
        *, policy: RiskPolicy, requested_quantity: ScaledInteger,
        position_quantity: ScaledInteger,
    ) -> RiskEvaluationResult:
        if type(policy) is not RiskPolicy:
            raise DecisionError("INVALID_RISK_POLICY")
        _amount(requested_quantity, "INVALID_REQUESTED_QUANTITY", positive=True)
        _amount(position_quantity, "INVALID_POSITION_QUANTITY")
        policy_ref = policy.reference
        context_ref = ContentRef.v2(
            "autotrade-next", "RiskReducingExitContext",
            {"policy_ref": policy_ref.to_canonical_value(),
             "requested_quantity": _amount_value(requested_quantity),
             "position_quantity": _amount_value(position_quantity),
             "turnover_exempt": True},
        )
        if position_quantity.units == 0:
            return _result(
                requested=requested_quantity,
                final=ScaledInteger(0, requested_quantity.scale),
                reasons=(RiskCheckReason.NO_POSITION,), policy_ref=policy_ref,
                context_ref=context_ref,
            )
        final = _min_quantity(requested_quantity, position_quantity,
                              requested_quantity.scale)
        reason = (RiskCheckReason.APPROVED if final == requested_quantity
                  else RiskCheckReason.EXIT_POSITION_CLAMP)
        return _result(requested=requested_quantity, final=final,
                       reasons=(reason,), policy_ref=policy_ref,
                       context_ref=context_ref)


__all__ = (
    "AdjustmentKind",
    "CanonicalEquitySnapshot",
    "EntryRiskRequest",
    "MAX_RISK_SCALE",
    "QuantityAdjustment",
    "RiskCheckReason",
    "RiskEvaluationResult",
    "RiskGovernor",
    "RiskPolicy",
    "RiskPortfolioState",
)
