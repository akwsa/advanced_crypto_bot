"""Pure unified protective EXIT state machine for Story 2.5."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum

from .content import ContentRef
from .execution import (
    ExecutionPreparation,
    ExecutionSide,
    OutboxMessage,
    OutboxStatus,
    SettlementEntry,
    prepare_execution,
)
from .identity import DeterministicIdentity, build_identity
from .numeric import ScaledInteger


MAX_EXIT_SCALE = 18


class ExitError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = self.error_code = code
        self.partial_result = None
        super().__init__(code)


def _fail(code: str) -> None:
    raise ExitError(code)


def _reference(value: object, code: str = "INVALID_EXIT_REFERENCE") -> str:
    if type(value) is not str or not value.strip():
        _fail(code)
    return value


def _optional_reference(value: object) -> str | None:
    if value is not None:
        _reference(value)
    return value


def _utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _fail("INVALID_EXIT_TIME")
    return value


def _scaled(value: object, code: str, *, positive: bool = False) -> ScaledInteger:
    if (type(value) is not ScaledInteger
            or value.scale > MAX_EXIT_SCALE
            or (value.units <= 0 if positive else value.units < 0)):
        _fail(code)
    return value


def _at_scale(value: ScaledInteger, scale: int) -> int:
    if (type(scale) is not int or scale < value.scale or scale > MAX_EXIT_SCALE
            or scale - value.scale > MAX_EXIT_SCALE):
        _fail("INVALID_EXIT_SCALE")
    return value.units * 10 ** (scale - value.scale)


def _compare(left: ScaledInteger, right: ScaledInteger) -> int:
    _scaled(left, "INVALID_EXIT_SCALE")
    _scaled(right, "INVALID_EXIT_SCALE")
    scale = max(left.scale, right.scale)
    difference = _at_scale(left, scale) - _at_scale(right, scale)
    return (difference > 0) - (difference < 0)


def _rescale_exact(value: ScaledInteger, scale: int, code: str) -> ScaledInteger:
    _scaled(value, "INVALID_EXIT_SCALE")
    if type(scale) is not int or not 0 <= scale <= MAX_EXIT_SCALE:
        _fail("INVALID_EXIT_SCALE")
    if value.scale <= scale:
        return ScaledInteger(_at_scale(value, scale), scale)
    divisor = 10 ** (value.scale - scale)
    units, remainder = divmod(value.units, divisor)
    if remainder:
        _fail(code)
    return ScaledInteger(units, scale)


def _subtract(left: ScaledInteger, right: ScaledInteger,
              code: str = "EXIT_ARITHMETIC_BREACH") -> ScaledInteger:
    scale = max(left.scale, right.scale)
    units = _at_scale(left, scale) - _at_scale(right, scale)
    if units < 0:
        _fail(code)
    return ScaledInteger(units, scale)


def _number(value: ScaledInteger) -> dict[str, int]:
    return {"units": value.units, "scale": value.scale}


class ExitReason(str, Enum):
    OPERATOR_EXIT = "OPERATOR_EXIT"
    HARD_DRAWDOWN = "HARD_DRAWDOWN"
    INVALIDATION = "INVALIDATION"
    STOP_LOSS = "STOP_LOSS"
    RECONCILIATION = "RECONCILIATION"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_EXPIRY = "TIME_EXPIRY"
    ALPHA_EXIT = "ALPHA_EXIT"
    NO_EXIT = "NO_EXIT"


class PositionProtectionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXIT_PENDING = "EXIT_PENDING"
    QUARANTINED_DUST = "QUARANTINED_DUST"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class ProtectionState:
    stop_loss_price: ScaledInteger | None
    take_profit_price: ScaledInteger | None
    trailing_high_water: ScaledInteger | None
    expiration_at_utc: datetime | None
    trailing_distance: ScaledInteger | None = None
    invalidation_ref: str | None = None

    def __post_init__(self) -> None:
        for value in (self.stop_loss_price, self.take_profit_price,
                      self.trailing_high_water, self.trailing_distance):
            if value is not None:
                _scaled(value, "INVALID_PROTECTION_VALUE", positive=True)
        if (self.trailing_distance is None) != (self.trailing_high_water is None):
            _fail("INCOMPLETE_TRAILING_PROTECTION")
        if self.expiration_at_utc is not None:
            _utc(self.expiration_at_utc)
        _optional_reference(self.invalidation_ref)
        if (self.stop_loss_price is not None and self.take_profit_price is not None
                and _compare(self.stop_loss_price, self.take_profit_price) >= 0):
            _fail("INVALID_PROTECTION_RANGE")
        if (self.trailing_high_water is not None
                and self.trailing_distance is not None
                and _compare(self.trailing_distance, self.trailing_high_water) >= 0):
            _fail("INVALID_TRAILING_DISTANCE")

    def to_canonical_value(self) -> dict[str, object]:
        def optional_number(value: ScaledInteger | None):
            return None if value is None else _number(value)
        return {
            "stop_loss_price": optional_number(self.stop_loss_price),
            "take_profit_price": optional_number(self.take_profit_price),
            "trailing_high_water": optional_number(self.trailing_high_water),
            "trailing_distance": optional_number(self.trailing_distance),
            "expiration_at_utc": self.expiration_at_utc,
            "invalidation_ref": self.invalidation_ref,
        }


@dataclass(frozen=True, slots=True)
class ExitSignals:
    operator_evidence_ref: str | None
    hard_drawdown_evidence_ref: str | None
    invalidation_evidence_ref: str | None
    reconciliation_evidence_ref: str | None
    alpha_exit_evidence_ref: str | None
    profit_target_quantity: ScaledInteger | None
    minimum_venue_quantity: ScaledInteger
    position_valuation: ScaledInteger
    valuation_evidence_ref: str

    def __post_init__(self) -> None:
        for value in (self.operator_evidence_ref,
                      self.hard_drawdown_evidence_ref,
                      self.invalidation_evidence_ref,
                      self.reconciliation_evidence_ref,
                      self.alpha_exit_evidence_ref):
            _optional_reference(value)
        if self.profit_target_quantity is not None:
            _scaled(self.profit_target_quantity, "INVALID_EXIT_TARGET", positive=True)
        _scaled(self.minimum_venue_quantity, "INVALID_MINIMUM_QUANTITY", positive=True)
        _scaled(self.position_valuation, "INVALID_DUST_VALUATION")
        _reference(self.valuation_evidence_ref)

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "operator_evidence_ref": self.operator_evidence_ref,
            "hard_drawdown_evidence_ref": self.hard_drawdown_evidence_ref,
            "invalidation_evidence_ref": self.invalidation_evidence_ref,
            "reconciliation_evidence_ref": self.reconciliation_evidence_ref,
            "alpha_exit_evidence_ref": self.alpha_exit_evidence_ref,
            "profit_target_quantity": (
                None if self.profit_target_quantity is None
                else _number(self.profit_target_quantity)
            ),
            "minimum_venue_quantity": _number(self.minimum_venue_quantity),
            "position_valuation": _number(self.position_valuation),
            "valuation_evidence_ref": self.valuation_evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class DustIncident:
    position_id: str
    remaining_quantity: ScaledInteger
    minimum_venue_quantity: ScaledInteger
    valuation: ScaledInteger
    valuation_evidence_ref: str
    triggering_fill_id: str
    recorded_at_utc: datetime
    incident_ref: ContentRef

    def __post_init__(self) -> None:
        _reference(self.position_id)
        _reference(self.triggering_fill_id)
        _scaled(self.remaining_quantity, "INVALID_DUST_QUANTITY", positive=True)
        _scaled(self.minimum_venue_quantity, "INVALID_DUST_QUANTITY", positive=True)
        _scaled(self.valuation, "INVALID_DUST_VALUATION")
        _reference(self.valuation_evidence_ref)
        _utc(self.recorded_at_utc)
        if _compare(self.remaining_quantity, self.minimum_venue_quantity) >= 0:
            _fail("INVALID_DUST_QUANTITY")
        if (type(self.incident_ref) is not ContentRef
                or self.incident_ref != ContentRef.v2(
                    "execution.dust", "dust-incident", self.binding_value(),
                )):
            _fail("DUST_INCIDENT_REFERENCE_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "dust-incident:v1",
            "position_id": self.position_id,
            "remaining_quantity": _number(self.remaining_quantity),
            "minimum_venue_quantity": _number(self.minimum_venue_quantity),
            "valuation": _number(self.valuation),
            "valuation_evidence_ref": self.valuation_evidence_ref,
            "triggering_fill_id": self.triggering_fill_id,
            "recorded_at_utc": self.recorded_at_utc,
        }

    @classmethod
    def create(cls, *, position_id: str, remaining_quantity: ScaledInteger,
               minimum_venue_quantity: ScaledInteger, valuation: ScaledInteger,
               valuation_evidence_ref: str,
               triggering_fill_id: str, recorded_at_utc: datetime) -> DustIncident:
        value = {
            "schema_version": "dust-incident:v1",
            "position_id": position_id,
            "remaining_quantity": _number(remaining_quantity),
            "minimum_venue_quantity": _number(minimum_venue_quantity),
            "valuation": _number(valuation),
            "valuation_evidence_ref": valuation_evidence_ref,
            "triggering_fill_id": triggering_fill_id,
            "recorded_at_utc": recorded_at_utc,
        }
        return cls(
            position_id, remaining_quantity, minimum_venue_quantity, valuation,
            valuation_evidence_ref,
            triggering_fill_id, recorded_at_utc,
            ContentRef.v2("execution.dust", "dust-incident", value),
        )


@dataclass(frozen=True, slots=True)
class PositionProtectionState:
    position_id: str
    authority_scope_id: str
    account_id: str
    instrument_id: str
    entry_price: ScaledInteger
    entered_at_utc: datetime
    last_evaluated_at_utc: datetime
    remaining_quantity: ScaledInteger
    sequence: int
    status: PositionProtectionStatus
    protection: ProtectionState
    policy_state_ref: str
    partial_exit: bool
    pending_exit_key: str | None
    pending_exit_sequence: int | None
    pending_order_id: str | None
    pending_reason: ExitReason | None
    pending_target_quantity: ScaledInteger | None
    processed_exit_fill_ids: tuple[str, ...]
    dust_incident: DustIncident | None

    def __post_init__(self) -> None:
        for value in (self.position_id, self.authority_scope_id, self.account_id,
                      self.instrument_id, self.policy_state_ref):
            _reference(value)
        _scaled(self.remaining_quantity, "INVALID_POSITION_QUANTITY")
        _scaled(self.entry_price, "INVALID_ENTRY_PRICE", positive=True)
        _utc(self.entered_at_utc)
        _utc(self.last_evaluated_at_utc)
        if self.last_evaluated_at_utc < self.entered_at_utc:
            _fail("INVALID_POSITION_TIME")
        if type(self.sequence) is not int or self.sequence < 0:
            _fail("INVALID_POSITION_SEQUENCE")
        if type(self.status) is not PositionProtectionStatus:
            _fail("INVALID_PROTECTION_STATUS")
        if type(self.protection) is not ProtectionState or type(self.partial_exit) is not bool:
            _fail("INVALID_PROTECTION_STATE")
        pending = (self.pending_exit_key, self.pending_exit_sequence,
                   self.pending_order_id, self.pending_reason,
                   self.pending_target_quantity)
        if self.status is PositionProtectionStatus.EXIT_PENDING:
            if (any(value is None for value in pending)
                    or type(self.pending_reason) is not ExitReason):
                _fail("INCOMPLETE_PENDING_EXIT")
            _reference(self.pending_exit_key)
            _reference(self.pending_order_id)
            if (type(self.pending_exit_sequence) is not int
                    or not 0 < self.pending_exit_sequence <= self.sequence):
                _fail("INVALID_PENDING_EXIT_SEQUENCE")
            _scaled(self.pending_target_quantity, "INVALID_EXIT_TARGET", positive=True)
            if _compare(self.pending_target_quantity, self.remaining_quantity) > 0:
                _fail("INVALID_EXIT_TARGET")
            if self.pending_reason is ExitReason.NO_EXIT:
                _fail("INVALID_PENDING_EXIT_REASON")
            expected_exit_key = build_identity("event", {
                "authority_scope_id": self.authority_scope_id,
                "aggregate_id": self.position_id,
                "aggregate_seq": self.pending_exit_sequence,
                "event_type": "ExitRequested",
                "schema_version": 1,
            }).key
            if self.pending_exit_key != expected_exit_key:
                _fail("EXIT_EVENT_ID_MISMATCH")
            intent_id = build_identity("intent", {"decision_id": self.pending_exit_key})
            expected_order_id = build_identity("client_order", {
                "authority_scope_id": self.authority_scope_id,
                "intent_id": intent_id.key,
                "order_ordinal": 0,
            }).key
            if self.pending_order_id != expected_order_id:
                _fail("EXIT_ORDER_ID_MISMATCH")
        elif any(value is not None for value in pending):
            _fail("UNEXPECTED_PENDING_EXIT")
        if self.status is PositionProtectionStatus.CLOSED:
            if self.remaining_quantity.units != 0:
                _fail("FALSE_CLOSED_POSITION")
            if not self.processed_exit_fill_ids:
                _fail("MISSING_EXIT_FILL_HISTORY")
        elif self.remaining_quantity.units <= 0:
            _fail("INVALID_POSITION_QUANTITY")
        if self.status is PositionProtectionStatus.QUARANTINED_DUST:
            if type(self.dust_incident) is not DustIncident:
                _fail("MISSING_DUST_INCIDENT")
            if (self.dust_incident.position_id != self.position_id
                    or not _compare(self.dust_incident.remaining_quantity,
                                    self.remaining_quantity) == 0):
                _fail("DUST_INCIDENT_STATE_MISMATCH")
        elif self.dust_incident is not None:
            _fail("UNEXPECTED_DUST_INCIDENT")
        if (type(self.processed_exit_fill_ids) is not tuple
                or any(type(item) is not str or not item.strip()
                       for item in self.processed_exit_fill_ids)
                or len(set(self.processed_exit_fill_ids))
                != len(self.processed_exit_fill_ids)):
            _fail("INVALID_EXIT_FILL_HISTORY")
        if self.partial_exit != bool(self.processed_exit_fill_ids):
            _fail("INVALID_PARTIAL_EXIT_STATE")


@dataclass(frozen=True, slots=True)
class ExitEvaluation:
    should_exit: bool
    reason: ExitReason
    target_quantity: ScaledInteger
    expected_sequence: int
    evaluated_at_utc: datetime
    current_price: ScaledInteger
    signals: ExitSignals
    previous_state: PositionProtectionState
    next_state: PositionProtectionState
    event_id: DeterministicIdentity | None
    event_ref: ContentRef | None
    outbox: OutboxMessage | None
    is_noop: bool

    def __post_init__(self) -> None:
        if (type(self.should_exit) is not bool or type(self.reason) is not ExitReason
                or type(self.expected_sequence) is not int
                or type(self.signals) is not ExitSignals
                or type(self.previous_state) is not PositionProtectionState
                or type(self.next_state) is not PositionProtectionState
                or type(self.is_noop) is not bool):
            _fail("INVALID_EXIT_EVALUATION")
        _scaled(self.target_quantity, "INVALID_EXIT_TARGET")
        _scaled(self.current_price, "INVALID_EXIT_PRICE", positive=True)
        _utc(self.evaluated_at_utc)
        if self.should_exit != (self.reason is not ExitReason.NO_EXIT):
            _fail("INVALID_EXIT_EVALUATION")
        if self.should_exit != (self.target_quantity.units > 0):
            _fail("INVALID_EXIT_EVALUATION")
        if (self.expected_sequence != self.previous_state.sequence
                or self.previous_state.position_id != self.next_state.position_id
                or self.previous_state.authority_scope_id
                != self.next_state.authority_scope_id
                or self.previous_state.account_id != self.next_state.account_id
                or self.previous_state.instrument_id != self.next_state.instrument_id
                or self.previous_state.remaining_quantity
                != self.next_state.remaining_quantity
                or self.previous_state.policy_state_ref != self.next_state.policy_state_ref):
            _fail("EXIT_STATE_TRANSITION_MISMATCH")
        expected_protection = _updated_high_water(
            self.previous_state.protection, self.current_price
        )
        if (self.previous_state.status is not PositionProtectionStatus.ACTIVE
                or self.next_state.protection != expected_protection
                or self.next_state.last_evaluated_at_utc != self.evaluated_at_utc
                or self.evaluated_at_utc < self.previous_state.last_evaluated_at_utc
                or _compare(self.target_quantity,
                            self.previous_state.remaining_quantity) > 0):
            _fail("EXIT_STATE_TRANSITION_MISMATCH")
        if self.should_exit:
            if self.next_state.status not in (
                    PositionProtectionStatus.EXIT_PENDING,
                    PositionProtectionStatus.QUARANTINED_DUST):
                _fail("EXIT_STATE_TRANSITION_MISMATCH")
            if (self.next_state.status is PositionProtectionStatus.EXIT_PENDING
                    and _compare(self.next_state.pending_target_quantity,
                                 self.target_quantity) != 0):
                _fail("EXIT_STATE_TRANSITION_MISMATCH")
        elif self.next_state.status is not PositionProtectionStatus.ACTIVE:
            _fail("EXIT_STATE_TRANSITION_MISMATCH")
        event_values = (self.event_id, self.event_ref, self.outbox)
        if self.is_noop:
            if (any(value is not None for value in event_values)
                    or self.previous_state != self.next_state):
                _fail("INVALID_EXIT_NOOP")
        else:
            if (type(self.event_id) is not DeterministicIdentity
                    or type(self.event_ref) is not ContentRef
                    or type(self.outbox) is not OutboxMessage
                    or self.event_ref != ContentRef.v2(
                        "execution.exit", "exit-evaluation", self.binding_value(),
                    )):
                _fail("EXIT_EVENT_REFERENCE_MISMATCH")
            event_type = (
                "DustQuarantined"
                if self.next_state.status is PositionProtectionStatus.QUARANTINED_DUST
                else "ExitRequested" if self.should_exit
                else "ProtectionAdvanced"
            )
            expected_id = build_identity("event", {
                "authority_scope_id": self.next_state.authority_scope_id,
                "aggregate_id": self.next_state.position_id,
                "aggregate_seq": self.next_state.sequence,
                "event_type": event_type,
                "schema_version": 1,
            })
            if (self.next_state.sequence != self.expected_sequence + 1
                    or self.event_id != expected_id
                    or self.outbox.message_id != expected_id
                    or self.outbox.aggregate_id != self.next_state.position_id
                    or self.outbox.aggregate_sequence != self.next_state.sequence
                    or self.outbox.event_type != event_type
                    or self.outbox.payload_ref != self.event_ref
                    or self.outbox.created_at_utc != self.evaluated_at_utc):
                _fail("EXIT_EVENT_BINDING_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "exit-evaluation:v1",
            "event_id": None if self.event_id is None else self.event_id.key,
            "position_id": self.next_state.position_id,
            "expected_sequence": self.expected_sequence,
            "result_sequence": self.next_state.sequence,
            "should_exit": self.should_exit,
            "reason": self.reason.value,
            "target_quantity": _number(self.target_quantity),
            "current_price": _number(self.current_price),
            "signals": self.signals.to_canonical_value(),
            "evaluated_at_utc": self.evaluated_at_utc,
            "policy_state_ref": self.next_state.policy_state_ref,
            "entry_price": _number(self.previous_state.entry_price),
            "entered_at_utc": self.previous_state.entered_at_utc,
            "protection_before": self.previous_state.protection.to_canonical_value(),
            "protection_after": self.next_state.protection.to_canonical_value(),
        }


def _event_values(state: PositionProtectionState, *, sequence: int,
                  event_type: str, at: datetime,
                  evaluation_fields: dict[str, object]
                  ) -> tuple[DeterministicIdentity, ContentRef, OutboxMessage]:
    identity = build_identity("event", {
        "authority_scope_id": state.authority_scope_id,
        "aggregate_id": state.position_id,
        "aggregate_seq": sequence,
        "event_type": event_type,
        "schema_version": 1,
    })
    value = {**evaluation_fields, "event_id": identity.key}
    reference = ContentRef.v2("execution.exit", "exit-evaluation", value)
    outbox_id = build_identity("event", {
        "authority_scope_id": state.authority_scope_id,
        "aggregate_id": state.position_id,
        "aggregate_seq": sequence,
        "event_type": event_type,
        "schema_version": 1,
    })
    outbox = OutboxMessage(
        outbox_id, state.authority_scope_id, state.position_id, sequence,
        event_type, reference, OutboxStatus.PENDING, at,
    )
    return identity, reference, outbox


def exit_command_ref(*, position_id: str, expected_sequence: int,
                     current_price: ScaledInteger, evaluated_at_utc: datetime,
                     signals: ExitSignals) -> ContentRef:
    _reference(position_id)
    if type(expected_sequence) is not int or expected_sequence < 0:
        _fail("INVALID_POSITION_SEQUENCE")
    _scaled(current_price, "INVALID_EXIT_PRICE", positive=True)
    _utc(evaluated_at_utc)
    if type(signals) is not ExitSignals:
        _fail("INVALID_EXIT_SIGNAL")
    value = {
        "schema_version": "evaluate-exit-command:v1",
        "position_id": position_id,
        "expected_sequence": expected_sequence,
        "current_price": _number(current_price),
        "evaluated_at_utc": evaluated_at_utc,
        "signals": signals.to_canonical_value(),
    }
    return ContentRef.v2(
        "execution.exit-command", "evaluate-exit-command", value,
    )


def _updated_high_water(protection: ProtectionState,
                        current_price: ScaledInteger) -> ProtectionState:
    if (protection.trailing_high_water is not None
            and _compare(current_price, protection.trailing_high_water) > 0):
        return replace(protection, trailing_high_water=current_price)
    return protection


def _trailing_triggered(protection: ProtectionState,
                        current_price: ScaledInteger) -> bool:
    if protection.trailing_high_water is None or protection.trailing_distance is None:
        return False
    stop = _subtract(protection.trailing_high_water, protection.trailing_distance)
    return _compare(current_price, stop) <= 0


def _select_reason(protection: ProtectionState, signals: ExitSignals,
                   current_price: ScaledInteger, at: datetime) -> ExitReason:
    if signals.operator_evidence_ref is not None:
        return ExitReason.OPERATOR_EXIT
    if signals.hard_drawdown_evidence_ref is not None:
        return ExitReason.HARD_DRAWDOWN
    if signals.invalidation_evidence_ref is not None:
        return ExitReason.INVALIDATION
    if (protection.stop_loss_price is not None
            and _compare(current_price, protection.stop_loss_price) <= 0):
        return ExitReason.STOP_LOSS
    if signals.reconciliation_evidence_ref is not None:
        return ExitReason.RECONCILIATION
    if (protection.take_profit_price is not None
            and _compare(current_price, protection.take_profit_price) >= 0):
        return ExitReason.TAKE_PROFIT
    if _trailing_triggered(protection, current_price):
        return ExitReason.TRAILING_STOP
    if protection.expiration_at_utc is not None and at >= protection.expiration_at_utc:
        return ExitReason.TIME_EXPIRY
    if signals.alpha_exit_evidence_ref is not None:
        return ExitReason.ALPHA_EXIT
    return ExitReason.NO_EXIT


def evaluate_exit(state: PositionProtectionState, *, current_price: ScaledInteger,
                  evaluated_at_utc: datetime, signals: ExitSignals) -> ExitEvaluation:
    if type(state) is not PositionProtectionState or type(signals) is not ExitSignals:
        _fail("INVALID_EXIT_INPUT")
    _scaled(current_price, "INVALID_EXIT_SCALE", positive=True)
    _utc(evaluated_at_utc)
    if state.status is not PositionProtectionStatus.ACTIVE:
        _fail("POSITION_NOT_EXITABLE")
    if evaluated_at_utc < state.last_evaluated_at_utc:
        _fail("EXIT_TIME_REGRESSION")
    updated_protection = _updated_high_water(state.protection, current_price)
    reason = _select_reason(updated_protection, signals, current_price, evaluated_at_utc)
    should_exit = reason is not ExitReason.NO_EXIT
    zero = ScaledInteger(0, state.remaining_quantity.scale)
    target = state.remaining_quantity if should_exit else zero
    if reason is ExitReason.TAKE_PROFIT and signals.profit_target_quantity is not None:
        target = _rescale_exact(
            signals.profit_target_quantity, state.remaining_quantity.scale,
            "EXIT_TARGET_PRECISION_BREACH",
        )
        if _compare(target, state.remaining_quantity) > 0:
            _fail("INVALID_EXIT_TARGET")
    changed = (should_exit or updated_protection != state.protection
               or evaluated_at_utc != state.last_evaluated_at_utc)
    if not changed:
        return ExitEvaluation(
            False, ExitReason.NO_EXIT, zero, state.sequence, evaluated_at_utc,
            current_price, signals, state, state, None, None, None, True,
        )
    sequence = state.sequence + 1
    dust = (should_exit and _compare(
        state.remaining_quantity, signals.minimum_venue_quantity
    ) < 0)
    event_type = (
        "DustQuarantined" if dust
        else "ExitRequested" if should_exit
        else "ProtectionAdvanced"
    )
    fields = {
        "schema_version": "exit-evaluation:v1",
        "event_id": None,
        "position_id": state.position_id,
        "expected_sequence": state.sequence,
        "result_sequence": sequence,
        "should_exit": should_exit,
        "reason": reason.value,
        "target_quantity": _number(target),
        "current_price": _number(current_price),
        "signals": signals.to_canonical_value(),
        "evaluated_at_utc": evaluated_at_utc,
        "policy_state_ref": state.policy_state_ref,
        "entry_price": _number(state.entry_price),
        "entered_at_utc": state.entered_at_utc,
        "protection_before": state.protection.to_canonical_value(),
        "protection_after": updated_protection.to_canonical_value(),
    }
    event_id, event_ref, outbox = _event_values(
        state, sequence=sequence, event_type=event_type, at=evaluated_at_utc,
        evaluation_fields=fields,
    )
    intent_id = build_identity("intent", {"decision_id": event_id.key})
    pending_order_id = build_identity("client_order", {
        "authority_scope_id": state.authority_scope_id,
        "intent_id": intent_id.key,
        "order_ordinal": 0,
    }).key
    incident = (
        DustIncident.create(
            position_id=state.position_id,
            remaining_quantity=state.remaining_quantity,
            minimum_venue_quantity=signals.minimum_venue_quantity,
            valuation=signals.position_valuation,
            valuation_evidence_ref=signals.valuation_evidence_ref,
            triggering_fill_id=f"zeroing-attempt:{event_id.key}",
            recorded_at_utc=evaluated_at_utc,
        )
        if dust else None
    )
    next_state = replace(
        state,
        sequence=sequence,
        last_evaluated_at_utc=evaluated_at_utc,
        status=(
            PositionProtectionStatus.QUARANTINED_DUST if dust
            else PositionProtectionStatus.EXIT_PENDING if should_exit
            else PositionProtectionStatus.ACTIVE
        ),
        protection=updated_protection,
        pending_exit_key=event_id.key if should_exit and not dust else None,
        pending_exit_sequence=sequence if should_exit and not dust else None,
        pending_order_id=pending_order_id if should_exit and not dust else None,
        pending_reason=reason if should_exit and not dust else None,
        pending_target_quantity=target if should_exit and not dust else None,
        dust_incident=incident,
    )
    return ExitEvaluation(
        should_exit, reason, target, state.sequence, evaluated_at_utc,
        current_price, signals, state, next_state, event_id, event_ref, outbox, False,
    )


def build_exit_execution(evaluation: ExitEvaluation, *,
                         created_at_utc: datetime) -> ExecutionPreparation:
    if (type(evaluation) is not ExitEvaluation or not evaluation.should_exit
            or evaluation.next_state.status is not PositionProtectionStatus.EXIT_PENDING):
        _fail("EXIT_EXECUTION_NOT_REQUIRED")
    if type(evaluation.event_id) is not DeterministicIdentity:
        _fail("MISSING_EXIT_EVENT")
    state = evaluation.next_state
    prepared = prepare_execution(
        decision_id=evaluation.event_id.key,
        authority_scope_id=state.authority_scope_id,
        account_id=state.account_id,
        instrument_id=state.instrument_id,
        side=ExecutionSide.SELL,
        requested_quantity=evaluation.target_quantity,
        order_ordinal=0,
        created_at_utc=created_at_utc,
    )
    if prepared.order.order_id.key != state.pending_order_id:
        _fail("EXIT_ORDER_ID_MISMATCH")
    return prepared


@dataclass(frozen=True, slots=True)
class ExitFillResult:
    previous_state: PositionProtectionState
    next_state: PositionProtectionState
    settlement_entry: SettlementEntry
    incident: DustIncident | None

    def __post_init__(self) -> None:
        if (type(self.previous_state) is not PositionProtectionState
                or type(self.next_state) is not PositionProtectionState
                or type(self.settlement_entry) is not SettlementEntry
                or (self.incident is not None and type(self.incident) is not DustIncident)):
            _fail("INVALID_EXIT_FILL_RESULT")
        if (self.previous_state.status is not PositionProtectionStatus.EXIT_PENDING
                or self.next_state.sequence != self.previous_state.sequence + 1
                or self.next_state.position_id != self.previous_state.position_id
                or self.next_state.authority_scope_id
                != self.previous_state.authority_scope_id
                or self.next_state.account_id != self.previous_state.account_id
                or self.next_state.instrument_id != self.previous_state.instrument_id
                or self.settlement_entry.fill_id
                not in self.next_state.processed_exit_fill_ids
                or self.next_state.dust_incident != self.incident):
            _fail("EXIT_FILL_RESULT_MISMATCH")
        expected_protection = self.previous_state.protection
        if (self.previous_state.pending_reason is ExitReason.TAKE_PROFIT
                and self.next_state.status is PositionProtectionStatus.ACTIVE):
            expected_protection = replace(
                expected_protection, take_profit_price=None,
            )
        if self.next_state.protection != expected_protection:
            _fail("EXIT_FILL_RESULT_MISMATCH")


def apply_exit_fill(state: PositionProtectionState, entry: SettlementEntry, *,
                    minimum_venue_quantity: ScaledInteger,
                    valuation: ScaledInteger,
                    valuation_evidence_ref: str,
                    recorded_at_utc: datetime) -> ExitFillResult:
    if (type(state) is not PositionProtectionState
            or state.status is not PositionProtectionStatus.EXIT_PENDING):
        _fail("POSITION_NOT_EXITABLE")
    if type(entry) is not SettlementEntry or entry.side is not ExecutionSide.SELL:
        _fail("INVALID_EXIT_FILL")
    if (entry.authority_scope_id != state.authority_scope_id
            or entry.account_id != state.account_id
            or entry.instrument_id != state.instrument_id
            or entry.order_id != state.pending_order_id):
        _fail("FOREIGN_EXIT_FILL")
    if entry.fill_id in state.processed_exit_fill_ids:
        _fail("DUPLICATE_EXIT_FILL")
    _scaled(minimum_venue_quantity, "INVALID_MINIMUM_QUANTITY", positive=True)
    _scaled(valuation, "INVALID_DUST_VALUATION")
    _reference(valuation_evidence_ref)
    _utc(recorded_at_utc)
    if recorded_at_utc < state.last_evaluated_at_utc:
        _fail("EXIT_FILL_TIME_REGRESSION")
    if recorded_at_utc != entry.recorded_at_utc:
        _fail("EXIT_FILL_TIME_MISMATCH")
    if (entry.quantity_delta.units >= 0
            or _compare(
                ScaledInteger(-entry.quantity_delta.units, entry.quantity_delta.scale),
                entry.quantity,
            ) != 0):
        _fail("EXIT_FILL_QUANTITY_MISMATCH")
    quantity = _rescale_exact(
        entry.quantity, state.remaining_quantity.scale,
        "EXIT_FILL_PRECISION_BREACH",
    )
    if state.pending_target_quantity is None:
        _fail("INCOMPLETE_PENDING_EXIT")
    pending = _rescale_exact(
        state.pending_target_quantity, state.remaining_quantity.scale,
        "EXIT_TARGET_PRECISION_BREACH",
    )
    if _compare(quantity, state.remaining_quantity) > 0 or _compare(quantity, pending) > 0:
        _fail("EXIT_FILL_OVERFLOW")
    remaining = _subtract(state.remaining_quantity, quantity)
    pending_remaining = _subtract(pending, quantity)
    incident = None
    if remaining.units == 0:
        status = PositionProtectionStatus.CLOSED
    elif _compare(remaining, minimum_venue_quantity) < 0:
        status = PositionProtectionStatus.QUARANTINED_DUST
        incident = DustIncident.create(
            position_id=state.position_id,
            remaining_quantity=remaining,
            minimum_venue_quantity=minimum_venue_quantity,
            valuation=valuation,
            valuation_evidence_ref=valuation_evidence_ref,
            triggering_fill_id=entry.fill_id,
            recorded_at_utc=recorded_at_utc,
        )
    elif pending_remaining.units > 0:
        status = PositionProtectionStatus.EXIT_PENDING
    else:
        status = PositionProtectionStatus.ACTIVE
    keep_pending = status is PositionProtectionStatus.EXIT_PENDING
    next_protection = state.protection
    if (state.pending_reason is ExitReason.TAKE_PROFIT
            and status is PositionProtectionStatus.ACTIVE):
        next_protection = replace(next_protection, take_profit_price=None)
    next_state = replace(
        state,
        remaining_quantity=remaining,
        sequence=state.sequence + 1,
        last_evaluated_at_utc=recorded_at_utc,
        status=status,
        protection=next_protection,
        partial_exit=True,
        pending_exit_key=state.pending_exit_key if keep_pending else None,
        pending_exit_sequence=state.pending_exit_sequence if keep_pending else None,
        pending_order_id=state.pending_order_id if keep_pending else None,
        pending_reason=state.pending_reason if keep_pending else None,
        pending_target_quantity=pending_remaining if keep_pending else None,
        processed_exit_fill_ids=(*state.processed_exit_fill_ids, entry.fill_id),
        dust_incident=incident,
    )
    return ExitFillResult(state, next_state, entry, incident)


ExitDecision = ExitEvaluation


class ExitEvaluator:
    evaluate = staticmethod(evaluate_exit)


__all__ = (
    "DustIncident", "ExitDecision", "ExitError", "ExitEvaluation", "ExitEvaluator",
    "ExitFillResult", "ExitReason", "ExitSignals", "PositionProtectionState",
    "PositionProtectionStatus", "ProtectionState", "apply_exit_fill",
    "build_exit_execution", "evaluate_exit", "exit_command_ref",
)
