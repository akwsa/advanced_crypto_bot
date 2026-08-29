"""Pure cost-aware abstention and hysteresis transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256

from .candidate import CandidateSnapshot, CandidateTrigger, CandidateUse
from .decision import (
    CanonicalDecision,
    DecisionAction,
    DecisionBoundary,
    DecisionReasonCode,
    PositionContext,
    PositionState,
    evaluate_decision,
)
from .encoding import canonical_bytes
from .errors import CanonicalEncodingError, PolicyEvaluationError
from .numeric import MAX_CANONICAL_INTEGER_BITS, ScaledInteger


class CalibrationStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"


class GapBehavior(str, Enum):
    RESET_ENTER_ONLY = "RESET_ENTER_ONLY"


class ShortfallComponent(str, Enum):
    FEE = "FEE"
    TAX_CLEARING = "TAX_CLEARING"
    SPREAD = "SPREAD"
    SLIPPAGE = "SLIPPAGE"
    IMPACT = "IMPACT"
    LATENCY_ADVERSE_SELECTION = "LATENCY_ADVERSE_SELECTION"
    OPPORTUNITY_COST_NON_FILL = "OPPORTUNITY_COST_NON_FILL"


def _fail(
    code: str,
    path: tuple[str | int, ...] = (),
    evidence_ref: str | None = None,
) -> None:
    raise PolicyEvaluationError(code, path=path, evidence_ref=evidence_ref)


def _reference(value: object, path: tuple[str | int, ...]) -> None:
    if type(value) is not str or not value or not value.strip():
        _fail("INVALID_POLICY_REFERENCE", path)
    try:
        canonical_bytes(value)
    except CanonicalEncodingError as error:
        raise PolicyEvaluationError("INVALID_POLICY_REFERENCE", path=path) from error


def _optional_reference(value: object, path: tuple[str | int, ...]) -> None:
    if value is not None:
        _reference(value, path)


def _scaled(
    value: object,
    path: tuple[str | int, ...],
    *,
    nonnegative: bool = False,
    positive: bool = False,
) -> None:
    if type(value) is not ScaledInteger:
        _fail("INVALID_POLICY_NUMERIC", path)
    if nonnegative and value.units < 0:
        _fail("INVALID_POLICY_NUMERIC", path)
    if positive and value.units <= 0:
        _fail("INVALID_POLICY_NUMERIC", path)


def _typed_canonical(value: object, path: tuple[str | int, ...]) -> bytes:
    try:
        return canonical_bytes(value)
    except CanonicalEncodingError as error:
        raise PolicyEvaluationError("INVALID_POLICY_VALUE", path=path) from error


@dataclass(frozen=True, slots=True)
class GrossReturnEvidence:
    lower_bound: ScaledInteger
    requested_size: ScaledInteger
    distribution_ref: str
    policy_version: str
    boundary_version: str

    def __post_init__(self) -> None:
        _scaled(self.lower_bound, ("gross", "lower_bound"))
        _scaled(self.requested_size, ("gross", "requested_size"), positive=True)
        for name in ("distribution_ref", "policy_version", "boundary_version"):
            _reference(getattr(self, name), ("gross", name))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "lower_bound": self.lower_bound,
            "requested_size": self.requested_size,
            "distribution_ref": self.distribution_ref,
            "policy_version": self.policy_version,
            "boundary_version": self.boundary_version,
        }


@dataclass(frozen=True, slots=True)
class ShortfallComponentEvidence:
    component: ShortfallComponent
    evidence_ref: str

    def __post_init__(self) -> None:
        if type(self.component) is not ShortfallComponent:
            _fail("INVALID_SHORTFALL_COMPONENT", ("shortfall", "components", "component"))
        _reference(self.evidence_ref, ("shortfall", "components", "evidence_ref"))

    def to_canonical_value(self) -> dict[str, str]:
        return {"component": self.component.value, "evidence_ref": self.evidence_ref}


@dataclass(frozen=True, slots=True)
class ShortfallEvidence:
    upper_bound: ScaledInteger
    requested_size: ScaledInteger
    distribution_ref: str
    policy_version: str
    boundary_version: str
    components: tuple[ShortfallComponentEvidence, ...] | list[ShortfallComponentEvidence]

    def __post_init__(self) -> None:
        _scaled(self.upper_bound, ("shortfall", "upper_bound"), nonnegative=True)
        _scaled(self.requested_size, ("shortfall", "requested_size"), positive=True)
        for name in ("distribution_ref", "policy_version", "boundary_version"):
            _reference(getattr(self, name), ("shortfall", name))
        if type(self.components) not in (tuple, list):
            _fail("INVALID_SHORTFALL_COMPONENT", ("shortfall", "components"))
        frozen = tuple(self.components)
        if any(type(item) is not ShortfallComponentEvidence for item in frozen):
            _fail("INVALID_SHORTFALL_COMPONENT", ("shortfall", "components"))
        kinds = tuple(item.component for item in frozen)
        if len(kinds) != len(set(kinds)) or set(kinds) != set(ShortfallComponent):
            _fail("INCOMPLETE_SHORTFALL_COMPONENTS", ("shortfall", "components"))
        ordered = tuple(sorted(frozen, key=lambda item: item.component.value))
        object.__setattr__(self, "components", ordered)

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "upper_bound": self.upper_bound,
            "requested_size": self.requested_size,
            "distribution_ref": self.distribution_ref,
            "policy_version": self.policy_version,
            "boundary_version": self.boundary_version,
            "components": tuple(item.to_canonical_value() for item in self.components),
        }


@dataclass(frozen=True, slots=True)
class CalibrationEvidence:
    status: CalibrationStatus
    reference: str
    horizon_id: str
    policy_version: str
    boundary_version: str

    def __post_init__(self) -> None:
        if type(self.status) is not CalibrationStatus:
            _fail("INVALID_CALIBRATION", ("calibration", "status"))
        for name in ("reference", "horizon_id", "policy_version", "boundary_version"):
            _reference(getattr(self, name), ("calibration", name))

    def to_canonical_value(self) -> dict[str, str]:
        return {
            "status": self.status.value,
            "reference": self.reference,
            "horizon_id": self.horizon_id,
            "policy_version": self.policy_version,
            "boundary_version": self.boundary_version,
        }


@dataclass(frozen=True, slots=True)
class PolicyState:
    policy_version: str
    boundary_version: str
    instrument_id: str
    horizon_id: str
    required_margin: ScaledInteger
    margin_ref: str
    enter_confirmations: int
    alpha_exit_confirmations: int
    last_enter_candidate_ref: str | None
    last_enter_input_ref: str | None
    last_enter_completed: bool
    last_alpha_exit_candidate_ref: str | None
    last_alpha_exit_input_ref: str | None
    last_alpha_exit_completed: bool
    enter_required: int
    protective_exit_required: int
    alpha_exit_required: int
    gap_behavior: GapBehavior
    high_water_ref: str
    protection_ref: str

    def __post_init__(self) -> None:
        for name in (
            "policy_version", "boundary_version", "instrument_id", "horizon_id",
            "margin_ref", "high_water_ref", "protection_ref",
        ):
            _reference(getattr(self, name), ("state", name))
        _scaled(self.required_margin, ("state", "required_margin"), nonnegative=True)
        expected_margin_ref = build_margin_ref(
            self.policy_version, self.boundary_version, self.required_margin
        )
        if self.margin_ref != expected_margin_ref:
            _fail("INVALID_MARGIN_REFERENCE", ("state", "margin_ref"), self.margin_ref)
        for name in (
            "last_enter_candidate_ref", "last_enter_input_ref",
            "last_alpha_exit_candidate_ref", "last_alpha_exit_input_ref",
        ):
            _optional_reference(getattr(self, name), ("state", name))
        for name in ("enter_confirmations", "alpha_exit_confirmations"):
            value = getattr(self, name)
            if (
                type(value) is not int
                or value < 0
                or value.bit_length() > MAX_CANONICAL_INTEGER_BITS
            ):
                _fail("INVALID_CONFIRMATION_STATE", ("state", name))
        if (self.enter_required, self.protective_exit_required, self.alpha_exit_required) != (2, 1, 2):
            _fail("INVALID_CONFIRMATION_POLICY", ("state", "confirmation_policy"))
        if self.enter_confirmations >= self.enter_required:
            _fail("INVALID_CONFIRMATION_STATE", ("state", "enter_confirmations"))
        if self.alpha_exit_confirmations >= self.alpha_exit_required:
            _fail("INVALID_CONFIRMATION_STATE", ("state", "alpha_exit_confirmations"))
        _validate_confirmation_marker(
            self.enter_confirmations, self.last_enter_candidate_ref,
            self.last_enter_input_ref, self.last_enter_completed,
            ("state", "last_enter_candidate_ref"),
        )
        _validate_confirmation_marker(
            self.alpha_exit_confirmations, self.last_alpha_exit_candidate_ref,
            self.last_alpha_exit_input_ref, self.last_alpha_exit_completed,
            ("state", "last_alpha_exit_candidate_ref"),
        )
        if type(self.gap_behavior) is not GapBehavior:
            _fail("INVALID_GAP_BEHAVIOR", ("state", "gap_behavior"))
        _typed_canonical(self.to_canonical_value(), ("state",))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": "policy-state:v1",
            "policy_version": self.policy_version,
            "boundary_version": self.boundary_version,
            "instrument_id": self.instrument_id,
            "horizon_id": self.horizon_id,
            "required_margin": self.required_margin,
            "margin_ref": self.margin_ref,
            "enter_confirmations": self.enter_confirmations,
            "alpha_exit_confirmations": self.alpha_exit_confirmations,
            "last_enter_candidate_ref": self.last_enter_candidate_ref,
            "last_enter_input_ref": self.last_enter_input_ref,
            "last_enter_completed": self.last_enter_completed,
            "last_alpha_exit_candidate_ref": self.last_alpha_exit_candidate_ref,
            "last_alpha_exit_input_ref": self.last_alpha_exit_input_ref,
            "last_alpha_exit_completed": self.last_alpha_exit_completed,
            "enter_required": self.enter_required,
            "protective_exit_required": self.protective_exit_required,
            "alpha_exit_required": self.alpha_exit_required,
            "gap_behavior": self.gap_behavior.value,
            "high_water_ref": self.high_water_ref,
            "protection_ref": self.protection_ref,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


def _validate_confirmation_marker(count, candidate_ref, input_ref, completed, path) -> None:
    if type(completed) is not bool:
        _fail("INVALID_CONFIRMATION_STATE", path)
    has_marker = candidate_ref is not None and input_ref is not None
    if (count > 0 or completed) and not has_marker:
        _fail("INVALID_CONFIRMATION_STATE", path)
    if completed and count != 0:
        _fail("INVALID_CONFIRMATION_STATE", path)
    if (candidate_ref is None) != (input_ref is None):
        _fail("INVALID_CONFIRMATION_STATE", path)


def build_margin_ref(
    policy_version: str, boundary_version: str, required_margin: ScaledInteger
) -> str:
    """Bind a preregistered exact margin to its policy and boundary versions."""

    _reference(policy_version, ("margin", "policy_version"))
    _reference(boundary_version, ("margin", "boundary_version"))
    _scaled(required_margin, ("margin", "required_margin"), nonnegative=True)
    value = {
        "domain": "autotrade-next.policy-margin",
        "version": 1,
        "policy_version": policy_version,
        "boundary_version": boundary_version,
        "required_margin": required_margin,
    }
    return f"policy-margin:v1:{sha256(_typed_canonical(value, ('margin',))).hexdigest()}"


@dataclass(frozen=True, slots=True)
class PolicyTransition:
    prior_state: PolicyState
    next_state: PolicyState
    conservative_edge: ScaledInteger | None
    decision: CanonicalDecision

    def __post_init__(self) -> None:
        if type(self.prior_state) is not PolicyState or type(self.next_state) is not PolicyState:
            _fail("INVALID_POLICY_TRANSITION", ("transition", "state"))
        if self.conservative_edge is not None:
            _scaled(self.conservative_edge, ("transition", "conservative_edge"))
            if self.conservative_edge.scale != self.prior_state.required_margin.scale:
                _fail("POLICY_SCALE_MISMATCH", ("transition", "conservative_edge"))
        if type(self.decision) is not CanonicalDecision:
            _fail("INVALID_POLICY_TRANSITION", ("transition", "decision"))
        invariant_fields = (
            "policy_version", "boundary_version", "instrument_id", "horizon_id",
            "required_margin", "margin_ref", "enter_required", "protective_exit_required",
            "alpha_exit_required", "gap_behavior", "high_water_ref", "protection_ref",
        )
        if any(getattr(self.prior_state, name) != getattr(self.next_state, name) for name in invariant_fields):
            _fail("POLICY_STATE_INVARIANT_CHANGED", ("transition", "next_state"))
        if self.decision.policy_version != self.prior_state.policy_version:
            _fail("POLICY_VERSION_MISMATCH", ("transition", "decision", "policy_version"))
        if self.decision.boundary.version != self.prior_state.boundary_version:
            _fail("POLICY_BOUNDARY_MISMATCH", ("transition", "decision", "boundary"))
        _typed_canonical(self.to_canonical_value(), ("transition",))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": "policy-transition:v1",
            "prior_state": self.prior_state.to_canonical_value(),
            "next_state": self.next_state.to_canonical_value(),
            "conservative_edge": self.conservative_edge,
            "decision": self.decision.to_canonical_value(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


def evaluate_policy_transition(
    candidate: CandidateSnapshot,
    *,
    position: PositionContext,
    proposed_action: DecisionAction,
    boundary: DecisionBoundary,
    state: PolicyState,
    gross: GrossReturnEvidence | None = None,
    shortfall: ShortfallEvidence | None = None,
    calibration: CalibrationEvidence | None = None,
    data_gap: bool = False,
    protective_exit: bool = False,
    exit_target: ScaledInteger | None = None,
    candidate_use: CandidateUse = CandidateUse.LIVE_ADMISSION,
) -> PolicyTransition:
    """Apply one deterministic cost/confirmation transition and legalize its action."""

    _validate_inputs(candidate, position, proposed_action, boundary, state, data_gap, protective_exit)
    if type(candidate_use) is not CandidateUse:
        _fail("INVALID_CANDIDATE_USE", ("candidate_use",))
    if protective_exit:
        if candidate.trigger_kind is not CandidateTrigger.PROTECTIVE_EVENT:
            _fail("INVALID_PROTECTIVE_TRIGGER", ("candidate", "trigger_kind"), candidate.candidate_id.key)
        decision = evaluate_decision(
            candidate, policy_version=state.policy_version, position=position,
            proposed_action=proposed_action, boundary=boundary, protective_exit=True,
            exit_target=exit_target,
        )
        return PolicyTransition(state, state, None, decision)
    if (
        position.state is PositionState.FLAT
        and proposed_action is DecisionAction.ENTER
        and not candidate.is_proof_bearing
        and candidate_use is CandidateUse.LIVE_ADMISSION
    ):
        next_state = _reset_enter(state)
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, next_state,
            None, DecisionReasonCode.CANDIDATE_INELIGIBLE, (),
        )
    if position.state is PositionState.EXPOSED:
        return _evaluate_exposed(candidate, position, proposed_action, boundary, state, data_gap, exit_target)
    return _evaluate_flat(
        candidate, position, proposed_action, boundary, state,
        gross, shortfall, calibration, data_gap, candidate_use,
    )


def _validate_inputs(candidate, position, proposed_action, boundary, state, data_gap, protective_exit) -> None:
    if type(candidate) is not CandidateSnapshot:
        _fail("INVALID_POLICY_INPUT", ("candidate",))
    if type(position) is not PositionContext or type(boundary) is not DecisionBoundary:
        _fail("INVALID_POLICY_INPUT")
    if type(proposed_action) is not DecisionAction:
        _fail("INVALID_POLICY_INPUT", ("proposed_action",))
    if type(state) is not PolicyState:
        _fail("INVALID_POLICY_INPUT", ("state",))
    if type(data_gap) is not bool or type(protective_exit) is not bool:
        _fail("INVALID_POLICY_INPUT")
    if state.boundary_version != boundary.version:
        _fail("POLICY_BOUNDARY_MISMATCH", ("state", "boundary_version"), boundary.reference)
    if (candidate.instrument_id, candidate.horizon_id) != (state.instrument_id, state.horizon_id):
        _fail("POLICY_SCOPE_MISMATCH", ("candidate", "instrument_id"), candidate.candidate_id.key)


def _evaluate_flat(candidate, position, proposed_action, boundary, state, gross, shortfall, calibration, data_gap,
                   candidate_use):
    input_ref = _enter_input_ref(gross, shortfall, calibration, data_gap, boundary)
    if state.last_enter_candidate_ref == candidate.candidate_id.key:
        if state.last_enter_input_ref != input_ref:
            _fail("DUPLICATE_POLICY_INPUT_MISMATCH", ("gross",), candidate.candidate_id.key)
        edge, evidence = _validated_cost(candidate, boundary, state, gross, shortfall, calibration)
        if state.last_enter_completed:
            return _transition(
                candidate, position, DecisionAction.ENTER, boundary, state, state,
                edge, None, evidence, candidate_use=candidate_use,
            )
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, state, edge,
            DecisionReasonCode.ENTER_CONFIRMATION_PENDING, evidence,
        )
    if proposed_action is not DecisionAction.ENTER:
        next_state = _reset_enter(state)
        return _transition(candidate, position, proposed_action, boundary, state, next_state, None, None, ())
    if not candidate.executable:
        next_state = _reset_enter(state)
        evidence = (candidate.provenance.eligibility.evidence_ref,)
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, next_state, None,
            DecisionReasonCode.CANDIDATE_INELIGIBLE, evidence,
        )
    if data_gap:
        next_state = _reset_enter(state)
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, next_state, None,
            DecisionReasonCode.DATA_GAP, (boundary.reference,),
        )
    if calibration is None:
        next_state = _reset_enter(state)
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, next_state, None,
            DecisionReasonCode.CALIBRATION_MISSING, (boundary.reference,),
        )
    _validate_calibration(candidate, boundary, state, calibration)
    if calibration.status is CalibrationStatus.STALE:
        next_state = _reset_enter(state)
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, next_state, None,
            DecisionReasonCode.CALIBRATION_STALE, (calibration.reference,),
        )
    edge, evidence = _validated_cost(candidate, boundary, state, gross, shortfall, calibration)
    if edge.units <= state.required_margin.units:
        next_state = _reset_enter(state)
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, next_state, edge,
            DecisionReasonCode.COST_MARGIN_NOT_MET, evidence,
        )
    if candidate.trigger_kind is not CandidateTrigger.CLOSED_BAR:
        _fail("INVALID_CONFIRMATION_TRIGGER", ("candidate", "trigger_kind"), candidate.candidate_id.key)
    count = state.enter_confirmations + 1
    if count < state.enter_required:
        next_state = replace(
            state, enter_confirmations=count, last_enter_candidate_ref=candidate.candidate_id.key,
            last_enter_input_ref=input_ref, last_enter_completed=False,
        )
        return _transition(
            candidate, position, DecisionAction.ABSTAIN, boundary, state, next_state, edge,
            DecisionReasonCode.ENTER_CONFIRMATION_PENDING, evidence,
        )
    next_state = replace(
        state, enter_confirmations=0, last_enter_candidate_ref=candidate.candidate_id.key,
        last_enter_input_ref=input_ref, last_enter_completed=True,
    )
    return _transition(
        candidate, position, DecisionAction.ENTER, boundary, state, next_state,
        edge, None, evidence, candidate_use=candidate_use,
    )


def _evaluate_exposed(candidate, position, proposed_action, boundary, state, data_gap, exit_target):
    input_ref = _alpha_input_ref(proposed_action, exit_target, data_gap, boundary)
    if state.last_alpha_exit_candidate_ref == candidate.candidate_id.key:
        if state.last_alpha_exit_input_ref != input_ref:
            _fail("DUPLICATE_POLICY_INPUT_MISMATCH", ("exit_target",), candidate.candidate_id.key)
        if state.last_alpha_exit_completed:
            return _transition(
                candidate, position, DecisionAction.EXIT, boundary, state, state, None, None,
                (boundary.reference,), exit_target=exit_target,
            )
        return _transition(
            candidate, position, DecisionAction.HOLD, boundary, state, state, None,
            DecisionReasonCode.ALPHA_EXIT_CONFIRMATION_PENDING, (boundary.reference,),
        )
    if data_gap:
        return _transition(
            candidate, position, DecisionAction.HOLD, boundary, state, state, None,
            DecisionReasonCode.DATA_GAP, (boundary.reference,),
        )
    if proposed_action is DecisionAction.EXIT:
        if candidate.trigger_kind is not CandidateTrigger.CLOSED_BAR:
            _fail("INVALID_CONFIRMATION_TRIGGER", ("candidate", "trigger_kind"), candidate.candidate_id.key)
        count = state.alpha_exit_confirmations + 1
        if count < state.alpha_exit_required:
            next_state = replace(
                state, alpha_exit_confirmations=count,
                last_alpha_exit_candidate_ref=candidate.candidate_id.key,
                last_alpha_exit_input_ref=input_ref, last_alpha_exit_completed=False,
            )
            return _transition(
                candidate, position, DecisionAction.HOLD, boundary, state, next_state, None,
                DecisionReasonCode.ALPHA_EXIT_CONFIRMATION_PENDING, (boundary.reference,),
            )
        next_state = replace(
            state, alpha_exit_confirmations=0,
            last_alpha_exit_candidate_ref=candidate.candidate_id.key,
            last_alpha_exit_input_ref=input_ref, last_alpha_exit_completed=True,
        )
        return _transition(
            candidate, position, DecisionAction.EXIT, boundary, state, next_state, None, None,
            (boundary.reference,), exit_target=exit_target,
        )
    next_state = _reset_alpha_exit(state)
    return _transition(candidate, position, proposed_action, boundary, state, next_state, None, None, ())


def _validated_cost(candidate, boundary, state, gross, shortfall, calibration):
    _validate_calibration(candidate, boundary, state, calibration)
    if type(gross) is not GrossReturnEvidence:
        _fail("MISSING_GROSS_EVIDENCE", ("gross",))
    if type(shortfall) is not ShortfallEvidence:
        _fail("MISSING_SHORTFALL_EVIDENCE", ("shortfall",))
    version_fields = (
        gross.policy_version, shortfall.policy_version, calibration.policy_version,
        state.policy_version,
    )
    if len(set(version_fields)) != 1:
        _fail("POLICY_VERSION_MISMATCH", ("gross", "policy_version"))
    boundary_fields = (
        gross.boundary_version, shortfall.boundary_version,
        calibration.boundary_version, state.boundary_version,
    )
    if len(set(boundary_fields)) != 1:
        _fail("POLICY_BOUNDARY_MISMATCH", ("gross", "boundary_version"))
    if gross.requested_size != shortfall.requested_size:
        _fail("REQUESTED_SIZE_MISMATCH", ("shortfall", "requested_size"))
    scales = {
        gross.lower_bound.scale, gross.requested_size.scale,
        shortfall.upper_bound.scale, shortfall.requested_size.scale,
        state.required_margin.scale,
    }
    if len(scales) != 1:
        _fail("POLICY_SCALE_MISMATCH", ("state", "required_margin"))
    units = gross.lower_bound.units - shortfall.upper_bound.units
    if abs(units).bit_length() > MAX_CANONICAL_INTEGER_BITS:
        _fail("INVALID_POLICY_NUMERIC", ("conservative_edge",))
    edge = ScaledInteger(units, state.required_margin.scale)
    return edge, _cost_evidence_refs(gross, shortfall, calibration, state)


def _validate_calibration(candidate, boundary, state, calibration) -> None:
    if type(calibration) is not CalibrationEvidence:
        _fail("INVALID_CALIBRATION", ("calibration",))
    if calibration.horizon_id != candidate.horizon_id:
        _fail("CALIBRATION_HORIZON_MISMATCH", ("calibration", "horizon_id"), calibration.reference)
    if calibration.policy_version != state.policy_version:
        _fail("POLICY_VERSION_MISMATCH", ("calibration", "policy_version"), calibration.reference)
    if calibration.boundary_version != boundary.version:
        _fail("CALIBRATION_BOUNDARY_MISMATCH", ("calibration", "boundary_version"), calibration.reference)


def _cost_evidence_refs(gross, shortfall, calibration, state) -> tuple[str, ...]:
    return (
        gross.distribution_ref, shortfall.distribution_ref, calibration.reference,
        state.margin_ref, *(item.evidence_ref for item in shortfall.components),
    )


def _enter_input_ref(gross, shortfall, calibration, data_gap, boundary) -> str:
    value = {
        "domain": "autotrade-next.enter-policy-input", "version": 1,
        "gross": None if gross is None else _canonical_member(gross, "gross"),
        "shortfall": None if shortfall is None else _canonical_member(shortfall, "shortfall"),
        "calibration": None if calibration is None else _canonical_member(calibration, "calibration"),
        "data_gap": data_gap, "boundary": boundary.to_canonical_value(),
    }
    return f"policy-input:v1:{sha256(_typed_canonical(value, ('policy_input',))).hexdigest()}"


def _alpha_input_ref(action, exit_target, data_gap, boundary) -> str:
    value = {
        "domain": "autotrade-next.alpha-exit-input", "version": 1,
        "action": action, "exit_target": exit_target, "data_gap": data_gap,
        "boundary": boundary.to_canonical_value(),
    }
    return f"policy-input:v1:{sha256(_typed_canonical(value, ('policy_input',))).hexdigest()}"


def _canonical_member(value, name):
    method = getattr(value, "to_canonical_value", None)
    if not callable(method):
        _fail("INVALID_POLICY_INPUT", (name,))
    return method()


def _reset_enter(state):
    return replace(
        state, enter_confirmations=0, last_enter_candidate_ref=None,
        last_enter_input_ref=None, last_enter_completed=False,
    )


def _reset_alpha_exit(state):
    return replace(
        state, alpha_exit_confirmations=0, last_alpha_exit_candidate_ref=None,
        last_alpha_exit_input_ref=None, last_alpha_exit_completed=False,
    )


def _transition(candidate, position, action, boundary, prior, next_state, edge, reason, evidence,
                *, exit_target=None, candidate_use=CandidateUse.LIVE_ADMISSION) -> PolicyTransition:
    decision = evaluate_decision(
        candidate, policy_version=prior.policy_version, position=position,
        proposed_action=action, boundary=boundary, exit_target=exit_target,
        reason_override=reason, reason_evidence_refs=evidence,
        candidate_use=candidate_use,
    )
    return PolicyTransition(prior, next_state, edge, decision)


__all__ = (
    "CalibrationEvidence", "CalibrationStatus", "GapBehavior", "GrossReturnEvidence",
    "PolicyEvaluationError", "PolicyState", "PolicyTransition", "ShortfallComponent",
    "ShortfallComponentEvidence", "ShortfallEvidence", "build_margin_ref",
    "evaluate_policy_transition",
)
