"""Additive safety-cause lattice with evidence-gated clear transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, IntEnum

from .content import ContentRecipe, ContentRef
from .errors import DecisionError


def _text(value: object, code: str) -> None:
    if type(value) is not str or not value.strip():
        raise DecisionError(code)


def _utc(value: object, code: str) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != UTC.utcoffset(value)):
        raise DecisionError(code)
    return value


def _refs(values: object, code: str) -> tuple[ContentRef, ...]:
    if (type(values) is not tuple or not values
            or any(type(item) is not ContentRef for item in values)):
        raise DecisionError(code)
    keys = tuple(item.key for item in values)
    if len(keys) != len(set(keys)) or keys != tuple(sorted(keys)):
        raise DecisionError(code)
    return values


def _clear_authority_ref(value: object) -> ContentRef:
    if (
        type(value) is not ContentRef
        or value.domain != "autotrade-next"
        or value.kind != "ClearAuthority"
        or value.recipe is not ContentRecipe.V2
    ):
        raise DecisionError("INVALID_CLEAR_AUTHORITY")
    return value


class SafetyScopeLevel(IntEnum):
    ORDER = 1
    INSTRUMENT = 2
    PORTFOLIO = 3
    AUTHORITY = 4


class SafetySeverity(IntEnum):
    WATCH = 1
    ENTRY_FREEZE = 2
    AUTHORITY_HALT = 3


class SafetyCauseKind(str, Enum):
    STALE_DATA = "STALE_DATA"
    CONTINUITY_GAP = "CONTINUITY_GAP"
    UNKNOWN_ORDER = "UNKNOWN_ORDER"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    DELIVERY_FAILURE = "DELIVERY_FAILURE"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    FENCE_LOSS = "FENCE_LOSS"


class ClearPredicate(str, Enum):
    FRESH_DATA = "FRESH_DATA"
    CONTINUITY_RESTORED = "CONTINUITY_RESTORED"
    ORDER_RECONCILED = "ORDER_RECONCILED"
    PORTFOLIO_RECONCILED = "PORTFOLIO_RECONCILED"
    DELIVERY_RESTORED = "DELIVERY_RESTORED"
    CLOCK_STABLE = "CLOCK_STABLE"
    STORAGE_HEALTHY = "STORAGE_HEALTHY"
    FENCE_REACQUIRED = "FENCE_REACQUIRED"


class ProtectiveAction(str, Enum):
    CANCEL = "CANCEL"
    EXIT = "EXIT"
    RECONCILE = "RECONCILE"


@dataclass(frozen=True, slots=True)
class _CauseRule:
    minimum_scope: SafetyScopeLevel
    minimum_severity: SafetySeverity
    clear_predicate: ClearPredicate
    allowed_actions: tuple[ProtectiveAction, ...]


_ALL_PROTECTIVE = tuple(ProtectiveAction)
_CAUSE_MATRIX = {
    SafetyCauseKind.STALE_DATA: _CauseRule(
        SafetyScopeLevel.INSTRUMENT, SafetySeverity.ENTRY_FREEZE,
        ClearPredicate.FRESH_DATA, _ALL_PROTECTIVE),
    SafetyCauseKind.CONTINUITY_GAP: _CauseRule(
        SafetyScopeLevel.INSTRUMENT, SafetySeverity.ENTRY_FREEZE,
        ClearPredicate.CONTINUITY_RESTORED, _ALL_PROTECTIVE),
    SafetyCauseKind.UNKNOWN_ORDER: _CauseRule(
        SafetyScopeLevel.ORDER, SafetySeverity.ENTRY_FREEZE,
        ClearPredicate.ORDER_RECONCILED, _ALL_PROTECTIVE),
    SafetyCauseKind.RECONCILIATION_MISMATCH: _CauseRule(
        SafetyScopeLevel.PORTFOLIO, SafetySeverity.ENTRY_FREEZE,
        ClearPredicate.PORTFOLIO_RECONCILED, _ALL_PROTECTIVE),
    SafetyCauseKind.DELIVERY_FAILURE: _CauseRule(
        SafetyScopeLevel.PORTFOLIO, SafetySeverity.ENTRY_FREEZE,
        ClearPredicate.DELIVERY_RESTORED, _ALL_PROTECTIVE),
    SafetyCauseKind.CLOCK_ANOMALY: _CauseRule(
        SafetyScopeLevel.AUTHORITY, SafetySeverity.AUTHORITY_HALT,
        ClearPredicate.CLOCK_STABLE, _ALL_PROTECTIVE),
    SafetyCauseKind.STORAGE_FAILURE: _CauseRule(
        SafetyScopeLevel.AUTHORITY, SafetySeverity.AUTHORITY_HALT,
        ClearPredicate.STORAGE_HEALTHY, _ALL_PROTECTIVE),
    SafetyCauseKind.FENCE_LOSS: _CauseRule(
        SafetyScopeLevel.AUTHORITY, SafetySeverity.AUTHORITY_HALT,
        ClearPredicate.FENCE_REACQUIRED, _ALL_PROTECTIVE),
}


@dataclass(frozen=True, slots=True)
class SafetyScope:
    level: SafetyScopeLevel
    scope_id: str

    def __post_init__(self) -> None:
        if type(self.level) is not SafetyScopeLevel:
            raise DecisionError("INVALID_SAFETY_SCOPE")
        _text(self.scope_id, "INVALID_SAFETY_SCOPE")

    def to_canonical_value(self) -> dict[str, object]:
        return {"level": self.level.name, "scope_id": self.scope_id}


def _cause_value(
    *, kind: SafetyCauseKind, scope: SafetyScope,
    severity: SafetySeverity, evidence_refs: tuple[ContentRef, ...],
    clear_predicate: ClearPredicate,
    allowed_actions: tuple[ProtectiveAction, ...],
    expected_sequence: int, recorded_at_utc: datetime,
) -> dict[str, object]:
    return {
        "kind": kind.value,
        "scope": scope.to_canonical_value(),
        "severity": severity.name,
        "evidence_refs": tuple(item.to_canonical_value() for item in evidence_refs),
        "clear_predicate": clear_predicate.value,
        "allowed_actions": tuple(item.value for item in allowed_actions),
        "expected_sequence": expected_sequence,
        "recorded_at_utc": recorded_at_utc,
    }


@dataclass(frozen=True, slots=True)
class SafetyCause:
    cause_id: str
    kind: SafetyCauseKind
    scope: SafetyScope
    severity: SafetySeverity
    evidence_refs: tuple[ContentRef, ...]
    clear_predicate: ClearPredicate
    allowed_actions: tuple[ProtectiveAction, ...]
    expected_sequence: int
    recorded_at_utc: datetime

    def __post_init__(self) -> None:
        if type(self.kind) is not SafetyCauseKind or type(self.scope) is not SafetyScope:
            raise DecisionError("INVALID_SAFETY_CAUSE")
        if type(self.severity) is not SafetySeverity:
            raise DecisionError("INVALID_SAFETY_SEVERITY")
        evidence = _refs(self.evidence_refs, "INVALID_SAFETY_EVIDENCE")
        rule = _CAUSE_MATRIX[self.kind]
        if self.scope.level < rule.minimum_scope:
            raise DecisionError("SAFETY_SCOPE_BELOW_MATRIX_MINIMUM")
        if self.severity < rule.minimum_severity:
            raise DecisionError("SAFETY_SEVERITY_BELOW_MATRIX_MINIMUM")
        if self.clear_predicate is not rule.clear_predicate:
            raise DecisionError("SAFETY_CLEAR_PREDICATE_MISMATCH")
        if self.allowed_actions != rule.allowed_actions:
            raise DecisionError("SAFETY_ACTION_MATRIX_MISMATCH")
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise DecisionError("INVALID_SAFETY_SEQUENCE")
        _utc(self.recorded_at_utc, "INVALID_SAFETY_TIMESTAMP")
        expected = ContentRef.v2(
            "autotrade-next", "SafetyCause",
            _cause_value(
                kind=self.kind, scope=self.scope, severity=self.severity,
                evidence_refs=evidence, clear_predicate=self.clear_predicate,
                allowed_actions=self.allowed_actions,
                expected_sequence=self.expected_sequence,
                recorded_at_utc=self.recorded_at_utc,
            ),
        ).key
        if self.cause_id != expected:
            raise DecisionError("SAFETY_CAUSE_ID_MISMATCH")

    @classmethod
    def create(
        cls, *, kind: SafetyCauseKind, scope: SafetyScope,
        severity: SafetySeverity, evidence_refs: tuple[ContentRef, ...],
        expected_sequence: int, recorded_at_utc: datetime,
    ) -> SafetyCause:
        if type(kind) is not SafetyCauseKind:
            raise DecisionError("INVALID_SAFETY_CAUSE_KIND")
        rule = _CAUSE_MATRIX[kind]
        canonical_evidence = _refs(evidence_refs, "INVALID_SAFETY_EVIDENCE")
        value = _cause_value(
            kind=kind, scope=scope, severity=severity,
            evidence_refs=canonical_evidence,
            clear_predicate=rule.clear_predicate,
            allowed_actions=rule.allowed_actions,
            expected_sequence=expected_sequence,
            recorded_at_utc=recorded_at_utc,
        )
        cause_id = ContentRef.v2("autotrade-next", "SafetyCause", value).key
        return cls(cause_id, kind, scope, severity, canonical_evidence,
                   rule.clear_predicate, rule.allowed_actions,
                   expected_sequence, recorded_at_utc)


@dataclass(frozen=True, slots=True)
class SafetyClearProof:
    cause_id: str
    predicate: ClearPredicate
    evidence_refs: tuple[ContentRef, ...]
    expected_sequence: int
    observed_at_utc: datetime
    authority_ref: ContentRef

    def __post_init__(self) -> None:
        _text(self.cause_id, "INVALID_CLEAR_CAUSE_ID")
        if type(self.predicate) is not ClearPredicate:
            raise DecisionError("INVALID_CLEAR_PREDICATE")
        _refs(self.evidence_refs, "INVALID_CLEAR_EVIDENCE")
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise DecisionError("INVALID_CLEAR_SEQUENCE")
        _utc(self.observed_at_utc, "INVALID_CLEAR_TIMESTAMP")
        _clear_authority_ref(self.authority_ref)

    @property
    def reference(self) -> ContentRef:
        return ContentRef.v2(
            "autotrade-next", "SafetyClearProof",
            {
                "cause_id": self.cause_id,
                "predicate": self.predicate.value,
                "evidence_refs": tuple(item.to_canonical_value()
                                       for item in self.evidence_refs),
                "expected_sequence": self.expected_sequence,
                "observed_at_utc": self.observed_at_utc,
                "authority_ref": self.authority_ref.to_canonical_value(),
            },
        )


@dataclass(frozen=True, slots=True)
class SafetyClearRecord:
    cause_id: str
    proof_ref: ContentRef
    cleared_sequence: int

    def __post_init__(self) -> None:
        _text(self.cause_id, "INVALID_CLEAR_CAUSE_ID")
        if (
            type(self.proof_ref) is not ContentRef
            or self.proof_ref.domain != "autotrade-next"
            or self.proof_ref.kind != "SafetyClearProof"
            or self.proof_ref.recipe is not ContentRecipe.V2
        ):
            raise DecisionError("INVALID_CLEAR_RECORD_PROOF")
        if type(self.cleared_sequence) is not int or self.cleared_sequence < 1:
            raise DecisionError("INVALID_CLEAR_RECORD_SEQUENCE")


@dataclass(frozen=True, slots=True)
class SafetyStateLattice:
    sequence: int
    active_causes: tuple[SafetyCause, ...]
    clear_history: tuple[SafetyClearRecord, ...]

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise DecisionError("INVALID_SAFETY_SEQUENCE")
        if (type(self.active_causes) is not tuple
                or any(type(item) is not SafetyCause for item in self.active_causes)):
            raise DecisionError("INVALID_ACTIVE_CAUSES")
        ids = tuple(item.cause_id for item in self.active_causes)
        if len(ids) != len(set(ids)) or ids != tuple(sorted(ids)):
            raise DecisionError("INVALID_ACTIVE_CAUSE_ORDER")
        if (type(self.clear_history) is not tuple
                or any(type(item) is not SafetyClearRecord for item in self.clear_history)):
            raise DecisionError("INVALID_CLEAR_HISTORY")
        active_sequences = tuple(item.expected_sequence for item in self.active_causes)
        if any(item >= self.sequence for item in active_sequences):
            raise DecisionError("INVALID_ACTIVE_CAUSE_SEQUENCE")
        cleared_sequences = tuple(item.cleared_sequence for item in self.clear_history)
        proof_keys = tuple(item.proof_ref.key for item in self.clear_history)
        cleared_ids = tuple(item.cause_id for item in self.clear_history)
        if (
            any(item > self.sequence for item in cleared_sequences)
            or cleared_sequences != tuple(sorted(cleared_sequences))
            or len(proof_keys) != len(set(proof_keys))
            or len(cleared_ids) != len(set(cleared_ids))
        ):
            raise DecisionError("INVALID_CLEAR_HISTORY")

    @classmethod
    def empty(cls) -> SafetyStateLattice:
        return cls(0, (), ())

    @property
    def causes(self) -> tuple[SafetyCause, ...]:
        return self.active_causes

    def add_cause(self, cause: SafetyCause, *, expected_sequence: int) -> SafetyStateLattice:
        if type(cause) is not SafetyCause:
            raise DecisionError("INVALID_SAFETY_CAUSE")
        existing = next((item for item in self.active_causes
                         if item.cause_id == cause.cause_id), None)
        if existing is not None:
            if existing == cause:
                return self
            raise DecisionError("SAFETY_CAUSE_IDENTITY_CONFLICT")
        if expected_sequence != self.sequence or cause.expected_sequence != self.sequence:
            raise DecisionError("SAFETY_SEQUENCE_CONFLICT")
        active = tuple(sorted((*self.active_causes, cause),
                              key=lambda item: item.cause_id))
        return SafetyStateLattice(self.sequence + 1, active, self.clear_history)

    def clear_cause(self, proof: SafetyClearProof) -> SafetyStateLattice:
        if type(proof) is not SafetyClearProof:
            raise DecisionError("INVALID_CLEAR_PROOF")
        for record in self.clear_history:
            if record.proof_ref == proof.reference:
                return self
        cause = next((item for item in self.active_causes
                      if item.cause_id == proof.cause_id), None)
        if cause is None:
            raise DecisionError("ACTIVE_SAFETY_CAUSE_NOT_FOUND")
        if proof.expected_sequence != self.sequence:
            raise DecisionError("SAFETY_SEQUENCE_CONFLICT")
        if proof.predicate is not cause.clear_predicate:
            raise DecisionError("SAFETY_CLEAR_PREDICATE_MISMATCH")
        if proof.observed_at_utc <= cause.recorded_at_utc:
            raise DecisionError("CLEAR_EVIDENCE_PRECEDES_CAUSE")
        old_keys = {item.key for item in cause.evidence_refs}
        if not any(item.key not in old_keys for item in proof.evidence_refs):
            raise DecisionError("NEW_CLEAR_EVIDENCE_REQUIRED")
        active = tuple(item for item in self.active_causes
                       if item.cause_id != cause.cause_id)
        record = SafetyClearRecord(cause.cause_id, proof.reference,
                                   self.sequence + 1)
        return SafetyStateLattice(self.sequence + 1, active,
                                  (*self.clear_history, record))

    @property
    def highest_effective_level(self) -> SafetyScopeLevel | None:
        return (None if not self.active_causes
                else max(item.scope.level for item in self.active_causes))

    @property
    def effective_severity(self) -> SafetySeverity | None:
        return (None if not self.active_causes
                else max(item.severity for item in self.active_causes))

    @property
    def allowed_protective_actions(self) -> tuple[ProtectiveAction, ...]:
        if not self.active_causes:
            return tuple(ProtectiveAction)
        allowed = set(self.active_causes[0].allowed_actions)
        for cause in self.active_causes[1:]:
            allowed.intersection_update(cause.allowed_actions)
        return tuple(action for action in ProtectiveAction if action in allowed)

    @property
    def is_entry_frozen(self) -> bool:
        severity = self.effective_severity
        return severity is not None and severity >= SafetySeverity.ENTRY_FREEZE


__all__ = (
    "ClearPredicate",
    "ProtectiveAction",
    "SafetyCause",
    "SafetyCauseKind",
    "SafetyClearProof",
    "SafetyClearRecord",
    "SafetyScope",
    "SafetyScopeLevel",
    "SafetySeverity",
    "SafetyStateLattice",
)
