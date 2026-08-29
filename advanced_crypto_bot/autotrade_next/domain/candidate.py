"""Immutable point-in-time Candidate capture contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import Any

from .encoding import canonical_bytes
from .errors import CandidateCaptureError, CanonicalEncodingError, IdentityError, MarketEvidenceError
from .identity import DeterministicIdentity, build_identity
from .market import (
    EvidenceDisposition,
    EvidenceRequirementSet,
    MarketEvidence,
)


class CandidateTrigger(str, Enum):
    CLOSED_BAR = "CLOSED_BAR"
    PROTECTIVE_EVENT = "PROTECTIVE_EVENT"


class CandidateUse(str, Enum):
    LIVE_ADMISSION = "LIVE_ADMISSION"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    PROJECTION_REBUILD = "PROJECTION_REBUILD"


class EligibilityReason(str, Enum):
    STALE = "STALE"
    GAPPED = "GAPPED"
    UNQUALIFIED = "UNQUALIFIED"
    AMBIGUOUS = "AMBIGUOUS"
    QUALITY_FAILED = "QUALITY_FAILED"
    LATE_CORRECTION = "LATE_CORRECTION"


@dataclass(frozen=True, slots=True)
class StableRef:
    kind: str
    value: str

    def __post_init__(self) -> None:
        _require_ref(self.kind, ("kind",))
        _require_ref(self.value, ("value",))

    def to_canonical_value(self) -> dict[str, str]:
        return {"kind": self.kind, "value": self.value}


@dataclass(frozen=True, slots=True)
class SourceCursor:
    source_id: str
    venue_cursor: str | None
    ingest_cursor: str
    cursor_capability: str
    freshness_micros: int
    quality: str

    def __post_init__(self) -> None:
        _require_ref(self.source_id, ("source_id",))
        if self.venue_cursor is not None:
            _require_ref(self.venue_cursor, ("venue_cursor",))
        _require_ref(self.ingest_cursor, ("ingest_cursor",))
        _require_ref(self.cursor_capability, ("cursor_capability",))
        if type(self.freshness_micros) is not int or self.freshness_micros < 0:
            _fail("INVALID_CANDIDATE_VALUE", ("freshness_micros",))
        _require_ref(self.quality, ("quality",))

    def to_canonical_value(self) -> dict[str, str | int | None]:
        return {
            "source_id": self.source_id,
            "venue_cursor": self.venue_cursor,
            "ingest_cursor": self.ingest_cursor,
            "cursor_capability": self.cursor_capability,
            "freshness_micros": self.freshness_micros,
            "quality": self.quality,
        }


@dataclass(frozen=True, slots=True)
class ClockRead:
    clock_id: str
    value_at_utc: datetime

    def __post_init__(self) -> None:
        _require_ref(self.clock_id, ("clock_id",))
        _require_utc(self.value_at_utc, ("value_at_utc",))

    def to_canonical_value(self) -> dict[str, Any]:
        return {"clock_id": self.clock_id, "value_at_utc": self.value_at_utc}


@dataclass(frozen=True, slots=True)
class RngRef:
    algorithm: str
    state_ref: str

    def __post_init__(self) -> None:
        _require_ref(self.algorithm, ("algorithm",))
        _require_ref(self.state_ref, ("state_ref",))

    def to_canonical_value(self) -> dict[str, str]:
        return {"algorithm": self.algorithm, "state_ref": self.state_ref}


@dataclass(frozen=True, slots=True)
class RuntimeManifestRef:
    runtime_version: str
    numeric_version: str
    environment_ref: str
    code_commit: str
    image_digest: str
    dependency_lock_ref: str

    def __post_init__(self) -> None:
        for field in (
            "runtime_version",
            "numeric_version",
            "environment_ref",
            "code_commit",
            "image_digest",
            "dependency_lock_ref",
        ):
            _require_ref(getattr(self, field), (field,))

    def to_canonical_value(self) -> dict[str, str]:
        return {
            "runtime_version": self.runtime_version,
            "numeric_version": self.numeric_version,
            "environment_ref": self.environment_ref,
            "code_commit": self.code_commit,
            "image_digest": self.image_digest,
            "dependency_lock_ref": self.dependency_lock_ref,
        }


@dataclass(frozen=True, slots=True)
class CandidateEligibility:
    executable: bool
    reason: EligibilityReason | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if type(self.executable) is not bool:
            _fail("INVALID_CANDIDATE_ELIGIBILITY", ("executable",))
        if self.executable:
            if self.reason is not None or self.evidence_ref is not None:
                _fail("INVALID_CANDIDATE_ELIGIBILITY", ("reason",))
            return
        if type(self.reason) is not EligibilityReason:
            _fail("INVALID_CANDIDATE_ELIGIBILITY", ("reason",))
        _require_ref(self.evidence_ref, ("evidence_ref",))

    def to_canonical_value(self) -> dict[str, Any]:
        return {
            "executable": self.executable,
            "reason": None if self.reason is None else self.reason.value,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class CandidateProvenance:
    authority_scope_id: str
    portfolio_id: str
    experiment_id: str
    strategy_version: str
    correlation_id: str
    causation_id: str
    ordered_input_ids: tuple[str, ...] | list[str]
    event_at_utc: datetime
    received_at_utc: datetime
    source_cursors: tuple[SourceCursor, ...] | list[SourceCursor]
    eligibility: CandidateEligibility
    universe_ref: StableRef
    instrument_rules_ref: StableRef
    scheduler_ref: StableRef
    clock_reads: tuple[ClockRead, ...] | list[ClockRead]
    rng_ref: RngRef
    runtime_ref: RuntimeManifestRef
    data_ref: StableRef
    feature_ref: StableRef
    model_ref: StableRef
    config_ref: StableRef
    external_response_ids: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        for field in (
            "authority_scope_id",
            "portfolio_id",
            "experiment_id",
            "strategy_version",
            "correlation_id",
            "causation_id",
        ):
            _require_ref(getattr(self, field), (field,))
        _require_utc(self.event_at_utc, ("event_at_utc",))
        _require_utc(self.received_at_utc, ("received_at_utc",))
        object.__setattr__(
            self,
            "ordered_input_ids",
            _freeze_refs(self.ordered_input_ids, ("ordered_input_ids",), nonempty=True),
        )
        object.__setattr__(
            self,
            "external_response_ids",
            _freeze_refs(self.external_response_ids, ("external_response_ids",)),
        )
        object.__setattr__(
            self,
            "source_cursors",
            _freeze_typed(
                self.source_cursors, SourceCursor, ("source_cursors",), nonempty=True
            ),
        )
        object.__setattr__(
            self,
            "clock_reads",
            _freeze_typed(self.clock_reads, ClockRead, ("clock_reads",), nonempty=True),
        )
        for field, expected in (
            ("eligibility", CandidateEligibility),
            ("universe_ref", StableRef),
            ("instrument_rules_ref", StableRef),
            ("scheduler_ref", StableRef),
            ("rng_ref", RngRef),
            ("runtime_ref", RuntimeManifestRef),
            ("data_ref", StableRef),
            ("feature_ref", StableRef),
            ("model_ref", StableRef),
            ("config_ref", StableRef),
        ):
            if type(getattr(self, field)) is not expected:
                _fail("INVALID_CANDIDATE_VALUE", (field,))
        if self.config_ref.kind != "config" or not self.config_ref.value.startswith(
            ("sha256:", "version:", "ref:")
        ):
            _fail("INVALID_CANDIDATE_REFERENCE", ("config_ref",))

    def to_canonical_value(self) -> dict[str, Any]:
        return {
            "authority_scope_id": self.authority_scope_id,
            "portfolio_id": self.portfolio_id,
            "experiment_id": self.experiment_id,
            "strategy_version": self.strategy_version,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "ordered_input_ids": self.ordered_input_ids,
            "event_at_utc": self.event_at_utc,
            "received_at_utc": self.received_at_utc,
            "source_cursors": tuple(item.to_canonical_value() for item in self.source_cursors),
            "eligibility": self.eligibility.to_canonical_value(),
            "universe_ref": self.universe_ref.to_canonical_value(),
            "instrument_rules_ref": self.instrument_rules_ref.to_canonical_value(),
            "scheduler_ref": self.scheduler_ref.to_canonical_value(),
            "clock_reads": tuple(item.to_canonical_value() for item in self.clock_reads),
            "rng_ref": self.rng_ref.to_canonical_value(),
            "runtime_ref": self.runtime_ref.to_canonical_value(),
            "data_ref": self.data_ref.to_canonical_value(),
            "feature_ref": self.feature_ref.to_canonical_value(),
            "model_ref": self.model_ref.to_canonical_value(),
            "config_ref": self.config_ref.to_canonical_value(),
            "external_response_ids": self.external_response_ids,
        }


@dataclass(frozen=True, slots=True)
class CandidateSourceV2:
    source_id: str
    evidence: MarketEvidence

    def __post_init__(self) -> None:
        _require_ref(self.source_id, ("source_id",))
        if type(self.evidence) is not MarketEvidence:
            _fail("INVALID_CANDIDATE_EVIDENCE", ("evidence",))

    def to_canonical_value(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "evidence": {
                **self.evidence.binding_value(),
                "evidence_ref": self.evidence.evidence_ref.to_canonical_value(),
            },
        }


@dataclass(frozen=True, slots=True)
class CandidateProvenanceV2:
    authority_scope_id: str
    portfolio_id: str
    experiment_id: str
    strategy_version: str
    correlation_id: str
    causation_id: str
    ordered_input_ids: tuple[str, ...] | list[str]
    event_at_utc: datetime
    received_at_utc: datetime
    sources: tuple[CandidateSourceV2, ...] | list[CandidateSourceV2]
    evidence_requirements: EvidenceRequirementSet
    eligibility: CandidateEligibility
    universe_ref: StableRef
    instrument_rules_ref: StableRef
    scheduler_ref: StableRef
    clock_reads: tuple[ClockRead, ...] | list[ClockRead]
    rng_ref: RngRef
    runtime_ref: RuntimeManifestRef
    data_ref: StableRef
    feature_ref: StableRef
    model_ref: StableRef
    config_ref: StableRef

    def __post_init__(self) -> None:
        for field in (
            "authority_scope_id", "portfolio_id", "experiment_id", "strategy_version",
            "correlation_id", "causation_id",
        ):
            _require_ref(getattr(self, field), (field,))
        _require_utc(self.event_at_utc, ("event_at_utc",))
        _require_utc(self.received_at_utc, ("received_at_utc",))
        object.__setattr__(self, "ordered_input_ids", _freeze_refs(
            self.ordered_input_ids, ("ordered_input_ids",), nonempty=True
        ))
        sources = _freeze_typed(self.sources, CandidateSourceV2, ("sources",), nonempty=True)
        source_refs = tuple(source.evidence.evidence_ref.key for source in sources)
        if len(source_refs) != len(set(source_refs)):
            _fail("DUPLICATE_CANDIDATE_EVIDENCE", ("sources",))
        object.__setattr__(self, "sources", sources)
        if type(self.evidence_requirements) is not EvidenceRequirementSet:
            _fail("INVALID_EVIDENCE_REQUIREMENT_SET", ("evidence_requirements",))
        if (
            self.authority_scope_id
            != self.evidence_requirements.scope.authority_scope_id
        ):
            _fail(
                "CANDIDATE_EVIDENCE_SCOPE_MISMATCH",
                ("evidence_requirements", "scope", "authority_scope_id"),
            )
        object.__setattr__(self, "clock_reads", _freeze_typed(
            self.clock_reads, ClockRead, ("clock_reads",), nonempty=True
        ))
        for field, expected in (
            ("eligibility", CandidateEligibility), ("universe_ref", StableRef),
            ("instrument_rules_ref", StableRef), ("scheduler_ref", StableRef),
            ("rng_ref", RngRef), ("runtime_ref", RuntimeManifestRef),
            ("data_ref", StableRef), ("feature_ref", StableRef),
            ("model_ref", StableRef), ("config_ref", StableRef),
        ):
            if type(getattr(self, field)) is not expected:
                _fail("INVALID_CANDIDATE_VALUE", (field,))
        if self.config_ref.kind != "config" or not self.config_ref.value.startswith(
            ("sha256:", "version:", "ref:")
        ):
            _fail("INVALID_CANDIDATE_REFERENCE", ("config_ref",))

    def to_canonical_value(self) -> dict[str, Any]:
        return {
            "authority_scope_id": self.authority_scope_id,
            "portfolio_id": self.portfolio_id,
            "experiment_id": self.experiment_id,
            "strategy_version": self.strategy_version,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "ordered_input_ids": self.ordered_input_ids,
            "event_at_utc": self.event_at_utc,
            "received_at_utc": self.received_at_utc,
            "sources": tuple(source.to_canonical_value() for source in self.sources),
            "evidence_requirements": {
                **self.evidence_requirements.binding_value(),
                "requirement_set_ref": self.evidence_requirements.requirement_set_ref.to_canonical_value(),
            },
            "eligibility": self.eligibility.to_canonical_value(),
            "universe_ref": self.universe_ref.to_canonical_value(),
            "instrument_rules_ref": self.instrument_rules_ref.to_canonical_value(),
            "scheduler_ref": self.scheduler_ref.to_canonical_value(),
            "clock_reads": tuple(item.to_canonical_value() for item in self.clock_reads),
            "rng_ref": self.rng_ref.to_canonical_value(),
            "runtime_ref": self.runtime_ref.to_canonical_value(),
            "data_ref": self.data_ref.to_canonical_value(),
            "feature_ref": self.feature_ref.to_canonical_value(),
            "model_ref": self.model_ref.to_canonical_value(),
            "config_ref": self.config_ref.to_canonical_value(),
        }


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    candidate_id: DeterministicIdentity
    original_candidate_id: DeterministicIdentity | None
    predecessor_candidate_id: DeterministicIdentity | None
    revision_lineage: tuple[DeterministicIdentity, ...]
    instrument_id: str
    horizon_id: str
    trigger_kind: CandidateTrigger
    trigger_at_utc: datetime
    scan_trigger_version: str
    data_revision: str
    parent_position_id: str | None
    provenance: CandidateProvenance | CandidateProvenanceV2

    def __post_init__(self) -> None:
        _validate_candidate_fields(
            instrument_id=self.instrument_id,
            horizon_id=self.horizon_id,
            trigger_kind=self.trigger_kind,
            trigger_at_utc=self.trigger_at_utc,
            scan_trigger_version=self.scan_trigger_version,
            data_revision=self.data_revision,
            parent_position_id=self.parent_position_id,
            provenance=self.provenance,
        )
        expected = _candidate_identity(
            self.instrument_id,
            self.horizon_id,
            self.trigger_kind,
            self.trigger_at_utc,
            self.scan_trigger_version,
            self.data_revision,
            self.parent_position_id,
        )
        if type(self.candidate_id) is not DeterministicIdentity:
            _fail("INVALID_CANDIDATE_VALUE", ("candidate_id",))
        if self.candidate_id != expected:
            _fail("INVALID_CANDIDATE_VALUE", ("candidate_id",))
        if type(self.revision_lineage) is not tuple or any(
            type(item) is not DeterministicIdentity for item in self.revision_lineage
        ):
            _fail("INVALID_CANDIDATE_REVISION", ("revision_lineage",))
        if self.original_candidate_id is not None:
            if type(self.original_candidate_id) is not DeterministicIdentity:
                _fail("INVALID_CANDIDATE_REVISION", ("original_candidate_id",))
            if self.original_candidate_id.kind != "candidate":
                _fail("INVALID_CANDIDATE_REVISION", ("original_candidate_id",))
            if (
                self.provenance.eligibility.reason
                is not EligibilityReason.LATE_CORRECTION
            ):
                _fail("INVALID_CANDIDATE_REVISION", ("provenance", "eligibility"))
            if self.candidate_id == self.original_candidate_id:
                _fail("INVALID_CANDIDATE_REVISION", ("candidate_id",))
            if type(self.predecessor_candidate_id) is not DeterministicIdentity:
                _fail("INVALID_CANDIDATE_REVISION", ("predecessor_candidate_id",))
            if not self.revision_lineage:
                _fail("INVALID_CANDIDATE_REVISION", ("revision_lineage",))
            if self.revision_lineage[0] != self.original_candidate_id:
                _fail("INVALID_CANDIDATE_REVISION", ("revision_lineage", 0))
            if self.revision_lineage[-1] != self.predecessor_candidate_id:
                _fail("INVALID_CANDIDATE_REVISION", ("revision_lineage",))
            if len(set(item.key for item in self.revision_lineage)) != len(
                self.revision_lineage
            ):
                _fail("INVALID_CANDIDATE_REVISION", ("revision_lineage",))
            if self.candidate_id in self.revision_lineage:
                _fail("INVALID_CANDIDATE_REVISION", ("candidate_id",))
            expected_revision = _revision_token(
                root_id=self.original_candidate_id,
                predecessor_id=self.predecessor_candidate_id,
                lineage=self.revision_lineage,
                provenance=self.provenance,
            )
            if self.data_revision != expected_revision:
                _fail("INVALID_CANDIDATE_REVISION", ("data_revision",))
        elif self.provenance.eligibility.reason is EligibilityReason.LATE_CORRECTION:
            _fail("INVALID_CANDIDATE_REVISION", ("original_candidate_id",))
        elif self.predecessor_candidate_id is not None or self.revision_lineage:
            _fail("INVALID_CANDIDATE_REVISION", ("revision_lineage",))
        _validate_canonical_snapshot(self)

    @property
    def executable(self) -> bool:
        return self.provenance.eligibility.executable

    @property
    def eligibility_reason(self) -> EligibilityReason | None:
        return self.provenance.eligibility.reason

    @property
    def is_proof_bearing(self) -> bool:
        return type(self.provenance) is CandidateProvenanceV2

    @property
    def provenance_version(self) -> str:
        return "v2" if self.is_proof_bearing else "v1"

    def to_canonical_value(self) -> dict[str, Any]:
        return {
            "schema_version": (
                "candidate-snapshot:v2"
                if type(self.provenance) is CandidateProvenanceV2
                else "candidate-snapshot:v1"
            ),
            "candidate_id": self.candidate_id.key,
            "original_candidate_id": (
                None if self.original_candidate_id is None else self.original_candidate_id.key
            ),
            "predecessor_candidate_id": (
                None
                if self.predecessor_candidate_id is None
                else self.predecessor_candidate_id.key
            ),
            "revision_lineage": tuple(item.key for item in self.revision_lineage),
            "instrument_id": self.instrument_id,
            "horizon_id": self.horizon_id,
            "trigger_kind": self.trigger_kind.value,
            "trigger_at_utc": self.trigger_at_utc,
            "scan_trigger_version": self.scan_trigger_version,
            "data_revision": self.data_revision,
            "parent_position_id": self.parent_position_id,
            "provenance": self.provenance.to_canonical_value(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_canonical_value())


def capture_candidate(
    *,
    instrument_id: str,
    horizon_id: str,
    trigger_kind: CandidateTrigger,
    trigger_at_utc: datetime,
    scan_trigger_version: str,
    data_revision: str,
    provenance: CandidateProvenance,
    parent_position_id: str | None = None,
) -> CandidateSnapshot:
    if type(provenance) is not CandidateProvenance:
        _fail("INVALID_CANDIDATE_VALUE", ("provenance",))
    _validate_candidate_fields(
        instrument_id=instrument_id,
        horizon_id=horizon_id,
        trigger_kind=trigger_kind,
        trigger_at_utc=trigger_at_utc,
        scan_trigger_version=scan_trigger_version,
        data_revision=data_revision,
        parent_position_id=parent_position_id,
        provenance=provenance,
    )
    identity = _candidate_identity(
        instrument_id,
        horizon_id,
        trigger_kind,
        trigger_at_utc,
        scan_trigger_version,
        data_revision,
        parent_position_id,
    )
    return CandidateSnapshot(
        candidate_id=identity,
        original_candidate_id=None,
        predecessor_candidate_id=None,
        revision_lineage=(),
        instrument_id=instrument_id,
        horizon_id=horizon_id,
        trigger_kind=trigger_kind,
        trigger_at_utc=trigger_at_utc,
        scan_trigger_version=scan_trigger_version,
        data_revision=data_revision,
        parent_position_id=parent_position_id,
        provenance=provenance,
    )


def capture_candidate_v2(
    *,
    instrument_id: str,
    horizon_id: str,
    trigger_kind: CandidateTrigger,
    trigger_at_utc: datetime,
    scan_trigger_version: str,
    data_revision: str,
    provenance: CandidateProvenanceV2,
    parent_position_id: str | None = None,
) -> CandidateSnapshot:
    _validate_candidate_fields(
        instrument_id=instrument_id, horizon_id=horizon_id, trigger_kind=trigger_kind,
        trigger_at_utc=trigger_at_utc, scan_trigger_version=scan_trigger_version,
        data_revision=data_revision, parent_position_id=parent_position_id,
        provenance=provenance,
    )
    _validate_v2_admission(
        instrument_id, horizon_id, trigger_kind, trigger_at_utc, provenance
    )
    identity = _candidate_identity(
        instrument_id, horizon_id, trigger_kind, trigger_at_utc,
        scan_trigger_version, data_revision, parent_position_id,
    )
    return CandidateSnapshot(
        candidate_id=identity, original_candidate_id=None, predecessor_candidate_id=None,
        revision_lineage=(), instrument_id=instrument_id, horizon_id=horizon_id,
        trigger_kind=trigger_kind, trigger_at_utc=trigger_at_utc,
        scan_trigger_version=scan_trigger_version, data_revision=data_revision,
        parent_position_id=parent_position_id, provenance=provenance,
    )


def revise_candidate(
    original: CandidateSnapshot,
    *,
    data_revision: str,
    provenance: CandidateProvenance,
) -> CandidateSnapshot:
    if type(original) is not CandidateSnapshot:
        _fail("INVALID_CANDIDATE_REVISION", ("original",))
    _require_ref(data_revision, ("data_revision",))
    if data_revision == original.data_revision:
        _fail("INVALID_CANDIDATE_REVISION", ("data_revision",))
    if type(provenance) is not CandidateProvenance:
        _fail("INVALID_CANDIDATE_VALUE", ("provenance",))
    scope = (
        "authority_scope_id",
        "portfolio_id",
        "experiment_id",
        "strategy_version",
    )
    if any(getattr(provenance, field) != getattr(original.provenance, field) for field in scope):
        _fail("CANDIDATE_SCOPE_MISMATCH", ("provenance",))
    root_id = original.original_candidate_id or original.candidate_id
    lineage = (*original.revision_lineage, original.candidate_id)
    expected_revision = _revision_token(
        root_id=root_id,
        predecessor_id=original.candidate_id,
        lineage=lineage,
        provenance=provenance,
    )
    if data_revision != expected_revision:
        _fail("INVALID_CANDIDATE_REVISION", ("data_revision",))
    corrected_provenance = CandidateProvenance(
        **{
            **_provenance_init_values(provenance),
            "eligibility": CandidateEligibility(
                executable=False,
                reason=EligibilityReason.LATE_CORRECTION,
                evidence_ref=root_id.key,
            ),
        }
    )
    identity = _candidate_identity(
        original.instrument_id,
        original.horizon_id,
        original.trigger_kind,
        original.trigger_at_utc,
        original.scan_trigger_version,
        data_revision,
        original.parent_position_id,
    )
    return CandidateSnapshot(
        candidate_id=identity,
        original_candidate_id=root_id,
        predecessor_candidate_id=original.candidate_id,
        revision_lineage=lineage,
        instrument_id=original.instrument_id,
        horizon_id=original.horizon_id,
        trigger_kind=original.trigger_kind,
        trigger_at_utc=original.trigger_at_utc,
        scan_trigger_version=original.scan_trigger_version,
        data_revision=data_revision,
        parent_position_id=original.parent_position_id,
        provenance=corrected_provenance,
    )


def derive_revision_token(
    original: CandidateSnapshot, provenance: CandidateProvenance
) -> str:
    if type(original) is not CandidateSnapshot:
        _fail("INVALID_CANDIDATE_REVISION", ("original",))
    if type(provenance) is not CandidateProvenance:
        _fail("INVALID_CANDIDATE_VALUE", ("provenance",))
    root_id = original.original_candidate_id or original.candidate_id
    return _revision_token(
        root_id=root_id,
        predecessor_id=original.candidate_id,
        lineage=(*original.revision_lineage, original.candidate_id),
        provenance=provenance,
    )


def _validate_candidate_fields(**values: Any) -> None:
    for field in ("instrument_id", "horizon_id", "scan_trigger_version", "data_revision"):
        _require_ref(values[field], (field,))
    if type(values["trigger_kind"]) is not CandidateTrigger:
        _fail("INVALID_CANDIDATE_TRIGGER", ("trigger_kind",))
    _require_utc(values["trigger_at_utc"], ("trigger_at_utc",))
    parent = values["parent_position_id"]
    if values["trigger_kind"] is CandidateTrigger.CLOSED_BAR:
        if parent is not None:
            _fail("INVALID_CANDIDATE_PARENT", ("parent_position_id",))
    elif parent is None:
        _fail("INVALID_CANDIDATE_PARENT", ("parent_position_id",))
    else:
        _require_ref(parent, ("parent_position_id",))
    if type(values["provenance"]) not in (CandidateProvenance, CandidateProvenanceV2):
        _fail("INVALID_CANDIDATE_VALUE", ("provenance",))
    if type(values["provenance"]) is CandidateProvenanceV2:
        _validate_v2_admission(
            values["instrument_id"], values["horizon_id"], values["trigger_kind"],
            values["trigger_at_utc"], values["provenance"],
        )


def _validate_v2_admission(
    instrument_id: str,
    horizon_id: str,
    trigger_kind: CandidateTrigger,
    trigger_at_utc: datetime,
    provenance: CandidateProvenanceV2,
) -> None:
    requirements = provenance.evidence_requirements
    if (
        requirements.instrument_id != instrument_id
        or requirements.horizon_id != horizon_id
        or requirements.trigger != trigger_kind.value
        or requirements.effective_at != trigger_at_utc
    ):
        _fail("CANDIDATE_EVIDENCE_SCOPE_MISMATCH", ("provenance", "evidence_requirements"))
    evidence = tuple(source.evidence for source in provenance.sources)
    try:
        requirements.assert_exact_capabilities(tuple(item.capability_ref for item in evidence))
    except MarketEvidenceError as error:
        code = getattr(error, "code", "EVIDENCE_REQUIREMENT_MISMATCH")
        _fail(code, ("provenance", "sources"))
    by_capability = {item.capability_ref.key: item for item in evidence}
    for requirement in requirements.requirements:
        item = by_capability[requirement.capability_ref.key]
        if item.instrument_id != instrument_id or item.scope != requirements.scope:
            _fail("FOREIGN_CANDIDATE_EVIDENCE", ("provenance", "sources"))
        if item.capability_version != requirement.capability_version:
            _fail("FOREIGN_CAPABILITY_VERSION", ("provenance", "sources"))
        if item.effective_at != requirements.effective_at:
            _fail("STALE_CANDIDATE_EVIDENCE", ("provenance", "sources"))
        if (
            provenance.eligibility.executable
            and item.evaluated_at_utc < requirements.effective_at
        ):
            _fail("STALE_CANDIDATE_EVIDENCE", ("provenance", "sources"))
        if item.policy.policy_ref != requirements.policy_ref:
            _fail("FOREIGN_EVIDENCE_POLICY", ("provenance", "sources"))
        actual_fields = frozenset(field.field for field in item.authoritative_fields)
        if actual_fields != frozenset(requirement.required_fields):
            _fail("EVIDENCE_FIELD_SET_MISMATCH", ("provenance", "sources"))
    bad = tuple(item for item in evidence if item.disposition is not EvidenceDisposition.QUALIFIED)
    if provenance.eligibility.executable and bad:
        _fail("UNQUALIFIED_CANDIDATE_EVIDENCE", ("provenance", "sources"))
    if provenance.eligibility.executable and provenance.eligibility.reason is not None:
        _fail("INVALID_CANDIDATE_ELIGIBILITY", ("provenance", "eligibility"))


def _candidate_identity(
    instrument_id: str,
    horizon_id: str,
    trigger_kind: CandidateTrigger,
    trigger_at_utc: datetime,
    scan_trigger_version: str,
    data_revision: str,
    parent_position_id: str | None,
) -> DeterministicIdentity:
    fields: dict[str, Any] = {
        "instrument_id": instrument_id,
        "horizon_id": horizon_id,
        "trigger_kind": trigger_kind.value,
        "trigger_at_utc": trigger_at_utc,
        "scan_trigger_version": scan_trigger_version,
        "data_revision": data_revision,
    }
    if parent_position_id is not None:
        fields["parent_position_id"] = parent_position_id
    try:
        return build_identity("candidate", fields)
    except (CanonicalEncodingError, IdentityError) as error:
        path = getattr(error, "path", ())
        _fail("INVALID_CANDIDATE_VALUE", ("identity", *path))


def _revision_token(
    *,
    root_id: DeterministicIdentity,
    predecessor_id: DeterministicIdentity,
    lineage: tuple[DeterministicIdentity, ...],
    provenance: CandidateProvenance,
) -> str:
    corrected_provenance = provenance.to_canonical_value()
    corrected_provenance.pop("eligibility")
    value = {
        "domain": "autotrade-next.candidate-revision",
        "version": 1,
        "root_candidate_id": root_id.key,
        "predecessor_candidate_id": predecessor_id.key,
        "lineage": tuple(item.key for item in lineage),
        "corrected_provenance": corrected_provenance,
    }
    try:
        digest = sha256(canonical_bytes(value)).hexdigest()
    except CanonicalEncodingError as error:
        _fail("INVALID_CANDIDATE_VALUE", ("provenance", *error.path))
    return f"revision:sha256:{digest}"


def _validate_canonical_snapshot(snapshot: CandidateSnapshot) -> None:
    try:
        canonical_bytes(snapshot.to_canonical_value())
    except CanonicalEncodingError as error:
        _fail("INVALID_CANDIDATE_VALUE", error.path)


def _provenance_init_values(value: CandidateProvenance) -> dict[str, Any]:
    return {field: getattr(value, field) for field in value.__dataclass_fields__}


def _freeze_refs(
    value: Iterable[str], path: tuple[str, ...], *, nonempty: bool = False
) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        _fail("INVALID_CANDIDATE_VALUE", path)
    frozen = tuple(value)
    if nonempty and not frozen:
        _fail("MISSING_CANDIDATE_PROVENANCE", path)
    for index, item in enumerate(frozen):
        _require_ref(item, (*path, index))
    return frozen


def _freeze_typed(
    value: Iterable[Any], expected: type[Any], path: tuple[str, ...], *, nonempty: bool
) -> tuple[Any, ...]:
    if type(value) not in (list, tuple):
        _fail("INVALID_CANDIDATE_VALUE", path)
    frozen = tuple(value)
    if nonempty and not frozen:
        _fail("MISSING_CANDIDATE_PROVENANCE", path)
    for index, item in enumerate(frozen):
        if type(item) is not expected:
            _fail("INVALID_CANDIDATE_VALUE", (*path, index))
    return frozen


def _require_ref(value: Any, path: tuple[str | int, ...]) -> None:
    if type(value) is not str:
        _fail("INVALID_CANDIDATE_VALUE", path)
    if not value or not value.strip():
        _fail("INVALID_CANDIDATE_REFERENCE", path)
    try:
        canonical_bytes(value)
    except CanonicalEncodingError:
        _fail("INVALID_CANDIDATE_REFERENCE", path)


def _require_utc(value: Any, path: tuple[str | int, ...]) -> None:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _fail("INVALID_CANDIDATE_TIMESTAMP", path)


def _fail(code: str, path: tuple[str | int, ...]) -> None:
    raise CandidateCaptureError(code, path=path)


__all__ = (
    "CandidateCaptureError",
    "CandidateEligibility",
    "CandidateProvenance",
    "CandidateProvenanceV2",
    "CandidateSourceV2",
    "CandidateSnapshot",
    "CandidateTrigger",
    "CandidateUse",
    "ClockRead",
    "EligibilityReason",
    "RngRef",
    "RuntimeManifestRef",
    "SourceCursor",
    "StableRef",
    "capture_candidate",
    "capture_candidate_v2",
    "derive_revision_token",
    "revise_candidate",
)
