"""Pure Candidate-to-Decision provenance projection and read queries."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import json

from autotrade_next.domain.candidate import CandidateSnapshot
from autotrade_next.domain.decision import (
    DecisionAction, DecisionBoundary, DecisionReason, PositionContext,
)
from autotrade_next.domain.encoding import canonical_bytes
from autotrade_next.domain.policy import (
    CalibrationEvidence,
    GrossReturnEvidence,
    PolicyState,
    PolicyTransition,
    ShortfallEvidence,
)
from autotrade_next.domain.numeric import ScaledInteger


_EVENT_VERSION = "decision-projection-event:v1"
_VIEW_VERSION = "decision-provenance-view:v1"
_STATE_VERSION = "decision-projection-state:v1"
_PAGE_VERSION = "decision-provenance-page:v1"
_CURSOR_VERSION = "decision-provenance-cursor:v1"
_MAX_PAGE_SIZE = 100


class ProjectionError(ValueError):
    """Fail a projection operation atomically with a stable error code."""

    def __init__(self, code: str, *, path: tuple[str | int, ...] = ()) -> None:
        self.code = self.error_code = code
        self.path = path
        self.partial_state = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = None
        self.correlation_id = None
        super().__init__(code)


def _fail(code: str, path: tuple[str | int, ...] = ()) -> None:
    raise ProjectionError(code, path=path)


def _ref(value: object, path: tuple[str | int, ...]) -> str:
    if type(value) is not str or not value or not value.strip():
        _fail("INVALID_PROJECTION_REFERENCE", path)
    canonical_bytes(value)
    return value


def _refs(value: object, path: tuple[str | int, ...]) -> tuple[str, ...]:
    if type(value) not in (tuple, list):
        _fail("INVALID_PROJECTION_VALUE", path)
    frozen = tuple(value)
    for index, item in enumerate(frozen):
        _ref(item, (*path, index))
    if len(frozen) != len(set(frozen)):
        _fail("DUPLICATE_PROJECTION_REFERENCE", path)
    return frozen


def _hash(kind: str, value: object) -> str:
    return f"{kind}:v1:{sha256(canonical_bytes(value)).hexdigest()}"


def _utc(value: object, path: tuple[str | int, ...]) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        _fail("INVALID_PROJECTION_TIMESTAMP", path)
    return value


class ProjectionEventType(str, Enum):
    CANDIDATE_COMMITTED = "CANDIDATE_COMMITTED"
    DECISION_COMMITTED = "DECISION_COMMITTED"


@dataclass(frozen=True, slots=True)
class CandidateProjectionPayload:
    candidate: CandidateSnapshot

    def __post_init__(self) -> None:
        if type(self.candidate) is not CandidateSnapshot:
            _fail("INVALID_PROJECTION_PAYLOAD", ("payload", "candidate"))

    def to_canonical_value(self) -> dict[str, object]:
        return {"payload_version": "candidate-projection-payload:v1", "candidate": self.candidate.to_canonical_value()}


@dataclass(frozen=True, slots=True)
class DecisionProjectionPayload:
    transition: PolicyTransition
    gross: GrossReturnEvidence | None
    shortfall: ShortfallEvidence | None
    calibration: CalibrationEvidence | None

    def __post_init__(self) -> None:
        if type(self.transition) is not PolicyTransition:
            _fail("INVALID_PROJECTION_PAYLOAD", ("payload", "transition"))
        for name, expected in (
            ("gross", GrossReturnEvidence),
            ("shortfall", ShortfallEvidence),
            ("calibration", CalibrationEvidence),
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not expected:
                _fail("INVALID_PROJECTION_PAYLOAD", ("payload", name))
            if value is not None:
                if value.policy_version != self.transition.decision.policy_version:
                    _fail("PROJECTION_POLICY_VERSION_MISMATCH", ("payload", name, "policy_version"))
                if value.boundary_version != self.transition.decision.boundary.version:
                    _fail("PROJECTION_BOUNDARY_MISMATCH", ("payload", name, "boundary_version"))
        evidence_presence = tuple(
            getattr(self, name) is not None for name in ("gross", "shortfall", "calibration")
        )
        if any(evidence_presence) and not all(evidence_presence):
            _fail("INCOMPLETE_PROJECTION_COST_EVIDENCE", ("payload",))
        if self.transition.conservative_edge is not None and any(
            getattr(self, name) is None for name in ("gross", "shortfall", "calibration")
        ):
            _fail("MISSING_PROJECTION_COST_EVIDENCE", ("payload",))
        if self.calibration is not None and self.calibration.horizon_id != self.transition.prior_state.horizon_id:
            _fail("PROJECTION_CALIBRATION_HORIZON_MISMATCH", ("payload", "calibration", "horizon_id"))
        if self.gross is not None and self.shortfall is not None:
            if self.gross.requested_size != self.shortfall.requested_size:
                _fail("PROJECTION_REQUESTED_SIZE_MISMATCH", ("payload", "shortfall", "requested_size"))
            scales = {
                self.gross.lower_bound.scale, self.gross.requested_size.scale,
                self.shortfall.upper_bound.scale, self.shortfall.requested_size.scale,
                self.transition.prior_state.required_margin.scale,
            }
            if len(scales) != 1:
                _fail("PROJECTION_EVIDENCE_SCALE_MISMATCH", ("payload", "evidence"))
            edge = ScaledInteger(
                self.gross.lower_bound.units - self.shortfall.upper_bound.units,
                self.gross.lower_bound.scale,
            )
            if edge != self.transition.conservative_edge:
                _fail("PROJECTION_CONSERVATIVE_EDGE_MISMATCH", ("payload", "transition", "conservative_edge"))
        supplied_refs = set(_payload_cost_refs(self))
        if not supplied_refs.issubset(self.transition.decision.reason.evidence_refs):
            _fail("PROJECTION_EVIDENCE_LINK_MISMATCH", ("payload", "evidence"))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "payload_version": "decision-projection-payload:v1",
            "transition": self.transition.to_canonical_value(),
            "gross": None if self.gross is None else self.gross.to_canonical_value(),
            "shortfall": None if self.shortfall is None else self.shortfall.to_canonical_value(),
            "calibration": None if self.calibration is None else self.calibration.to_canonical_value(),
        }


ProjectionPayload = CandidateProjectionPayload | DecisionProjectionPayload


def projection_payload_hash(payload: ProjectionPayload) -> str:
    if type(payload) not in (CandidateProjectionPayload, DecisionProjectionPayload):
        _fail("INVALID_PROJECTION_PAYLOAD", ("payload",))
    return _hash("projection-payload", payload.to_canonical_value())


def projection_event_id(**values: object) -> str:
    payload = values.get("payload")
    event_type = values.get("event_type")
    projected = {
        "domain": "autotrade-next.decision-projection-event",
        "version": values.get("version"),
        "event_type": event_type.value if type(event_type) is ProjectionEventType else event_type,
        "authority_scope_id": values.get("authority_scope_id"),
        "journal_seq": values.get("journal_seq"),
        "aggregate_id": values.get("aggregate_id"),
        "aggregate_seq": values.get("aggregate_seq"),
        "correlation_id": values.get("correlation_id"),
        "causation_id": values.get("causation_id"),
        "payload_hash": values.get("payload_hash"),
        "outbox_ref": values.get("outbox_ref"),
        "event_at_utc": values.get("event_at_utc"),
        "recorded_at_utc": values.get("recorded_at_utc"),
        "payload_type": type(payload).__name__,
    }
    return _hash("projection-event", projected)


def projection_outbox_ref(**values: object) -> str:
    event_type = values.get("event_type")
    projected = {
        "domain": "autotrade-next.trusted-outbox-reference",
        "version": 1,
        "event_type": event_type.value if type(event_type) is ProjectionEventType else event_type,
        "authority_scope_id": values.get("authority_scope_id"),
        "journal_seq": values.get("journal_seq"),
        "aggregate_id": values.get("aggregate_id"),
        "aggregate_seq": values.get("aggregate_seq"),
        "correlation_id": values.get("correlation_id"),
        "causation_id": values.get("causation_id"),
        "event_at_utc": values.get("event_at_utc"),
        "recorded_at_utc": values.get("recorded_at_utc"),
        "payload_hash": values.get("payload_hash"),
    }
    return _hash("trusted-outbox", projected)


@dataclass(frozen=True, slots=True)
class ProjectionEvent:
    version: str
    event_id: str
    event_type: ProjectionEventType
    authority_scope_id: str
    journal_seq: int
    aggregate_id: str
    aggregate_seq: int
    correlation_id: str
    causation_id: str
    event_at_utc: datetime
    recorded_at_utc: datetime
    payload_hash: str
    outbox_ref: str
    payload: ProjectionPayload

    def __post_init__(self) -> None:
        if self.version != _EVENT_VERSION:
            _fail("UNSUPPORTED_PROJECTION_EVENT_VERSION", ("event", "version"))
        if type(self.event_type) is not ProjectionEventType:
            _fail("INVALID_PROJECTION_EVENT", ("event", "event_type"))
        for name in (
            "event_id", "authority_scope_id", "aggregate_id", "correlation_id",
            "causation_id", "payload_hash", "outbox_ref",
        ):
            _ref(getattr(self, name), ("event", name))
        _utc(self.event_at_utc, ("event", "event_at_utc"))
        _utc(self.recorded_at_utc, ("event", "recorded_at_utc"))
        if self.recorded_at_utc < self.event_at_utc:
            _fail("PROJECTION_TIMESTAMP_ORDER_MISMATCH", ("event", "recorded_at_utc"))
        if type(self.journal_seq) is not int or self.journal_seq <= 0:
            _fail("INVALID_PROJECTION_SEQUENCE", ("event", "journal_seq"))
        if type(self.aggregate_seq) is not int or self.aggregate_seq <= 0:
            _fail("INVALID_PROJECTION_SEQUENCE", ("event", "aggregate_seq"))
        expected_type = (
            CandidateProjectionPayload
            if self.event_type is ProjectionEventType.CANDIDATE_COMMITTED
            else DecisionProjectionPayload
        )
        if type(self.payload) is not expected_type:
            _fail("PROJECTION_EVENT_TYPE_MISMATCH", ("event", "payload"))
        if self.payload_hash != projection_payload_hash(self.payload):
            _fail("PROJECTION_PAYLOAD_HASH_MISMATCH", ("event", "payload_hash"))
        if self.outbox_ref != projection_outbox_ref(**self._identity_values()):
            _fail("PROJECTION_OUTBOX_REFERENCE_MISMATCH", ("event", "outbox_ref"))
        if self.event_id != projection_event_id(**self._identity_values()):
            _fail("PROJECTION_EVENT_ID_MISMATCH", ("event", "event_id"))
        candidate = (
            self.payload.candidate
            if type(self.payload) is CandidateProjectionPayload
            else None
        )
        if candidate is not None:
            if self.aggregate_id != candidate.candidate_id.key:
                _fail("PROJECTION_AGGREGATE_MISMATCH", ("event", "aggregate_id"))
            if self.authority_scope_id != candidate.provenance.authority_scope_id:
                _fail("PROJECTION_SCOPE_MISMATCH", ("event", "authority_scope_id"))
            if self.correlation_id != candidate.provenance.correlation_id:
                _fail("PROJECTION_CORRELATION_MISMATCH", ("event", "correlation_id"))
            if self.causation_id != candidate.provenance.causation_id:
                _fail("PROJECTION_CAUSATION_MISMATCH", ("event", "causation_id"))
            if self.event_at_utc != candidate.provenance.event_at_utc:
                _fail("PROJECTION_TIMESTAMP_MISMATCH", ("event", "event_at_utc"))
            if self.recorded_at_utc != candidate.provenance.received_at_utc:
                _fail("PROJECTION_TIMESTAMP_MISMATCH", ("event", "recorded_at_utc"))
        else:
            decision = self.payload.transition.decision
            if self.aggregate_id != decision.decision_id.key:
                _fail("PROJECTION_AGGREGATE_MISMATCH", ("event", "aggregate_id"))
            if self.correlation_id != decision.correlation_id:
                _fail("PROJECTION_CORRELATION_MISMATCH", ("event", "correlation_id"))
            if self.causation_id != decision.causation_id:
                _fail("PROJECTION_CAUSATION_MISMATCH", ("event", "causation_id"))

    def _identity_values(self) -> dict[str, object]:
        return {
            "version": self.version, "event_type": self.event_type,
            "authority_scope_id": self.authority_scope_id,
            "journal_seq": self.journal_seq, "aggregate_id": self.aggregate_id,
            "aggregate_seq": self.aggregate_seq, "correlation_id": self.correlation_id,
            "causation_id": self.causation_id, "payload_hash": self.payload_hash,
            "event_at_utc": self.event_at_utc, "recorded_at_utc": self.recorded_at_utc,
            "outbox_ref": self.outbox_ref,
            "payload": self.payload,
        }

    @property
    def fingerprint(self) -> str:
        return _hash("projection-delivery", self.to_canonical_value())

    @property
    def aggregate_key(self) -> tuple[str, str, int]:
        return self.event_type.value, self.aggregate_id, self.aggregate_seq

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": self.version, "event_id": self.event_id,
            "event_type": self.event_type.value,
            "authority_scope_id": self.authority_scope_id,
            "journal_seq": self.journal_seq, "aggregate_id": self.aggregate_id,
            "aggregate_seq": self.aggregate_seq, "correlation_id": self.correlation_id,
            "causation_id": self.causation_id, "payload_hash": self.payload_hash,
            "event_at_utc": self.event_at_utc, "recorded_at_utc": self.recorded_at_utc,
            "outbox_ref": self.outbox_ref,
            "payload": self.payload.to_canonical_value(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class DecisionProvenanceView:
    version: str
    authority_scope_id: str
    candidate_id: str
    decision_id: str
    candidate_snapshot_ref: str
    instrument_id: str
    horizon_id: str
    action: DecisionAction
    reason: object
    boundary: object
    conservative_edge: object
    reason_evidence_refs: tuple[str, ...]
    gross_evidence_ref: str | None
    shortfall_evidence_ref: str | None
    shortfall_component_refs: tuple[str, ...]
    calibration_evidence_ref: str | None
    policy_version: str
    previous_policy_state: PolicyState
    next_policy_state: PolicyState
    position: object
    correlation_id: str
    causation_id: str
    candidate_event_at_utc: datetime
    candidate_recorded_at_utc: datetime
    decision_event_at_utc: datetime
    decision_recorded_at_utc: datetime
    projection_high_water: int

    def __post_init__(self) -> None:
        if (
            self.version != _VIEW_VERSION
            or type(self.action) is not DecisionAction
            or type(self.reason) is not DecisionReason
            or type(self.boundary) is not DecisionBoundary
            or (
                self.conservative_edge is not None
                and type(self.conservative_edge) is not ScaledInteger
            )
            or type(self.previous_policy_state) is not PolicyState
            or type(self.next_policy_state) is not PolicyState
            or type(self.position) is not PositionContext
            or type(self.projection_high_water) is not int
            or self.projection_high_water <= 0
        ):
            _fail("INVALID_PROVENANCE_VIEW", ("view",))
        for name in (
            "authority_scope_id", "candidate_id", "decision_id", "candidate_snapshot_ref",
            "instrument_id", "horizon_id", "policy_version", "correlation_id", "causation_id",
        ):
            _ref(getattr(self, name), ("view", name))
        object.__setattr__(
            self, "reason_evidence_refs",
            _refs(self.reason_evidence_refs, ("view", "reason_evidence_refs")),
        )
        object.__setattr__(
            self, "shortfall_component_refs",
            _refs(self.shortfall_component_refs, ("view", "shortfall_component_refs")),
        )
        for name in ("gross_evidence_ref", "shortfall_evidence_ref", "calibration_evidence_ref"):
            value = getattr(self, name)
            if value is not None:
                _ref(value, ("view", name))
        for name in (
            "candidate_event_at_utc", "candidate_recorded_at_utc",
            "decision_event_at_utc", "decision_recorded_at_utc",
        ):
            _utc(getattr(self, name), ("view", name))
        canonical_bytes(self.to_canonical_value())

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": self.version,
            "authority_scope_id": self.authority_scope_id,
            "candidate_id": self.candidate_id, "decision_id": self.decision_id,
            "candidate_snapshot_ref": self.candidate_snapshot_ref,
            "instrument_id": self.instrument_id, "horizon_id": self.horizon_id,
            "action": self.action.value,
            "reason": self.reason.to_canonical_value(),
            "boundary": self.boundary.to_canonical_value(),
            "conservative_edge": self.conservative_edge,
            "reason_evidence_refs": self.reason_evidence_refs,
            "gross_evidence_ref": self.gross_evidence_ref,
            "shortfall_evidence_ref": self.shortfall_evidence_ref,
            "shortfall_component_refs": self.shortfall_component_refs,
            "calibration_evidence_ref": self.calibration_evidence_ref,
            "policy_version": self.policy_version,
            "previous_policy_state": self.previous_policy_state.to_canonical_value(),
            "next_policy_state": self.next_policy_state.to_canonical_value(),
            "position": self.position.to_canonical_value(),
            "correlation_id": self.correlation_id, "causation_id": self.causation_id,
            "candidate_event_at_utc": self.candidate_event_at_utc,
            "candidate_recorded_at_utc": self.candidate_recorded_at_utc,
            "decision_event_at_utc": self.decision_event_at_utc,
            "decision_recorded_at_utc": self.decision_recorded_at_utc,
            "projection_high_water": self.projection_high_water,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class ProjectionState:
    version: str
    authority_scope_id: str
    high_water: int
    applied_fingerprints: tuple[tuple[str, str], ...]
    aggregate_fingerprints: tuple[tuple[tuple[str, str, int], str], ...]
    pending_events: tuple[ProjectionEvent, ...]
    candidates: tuple[ProjectionEvent, ...]
    decisions: tuple[ProjectionEvent, ...]
    views: tuple[DecisionProvenanceView, ...]

    @classmethod
    def empty(cls, authority_scope_id: str) -> ProjectionState:
        _ref(authority_scope_id, ("state", "authority_scope_id"))
        return cls(_STATE_VERSION, authority_scope_id, 0, (), (), (), (), (), ())

    def __post_init__(self) -> None:
        if self.version != _STATE_VERSION or type(self.high_water) is not int or self.high_water < 0:
            _fail("INVALID_PROJECTION_STATE", ("state",))
        _ref(self.authority_scope_id, ("state", "authority_scope_id"))
        for name in (
            "applied_fingerprints", "aggregate_fingerprints", "pending_events",
            "candidates", "decisions", "views",
        ):
            if type(getattr(self, name)) is not tuple:
                _fail("INVALID_PROJECTION_STATE", ("state", name))
        if any(type(item) is not ProjectionEvent for item in self.pending_events):
            _fail("INVALID_PROJECTION_STATE", ("state", "pending_events"))
        if any(
            item.authority_scope_id != self.authority_scope_id
            or item.journal_seq <= self.high_water
            for item in self.pending_events
        ):
            _fail("INVALID_PROJECTION_STATE", ("state", "pending_events"))
        if any(
            type(item) is not ProjectionEvent
            or item.event_type is not ProjectionEventType.CANDIDATE_COMMITTED
            for item in self.candidates
        ):
            _fail("INVALID_PROJECTION_STATE", ("state", "candidates"))
        if any(
            type(item) is not ProjectionEvent
            or item.event_type is not ProjectionEventType.DECISION_COMMITTED
            for item in self.decisions
        ):
            _fail("INVALID_PROJECTION_STATE", ("state", "decisions"))
        if any(type(item) is not DecisionProvenanceView for item in self.views):
            _fail("INVALID_PROJECTION_STATE", ("state", "views"))
        if tuple(sorted(self.pending_events, key=lambda item: item.journal_seq)) != self.pending_events:
            _fail("INVALID_PROJECTION_STATE", ("state", "pending_events"))
        if len({item.journal_seq for item in self.pending_events}) != len(self.pending_events):
            _fail("INVALID_PROJECTION_STATE", ("state", "pending_events"))
        if len({item.event_id for item in self.pending_events}) != len(self.pending_events):
            _fail("INVALID_PROJECTION_STATE", ("state", "pending_events"))
        if tuple(sorted(self.applied_fingerprints)) != self.applied_fingerprints:
            _fail("INVALID_PROJECTION_STATE", ("state", "applied_fingerprints"))
        if tuple(sorted(self.aggregate_fingerprints)) != self.aggregate_fingerprints:
            _fail("INVALID_PROJECTION_STATE", ("state", "aggregate_fingerprints"))
        try:
            applied = dict(self.applied_fingerprints)
            aggregates = dict(self.aggregate_fingerprints)
        except (TypeError, ValueError) as error:
            raise ProjectionError("INVALID_PROJECTION_STATE", path=("state", "indexes")) from error
        if len(applied) != len(self.applied_fingerprints) or len(aggregates) != len(self.aggregate_fingerprints):
            _fail("INVALID_PROJECTION_STATE", ("state", "indexes"))
        if len(applied) != self.high_water or len(aggregates) != self.high_water:
            _fail("INVALID_PROJECTION_STATE", ("state", "high_water"))
        if any(type(key) is not str or type(value) is not str for key, value in self.applied_fingerprints):
            _fail("INVALID_PROJECTION_STATE", ("state", "applied_fingerprints"))
        if any(
            type(key) is not tuple or len(key) != 3
            or type(key[0]) is not str or type(key[1]) is not str or type(key[2]) is not int
            or type(value) is not str
            for key, value in self.aggregate_fingerprints
        ):
            _fail("INVALID_PROJECTION_STATE", ("state", "aggregate_fingerprints"))
        if len({item.aggregate_id for item in self.candidates}) != len(self.candidates):
            _fail("INVALID_PROJECTION_STATE", ("state", "candidates"))
        if len({item.aggregate_id for item in self.decisions}) != len(self.decisions):
            _fail("INVALID_PROJECTION_STATE", ("state", "decisions"))
        if len({item.decision_id for item in self.views}) != len(self.views):
            _fail("INVALID_PROJECTION_STATE", ("state", "views"))
        if any(item.authority_scope_id != self.authority_scope_id for item in (*self.candidates, *self.decisions)):
            _fail("INVALID_PROJECTION_STATE", ("state", "scope"))
        if any(item.authority_scope_id != self.authority_scope_id for item in self.views):
            _fail("INVALID_PROJECTION_STATE", ("state", "views"))
        if tuple(sorted(self.candidates, key=lambda item: item.aggregate_id)) != self.candidates:
            _fail("INVALID_PROJECTION_STATE", ("state", "candidates"))
        if tuple(sorted(self.decisions, key=lambda item: item.aggregate_id)) != self.decisions:
            _fail("INVALID_PROJECTION_STATE", ("state", "decisions"))
        if tuple(sorted(self.views, key=lambda item: item.decision_id)) != self.views:
            _fail("INVALID_PROJECTION_STATE", ("state", "views"))
        for item in (*self.candidates, *self.decisions):
            if item.journal_seq > self.high_water or applied.get(item.event_id) != item.fingerprint:
                _fail("INVALID_PROJECTION_STATE", ("state", "applied_fingerprints"))
        candidate_ids = {item.aggregate_id for item in self.candidates}
        decision_by_id = {item.aggregate_id: item for item in self.decisions}
        for view in self.views:
            decision_event = decision_by_id.get(view.decision_id)
            if (
                view.candidate_id not in candidate_ids
                or decision_event is None
                or decision_event.payload.transition.decision.candidate_id.key != view.candidate_id
                or view.projection_high_water > self.high_water
            ):
                _fail("INVALID_PROJECTION_STATE", ("state", "views"))
        if len({(item.candidate_id, item.policy_version) for item in self.views}) != len(self.views):
            _fail("INVALID_PROJECTION_STATE", ("state", "views"))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": self.version, "authority_scope_id": self.authority_scope_id,
            "high_water": self.high_water,
            "applied_fingerprints": self.applied_fingerprints,
            "aggregate_fingerprints": self.aggregate_fingerprints,
            "pending_events": tuple(item.to_canonical_value() for item in self.pending_events),
            "candidates": tuple(item.to_canonical_value() for item in self.candidates),
            "decisions": tuple(item.to_canonical_value() for item in self.decisions),
            "views": tuple(item.to_canonical_value() for item in self.views),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class ProjectionConsumeResult:
    state: ProjectionState
    duplicate: bool
    applied_count: int


def consume_projection_event(state: ProjectionState, event: ProjectionEvent) -> ProjectionConsumeResult:
    if type(state) is not ProjectionState or type(event) is not ProjectionEvent:
        _fail("INVALID_PROJECTION_INPUT")
    if state.authority_scope_id != event.authority_scope_id:
        _fail("PROJECTION_SCOPE_MISMATCH", ("event", "authority_scope_id"))
    _validate_entity_immutability(state, event)
    applied = dict(state.applied_fingerprints)
    if event.event_id in applied:
        if applied[event.event_id] != event.fingerprint:
            _fail("PROJECTION_EVENT_CONFLICT", ("event", "event_id"))
        return ProjectionConsumeResult(state, True, 0)
    for pending in state.pending_events:
        if pending.event_id == event.event_id:
            if pending.fingerprint != event.fingerprint:
                _fail("PROJECTION_EVENT_CONFLICT", ("event", "event_id"))
            return ProjectionConsumeResult(state, True, 0)
        if pending.journal_seq == event.journal_seq:
            _fail("PROJECTION_JOURNAL_SEQUENCE_CONFLICT", ("event", "journal_seq"))
        if pending.aggregate_key == event.aggregate_key and pending.fingerprint != event.fingerprint:
            _fail("PROJECTION_AGGREGATE_SEQUENCE_CONFLICT", ("event", "aggregate_seq"))
    aggregate = dict(state.aggregate_fingerprints)
    if event.aggregate_key in aggregate and aggregate[event.aggregate_key] != event.fingerprint:
        _fail("PROJECTION_AGGREGATE_SEQUENCE_CONFLICT", ("event", "aggregate_seq"))
    if event.journal_seq <= state.high_water:
        _fail("PROJECTION_STALE_UNSEEN_EVENT", ("event", "journal_seq"))
    pending = tuple(sorted((*state.pending_events, event), key=lambda item: item.journal_seq))
    current = replace(state, pending_events=pending)
    count = 0
    while current.pending_events and current.pending_events[0].journal_seq == current.high_water + 1:
        _validate_aggregate_continuity(current, current.pending_events[0])
        if not _link_is_available(current, current.pending_events[0]):
            break
        current = _apply_contiguous(current, current.pending_events[0])
        count += 1
    return ProjectionConsumeResult(current, False, count)


def _apply_contiguous(state: ProjectionState, event: ProjectionEvent) -> ProjectionState:
    candidates = {item.aggregate_id: item for item in state.candidates}
    decisions = {item.aggregate_id: item for item in state.decisions}
    if type(event.payload) is CandidateProjectionPayload:
        candidates[event.payload.candidate.candidate_id.key] = event
    else:
        decisions[event.payload.transition.decision.decision_id.key] = event
    views = {item.decision_id: item for item in state.views}
    for decision_event in decisions.values():
        payload = decision_event.payload
        decision = payload.transition.decision
        if decision.decision_id.key in views:
            continue
        candidate_event = candidates.get(decision.candidate_id.key)
        if candidate_event is None:
            continue
        candidate = candidate_event.payload.candidate
        _validate_link(candidate, payload, event.authority_scope_id)
        components = () if payload.shortfall is None else tuple(
            item.evidence_ref for item in payload.shortfall.components
        )
        views[decision.decision_id.key] = DecisionProvenanceView(
            _VIEW_VERSION, event.authority_scope_id, candidate.candidate_id.key,
            decision.decision_id.key, decision.candidate_snapshot_ref,
            candidate.instrument_id, candidate.horizon_id, decision.action,
            decision.reason, decision.boundary, payload.transition.conservative_edge,
            tuple(decision.reason.evidence_refs),
            None if payload.gross is None else payload.gross.distribution_ref,
            None if payload.shortfall is None else payload.shortfall.distribution_ref,
            components,
            None if payload.calibration is None else payload.calibration.reference,
            decision.policy_version, payload.transition.prior_state,
            payload.transition.next_state, decision.position, decision.correlation_id,
            decision.causation_id,
            candidate_event.event_at_utc, candidate_event.recorded_at_utc,
            decision_event.event_at_utc, decision_event.recorded_at_utc,
            event.journal_seq,
        )
    applied = dict(state.applied_fingerprints)
    applied[event.event_id] = event.fingerprint
    aggregate = dict(state.aggregate_fingerprints)
    aggregate[event.aggregate_key] = event.fingerprint
    return ProjectionState(
        _STATE_VERSION, state.authority_scope_id, event.journal_seq,
        tuple(sorted(applied.items())), tuple(sorted(aggregate.items())),
        state.pending_events[1:],
        tuple(sorted(candidates.values(), key=lambda item: item.aggregate_id)),
        tuple(sorted(decisions.values(), key=lambda item: item.aggregate_id)),
        tuple(sorted(views.values(), key=lambda item: item.decision_id)),
    )


def _validate_entity_immutability(state: ProjectionState, event: ProjectionEvent) -> None:
    existing = (*state.candidates, *state.decisions, *state.pending_events)
    for item in existing:
        if item.event_type is event.event_type and item.aggregate_id == event.aggregate_id:
            if item.payload_hash != event.payload_hash:
                _fail("PROJECTION_ENTITY_CONFLICT", ("event", "aggregate_id"))


def _validate_aggregate_continuity(state: ProjectionState, event: ProjectionEvent) -> None:
    prior_sequences = [
        key[2] for key, _ in state.aggregate_fingerprints
        if key[0] == event.event_type.value and key[1] == event.aggregate_id
    ]
    expected = (max(prior_sequences) + 1) if prior_sequences else 1
    if event.aggregate_seq != expected:
        _fail("PROJECTION_AGGREGATE_SEQUENCE_GAP", ("event", "aggregate_seq"))


def _link_is_available(state: ProjectionState, event: ProjectionEvent) -> bool:
    if type(event.payload) is CandidateProjectionPayload:
        return True
    candidate_id = event.payload.transition.decision.candidate_id.key
    candidate_events = (
        *state.candidates,
        *(item for item in state.pending_events if type(item.payload) is CandidateProjectionPayload),
    )
    candidate_event = next(
        (item for item in candidate_events if item.aggregate_id == candidate_id), None
    )
    if candidate_event is None:
        return False
    _validate_link(candidate_event.payload.candidate, event.payload, event.authority_scope_id)
    return True


def _validate_link(candidate: CandidateSnapshot, payload: DecisionProjectionPayload, scope: str) -> None:
    decision = payload.transition.decision
    if candidate.provenance.authority_scope_id != scope:
        _fail("PROJECTION_SCOPE_MISMATCH", ("candidate", "authority_scope_id"))
    if decision.candidate_id != candidate.candidate_id or decision.candidate_snapshot_ref != candidate.candidate_id.key:
        _fail("PROJECTION_CANDIDATE_LINK_MISMATCH", ("decision", "candidate_id"))
    if decision.correlation_id != candidate.provenance.correlation_id:
        _fail("PROJECTION_CORRELATION_MISMATCH", ("decision", "correlation_id"))
    if decision.causation_id != candidate.provenance.causation_id:
        _fail("PROJECTION_CAUSATION_MISMATCH", ("decision", "causation_id"))
    for item in (payload.transition.prior_state, payload.transition.next_state):
        if item.instrument_id != candidate.instrument_id or item.horizon_id != candidate.horizon_id:
            _fail("PROJECTION_POLICY_SCOPE_MISMATCH", ("transition", "state"))


def _payload_cost_refs(payload: DecisionProjectionPayload) -> tuple[str, ...]:
    refs: list[str] = []
    if payload.gross is not None:
        refs.append(payload.gross.distribution_ref)
    if payload.shortfall is not None:
        refs.extend((payload.shortfall.distribution_ref, *(item.evidence_ref for item in payload.shortfall.components)))
    if payload.calibration is not None:
        refs.append(payload.calibration.reference)
    return tuple(dict.fromkeys(refs))


@dataclass(frozen=True, slots=True)
class DecisionProvenancePage:
    version: str
    items: tuple[DecisionProvenanceView, ...]
    as_of_high_water: int
    next_cursor: str | None

    def __post_init__(self) -> None:
        if (
            self.version != _PAGE_VERSION
            or type(self.items) is not tuple
            or any(type(item) is not DecisionProvenanceView for item in self.items)
            or type(self.as_of_high_water) is not int
            or self.as_of_high_water < 0
            or (self.next_cursor is not None and type(self.next_cursor) is not str)
        ):
            _fail("INVALID_PROJECTION_PAGE", ("page",))


class DecisionProvenanceQuery:
    __slots__ = ("_state",)

    def __init__(self, state: ProjectionState) -> None:
        if type(state) is not ProjectionState:
            _fail("INVALID_PROJECTION_STATE")
        self._state = state

    def get_by_decision_id(self, authority_scope_id: str, decision_id: str) -> DecisionProvenanceView | None:
        self._scope(authority_scope_id)
        _ref(decision_id, ("query", "decision_id"))
        return next((item for item in self._state.views if item.decision_id == decision_id), None)

    def get_by_candidate_id(self, authority_scope_id: str, candidate_id: str) -> tuple[DecisionProvenanceView, ...]:
        self._scope(authority_scope_id)
        _ref(candidate_id, ("query", "candidate_id"))
        return tuple(item for item in self._state.views if item.candidate_id == candidate_id)

    def list_views(
        self, authority_scope_id: str, *, page_size: int, cursor: str | None = None,
        instrument_id: str | None = None,
    ) -> DecisionProvenancePage:
        self._scope(authority_scope_id)
        if type(page_size) is not int or not 1 <= page_size <= _MAX_PAGE_SIZE:
            _fail("INVALID_PROJECTION_PAGE_SIZE", ("query", "page_size"))
        if instrument_id is not None:
            _ref(instrument_id, ("query", "instrument_id"))
        fingerprint = _hash("projection-filter", {"instrument_id": instrument_id})
        if cursor is None:
            as_of, after, cursor_snapshot_ref = self._state.high_water, None, None
        else:
            decoded = _decode_cursor(cursor)
            if decoded["scope"] != authority_scope_id:
                _fail("PROJECTION_CURSOR_SCOPE_MISMATCH", ("query", "cursor"))
            if decoded["filter"] != fingerprint:
                _fail("PROJECTION_CURSOR_FILTER_MISMATCH", ("query", "cursor"))
            as_of = decoded["as_of"]
            if as_of > self._state.high_water:
                _fail("PROJECTION_CURSOR_FUTURE_HIGH_WATER", ("query", "cursor"))
            after = (decoded["last_high_water"], decoded["last_decision_id"])
            cursor_snapshot_ref = decoded["snapshot_ref"]
        ordered = sorted(
            (
                item for item in self._state.views
                if item.projection_high_water <= as_of
                and (instrument_id is None or item.instrument_id == instrument_id)
            ),
            key=lambda item: (-item.projection_high_water, item.decision_id),
        )
        snapshot_ref = _query_snapshot_ref(
            authority_scope_id, fingerprint, as_of, tuple(ordered)
        )
        if cursor_snapshot_ref is not None and cursor_snapshot_ref != snapshot_ref:
            _fail("PROJECTION_CURSOR_SNAPSHOT_MISMATCH", ("query", "cursor"))
        if after is not None:
            if after not in {
                (item.projection_high_water, item.decision_id) for item in ordered
            }:
                _fail("PROJECTION_CURSOR_ORDER_KEY_MISMATCH", ("query", "cursor"))
            after_key = (-after[0], after[1])
            ordered = [item for item in ordered if (-item.projection_high_water, item.decision_id) > after_key]
        selected = tuple(ordered[:page_size])
        next_cursor = None
        if len(ordered) > page_size:
            last = selected[-1]
            next_cursor = _encode_cursor(
                authority_scope_id, fingerprint, as_of, snapshot_ref, last
            )
        return DecisionProvenancePage(_PAGE_VERSION, selected, as_of, next_cursor)

    def _scope(self, authority_scope_id: str) -> None:
        _ref(authority_scope_id, ("query", "authority_scope_id"))
        if authority_scope_id != self._state.authority_scope_id:
            _fail("PROJECTION_QUERY_SCOPE_MISMATCH", ("query", "authority_scope_id"))


def _query_snapshot_ref(
    scope: str, fingerprint: str, as_of: int,
    ordered: tuple[DecisionProvenanceView, ...],
) -> str:
    return _hash("projection-query-snapshot", {
        "scope": scope, "filter": fingerprint, "as_of": as_of,
        "order": tuple(
            (item.projection_high_water, item.decision_id) for item in ordered
        ),
    })


def _encode_cursor(
    scope: str, fingerprint: str, as_of: int, snapshot_ref: str,
    last: DecisionProvenanceView,
) -> str:
    body = {
        "version": _CURSOR_VERSION, "scope": scope, "filter": fingerprint,
        "as_of": as_of, "last_high_water": last.projection_high_water,
        "last_decision_id": last.decision_id, "snapshot_ref": snapshot_ref,
    }
    body["checksum"] = sha256(canonical_bytes(body)).hexdigest()
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(token: object) -> dict[str, object]:
    if type(token) is not str or not token:
        _fail("INVALID_PROJECTION_CURSOR", ("query", "cursor"))
    try:
        padding = "=" * (-len(token) % 4)
        body = json.loads(urlsafe_b64decode(token + padding).decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError, Base64Error) as error:
        raise ProjectionError("INVALID_PROJECTION_CURSOR", path=("query", "cursor")) from error
    required = {
        "version", "scope", "filter", "as_of", "last_high_water",
        "last_decision_id", "snapshot_ref", "checksum",
    }
    if type(body) is not dict or set(body) != required or body["version"] != _CURSOR_VERSION:
        _fail("INVALID_PROJECTION_CURSOR", ("query", "cursor"))
    checksum = body.pop("checksum")
    if type(checksum) is not str or checksum != sha256(canonical_bytes(body)).hexdigest():
        _fail("INVALID_PROJECTION_CURSOR", ("query", "cursor"))
    if (
        type(body["as_of"]) is not int or body["as_of"] < 0
        or type(body["last_high_water"]) is not int
        or body["last_high_water"] <= 0
        or body["last_high_water"] > body["as_of"]
    ):
        _fail("INVALID_PROJECTION_CURSOR", ("query", "cursor"))
    for name in ("scope", "filter", "last_decision_id", "snapshot_ref"):
        _ref(body[name], ("query", "cursor", name))
    return body


class DeliveryDisposition(str, Enum):
    RETRY = "RETRY"
    DEAD_LETTER = "DEAD_LETTER"


@dataclass(frozen=True, slots=True)
class ProjectionDeliveryFailure:
    event: ProjectionEvent
    attempt: int
    max_attempts: int
    error_code: str
    evidence_refs: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        if type(self.event) is not ProjectionEvent:
            _fail("INVALID_DELIVERY_FAILURE", ("failure", "event"))
        if (
            type(self.attempt) is not int or type(self.max_attempts) is not int
            or self.attempt <= 0 or self.max_attempts <= 0 or self.attempt > self.max_attempts
        ):
            _fail("INVALID_DELIVERY_FAILURE", ("failure", "attempt"))
        _ref(self.error_code, ("failure", "error_code"))
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs, ("failure", "evidence_refs")))


@dataclass(frozen=True, slots=True)
class ProjectionDeliveryOutcome:
    event: ProjectionEvent
    disposition: DeliveryDisposition
    attempt: int
    max_attempts: int
    error_code: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.disposition) is not DeliveryDisposition
            or type(self.event) is not ProjectionEvent
            or type(self.attempt) is not int
            or self.attempt <= 0
            or type(self.max_attempts) is not int
            or self.max_attempts <= 0
            or self.attempt > self.max_attempts
            or type(self.evidence_refs) is not tuple
        ):
            _fail("INVALID_DELIVERY_OUTCOME", ("outcome",))
        _ref(self.error_code, ("outcome", "error_code"))
        _refs(self.evidence_refs, ("outcome", "evidence_refs"))

    @property
    def event_id(self) -> str:
        return self.event.event_id


def decide_delivery_failure(failure: ProjectionDeliveryFailure) -> ProjectionDeliveryOutcome:
    if type(failure) is not ProjectionDeliveryFailure:
        _fail("INVALID_DELIVERY_FAILURE", ("failure",))
    disposition = (
        DeliveryDisposition.DEAD_LETTER
        if failure.attempt == failure.max_attempts else DeliveryDisposition.RETRY
    )
    return ProjectionDeliveryOutcome(
        failure.event, disposition, failure.attempt, failure.max_attempts,
        failure.error_code, tuple(failure.evidence_refs),
    )


__all__ = (
    "CandidateProjectionPayload", "DecisionProjectionPayload",
    "DecisionProvenancePage", "DecisionProvenanceQuery", "DecisionProvenanceView",
    "DeliveryDisposition", "ProjectionConsumeResult", "ProjectionDeliveryFailure",
    "ProjectionDeliveryOutcome", "ProjectionError", "ProjectionEvent",
    "ProjectionEventType", "ProjectionState", "consume_projection_event",
    "decide_delivery_failure", "projection_event_id", "projection_outbox_ref",
    "projection_payload_hash",
)
