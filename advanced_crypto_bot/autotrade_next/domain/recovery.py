"""Deterministic recovery checkpoint and query-before-resubmit plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from .content import ContentRef
from .execution import (
    AccountState,
    ExecutionPreparation,
    OrderSettlementState,
    OutboxMessage,
    OutboxStatus,
)
from .exit_protection import PositionProtectionState
from .simulator import OrderStatus


class RecoveryError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = self.error_code = code
        self.partial_result = None
        super().__init__(code)


def _fail(code: str) -> None:
    raise RecoveryError(code)


def _reference(value: object, code: str = "INVALID_RECOVERY_REFERENCE") -> str:
    if type(value) is not str or not value.strip():
        _fail(code)
    return value


def _utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _fail("INVALID_RECOVERY_TIME")
    return value


def _number(value) -> dict[str, int]:
    return {"units": value.units, "scale": value.scale}


class RecoveryAction(str, Enum):
    QUERY_VENUE = "QUERY_VENUE"
    FREEZE_ENTRY = "FREEZE_ENTRY"
    APPLY_CORRECTION = "APPLY_CORRECTION"
    REDELIVER_OUTBOX = "REDELIVER_OUTBOX"
    RESUME_PENDING_DISPATCH = "RESUME_PENDING_DISPATCH"
    NO_ACTION = "NO_ACTION"


class CorrectionKind(str, Enum):
    ADJUSTMENT_QUARANTINE = "ADJUSTMENT_QUARANTINE"
    EXTERNAL_FILL_IMPORT = "EXTERNAL_FILL_IMPORT"
    ORDER_STATE_CORRECTION = "ORDER_STATE_CORRECTION"
    FORCED_CLOSE_REQUEST = "FORCED_CLOSE_REQUEST"


@dataclass(frozen=True, slots=True)
class ProjectionHighWater:
    projection_name: str
    sequence: int

    def __post_init__(self) -> None:
        _reference(self.projection_name)
        if type(self.sequence) is not int or self.sequence < 0:
            _fail("INVALID_PROJECTION_HIGH_WATER")

    def to_canonical_value(self) -> dict[str, object]:
        return {"projection_name": self.projection_name, "sequence": self.sequence}


@dataclass(frozen=True, slots=True)
class VenueOrderEvidence:
    order_id: str
    status: OrderStatus
    evidence_ref: str
    observed_at_utc: datetime

    def __post_init__(self) -> None:
        _reference(self.order_id)
        _reference(self.evidence_ref)
        if type(self.status) is not OrderStatus:
            _fail("INVALID_VENUE_ORDER_STATUS")
        _utc(self.observed_at_utc)

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "status": self.status.value,
            "evidence_ref": self.evidence_ref,
            "observed_at_utc": self.observed_at_utc,
        }


@dataclass(frozen=True, slots=True)
class CorrectionRequest:
    kind: CorrectionKind
    target_id: str
    evidence_ref: str
    approval_ref: str
    expected_journal_high_water: int
    idempotency_ref: str

    def __post_init__(self) -> None:
        if type(self.kind) is not CorrectionKind:
            _fail("INVALID_CORRECTION_KIND")
        for value in (self.target_id, self.evidence_ref, self.approval_ref,
                      self.idempotency_ref):
            _reference(value)
        if (type(self.expected_journal_high_water) is not int
                or self.expected_journal_high_water < 0):
            _fail("INVALID_CORRECTION_HIGH_WATER")

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "target_id": self.target_id,
            "evidence_ref": self.evidence_ref,
            "approval_ref": self.approval_ref,
            "expected_journal_high_water": self.expected_journal_high_water,
            "idempotency_ref": self.idempotency_ref,
        }


def _account_value(account: AccountState) -> dict[str, object]:
    return {
        "account_id": account.account_id,
        "instrument_id": account.instrument_id,
        "cash_balance": _number(account.cash_balance),
        "position_quantity": _number(account.position_quantity),
        "fees_paid": _number(account.fees_paid),
        "taxes_paid": _number(account.taxes_paid),
        "processed_fill_ids": account.processed_fill_ids,
        "revision": account.revision,
    }


def _order_value(state: OrderSettlementState) -> dict[str, object]:
    return {
        "order_id": state.order.order_id.key,
        "order_ref": state.order.order_ref.key,
        "last_sequence": state.last_sequence,
        "status": None if state.status is None else state.status.value,
        "filled_quantity": _number(state.filled_quantity),
        "remaining_quantity": _number(state.remaining_quantity),
        "fill_ids": tuple(fill.fill_id for fill in state.cumulative_fills),
        "receipt_refs": tuple(event.event_ref.key for event in state.receipts),
        "entry_frozen": state.entry_frozen,
    }


def _position_value(state: PositionProtectionState) -> dict[str, object]:
    return {
        "position_id": state.position_id,
        "account_id": state.account_id,
        "instrument_id": state.instrument_id,
        "entry_price": _number(state.entry_price),
        "entered_at_utc": state.entered_at_utc,
        "last_evaluated_at_utc": state.last_evaluated_at_utc,
        "remaining_quantity": _number(state.remaining_quantity),
        "sequence": state.sequence,
        "status": state.status.value,
        "policy_state_ref": state.policy_state_ref,
        "protection": state.protection.to_canonical_value(),
        "pending_exit_key": state.pending_exit_key,
        "pending_exit_sequence": state.pending_exit_sequence,
        "pending_order_id": state.pending_order_id,
        "processed_exit_fill_ids": state.processed_exit_fill_ids,
        "dust_incident_ref": (
            None if state.dust_incident is None else state.dust_incident.incident_ref.key
        ),
    }


def _preparation_value(value: ExecutionPreparation) -> dict[str, object]:
    return {
        "intent_id": value.intent.intent_id.key,
        "intent_ref": value.intent.intent_ref.key,
        "order_id": value.order.order_id.key,
        "order_ref": value.order.order_ref.key,
        "outbox_id": value.outbox.message_id.key,
    }


def _outbox_value(value: OutboxMessage) -> dict[str, object]:
    return {
        "message_id": value.message_id.key,
        "aggregate_id": value.aggregate_id,
        "aggregate_sequence": value.aggregate_sequence,
        "event_type": value.event_type,
        "payload_ref": value.payload_ref.key,
        "created_at_utc": value.created_at_utc,
    }


@dataclass(frozen=True, slots=True)
class RecoveryCheckpoint:
    authority_scope_id: str
    journal_high_water: int
    account_snapshot: AccountState
    order_states: tuple[OrderSettlementState, ...]
    positions: tuple[PositionProtectionState, ...]
    preparations: tuple[ExecutionPreparation, ...]
    pending_command_refs: tuple[str, ...]
    inbox_ids: tuple[str, ...]
    outbox: tuple[OutboxMessage, ...]
    projection_high_waters: tuple[ProjectionHighWater, ...]
    entry_frozen: bool
    unknown_deadline_utc: datetime | None
    captured_at_utc: datetime
    checkpoint_ref: ContentRef

    def __post_init__(self) -> None:
        _reference(self.authority_scope_id)
        if type(self.journal_high_water) is not int or self.journal_high_water < 0:
            _fail("INVALID_JOURNAL_HIGH_WATER")
        if type(self.account_snapshot) is not AccountState:
            _fail("INVALID_RECOVERY_ACCOUNT")
        typed_tuples = (
            (self.order_states, OrderSettlementState, "INVALID_RECOVERY_ORDERS"),
            (self.positions, PositionProtectionState, "INVALID_RECOVERY_POSITIONS"),
            (self.preparations, ExecutionPreparation, "INVALID_RECOVERY_PREPARATIONS"),
            (self.outbox, OutboxMessage, "INVALID_RECOVERY_OUTBOX"),
            (self.projection_high_waters, ProjectionHighWater,
             "INVALID_PROJECTION_HIGH_WATER"),
        )
        for values, expected, code in typed_tuples:
            if type(values) is not tuple or any(type(value) is not expected for value in values):
                _fail(code)
        for values in (self.pending_command_refs, self.inbox_ids):
            if (type(values) is not tuple
                    or any(type(value) is not str or not value.strip() for value in values)
                    or len(set(values)) != len(values)):
                _fail("INVALID_RECOVERY_REFERENCES")
        order_ids = tuple(item.order.order_id.key for item in self.order_states)
        if len(set(order_ids)) != len(order_ids):
            _fail("DUPLICATE_RECOVERY_ORDER")
        for values, code in (
            (tuple(item.position_id for item in self.positions),
             "DUPLICATE_RECOVERY_POSITION"),
            (tuple(item.intent.intent_id.key for item in self.preparations),
             "DUPLICATE_RECOVERY_PREPARATION"),
            (tuple(item.message_id.key for item in self.outbox),
             "DUPLICATE_RECOVERY_OUTBOX"),
            (tuple(item.projection_name for item in self.projection_high_waters),
             "DUPLICATE_PROJECTION_HIGH_WATER"),
        ):
            if len(set(values)) != len(values):
                _fail(code)
        if any(item.authority_scope_id != self.authority_scope_id
               for item in self.positions):
            _fail("RECOVERY_SCOPE_MISMATCH")
        if any(item.order.authority_scope_id != self.authority_scope_id
               for item in self.order_states):
            _fail("RECOVERY_SCOPE_MISMATCH")
        if any(item.outbox.authority_scope_id != self.authority_scope_id
               for item in self.preparations):
            _fail("RECOVERY_SCOPE_MISMATCH")
        if any(item.authority_scope_id != self.authority_scope_id
               or item.status is not OutboxStatus.PENDING for item in self.outbox):
            _fail("INVALID_RECOVERY_OUTBOX")
        if any(item.sequence > self.journal_high_water
               for item in self.projection_high_waters):
            _fail("PROJECTION_AHEAD_OF_JOURNAL")
        state_by_order = {
            item.order.order_id.key: item for item in self.order_states
        }
        outbox_ids = {item.message_id.key for item in self.outbox}
        for prepared in self.preparations:
            state = state_by_order.get(prepared.order.order_id.key)
            if (state is None or state.order != prepared.order
                    or prepared.outbox.message_id.key not in outbox_ids):
                _fail("RECOVERY_PREPARATION_MISMATCH")
        known_fill_ids = {
            fill.fill_id for state in self.order_states
            for fill in state.cumulative_fills
        }
        if not known_fill_ids.issubset(set(self.account_snapshot.processed_fill_ids)):
            _fail("RECOVERY_FILL_HISTORY_MISMATCH")
        unknown_ids = tuple(
            item.order.order_id.key for item in self.order_states
            if item.status is OrderStatus.UNKNOWN
        )
        if unknown_ids and not self.entry_frozen:
            _fail("UNKNOWN_NOT_FROZEN")
        if bool(unknown_ids) != (self.unknown_deadline_utc is not None):
            _fail("INVALID_UNKNOWN_DEADLINE")
        if self.unknown_deadline_utc is not None:
            _utc(self.unknown_deadline_utc)
        _utc(self.captured_at_utc)
        if (any(state.receipts and state.receipts[-1].event_at_utc > self.captured_at_utc
                for state in self.order_states)
                or any(state.last_evaluated_at_utc > self.captured_at_utc
                       for state in self.positions)
                or any(item.created_at_utc > self.captured_at_utc for item in self.outbox)):
            _fail("RECOVERY_TIME_REGRESSION")
        if (self.unknown_deadline_utc is not None
                and self.unknown_deadline_utc <= self.captured_at_utc):
            _fail("INVALID_UNKNOWN_DEADLINE")
        if (type(self.entry_frozen) is not bool
                or type(self.checkpoint_ref) is not ContentRef
                or not self.checkpoint_ref.verify(self.binding_value())):
            _fail("RECOVERY_CHECKPOINT_REFERENCE_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "recovery-checkpoint:v2",
            "authority_scope_id": self.authority_scope_id,
            "journal_high_water": self.journal_high_water,
            "account_snapshot": _account_value(self.account_snapshot),
            "order_states": tuple(_order_value(item) for item in self.order_states),
            "positions": tuple(_position_value(item) for item in self.positions),
            "preparations": tuple(_preparation_value(item) for item in self.preparations),
            "pending_command_refs": self.pending_command_refs,
            "inbox_ids": self.inbox_ids,
            "outbox": tuple(_outbox_value(item) for item in self.outbox),
            "projection_high_waters": tuple(
                item.to_canonical_value() for item in self.projection_high_waters
            ),
            "entry_frozen": self.entry_frozen,
            "unknown_deadline_utc": self.unknown_deadline_utc,
            "captured_at_utc": self.captured_at_utc,
        }

    @classmethod
    def create(cls, **values) -> RecoveryCheckpoint:
        binding = {
            "schema_version": "recovery-checkpoint:v2",
            "authority_scope_id": values["authority_scope_id"],
            "journal_high_water": values["journal_high_water"],
            "account_snapshot": _account_value(values["account_snapshot"]),
            "order_states": tuple(_order_value(item) for item in values["order_states"]),
            "positions": tuple(_position_value(item) for item in values["positions"]),
            "preparations": tuple(
                _preparation_value(item) for item in values["preparations"]
            ),
            "pending_command_refs": values["pending_command_refs"],
            "inbox_ids": values["inbox_ids"],
            "outbox": tuple(_outbox_value(item) for item in values["outbox"]),
            "projection_high_waters": tuple(
                item.to_canonical_value() for item in values["projection_high_waters"]
            ),
            "entry_frozen": values["entry_frozen"],
            "unknown_deadline_utc": values["unknown_deadline_utc"],
            "captured_at_utc": values["captured_at_utc"],
        }
        return cls(
            **values,
            checkpoint_ref=ContentRef.v2(
                "recovery.checkpoint", "recovery-checkpoint", binding,
            ),
        )


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    checkpoint_ref: ContentRef
    actions: tuple[RecoveryAction, ...]
    query_order_ids: tuple[str, ...]
    mismatch_order_ids: tuple[str, ...]
    redispatch_order_ids: tuple[str, ...]
    redeliver_message_ids: tuple[str, ...]
    corrections: tuple[CorrectionRequest, ...]
    entry_frozen: bool
    no_strategy_evaluation: bool
    plan_ref: ContentRef

    def __post_init__(self) -> None:
        if (type(self.checkpoint_ref) is not ContentRef
                or type(self.actions) is not tuple
                or any(type(item) is not RecoveryAction for item in self.actions)
                or type(self.corrections) is not tuple
                or any(type(item) is not CorrectionRequest for item in self.corrections)
                or type(self.entry_frozen) is not bool
                or self.no_strategy_evaluation is not True
                or type(self.plan_ref) is not ContentRef
                or not self.plan_ref.verify(self.binding_value())):
            _fail("INVALID_RECOVERY_PLAN")

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "recovery-plan:v1",
            "checkpoint_ref": self.checkpoint_ref.key,
            "actions": tuple(item.value for item in self.actions),
            "query_order_ids": self.query_order_ids,
            "mismatch_order_ids": self.mismatch_order_ids,
            "redispatch_order_ids": self.redispatch_order_ids,
            "redeliver_message_ids": self.redeliver_message_ids,
            "corrections": tuple(item.to_canonical_value() for item in self.corrections),
            "entry_frozen": self.entry_frozen,
            "no_strategy_evaluation": self.no_strategy_evaluation,
        }


def plan_recovery(checkpoint: RecoveryCheckpoint, *,
                  venue_evidence: tuple[VenueOrderEvidence, ...],
                  corrections: tuple[CorrectionRequest, ...]) -> RecoveryPlan:
    if type(checkpoint) is not RecoveryCheckpoint:
        _fail("INVALID_RECOVERY_CHECKPOINT")
    if (type(venue_evidence) is not tuple
            or any(type(item) is not VenueOrderEvidence for item in venue_evidence)):
        _fail("INVALID_VENUE_EVIDENCE")
    if (type(corrections) is not tuple
            or any(type(item) is not CorrectionRequest for item in corrections)):
        _fail("INVALID_CORRECTION_REQUESTS")
    evidence_ids = tuple(item.order_id for item in venue_evidence)
    if len(set(evidence_ids)) != len(evidence_ids):
        _fail("DUPLICATE_VENUE_EVIDENCE")
    correction_ids = tuple(item.idempotency_ref for item in corrections)
    if len(set(correction_ids)) != len(correction_ids):
        _fail("DUPLICATE_CORRECTION_REQUEST")
    if any(item.expected_journal_high_water != checkpoint.journal_high_water
           for item in corrections):
        _fail("CORRECTION_HIGH_WATER_CONFLICT")

    states = {item.order.order_id.key: item for item in checkpoint.order_states}
    if any(order_id not in states for order_id in evidence_ids):
        _fail("FOREIGN_VENUE_EVIDENCE")
    query = {
        order_id for order_id, state in states.items()
        if state.status is OrderStatus.UNKNOWN
    }
    mismatch = set()
    for item in venue_evidence:
        if item.observed_at_utc < checkpoint.captured_at_utc:
            _fail("STALE_VENUE_EVIDENCE")
        local = states[item.order_id].status
        if item.status is OrderStatus.UNKNOWN:
            query.add(item.order_id)
        elif local is not item.status:
            mismatch.add(item.order_id)

    frozen = checkpoint.entry_frozen or bool(query) or bool(mismatch)
    if any(item.target_id in query for item in corrections):
        _fail("UNKNOWN_CORRECTION_FORBIDDEN")
    evidence_by_order = {item.order_id: item for item in venue_evidence}
    for correction in corrections:
        if correction.kind is CorrectionKind.ORDER_STATE_CORRECTION:
            evidence = evidence_by_order.get(correction.target_id)
            if (correction.target_id not in mismatch or evidence is None
                    or correction.evidence_ref != evidence.evidence_ref):
                _fail("UNBOUND_ORDER_STATE_CORRECTION")
    redeliver = tuple(item.message_id.key for item in checkpoint.outbox)
    # IntentPrepared redelivery is the one dispatch-resume path. Emitting a second
    # direct redispatch action here would duplicate submit after a crash boundary.
    redispatch = ()

    actions = []
    if query:
        actions.append(RecoveryAction.QUERY_VENUE)
    if frozen:
        actions.append(RecoveryAction.FREEZE_ENTRY)
    if corrections:
        actions.append(RecoveryAction.APPLY_CORRECTION)
    if redeliver:
        actions.append(RecoveryAction.REDELIVER_OUTBOX)
    if redispatch:
        actions.append(RecoveryAction.RESUME_PENDING_DISPATCH)
    if not actions:
        actions.append(RecoveryAction.NO_ACTION)
    values = {
        "schema_version": "recovery-plan:v1",
        "checkpoint_ref": checkpoint.checkpoint_ref.key,
        "actions": tuple(item.value for item in actions),
        "query_order_ids": tuple(sorted(query)),
        "mismatch_order_ids": tuple(sorted(mismatch)),
        "redispatch_order_ids": redispatch,
        "redeliver_message_ids": redeliver,
        "corrections": tuple(item.to_canonical_value() for item in corrections),
        "entry_frozen": frozen,
        "no_strategy_evaluation": True,
    }
    return RecoveryPlan(
        checkpoint.checkpoint_ref, tuple(actions), tuple(sorted(query)),
        tuple(sorted(mismatch)), redispatch, redeliver, corrections, frozen, True,
        ContentRef.v2("recovery.plan", "recovery-plan", values),
    )


RecoveryState = RecoveryCheckpoint


class LifecycleRecoveryManager:
    plan_recovery = staticmethod(plan_recovery)


__all__ = (
    "CorrectionKind", "CorrectionRequest", "LifecycleRecoveryManager",
    "ProjectionHighWater", "RecoveryAction", "RecoveryCheckpoint", "RecoveryError",
    "RecoveryPlan", "RecoveryState", "VenueOrderEvidence", "plan_recovery",
)
