"""Pure state-legal Canonical Decision kernel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .candidate import CandidateSnapshot, CandidateUse
from .encoding import canonical_bytes
from .errors import CanonicalEncodingError, DecisionError
from .identity import DeterministicIdentity, build_identity
from .numeric import ScaledInteger


class DecisionAction(str, Enum):
    ENTER = "ENTER"
    ABSTAIN = "ABSTAIN"
    HOLD = "HOLD"
    EXIT = "EXIT"


class PositionState(str, Enum):
    FLAT = "FLAT"
    EXPOSED = "EXPOSED"


class DecisionReasonCode(str, Enum):
    ENTER_APPROVED = "ENTER_APPROVED"
    POLICY_ABSTAIN = "POLICY_ABSTAIN"
    ENTRY_VETO = "ENTRY_VETO"
    CANDIDATE_INELIGIBLE = "CANDIDATE_INELIGIBLE"
    MAINTAIN_EXPOSURE = "MAINTAIN_EXPOSURE"
    ALPHA_EXIT = "ALPHA_EXIT"
    PROTECTIVE_EXIT = "PROTECTIVE_EXIT"
    COST_MARGIN_NOT_MET = "COST_MARGIN_NOT_MET"
    CALIBRATION_MISSING = "CALIBRATION_MISSING"
    CALIBRATION_STALE = "CALIBRATION_STALE"
    ENTER_CONFIRMATION_PENDING = "ENTER_CONFIRMATION_PENDING"
    ALPHA_EXIT_CONFIRMATION_PENDING = "ALPHA_EXIT_CONFIRMATION_PENDING"
    DATA_GAP = "DATA_GAP"


class CommitStatus(str, Enum):
    CREATED = "CREATED"
    IDEMPOTENT = "IDEMPOTENT"
    CONFLICT = "CONFLICT"


def _fail(code: str, path: tuple[str | int, ...] = (), incident=None) -> None:
    raise DecisionError(code, path=path, incident=incident)


def _reference(value: object, path: tuple[str | int, ...]) -> None:
    if type(value) is not str or not value or not value.strip():
        _fail("INVALID_DECISION_REFERENCE", path)
    try:
        canonical_bytes(value)
    except CanonicalEncodingError as error:
        raise DecisionError("INVALID_DECISION_REFERENCE", path=path) from error


def _references(value: object, path: tuple[str | int, ...]) -> tuple[str, ...]:
    if type(value) not in (tuple, list):
        _fail("INVALID_DECISION_VALUE", path)
    result = tuple(value)
    for index, item in enumerate(result):
        _reference(item, (*path, index))
    return result


@dataclass(frozen=True, slots=True)
class DecisionBoundary:
    version: str
    reference: str
    evidence_refs: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        _reference(self.version, ("boundary", "version"))
        _reference(self.reference, ("boundary", "reference"))
        object.__setattr__(self, "evidence_refs", _references(self.evidence_refs, ("boundary", "evidence_refs")))

    def to_canonical_value(self) -> dict[str, object]:
        return {"version": self.version, "reference": self.reference, "evidence_refs": self.evidence_refs}


@dataclass(frozen=True, slots=True)
class PositionContext:
    state: PositionState
    snapshot_ref: str
    position_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.state) is not PositionState:
            _fail("INVALID_POSITION_CONTEXT", ("position", "state"))
        _reference(self.snapshot_ref, ("position", "snapshot_ref"))
        if self.state is PositionState.FLAT and self.position_id is not None:
            _fail("INVALID_POSITION_CONTEXT", ("position", "position_id"))
        if self.state is PositionState.EXPOSED:
            if self.position_id is None:
                _fail("INVALID_POSITION_CONTEXT", ("position", "position_id"))
            _reference(self.position_id, ("position", "position_id"))

    def to_canonical_value(self) -> dict[str, str | None]:
        return {"state": self.state.value, "snapshot_ref": self.snapshot_ref, "position_id": self.position_id}


@dataclass(frozen=True, slots=True)
class DecisionReason:
    code: DecisionReasonCode
    evidence_refs: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        if type(self.code) is not DecisionReasonCode:
            _fail("INVALID_DECISION_REASON", ("reason", "code"))
        object.__setattr__(self, "evidence_refs", _references(self.evidence_refs, ("reason", "evidence_refs")))

    def to_canonical_value(self) -> dict[str, object]:
        return {"code": self.code.value, "evidence_refs": self.evidence_refs}


@dataclass(frozen=True, slots=True)
class IntegrityIncident:
    code: str
    decision_key: str
    evidence_refs: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        _reference(self.code, ("incident", "code"))
        _reference(self.decision_key, ("incident", "decision_key"))
        object.__setattr__(self, "evidence_refs", _references(self.evidence_refs, ("incident", "evidence_refs")))


@dataclass(frozen=True, slots=True)
class CanonicalDecision:
    decision_id: DeterministicIdentity
    candidate_id: DeterministicIdentity
    candidate_snapshot_ref: str
    policy_version: str
    position: PositionContext
    action: DecisionAction
    reason: DecisionReason
    boundary: DecisionBoundary
    exit_target: ScaledInteger | None
    correlation_id: str
    causation_id: str

    def __post_init__(self) -> None:
        if type(self.candidate_id) is not DeterministicIdentity or self.candidate_id.kind != "candidate":
            _fail("INVALID_CANDIDATE_REFERENCE", ("candidate_id",))
        for name in ("candidate_snapshot_ref", "policy_version", "correlation_id", "causation_id"):
            _reference(getattr(self, name), (name,))
        if self.candidate_snapshot_ref != self.candidate_id.key:
            _fail("INVALID_CANDIDATE_REFERENCE", ("candidate_snapshot_ref",))
        expected = _decision_identity(self.candidate_id, self.policy_version)
        if type(self.decision_id) is not DeterministicIdentity or self.decision_id != expected:
            _fail("INVALID_DECISION_ID", ("decision_id",))
        if type(self.position) is not PositionContext or type(self.boundary) is not DecisionBoundary:
            _fail("INVALID_DECISION_VALUE")
        if type(self.action) is not DecisionAction:
            _fail("INVALID_DECISION_ACTION", ("action",))
        if type(self.reason) is not DecisionReason:
            _fail("INVALID_DECISION_REASON", ("reason",))
        incident = _incident(
            "ILLEGAL_DECISION_TRANSITION",
            self.decision_id.key,
            (self.candidate_id.key,),
        )
        if self.action not in _LEGAL_ACTIONS[self.position.state]:
            _fail("ILLEGAL_DECISION_TRANSITION", ("action",), incident)
        if self.reason.code not in _REASONS_BY_ACTION[self.action]:
            _fail("INVALID_DECISION_REASON", ("reason", "code"), incident)
        _validate_exit_target(
            self.action,
            self.exit_target,
            incident=_incident(
                "INVALID_EXIT_TARGET",
                self.decision_id.key,
                (self.candidate_id.key,),
            ),
        )
        try:
            canonical_bytes(self.to_canonical_value())
        except CanonicalEncodingError as error:
            raise DecisionError("INVALID_DECISION_VALUE") from error

    @property
    def semantic_key(self) -> str:
        return self.decision_id.key

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": "canonical-decision:v1", "decision_id": self.decision_id.key,
            "candidate_id": self.candidate_id.key, "candidate_snapshot_ref": self.candidate_snapshot_ref,
            "policy_version": self.policy_version, "position": self.position.to_canonical_value(),
            "action": self.action.value, "reason": self.reason.to_canonical_value(),
            "boundary": self.boundary.to_canonical_value(), "exit_target": self.exit_target,
            "correlation_id": self.correlation_id, "causation_id": self.causation_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class DecisionCommitResult:
    status: CommitStatus
    decision: CanonicalDecision
    incident: IntegrityIncident | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not CommitStatus or type(self.decision) is not CanonicalDecision:
            _fail("INVALID_DECISION_VALUE", ("commit_result",))
        expects_incident = self.status is CommitStatus.CONFLICT
        if expects_incident != (type(self.incident) is IntegrityIncident):
            _fail("INVALID_DECISION_VALUE", ("commit_result", "incident"))
        if expects_incident and (
            self.incident.code != "DECISION_CONFLICT"
            or self.incident.decision_key != self.decision.semantic_key
        ):
            _fail("INVALID_DECISION_VALUE", ("commit_result", "incident"))


def evaluate_decision(candidate: CandidateSnapshot, *, policy_version: str, position: PositionContext,
                      proposed_action: DecisionAction, boundary: DecisionBoundary, entry_veto: bool = False,
                      protective_exit: bool = False, exit_target: ScaledInteger | None = None,
                      reason_override: DecisionReasonCode | None = None,
                      reason_evidence_refs: tuple[str, ...] | list[str] = (),
                      candidate_use: CandidateUse = CandidateUse.LIVE_ADMISSION) -> CanonicalDecision:
    """Legalize one proposal and return its immutable canonical decision."""
    if type(candidate) is not CandidateSnapshot:
        _fail("INVALID_CANDIDATE_REFERENCE", ("candidate",))
    if type(candidate_use) is not CandidateUse:
        _fail("INVALID_CANDIDATE_USE", ("candidate_use",))
    _reference(policy_version, ("policy_version",))
    decision_key = _decision_identity(candidate.candidate_id, policy_version).key
    if type(proposed_action) is not DecisionAction:
        _fail(
            "INVALID_DECISION_ACTION",
            ("proposed_action",),
            _incident(
                "INVALID_DECISION_ACTION", decision_key, (candidate.candidate_id.key,)
            ),
        )
    if type(position) is not PositionContext or type(boundary) is not DecisionBoundary:
        _fail(
            "INVALID_DECISION_VALUE",
            incident=_incident(
                "INVALID_DECISION_VALUE", decision_key, (candidate.candidate_id.key,)
            ),
        )
    if type(entry_veto) is not bool or type(protective_exit) is not bool:
        _fail(
            "INVALID_DECISION_VALUE",
            incident=_incident(
                "INVALID_DECISION_VALUE", decision_key, (candidate.candidate_id.key,)
            ),
        )
    if reason_override is not None and type(reason_override) is not DecisionReasonCode:
        _fail(
            "INVALID_DECISION_REASON",
            ("reason_override",),
            _incident(
                "INVALID_DECISION_REASON", decision_key, (candidate.candidate_id.key,)
            ),
        )
    extra_reason_evidence = _references(
        reason_evidence_refs, ("reason_evidence_refs",)
    )
    policy_reason_codes = {
        DecisionReasonCode.COST_MARGIN_NOT_MET,
        DecisionReasonCode.CALIBRATION_MISSING,
        DecisionReasonCode.CALIBRATION_STALE,
        DecisionReasonCode.ENTER_CONFIRMATION_PENDING,
        DecisionReasonCode.ALPHA_EXIT_CONFIRMATION_PENDING,
        DecisionReasonCode.DATA_GAP,
    }
    if reason_override in policy_reason_codes and not extra_reason_evidence:
        _fail(
            "INVALID_DECISION_REASON",
            ("reason_evidence_refs",),
            _incident(
                "INVALID_DECISION_REASON", decision_key, (candidate.candidate_id.key,)
            ),
        )
    if candidate.parent_position_id is not None and (
        position.state is not PositionState.EXPOSED
        or position.position_id != candidate.parent_position_id
    ):
        _fail(
            "POSITION_REFERENCE_MISMATCH",
            ("position", "position_id"),
            _incident(
                "POSITION_REFERENCE_MISMATCH",
                decision_key,
                (candidate.candidate_id.key, candidate.parent_position_id),
            ),
        )

    action = proposed_action
    reason = {
        DecisionAction.ENTER: DecisionReasonCode.ENTER_APPROVED,
        DecisionAction.ABSTAIN: DecisionReasonCode.POLICY_ABSTAIN,
        DecisionAction.HOLD: DecisionReasonCode.MAINTAIN_EXPOSURE,
        DecisionAction.EXIT: DecisionReasonCode.ALPHA_EXIT,
    }[action]
    if protective_exit:
        if position.state is not PositionState.EXPOSED:
            _raise_illegal_transition(candidate, policy_version)
        action, reason = DecisionAction.EXIT, DecisionReasonCode.PROTECTIVE_EXIT
    elif position.state is PositionState.FLAT and proposed_action is DecisionAction.ENTER:
        if entry_veto:
            action, reason = DecisionAction.ABSTAIN, DecisionReasonCode.ENTRY_VETO
        elif (
            (not candidate.is_proof_bearing and candidate_use is CandidateUse.LIVE_ADMISSION)
            or not candidate.executable
        ):
            action, reason = DecisionAction.ABSTAIN, DecisionReasonCode.CANDIDATE_INELIGIBLE
    elif reason_override is not None:
        reason = reason_override

    if action not in _LEGAL_ACTIONS[position.state]:
        _raise_illegal_transition(candidate, policy_version)
    _validate_exit_target(
        action,
        exit_target,
        incident=_incident(
            "INVALID_EXIT_TARGET", decision_key, (candidate.candidate_id.key,)
        ),
    )
    evidence_refs = [candidate.candidate_id.key]
    if reason is DecisionReasonCode.CANDIDATE_INELIGIBLE:
        if candidate.provenance.eligibility.evidence_ref is not None:
            evidence_refs.append(candidate.provenance.eligibility.evidence_ref)
    elif reason in (DecisionReasonCode.ENTRY_VETO, DecisionReasonCode.PROTECTIVE_EXIT):
        evidence_refs.extend((boundary.reference, *boundary.evidence_refs))
    evidence_refs.extend(extra_reason_evidence)
    return CanonicalDecision(
        _decision_identity(candidate.candidate_id, policy_version), candidate.candidate_id,
        candidate.candidate_id.key, policy_version, position, action,
        DecisionReason(reason, evidence_refs), boundary, exit_target,
        candidate.provenance.correlation_id, candidate.provenance.causation_id,
    )


def commit_decision(existing: CanonicalDecision | None, proposed: CanonicalDecision) -> DecisionCommitResult:
    """Classify a repository-boundary insert without mutating either decision."""
    if type(proposed) is not CanonicalDecision:
        _fail("INVALID_DECISION_VALUE", ("proposed",))
    if existing is None:
        return DecisionCommitResult(CommitStatus.CREATED, proposed)
    if type(existing) is not CanonicalDecision:
        _fail("INVALID_DECISION_VALUE", ("existing",))
    if existing.semantic_key != proposed.semantic_key:
        _fail(
            "DECISION_KEY_MISMATCH",
            ("existing",),
            _incident(
                "DECISION_KEY_MISMATCH",
                existing.semantic_key,
                (existing.semantic_key, proposed.semantic_key),
            ),
        )
    if existing.canonical_bytes() == proposed.canonical_bytes():
        return DecisionCommitResult(CommitStatus.IDEMPOTENT, existing)
    incident = IntegrityIncident("DECISION_CONFLICT", existing.semantic_key, (
        sha256(existing.canonical_bytes()).hexdigest(), sha256(proposed.canonical_bytes()).hexdigest()))
    return DecisionCommitResult(CommitStatus.CONFLICT, existing, incident)


def _decision_identity(candidate_id: DeterministicIdentity, policy_version: str) -> DeterministicIdentity:
    return build_identity("decision", {"candidate_id": candidate_id.key, "policy_version": policy_version})


def _validate_exit_target(
    action: DecisionAction,
    target: ScaledInteger | None,
    *,
    incident: IntegrityIncident | None = None,
) -> None:
    if action is DecisionAction.EXIT and type(target) is not ScaledInteger:
        _fail("INVALID_EXIT_TARGET", ("exit_target",), incident)
    if action is DecisionAction.EXIT and target.units < 0:
        _fail("INVALID_EXIT_TARGET", ("exit_target",), incident)
    if action is not DecisionAction.EXIT and target is not None:
        _fail("INVALID_EXIT_TARGET", ("exit_target",), incident)


def _incident(
    code: str, decision_key: str, evidence_refs: tuple[str, ...]
) -> IntegrityIncident:
    return IntegrityIncident(code, decision_key, evidence_refs)


def _raise_illegal_transition(candidate: CandidateSnapshot, policy_version: str) -> None:
    key = _decision_identity(candidate.candidate_id, policy_version).key
    incident = _incident("ILLEGAL_DECISION_TRANSITION", key, (candidate.candidate_id.key,))
    raise DecisionError("ILLEGAL_DECISION_TRANSITION", path=("action",), incident=incident)


_LEGAL_ACTIONS = {
    PositionState.FLAT: frozenset((DecisionAction.ENTER, DecisionAction.ABSTAIN)),
    PositionState.EXPOSED: frozenset((DecisionAction.HOLD, DecisionAction.EXIT)),
}

_REASONS_BY_ACTION = {
    DecisionAction.ENTER: frozenset((DecisionReasonCode.ENTER_APPROVED,)),
    DecisionAction.ABSTAIN: frozenset(
        (
            DecisionReasonCode.POLICY_ABSTAIN,
            DecisionReasonCode.ENTRY_VETO,
            DecisionReasonCode.CANDIDATE_INELIGIBLE,
            DecisionReasonCode.COST_MARGIN_NOT_MET,
            DecisionReasonCode.CALIBRATION_MISSING,
            DecisionReasonCode.CALIBRATION_STALE,
            DecisionReasonCode.ENTER_CONFIRMATION_PENDING,
            DecisionReasonCode.DATA_GAP,
        )
    ),
    DecisionAction.HOLD: frozenset(
        (
            DecisionReasonCode.MAINTAIN_EXPOSURE,
            DecisionReasonCode.ALPHA_EXIT_CONFIRMATION_PENDING,
            DecisionReasonCode.DATA_GAP,
        )
    ),
    DecisionAction.EXIT: frozenset(
        (DecisionReasonCode.ALPHA_EXIT, DecisionReasonCode.PROTECTIVE_EXIT)
    ),
}


__all__ = ("CanonicalDecision", "CommitStatus", "DecisionAction", "DecisionBoundary",
           "DecisionCommitResult", "DecisionError", "DecisionReason", "DecisionReasonCode",
           "IntegrityIncident", "PositionContext", "PositionState", "commit_decision", "evaluate_decision")
