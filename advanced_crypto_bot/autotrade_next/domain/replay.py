"""Deterministic decision replay contracts and semantic comparison."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from .candidate import CandidateSnapshot, CandidateTrigger, CandidateUse, ClockRead, SourceCursor, StableRef
from .content import ContentRef
from .decision import DecisionAction, DecisionBoundary, PositionContext
from .encoding import canonical_bytes
from .errors import CanonicalEncodingError, DecisionError, PolicyEvaluationError, ReplayError
from .numeric import ScaledInteger
from .policy import (
    CalibrationEvidence,
    GrossReturnEvidence,
    PolicyState,
    PolicyTransition,
    ShortfallEvidence,
    evaluate_policy_transition,
)


class ReplayMode(str, Enum):
    CANONICAL_STATE_REHYDRATION = "CANONICAL_STATE_REHYDRATION"
    DECISION_LIFECYCLE_REGENERATION = "DECISION_LIFECYCLE_REGENERATION"
    PROJECTION_REBUILD = "PROJECTION_REBUILD"


_MANIFEST_VERSION = "replay-manifest:v1"
_BUNDLE_VERSION = "decision-replay-bundle:v1"
_SEMANTIC_VERSION = "replay-semantic:v1"
_ALLOWED_EXCLUSIONS = frozenset(
    ("observability.run_ref", "observability.trace_ref")
)


def _fail(code: str, path: tuple[str | int, ...] = ()) -> None:
    raise ReplayError(code, path=path)


def _reference(value: object, path: tuple[str | int, ...]) -> None:
    if type(value) is not str or not value or not value.strip():
        _fail("MISSING_REPLAY_REFERENCE", path)
    try:
        canonical_bytes(value)
    except CanonicalEncodingError as error:
        raise ReplayError("INVALID_REPLAY_REFERENCE", path=path) from error


def _references(
    value: object,
    path: tuple[str | int, ...],
    *,
    nonempty: bool,
) -> tuple[str, ...]:
    if type(value) not in (tuple, list):
        _fail("UNORDERED_REPLAY_REFERENCES", path)
    frozen = tuple(value)
    if nonempty and not frozen:
        _fail("MISSING_REPLAY_REFERENCE", path)
    for index, item in enumerate(frozen):
        _reference(item, (*path, index))
    if len(frozen) != len(set(frozen)):
        _fail("DUPLICATE_REPLAY_REFERENCE", path)
    return frozen


def _typed_canonical(value: object, path: tuple[str | int, ...]) -> bytes:
    try:
        return canonical_bytes(value)
    except CanonicalEncodingError as error:
        raise ReplayError("INVALID_REPLAY_VALUE", path=path) from error


def _content_ref(kind: str, value: object) -> str:
    return ContentRef.v1(kind, value).key


def stable_ref_key(value: StableRef) -> str:
    if type(value) is not StableRef:
        _fail("INVALID_REPLAY_REFERENCE", ("stable_ref",))
    return f"{value.kind}:{value.value}"


def source_cursor_ref(value: SourceCursor) -> str:
    if type(value) is not SourceCursor:
        _fail("INVALID_REPLAY_REFERENCE", ("source_cursor",))
    return _content_ref("source-cursor", value.to_canonical_value())


def clock_read_ref(value: ClockRead) -> str:
    if type(value) is not ClockRead:
        _fail("INVALID_REPLAY_REFERENCE", ("clock_read",))
    return _content_ref("clock-read", value.to_canonical_value())


def policy_state_ref(value: PolicyState) -> str:
    if type(value) is not PolicyState:
        _fail("INVALID_REPLAY_REFERENCE", ("policy_state",))
    return _content_ref("policy-state", value.to_canonical_value())


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    version: str
    ordered_input_ids: tuple[str, ...] | list[str]
    market_snapshot_ref: str
    universe_ref: str
    initial_portfolio_state_ref: str
    initial_risk_state_ref: str
    cursor_refs: tuple[str, ...] | list[str]
    fee_rules_ref: str
    instrument_rules_ref: str
    strategy_ref: str
    model_ref: str
    calibrator_ref: str
    simulator_ref: str
    cost_model_ref: str
    config_ref: str
    schema_ref: str
    code_commit_ref: str
    image_digest_ref: str
    dependency_lock_ref: str
    runtime_numeric_ref: str
    rng_algorithm: str
    rng_state_ref: str
    clock_refs: tuple[str, ...] | list[str]
    external_response_refs: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        if self.version != _MANIFEST_VERSION:
            _fail("UNSUPPORTED_REPLAY_MANIFEST_VERSION", ("manifest", "version"))
        object.__setattr__(
            self,
            "ordered_input_ids",
            _references(self.ordered_input_ids, ("manifest", "ordered_input_ids"), nonempty=True),
        )
        object.__setattr__(
            self,
            "cursor_refs",
            _references(self.cursor_refs, ("manifest", "cursor_refs"), nonempty=True),
        )
        object.__setattr__(
            self,
            "clock_refs",
            _references(self.clock_refs, ("manifest", "clock_refs"), nonempty=True),
        )
        object.__setattr__(
            self,
            "external_response_refs",
            _references(
                self.external_response_refs,
                ("manifest", "external_response_refs"),
                nonempty=False,
            ),
        )
        for name in (
            "market_snapshot_ref", "universe_ref", "initial_portfolio_state_ref",
            "initial_risk_state_ref", "fee_rules_ref", "instrument_rules_ref",
            "strategy_ref", "model_ref", "calibrator_ref", "simulator_ref",
            "cost_model_ref", "config_ref", "schema_ref", "code_commit_ref",
            "image_digest_ref", "dependency_lock_ref", "runtime_numeric_ref",
            "rng_algorithm", "rng_state_ref",
        ):
            _reference(getattr(self, name), ("manifest", name))
        _typed_canonical(self.to_canonical_value(), ("manifest",))

    @property
    def manifest_ref(self) -> str:
        digest = sha256(self.canonical_bytes()).hexdigest()
        return f"replay-manifest:v1:{digest}"

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": self.version,
            "ordered_input_ids": self.ordered_input_ids,
            "market_snapshot_ref": self.market_snapshot_ref,
            "universe_ref": self.universe_ref,
            "initial_portfolio_state_ref": self.initial_portfolio_state_ref,
            "initial_risk_state_ref": self.initial_risk_state_ref,
            "cursor_refs": self.cursor_refs,
            "fee_rules_ref": self.fee_rules_ref,
            "instrument_rules_ref": self.instrument_rules_ref,
            "strategy_ref": self.strategy_ref,
            "model_ref": self.model_ref,
            "calibrator_ref": self.calibrator_ref,
            "simulator_ref": self.simulator_ref,
            "cost_model_ref": self.cost_model_ref,
            "config_ref": self.config_ref,
            "schema_ref": self.schema_ref,
            "code_commit_ref": self.code_commit_ref,
            "image_digest_ref": self.image_digest_ref,
            "dependency_lock_ref": self.dependency_lock_ref,
            "runtime_numeric_ref": self.runtime_numeric_ref,
            "rng_algorithm": self.rng_algorithm,
            "rng_state_ref": self.rng_state_ref,
            "clock_refs": self.clock_refs,
            "external_response_refs": self.external_response_refs,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class DecisionReplayBundle:
    version: str
    manifest: ReplayManifest
    candidate: CandidateSnapshot
    initial_policy_state: PolicyState
    position: PositionContext
    proposed_action: DecisionAction
    boundary: DecisionBoundary
    gross: GrossReturnEvidence | None
    shortfall: ShortfallEvidence | None
    calibration: CalibrationEvidence | None
    data_gap: bool
    protective_exit: bool
    exit_target: ScaledInteger | None

    def __post_init__(self) -> None:
        if self.version != _BUNDLE_VERSION:
            _fail("UNSUPPORTED_REPLAY_BUNDLE_VERSION", ("bundle", "version"))
        for name, expected in (
            ("manifest", ReplayManifest), ("candidate", CandidateSnapshot),
            ("initial_policy_state", PolicyState), ("position", PositionContext),
            ("proposed_action", DecisionAction), ("boundary", DecisionBoundary),
        ):
            if type(getattr(self, name)) is not expected:
                _fail("INVALID_REPLAY_BUNDLE", ("bundle", name))
        for name, expected in (
            ("gross", GrossReturnEvidence), ("shortfall", ShortfallEvidence),
            ("calibration", CalibrationEvidence),
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not expected:
                _fail("INVALID_REPLAY_BUNDLE", ("bundle", name))
        if type(self.data_gap) is not bool or type(self.protective_exit) is not bool:
            _fail("INVALID_REPLAY_BUNDLE", ("bundle", "flags"))
        if self.exit_target is not None and type(self.exit_target) is not ScaledInteger:
            _fail("INVALID_REPLAY_BUNDLE", ("bundle", "exit_target"))
        if self.manifest.ordered_input_ids != self.candidate.provenance.ordered_input_ids:
            _fail("REPLAY_ORDERED_INPUT_MISMATCH", ("bundle", "manifest", "ordered_input_ids"))
        if (
            self.initial_policy_state.instrument_id != self.candidate.instrument_id
            or self.initial_policy_state.horizon_id != self.candidate.horizon_id
        ):
            _fail("REPLAY_SCOPE_MISMATCH", ("bundle", "initial_policy_state"))
        if self.initial_policy_state.boundary_version != self.boundary.version:
            _fail("REPLAY_BOUNDARY_MISMATCH", ("bundle", "boundary"))
        provenance = self.candidate.provenance
        manifest_bindings = (
            ("market_snapshot_ref", stable_ref_key(provenance.data_ref)),
            ("universe_ref", stable_ref_key(provenance.universe_ref)),
            ("initial_portfolio_state_ref", self.position.snapshot_ref),
            ("initial_risk_state_ref", policy_state_ref(self.initial_policy_state)),
            ("instrument_rules_ref", stable_ref_key(provenance.instrument_rules_ref)),
            ("strategy_ref", provenance.strategy_version),
            ("model_ref", stable_ref_key(provenance.model_ref)),
            ("config_ref", stable_ref_key(provenance.config_ref)),
            ("code_commit_ref", provenance.runtime_ref.code_commit),
            ("image_digest_ref", provenance.runtime_ref.image_digest),
            ("dependency_lock_ref", provenance.runtime_ref.dependency_lock_ref),
            ("runtime_numeric_ref", provenance.runtime_ref.numeric_version),
            ("rng_algorithm", provenance.rng_ref.algorithm),
            ("rng_state_ref", provenance.rng_ref.state_ref),
        )
        for name, expected in manifest_bindings:
            if getattr(self.manifest, name) != expected:
                _fail("REPLAY_MANIFEST_MISMATCH", ("bundle", "manifest", name))
        expected_cursors = tuple(source_cursor_ref(item) for item in provenance.source_cursors)
        if self.manifest.cursor_refs != expected_cursors:
            _fail("REPLAY_MANIFEST_MISMATCH", ("bundle", "manifest", "cursor_refs"))
        expected_clocks = tuple(clock_read_ref(item) for item in provenance.clock_reads)
        if self.manifest.clock_refs != expected_clocks:
            _fail("REPLAY_MANIFEST_MISMATCH", ("bundle", "manifest", "clock_refs"))
        for name in ("gross", "shortfall", "calibration"):
            evidence = getattr(self, name)
            if evidence is None:
                continue
            if evidence.policy_version != self.initial_policy_state.policy_version:
                _fail("REPLAY_POLICY_VERSION_MISMATCH", ("bundle", name, "policy_version"))
            if evidence.boundary_version != self.boundary.version:
                _fail("REPLAY_BOUNDARY_MISMATCH", ("bundle", name, "boundary_version"))
        if (
            self.protective_exit
            and self.candidate.trigger_kind is not CandidateTrigger.PROTECTIVE_EVENT
        ):
            _fail("REPLAY_PROTECTIVE_MISMATCH", ("bundle", "protective_exit"))
        if self.manifest.external_response_refs != self.candidate.provenance.external_response_ids:
            _fail("REPLAY_MANIFEST_MISMATCH", ("bundle", "manifest", "external_response_refs"))
        _typed_canonical(self.to_canonical_value(), ("bundle",))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": self.version,
            "manifest": self.manifest.to_canonical_value(),
            "candidate": self.candidate.to_canonical_value(),
            "initial_policy_state": self.initial_policy_state.to_canonical_value(),
            "position": self.position.to_canonical_value(),
            "proposed_action": self.proposed_action.value,
            "boundary": self.boundary.to_canonical_value(),
            "gross": None if self.gross is None else self.gross.to_canonical_value(),
            "shortfall": None if self.shortfall is None else self.shortfall.to_canonical_value(),
            "calibration": None if self.calibration is None else self.calibration.to_canonical_value(),
            "data_gap": self.data_gap,
            "protective_exit": self.protective_exit,
            "exit_target": self.exit_target,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class ReplayObservability:
    run_ref: str
    trace_ref: str

    def __post_init__(self) -> None:
        _reference(self.run_ref, ("observability", "run_ref"))
        _reference(self.trace_ref, ("observability", "trace_ref"))

    def to_canonical_value(self) -> dict[str, str]:
        return {"run_ref": self.run_ref, "trace_ref": self.trace_ref}


@dataclass(frozen=True, slots=True)
class ReplayResult:
    mode: ReplayMode
    manifest_ref: str
    transition: PolicyTransition
    external_call_count: int
    observability: ReplayObservability

    def __post_init__(self) -> None:
        if self.mode is not ReplayMode.DECISION_LIFECYCLE_REGENERATION:
            _fail("UNSUPPORTED_REPLAY_MODE", ("result", "mode"))
        _reference(self.manifest_ref, ("result", "manifest_ref"))
        if type(self.transition) is not PolicyTransition:
            _fail("INVALID_REPLAY_RESULT", ("result", "transition"))
        if type(self.external_call_count) is not int or self.external_call_count != 0:
            _fail("EXTERNAL_CALL_DURING_REPLAY", ("result", "external_call_count"))
        if type(self.observability) is not ReplayObservability:
            _fail("INVALID_REPLAY_RESULT", ("result", "observability"))
        _typed_canonical(self.to_canonical_value(), ("result",))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "schema_version": "replay-result:v1",
            "mode": self.mode.value,
            "manifest_ref": self.manifest_ref,
            "transition": self.transition.to_canonical_value(),
            "external_call_count": self.external_call_count,
            "observability": self.observability.to_canonical_value(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class SemanticProjectionProfile:
    version: str
    excluded_paths: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        if self.version != _SEMANTIC_VERSION:
            _fail("UNSUPPORTED_SEMANTIC_PROJECTION_VERSION", ("profile", "version"))
        frozen = _references(
            self.excluded_paths, ("profile", "excluded_paths"), nonempty=False
        )
        if any(item not in _ALLOWED_EXCLUSIONS for item in frozen):
            _fail("FORBIDDEN_SEMANTIC_EXCLUSION", ("profile", "excluded_paths"))
        object.__setattr__(self, "excluded_paths", tuple(sorted(frozen)))


@dataclass(frozen=True, slots=True)
class SemanticDiff:
    path: tuple[str | int, ...]
    expected: object
    actual: object
    expected_present: bool = True
    actual_present: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.path) is not tuple
            or any(type(item) not in (str, int) for item in self.path)
            or type(self.expected_present) is not bool
            or type(self.actual_present) is not bool
            or (not self.expected_present and not self.actual_present)
        ):
            _fail("INVALID_SEMANTIC_DIFF", ("diff",))
        _typed_canonical(self.to_canonical_value(), ("diff",))

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "path": self.path,
            "expected_present": self.expected_present,
            "expected": self.expected if self.expected_present else None,
            "actual_present": self.actual_present,
            "actual": self.actual if self.actual_present else None,
        }


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    matches: bool
    profile_version: str
    expected_hash: str
    actual_hash: str
    diffs: tuple[SemanticDiff, ...]

    def __post_init__(self) -> None:
        if (
            type(self.matches) is not bool
            or self.profile_version != _SEMANTIC_VERSION
            or type(self.diffs) is not tuple
            or any(type(item) is not SemanticDiff for item in self.diffs)
            or not _is_semantic_hash(self.expected_hash)
            or not _is_semantic_hash(self.actual_hash)
        ):
            _fail("INVALID_REPLAY_COMPARISON", ("comparison",))
        if self.matches != (not self.diffs and self.expected_hash == self.actual_hash):
            _fail("INVALID_REPLAY_COMPARISON", ("comparison", "matches"))


def regenerate_replay(
    bundle: DecisionReplayBundle,
    mode: ReplayMode,
    observability: ReplayObservability,
) -> ReplayResult:
    """Regenerate a decision transition using recorded inputs and no external ports."""

    if type(bundle) is not DecisionReplayBundle:
        _fail("INVALID_REPLAY_BUNDLE", ("bundle",))
    if type(mode) is not ReplayMode:
        _fail("INVALID_REPLAY_MODE", ("mode",))
    if mode is not ReplayMode.DECISION_LIFECYCLE_REGENERATION:
        _fail("UNSUPPORTED_REPLAY_MODE", ("mode",))
    if type(observability) is not ReplayObservability:
        _fail("INVALID_REPLAY_OBSERVABILITY", ("observability",))
    try:
        transition = evaluate_policy_transition(
            bundle.candidate,
            position=bundle.position,
            proposed_action=bundle.proposed_action,
            boundary=bundle.boundary,
            state=bundle.initial_policy_state,
            gross=bundle.gross,
            shortfall=bundle.shortfall,
            calibration=bundle.calibration,
            data_gap=bundle.data_gap,
            protective_exit=bundle.protective_exit,
            exit_target=bundle.exit_target,
            candidate_use=CandidateUse.HISTORICAL_REPLAY,
        )
    except (PolicyEvaluationError, DecisionError) as error:
        raise ReplayError(
            "REPLAY_REGENERATION_REJECTED", path=("bundle", *error.path)
        ) from error
    return ReplayResult(mode, bundle.manifest.manifest_ref, transition, 0, observability)


def semantic_projection(
    result: ReplayResult, profile: SemanticProjectionProfile
) -> dict[str, object]:
    if type(result) is not ReplayResult or type(profile) is not SemanticProjectionProfile:
        _fail("INVALID_SEMANTIC_PROJECTION_INPUT")
    value = result.to_canonical_value()
    for path in profile.excluded_paths:
        parent, field = path.split(".")
        del value[parent][field]
    value["schema_version"] = profile.version
    return value


def semantic_hash(result: ReplayResult, profile: SemanticProjectionProfile) -> str:
    digest = sha256(canonical_bytes(semantic_projection(result, profile))).hexdigest()
    return f"replay-semantic:v1:{digest}"


def _is_semantic_hash(value: object) -> bool:
    prefix = "replay-semantic:v1:"
    if type(value) is not str or not value.startswith(prefix):
        return False
    digest = value[len(prefix):]
    return len(digest) == 64 and all(item in "0123456789abcdef" for item in digest)


def compare_replay_results(
    expected: ReplayResult,
    actual: ReplayResult,
    profile: SemanticProjectionProfile,
) -> ReplayComparison:
    expected_value = semantic_projection(expected, profile)
    actual_value = semantic_projection(actual, profile)
    diffs = tuple(_diff(expected_value, actual_value, ()))
    expected_digest = semantic_hash(expected, profile)
    actual_digest = semantic_hash(actual, profile)
    return ReplayComparison(
        not diffs and expected_digest == actual_digest,
        profile.version,
        expected_digest,
        actual_digest,
        diffs,
    )


def _diff(expected: object, actual: object, path: tuple[str | int, ...]):
    if type(expected) is not type(actual):
        yield SemanticDiff(path, expected, actual)
        return
    if isinstance(expected, Mapping):
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            if key not in expected:
                yield SemanticDiff((*path, key), None, actual[key], False, True)
            elif key not in actual:
                yield SemanticDiff((*path, key), expected[key], None, True, False)
            else:
                yield from _diff(expected[key], actual[key], (*path, key))
        return
    if type(expected) in (tuple, list):
        if len(expected) != len(actual):
            yield SemanticDiff(path, expected, actual)
            return
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            yield from _diff(left, right, (*path, index))
        return
    if expected != actual:
        yield SemanticDiff(path, expected, actual)


__all__ = (
    "DecisionReplayBundle", "ReplayComparison", "ReplayError", "ReplayManifest",
    "ReplayMode", "ReplayObservability", "ReplayResult", "SemanticDiff",
    "SemanticProjectionProfile", "compare_replay_results", "regenerate_replay",
    "clock_read_ref", "policy_state_ref", "semantic_hash", "semantic_projection",
    "source_cursor_ref", "stable_ref_key",
)
