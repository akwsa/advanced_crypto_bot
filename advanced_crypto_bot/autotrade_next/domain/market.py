"""Immutable market-capability, evidence, and recovery contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .content import ContentRecipe, ContentRef
from .encoding import canonical_bytes
from .errors import CapabilityRegistryError, MarketEvidenceError, RecoveryEvaluationError
from .numeric import ScaledInteger


class ProductFamily(str, Enum):
    PUBLIC_REST = "PUBLIC_REST"
    PRIVATE_REST = "PRIVATE_REST"
    TRADE_API_V2 = "TRADE_API_V2"
    MARKET_DATA_WEBSOCKET = "MARKET_DATA_WEBSOCKET"
    PRIVATE_WEBSOCKET = "PRIVATE_WEBSOCKET"


class QualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"


class QualificationReason(str, Enum):
    QUALIFIED = "QUALIFIED"
    NO_MATCH = "NO_MATCH"
    ENTRY_UNQUALIFIED = "ENTRY_UNQUALIFIED"
    FIELD_NOT_AUTHORITATIVE = "FIELD_NOT_AUTHORITATIVE"


class CursorCapability(str, Enum):
    NO_AUTHORITATIVE_SEQUENCE = "NO_AUTHORITATIVE_SEQUENCE"
    VENUE_OFFSET = "VENUE_OFFSET"
    VENUE_SEQUENCE = "VENUE_SEQUENCE"


class AuthScope(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE_READ = "PRIVATE_READ"
    TRADE_API_V2_READ = "TRADE_API_V2_READ"
    PRIVATE_WEBSOCKET_READ = "PRIVATE_WEBSOCKET_READ"


class TimestampUnit(str, Enum):
    NONE = "NONE"
    SECONDS = "SECONDS"
    MILLISECONDS = "MILLISECONDS"


class RateLimitStatus(str, Enum):
    DOCUMENTED = "DOCUMENTED"
    NOT_DOCUMENTED = "NOT_DOCUMENTED"


class RecoveryMode(str, Enum):
    SNAPSHOT = "SNAPSHOT"
    OFFSET_REPLAY = "OFFSET_REPLAY"
    REST_RECONCILIATION = "REST_RECONCILIATION"
    NONE = "NONE"


class ScopeKind(str, Enum):
    INSTRUMENT_CHANNEL = "INSTRUMENT_CHANNEL"
    AUTHORITY = "AUTHORITY"


class ContinuityResult(str, Enum):
    QUALIFIED = "QUALIFIED"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    NO_AUTHORITATIVE_SEQUENCE = "NO_AUTHORITATIVE_SEQUENCE"
    GAP = "GAP"
    REGRESSION = "REGRESSION"
    CONFLICT = "CONFLICT"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    DISCONNECTED = "DISCONNECTED"
    STALE = "STALE"
    FUTURE = "FUTURE"
    CLOCK_SKEW = "CLOCK_SKEW"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"


class EvidenceDisposition(str, Enum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"
    SAFE_LATCHED = "SAFE_LATCHED"


class RecoveryDisposition(str, Enum):
    FROZEN = "FROZEN"
    CLEAR_REQUESTED = "CLEAR_REQUESTED"


@dataclass(frozen=True, slots=True)
class TimestampContract:
    unit: TimestampUnit
    field: str | None

    def __post_init__(self) -> None:
        if type(self.unit) is not TimestampUnit:
            _registry_fail("INVALID_TIMESTAMP_CONTRACT")
        if self.unit is TimestampUnit.NONE:
            if self.field is not None:
                _registry_fail("INVALID_TIMESTAMP_CONTRACT")
        else:
            _text(self.field, "INVALID_TIMESTAMP_CONTRACT")

    def to_canonical_value(self) -> dict[str, str | None]:
        return {"unit": self.unit.value, "field": self.field}


@dataclass(frozen=True, slots=True)
class RateLimitContract:
    status: RateLimitStatus
    requests: int | None = None
    window_micros: int | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not RateLimitStatus:
            _registry_fail("INVALID_RATE_LIMIT_CONTRACT")
        if self.status is RateLimitStatus.NOT_DOCUMENTED:
            if self.requests is not None or self.window_micros is not None:
                _registry_fail("INVALID_RATE_LIMIT_CONTRACT")
            return
        if type(self.requests) is not int or self.requests <= 0:
            _registry_fail("INVALID_RATE_LIMIT_CONTRACT")
        if type(self.window_micros) is not int or self.window_micros <= 0:
            _registry_fail("INVALID_RATE_LIMIT_CONTRACT")

    def to_canonical_value(self) -> dict[str, str | int | None]:
        return {
            "status": self.status.value,
            "requests": self.requests,
            "window_micros": self.window_micros,
        }


@dataclass(frozen=True, slots=True)
class RecoveryContract:
    mode: RecoveryMode
    route: str | None
    source_capability_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.mode) is not RecoveryMode:
            _registry_fail("INVALID_RECOVERY_CONTRACT")
        if self.mode is RecoveryMode.NONE:
            if self.route is not None or self.source_capability_id is not None:
                _registry_fail("INVALID_RECOVERY_CONTRACT")
        else:
            _text(self.route, "INVALID_RECOVERY_CONTRACT")
            if self.source_capability_id is not None:
                _text(self.source_capability_id, "INVALID_RECOVERY_CONTRACT")

    def to_canonical_value(self) -> dict[str, str | None]:
        return {
            "mode": self.mode.value,
            "route": self.route,
            "source_capability_id": self.source_capability_id,
        }


@dataclass(frozen=True, slots=True)
class CapabilityArtifact:
    artifact_id: str
    repository_commit: str
    document_path: str
    git_blob_digest: str
    document_content_digest: str
    extracted_assertions: tuple[str, ...] | list[str]
    authoritative_fields: tuple[str, ...] | list[str]
    sanitized_payload_digest: str
    contract_ref: ContentRef

    def __post_init__(self) -> None:
        for field in ("artifact_id", "document_path"):
            _text(getattr(self, field), "MISSING_CAPABILITY_FIELD", (field,))
        _commit(self.repository_commit, ("repository_commit",))
        _hex(self.git_blob_digest, 40, "INVALID_GIT_BLOB_DIGEST", ("git_blob_digest",))
        _hex(self.document_content_digest, 64, "INVALID_CONTENT_DIGEST", ("document_content_digest",))
        _hex(self.sanitized_payload_digest, 64, "INVALID_PAYLOAD_DIGEST", ("sanitized_payload_digest",))
        object.__setattr__(self, "extracted_assertions", _texts(self.extracted_assertions, "extracted_assertions"))
        object.__setattr__(self, "authoritative_fields", _texts(self.authoritative_fields, "authoritative_fields"))
        if (
            type(self.contract_ref) is not ContentRef
            or self.contract_ref.recipe is not ContentRecipe.V2
            or self.contract_ref.domain != "indodax.contract-artifact"
            or self.contract_ref.kind != "capability-artifact"
        ):
            _registry_fail("INVALID_ARTIFACT_REFERENCE", ("contract_ref",))
        if not self.contract_ref.verify(self.binding_value()):
            _registry_fail("ARTIFACT_MISMATCH", ("contract_ref",))

    def binding_value(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "repository_commit": self.repository_commit,
            "document_path": self.document_path,
            "git_blob_digest": self.git_blob_digest,
            "document_content_digest": self.document_content_digest,
            "extracted_assertions": self.extracted_assertions,
            "authoritative_fields": self.authoritative_fields,
            "sanitized_payload_digest": self.sanitized_payload_digest,
        }

    def to_canonical_value(self) -> dict[str, object]:
        return {**self.binding_value(), "contract_ref": self.contract_ref.to_canonical_value()}


@dataclass(frozen=True, slots=True)
class CapabilityEntry:
    capability_id: str
    version: str
    product: ProductFamily
    base_url: str
    resource: str
    documentation_commit: str
    document_path: str
    git_blob_digest: str
    document_content_digest: str
    effective_from: datetime
    effective_until: datetime | None
    auth_scope: AuthScope
    authoritative_fields: tuple[str, ...] | list[str]
    cursor_capability: CursorCapability
    snapshot_source: str
    timestamp_contract: TimestampContract
    rate_limit_contract: RateLimitContract
    recovery_contract: RecoveryContract
    qualification_status: QualificationStatus
    artifact: CapabilityArtifact

    def __post_init__(self) -> None:
        for field in ("capability_id", "version", "base_url", "resource", "document_path", "snapshot_source"):
            _text(getattr(self, field), "MISSING_CAPABILITY_FIELD", (field,))
        if type(self.product) is not ProductFamily or type(self.auth_scope) is not AuthScope:
            _registry_fail("INVALID_CAPABILITY_ENUM")
        if type(self.cursor_capability) is not CursorCapability or type(self.qualification_status) is not QualificationStatus:
            _registry_fail("INVALID_CAPABILITY_ENUM")
        _commit(self.documentation_commit, ("documentation_commit",))
        _hex(self.git_blob_digest, 40, "INVALID_GIT_BLOB_DIGEST", ("git_blob_digest",))
        _hex(self.document_content_digest, 64, "INVALID_CONTENT_DIGEST", ("document_content_digest",))
        _utc(self.effective_from, "INVALID_EFFECTIVE_TIME", ("effective_from",))
        if self.effective_until is not None:
            _utc(self.effective_until, "INVALID_EFFECTIVE_TIME", ("effective_until",))
            if self.effective_until <= self.effective_from:
                _registry_fail("INVALID_EFFECTIVE_INTERVAL", ("effective_until",))
        fields = _texts(self.authoritative_fields, "authoritative_fields")
        if len(fields) != len(set(fields)):
            _registry_fail("DUPLICATE_AUTHORITATIVE_FIELD", ("authoritative_fields",))
        object.__setattr__(self, "authoritative_fields", fields)
        for field, expected in (
            ("timestamp_contract", TimestampContract),
            ("rate_limit_contract", RateLimitContract),
            ("recovery_contract", RecoveryContract),
            ("artifact", CapabilityArtifact),
        ):
            if type(getattr(self, field)) is not expected:
                _registry_fail("MISSING_CAPABILITY_FIELD", (field,))
        if (
            self.documentation_commit != self.artifact.repository_commit
            or self.document_path != self.artifact.document_path
            or self.git_blob_digest != self.artifact.git_blob_digest
            or self.document_content_digest != self.artifact.document_content_digest
            or self.authoritative_fields != self.artifact.authoritative_fields
        ):
            _registry_fail("ARTIFACT_MISMATCH", ("artifact",))

    @property
    def capability_ref(self) -> ContentRef:
        return ContentRef.v2("market.capability", "capability-entry", self.to_canonical_value())

    def contains(self, effective_at: datetime) -> bool:
        _utc(effective_at, "INVALID_EFFECTIVE_TIME", ("effective_at",))
        return self.effective_from <= effective_at and (
            self.effective_until is None or effective_at < self.effective_until
        )

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "version": self.version,
            "product": self.product.value,
            "base_url": self.base_url,
            "resource": self.resource,
            "documentation_commit": self.documentation_commit,
            "document_path": self.document_path,
            "git_blob_digest": self.git_blob_digest,
            "document_content_digest": self.document_content_digest,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "auth_scope": self.auth_scope.value,
            "authoritative_fields": self.authoritative_fields,
            "cursor_capability": self.cursor_capability.value,
            "snapshot_source": self.snapshot_source,
            "timestamp_contract": self.timestamp_contract.to_canonical_value(),
            "rate_limit_contract": self.rate_limit_contract.to_canonical_value(),
            "recovery_contract": self.recovery_contract.to_canonical_value(),
            "qualification_status": self.qualification_status.value,
            "artifact": self.artifact.to_canonical_value(),
        }


@dataclass(frozen=True, slots=True)
class CapabilityLookup:
    status: QualificationStatus
    reason: QualificationReason
    entry: CapabilityEntry | None


@dataclass(frozen=True, slots=True)
class CapabilityRegistry:
    entries: tuple[CapabilityEntry, ...] | list[CapabilityEntry]

    def __post_init__(self) -> None:
        if type(self.entries) not in (tuple, list):
            _registry_fail("INVALID_CAPABILITY_REGISTRY")
        entries = tuple(self.entries)
        if not entries or any(type(entry) is not CapabilityEntry for entry in entries):
            _registry_fail("INVALID_CAPABILITY_REGISTRY")
        exact_keys = [
            (entry.product, entry.resource, entry.effective_from, entry.version)
            for entry in entries
        ]
        if len(exact_keys) != len(set(exact_keys)):
            _registry_fail("DUPLICATE_CAPABILITY_KEY")
        grouped: dict[tuple[ProductFamily, str], list[CapabilityEntry]] = {}
        for entry in entries:
            grouped.setdefault((entry.product, entry.resource), []).append(entry)
        for group in grouped.values():
            ordered = sorted(group, key=lambda item: item.effective_from)
            for previous, current in zip(ordered, ordered[1:]):
                if previous.effective_until is None or current.effective_from < previous.effective_until:
                    _registry_fail("OVERLAPPING_CAPABILITY_INTERVAL")
        artifact_keys = tuple(
            (entry.artifact.artifact_id, entry.artifact.contract_ref.key)
            for entry in entries
        )
        if (
            len({item[0] for item in artifact_keys}) != len(artifact_keys)
            or len({item[1] for item in artifact_keys}) != len(artifact_keys)
        ):
            _registry_fail("DUPLICATE_CAPABILITY_ARTIFACT")
        entries_by_id = {entry.capability_id: entry for entry in entries}
        if len(entries_by_id) != len(entries):
            _registry_fail("DUPLICATE_CAPABILITY_KEY")
        for entry in entries:
            source_id = entry.recovery_contract.source_capability_id
            if source_id is None:
                continue
            source = entries_by_id.get(source_id)
            if (
                source is None
                or source.qualification_status is not QualificationStatus.QUALIFIED
                or source.resource != entry.recovery_contract.route
                or source.documentation_commit != entry.documentation_commit
                or not source.contains(entry.effective_from)
                or (
                    source.effective_until is not None
                    and (
                        entry.effective_until is None
                        or source.effective_until < entry.effective_until
                    )
                )
            ):
                _registry_fail("INVALID_RECOVERY_CAPABILITY_BINDING")
        object.__setattr__(self, "entries", entries)

    def lookup(self, product: ProductFamily, resource: str, effective_at: datetime) -> CapabilityLookup:
        if type(product) is not ProductFamily:
            _registry_fail("INVALID_CAPABILITY_ENUM", ("product",))
        _text(resource, "MISSING_CAPABILITY_FIELD", ("resource",))
        _utc(effective_at, "INVALID_EFFECTIVE_TIME", ("effective_at",))
        matches = tuple(
            entry for entry in self.entries
            if entry.product is product and entry.resource == resource and entry.contains(effective_at)
        )
        if len(matches) > 1:
            _registry_fail("AMBIGUOUS_CAPABILITY_MATCH")
        if not matches:
            return CapabilityLookup(QualificationStatus.UNQUALIFIED, QualificationReason.NO_MATCH, None)
        entry = matches[0]
        if entry.qualification_status is not QualificationStatus.QUALIFIED:
            return CapabilityLookup(QualificationStatus.UNQUALIFIED, QualificationReason.ENTRY_UNQUALIFIED, entry)
        return CapabilityLookup(QualificationStatus.QUALIFIED, QualificationReason.QUALIFIED, entry)

    def qualifies_field(self, entry: CapabilityEntry, field: str, effective_at: datetime) -> bool:
        if type(entry) is not CapabilityEntry or entry not in self.entries:
            return False
        lookup = self.lookup(entry.product, entry.resource, effective_at)
        return lookup.entry == entry and lookup.status is QualificationStatus.QUALIFIED and field in entry.authoritative_fields


@dataclass(frozen=True, slots=True)
class AffectedScope:
    kind: ScopeKind
    authority_scope_id: str
    instrument_id: str | None = None
    channel: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ScopeKind:
            _evidence_fail("INVALID_AFFECTED_SCOPE")
        _evidence_text(self.authority_scope_id, ("authority_scope_id",))
        if self.kind is ScopeKind.INSTRUMENT_CHANNEL:
            _evidence_text(self.instrument_id, ("instrument_id",))
            _evidence_text(self.channel, ("channel",))
        elif self.instrument_id is not None or self.channel is not None:
            _evidence_fail("INVALID_AFFECTED_SCOPE")

    def to_canonical_value(self) -> dict[str, str | None]:
        return {"kind": self.kind.value, "authority_scope_id": self.authority_scope_id,
                "instrument_id": self.instrument_id, "channel": self.channel}


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    capability_ref: ContentRef
    capability_version: str
    resource: str
    required_fields: tuple[str, ...] | list[str]

    def __post_init__(self) -> None:
        if (
            type(self.capability_ref) is not ContentRef
            or self.capability_ref.recipe is not ContentRecipe.V2
            or self.capability_ref.domain != "market.capability"
            or self.capability_ref.kind != "capability-entry"
        ):
            _evidence_fail("INVALID_CAPABILITY_REFERENCE", ("capability_ref",))
        _evidence_text(self.capability_version, ("capability_version",))
        _evidence_text(self.resource, ("resource",))
        fields = _evidence_texts(self.required_fields, ("required_fields",))
        if len(fields) != len(set(fields)):
            _evidence_fail("DUPLICATE_EVIDENCE_REQUIREMENT", ("required_fields",))
        object.__setattr__(self, "required_fields", fields)

    def to_canonical_value(self) -> dict[str, object]:
        return {"capability_ref": self.capability_ref.to_canonical_value(),
                "capability_version": self.capability_version, "resource": self.resource,
                "required_fields": self.required_fields}


@dataclass(frozen=True, slots=True)
class EvidenceRequirementSet:
    trigger: str
    horizon_id: str
    instrument_id: str
    scope: AffectedScope
    effective_at: datetime
    requirements: tuple[EvidenceRequirement, ...] | list[EvidenceRequirement]
    policy_ref: ContentRef
    requirement_set_ref: ContentRef

    def __post_init__(self) -> None:
        for field in ("trigger", "horizon_id", "instrument_id"):
            _evidence_text(getattr(self, field), (field,))
        if type(self.scope) is not AffectedScope:
            _evidence_fail("INVALID_AFFECTED_SCOPE", ("scope",))
        _evidence_utc(self.effective_at, ("effective_at",))
        requirements = _freeze_evidence(self.requirements, EvidenceRequirement, ("requirements",), nonempty=True)
        refs = tuple(item.capability_ref.key for item in requirements)
        if len(refs) != len(set(refs)):
            _evidence_fail("DUPLICATE_EVIDENCE_REQUIREMENT", ("requirements",))
        object.__setattr__(self, "requirements", requirements)
        if (
            type(self.policy_ref) is not ContentRef
            or self.policy_ref.recipe is not ContentRecipe.V2
            or self.policy_ref.domain != "market.policy"
            or self.policy_ref.kind != "evidence-policy"
        ):
            _evidence_fail("INVALID_POLICY_REFERENCE", ("policy_ref",))
        if (
            type(self.requirement_set_ref) is not ContentRef
            or self.requirement_set_ref.recipe is not ContentRecipe.V2
            or self.requirement_set_ref.domain != "market.evidence-requirements"
            or self.requirement_set_ref.kind != "requirement-set"
            or not self.requirement_set_ref.verify(self.binding_value())
        ):
            _evidence_fail("REQUIREMENT_SET_MISMATCH", ("requirement_set_ref",))

    def binding_value(self) -> dict[str, object]:
        return {
            "trigger": self.trigger, "horizon_id": self.horizon_id,
            "instrument_id": self.instrument_id, "scope": self.scope.to_canonical_value(),
            "effective_at": self.effective_at,
            "requirements": tuple(item.to_canonical_value() for item in self.requirements),
            "policy_ref": self.policy_ref.to_canonical_value(),
        }

    def assert_exact_capabilities(
        self, provided: tuple[ContentRef, ...] | list[ContentRef]
    ) -> None:
        if type(provided) not in (tuple, list):
            _evidence_fail("INVALID_EVIDENCE_VALUE", ("provided",))
        frozen = tuple(provided)
        if any(type(item) is not ContentRef for item in frozen):
            _evidence_fail("INVALID_CAPABILITY_REFERENCE", ("provided",))
        keys = tuple(item.key for item in frozen)
        if len(keys) != len(set(keys)):
            _evidence_fail("DUPLICATE_EVIDENCE", ("provided",))
        expected = frozenset(item.capability_ref.key for item in self.requirements)
        actual = frozenset(keys)
        if actual - expected:
            _evidence_fail("EXTRA_OR_FOREIGN_EVIDENCE", ("provided",))
        if expected - actual:
            _evidence_fail("MISSING_REQUIRED_EVIDENCE", ("provided",))

    @classmethod
    def create(cls, *, trigger: str, horizon_id: str, instrument_id: str,
               scope: AffectedScope, effective_at: datetime,
               requirements: tuple[EvidenceRequirement, ...] | list[EvidenceRequirement],
               policy_ref: ContentRef) -> EvidenceRequirementSet:
        frozen = tuple(requirements)
        value = {
            "trigger": trigger, "horizon_id": horizon_id, "instrument_id": instrument_id,
            "scope": scope.to_canonical_value(), "effective_at": effective_at,
            "requirements": tuple(item.to_canonical_value() for item in frozen),
            "policy_ref": policy_ref.to_canonical_value(),
        }
        return cls(trigger, horizon_id, instrument_id, scope, effective_at, frozen, policy_ref,
                   ContentRef.v2("market.evidence-requirements", "requirement-set", value))


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    version: str
    maximum_age_micros: int = 3_000_000
    maximum_remote_skew_micros: int = 1_000_000
    maximum_sequence_gap: int = 0

    def __post_init__(self) -> None:
        _evidence_text(self.version, ("version",))
        for field in ("maximum_age_micros", "maximum_remote_skew_micros", "maximum_sequence_gap"):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                _evidence_fail("INVALID_EVIDENCE_POLICY", (field,))

    def to_canonical_value(self) -> dict[str, str | int]:
        return {"version": self.version, "maximum_age_micros": self.maximum_age_micros,
                "maximum_remote_skew_micros": self.maximum_remote_skew_micros,
                "maximum_sequence_gap": self.maximum_sequence_gap}

    @property
    def policy_ref(self) -> ContentRef:
        return ContentRef.v2("market.policy", "evidence-policy", self.to_canonical_value())


@dataclass(frozen=True, slots=True)
class AuthoritativeFieldEvidence:
    field: str
    value_ref: ContentRef

    def __post_init__(self) -> None:
        _evidence_text(self.field, ("field",))
        if (
            type(self.value_ref) is not ContentRef
            or self.value_ref.recipe is not ContentRecipe.V2
            or self.value_ref.domain != "market.authoritative-field"
            or self.value_ref.kind != f"field-{self.field}"
        ):
            _evidence_fail("INVALID_FIELD_EVIDENCE", ("value_ref",))

    def to_canonical_value(self) -> dict[str, object]:
        return {"field": self.field, "value_ref": self.value_ref.to_canonical_value()}


@dataclass(frozen=True, slots=True)
class MarketEvidence:
    capability_ref: ContentRef
    capability_version: str
    external_response_ref: ContentRef
    instrument_id: str
    scope: AffectedScope
    effective_at: datetime
    event_at_utc: datetime
    received_at_utc: datetime
    evaluated_at_utc: datetime
    venue_cursor: str | None
    ingest_cursor: str
    continuity: ContinuityResult
    freshness_micros: int
    remote_skew_micros: int
    policy: EvidencePolicy
    authoritative_fields: tuple[AuthoritativeFieldEvidence, ...] | list[AuthoritativeFieldEvidence]
    recovery_evidence_refs: tuple[ContentRef, ...] | list[ContentRef]
    disposition: EvidenceDisposition
    evidence_ref: ContentRef

    def __post_init__(self) -> None:
        for field, domain, kind in (
            ("capability_ref", "market.capability", "capability-entry"),
            ("external_response_ref", "market.external-response", "external-response"),
        ):
            reference = getattr(self, field)
            if (
                type(reference) is not ContentRef
                or reference.recipe is not ContentRecipe.V2
                or reference.domain != domain
                or reference.kind != kind
            ):
                _evidence_fail("INVALID_EVIDENCE_REFERENCE", (field,))
        for field in ("capability_version", "instrument_id", "ingest_cursor"):
            _evidence_text(getattr(self, field), (field,))
        if type(self.scope) is not AffectedScope:
            _evidence_fail("INVALID_AFFECTED_SCOPE", ("scope",))
        for field in ("effective_at", "event_at_utc", "received_at_utc", "evaluated_at_utc"):
            _evidence_utc(getattr(self, field), (field,))
        if self.venue_cursor is not None:
            _evidence_text(self.venue_cursor, ("venue_cursor",))
        if type(self.continuity) is not ContinuityResult or type(self.disposition) is not EvidenceDisposition:
            _evidence_fail("INVALID_EVIDENCE_DISPOSITION")
        for field in ("freshness_micros", "remote_skew_micros"):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                _evidence_fail("INVALID_EVIDENCE_VALUE", (field,))
        if type(self.policy) is not EvidencePolicy:
            _evidence_fail("INVALID_EVIDENCE_POLICY", ("policy",))
        qualified_continuity = (
            ContinuityResult.QUALIFIED,
            ContinuityResult.EXACT_DUPLICATE,
            ContinuityResult.NO_AUTHORITATIVE_SEQUENCE,
        )
        expected_disposition = (
            EvidenceDisposition.SAFE_LATCHED
            if self.continuity is ContinuityResult.CLOCK_ANOMALY
            else EvidenceDisposition.QUALIFIED
            if self.continuity in qualified_continuity
            else EvidenceDisposition.UNQUALIFIED
        )
        if self.disposition is not expected_disposition:
            _evidence_fail("INVALID_EVIDENCE_DISPOSITION", ("disposition",))
        if self.disposition is EvidenceDisposition.QUALIFIED and (
            self.freshness_micros > self.policy.maximum_age_micros
            or self.remote_skew_micros > self.policy.maximum_remote_skew_micros
        ):
            _evidence_fail("INVALID_EVIDENCE_DISPOSITION", ("disposition",))
        fields = _freeze_evidence(self.authoritative_fields, AuthoritativeFieldEvidence, ("authoritative_fields",), nonempty=True)
        names = tuple(field.field for field in fields)
        if len(names) != len(set(names)):
            _evidence_fail("DUPLICATE_FIELD_EVIDENCE", ("authoritative_fields",))
        object.__setattr__(self, "authoritative_fields", fields)
        refs = _freeze_evidence(self.recovery_evidence_refs, ContentRef, ("recovery_evidence_refs",), nonempty=False)
        if any(ref.recipe is not ContentRecipe.V2 for ref in refs):
            _evidence_fail("INVALID_EVIDENCE_REFERENCE", ("recovery_evidence_refs",))
        object.__setattr__(self, "recovery_evidence_refs", refs)
        if (
            type(self.evidence_ref) is not ContentRef
            or self.evidence_ref.recipe is not ContentRecipe.V2
            or self.evidence_ref.domain != "market.evidence"
            or self.evidence_ref.kind != "market-evidence"
            or not self.evidence_ref.verify(self.binding_value())
        ):
            _evidence_fail("EVIDENCE_CONTENT_MISMATCH", ("evidence_ref",))

    def binding_value(self) -> dict[str, object]:
        return {
            "capability_ref": self.capability_ref.to_canonical_value(),
            "capability_version": self.capability_version,
            "external_response_ref": self.external_response_ref.to_canonical_value(),
            "instrument_id": self.instrument_id,
            "scope": self.scope.to_canonical_value(),
            "effective_at": self.effective_at,
            "event_at_utc": self.event_at_utc,
            "received_at_utc": self.received_at_utc,
            "evaluated_at_utc": self.evaluated_at_utc,
            "venue_cursor": self.venue_cursor,
            "ingest_cursor": self.ingest_cursor,
            "continuity": self.continuity.value,
            "freshness_micros": self.freshness_micros,
            "remote_skew_micros": self.remote_skew_micros,
            "policy": self.policy.to_canonical_value(),
            "authoritative_fields": tuple(item.to_canonical_value() for item in self.authoritative_fields),
            "recovery_evidence_refs": tuple(item.to_canonical_value() for item in self.recovery_evidence_refs),
            "disposition": self.disposition.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes({**self.binding_value(), "evidence_ref": self.evidence_ref.to_canonical_value()})


@dataclass(frozen=True, slots=True)
class FreezeRequest:
    cause: ContinuityResult
    scope: AffectedScope
    capability_ref: ContentRef
    evidence_ref: ContentRef


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    capability_ref: ContentRef
    capability_version: str
    scope: AffectedScope
    recovery_route: str
    requirement_set_ref: ContentRef
    cause_evidence_ref: ContentRef

    def __post_init__(self) -> None:
        _recovery_ref(
            self.capability_ref,
            "market.capability",
            "capability-entry",
            "INVALID_RECOVERY_REQUEST",
        )
        _recovery_ref(
            self.requirement_set_ref,
            "market.recovery-requirements",
            "recovery-requirement-set",
            "INVALID_RECOVERY_REQUEST",
        )
        _evidence_text(self.capability_version, ("capability_version",))
        if type(self.scope) is not AffectedScope:
            _recovery_fail("INVALID_RECOVERY_SCOPE")
        _evidence_text(self.recovery_route, ("recovery_route",))
        _recovery_ref(
            self.cause_evidence_ref,
            "market.evidence",
            "market-evidence",
            "INVALID_RECOVERY_REQUEST",
        )


@dataclass(frozen=True, slots=True)
class ReconciliationRequest:
    capability_ref: ContentRef
    capability_version: str
    scope: AffectedScope
    requirement_set_ref: ContentRef
    cause_evidence_ref: ContentRef

    def __post_init__(self) -> None:
        _recovery_ref(self.capability_ref, "market.capability", "capability-entry",
                      "INVALID_RECONCILIATION_REQUEST")
        _recovery_ref(self.requirement_set_ref, "market.recovery-requirements",
                      "recovery-requirement-set", "INVALID_RECONCILIATION_REQUEST")
        _recovery_ref(self.cause_evidence_ref, "market.evidence", "market-evidence",
                      "INVALID_RECONCILIATION_REQUEST")
        _evidence_text(self.capability_version, ("capability_version",))
        if type(self.scope) is not AffectedScope:
            _recovery_fail("INVALID_RECOVERY_SCOPE")


@dataclass(frozen=True, slots=True)
class EvidenceAdmission:
    disposition: EvidenceDisposition
    reason: str
    evidence: MarketEvidence | None
    canonical_fields: tuple[str, ...]
    freeze_request: FreezeRequest | None = None
    recovery_request: RecoveryRequest | None = None
    reconciliation_request: ReconciliationRequest | None = None

    def __post_init__(self) -> None:
        if type(self.disposition) is not EvidenceDisposition:
            _evidence_fail("INVALID_EVIDENCE_DISPOSITION")
        _evidence_text(self.reason, ("reason",))
        if self.evidence is not None and type(self.evidence) is not MarketEvidence:
            _evidence_fail("INVALID_EVIDENCE_VALUE", ("evidence",))
        if type(self.canonical_fields) is not tuple:
            _evidence_fail("INVALID_EVIDENCE_VALUE", ("canonical_fields",))


@dataclass(frozen=True, slots=True)
class RecoveryProof:
    capability_ref: ContentRef
    capability_version: str
    scope: AffectedScope
    recovery_route: str
    evidence_ref: ContentRef
    qualified: bool

    def __post_init__(self) -> None:
        _recovery_ref(self.capability_ref, "market.capability", "capability-entry",
                      "INVALID_RECOVERY_PROOF")
        _recovery_ref(self.evidence_ref, "market.recovery-proof", "recovery-proof",
                      "INVALID_RECOVERY_PROOF")
        _evidence_text(self.capability_version, ("capability_version",))
        if type(self.scope) is not AffectedScope:
            _recovery_fail("INVALID_RECOVERY_SCOPE")
        _evidence_text(self.recovery_route, ("recovery_route",))
        if type(self.qualified) is not bool:
            _recovery_fail("INVALID_RECOVERY_PROOF")
        if not self.evidence_ref.verify(self.binding_value()):
            _recovery_fail("RECOVERY_PROOF_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {
            "capability_ref": self.capability_ref.to_canonical_value(),
            "capability_version": self.capability_version,
            "scope": self.scope.to_canonical_value(),
            "recovery_route": self.recovery_route,
            "qualified": self.qualified,
        }

    @classmethod
    def create(cls, *, capability_ref: ContentRef, capability_version: str,
               scope: AffectedScope, recovery_route: str, qualified: bool) -> RecoveryProof:
        value = {
            "capability_ref": capability_ref.to_canonical_value(),
            "capability_version": capability_version,
            "scope": scope.to_canonical_value(),
            "recovery_route": recovery_route,
            "qualified": qualified,
        }
        return cls(capability_ref, capability_version, scope, recovery_route,
                   ContentRef.v2("market.recovery-proof", "recovery-proof", value), qualified)


@dataclass(frozen=True, slots=True)
class ReconciliationCheckpoint:
    capability_ref: ContentRef
    capability_version: str
    scope: AffectedScope
    requirement_set_ref: ContentRef
    evidence_ref: ContentRef
    current: bool

    def __post_init__(self) -> None:
        _recovery_ref(self.capability_ref, "market.capability", "capability-entry",
                      "INVALID_RECONCILIATION_CHECKPOINT")
        _recovery_ref(self.requirement_set_ref, "market.recovery-requirements",
                      "recovery-requirement-set", "INVALID_RECONCILIATION_CHECKPOINT")
        _recovery_ref(self.evidence_ref, "market.reconciliation-checkpoint",
                      "reconciliation-checkpoint", "INVALID_RECONCILIATION_CHECKPOINT")
        _evidence_text(self.capability_version, ("capability_version",))
        if type(self.scope) is not AffectedScope or type(self.current) is not bool:
            _recovery_fail("INVALID_RECONCILIATION_CHECKPOINT")
        if not self.evidence_ref.verify(self.binding_value()):
            _recovery_fail("RECONCILIATION_CHECKPOINT_MISMATCH")

    def binding_value(self) -> dict[str, object]:
        return {
            "capability_ref": self.capability_ref.to_canonical_value(),
            "capability_version": self.capability_version,
            "scope": self.scope.to_canonical_value(),
            "requirement_set_ref": self.requirement_set_ref.to_canonical_value(),
            "current": self.current,
        }

    @classmethod
    def create(cls, *, capability_ref: ContentRef, capability_version: str,
               scope: AffectedScope, requirement_set_ref: ContentRef,
               current: bool) -> ReconciliationCheckpoint:
        value = {
            "capability_ref": capability_ref.to_canonical_value(),
            "capability_version": capability_version,
            "scope": scope.to_canonical_value(),
            "requirement_set_ref": requirement_set_ref.to_canonical_value(),
            "current": current,
        }
        return cls(
            capability_ref, capability_version, scope, requirement_set_ref,
            ContentRef.v2("market.reconciliation-checkpoint", "reconciliation-checkpoint", value),
            current,
        )


@dataclass(frozen=True, slots=True)
class ScopedClearRequest:
    capability_ref: ContentRef
    capability_version: str
    scope: AffectedScope
    recovery_evidence_ref: ContentRef
    reconciliation_evidence_ref: ContentRef


@dataclass(frozen=True, slots=True)
class RecoveryGateResult:
    disposition: RecoveryDisposition
    clear_request: ScopedClearRequest | None
    reason: str


def evaluate_recovery_gate(
    active_request: RecoveryRequest,
    recovery_proof: RecoveryProof | None,
    reconciliation_checkpoint: ReconciliationCheckpoint | None,
) -> RecoveryGateResult:
    """Evaluate two immutable proofs; never persists or clears safety state."""
    if type(active_request) is not RecoveryRequest:
        _recovery_fail("INVALID_RECOVERY_REQUEST")
    if recovery_proof is None or reconciliation_checkpoint is None:
        return RecoveryGateResult(RecoveryDisposition.FROZEN, None, "BOTH_PROOFS_REQUIRED")
    if type(recovery_proof) is not RecoveryProof or type(reconciliation_checkpoint) is not ReconciliationCheckpoint:
        _recovery_fail("INVALID_RECOVERY_PROOF")
    proof_matches = (
        recovery_proof.qualified
        and recovery_proof.capability_ref == active_request.capability_ref
        and recovery_proof.capability_version == active_request.capability_version
        and recovery_proof.scope == active_request.scope
        and recovery_proof.recovery_route == active_request.recovery_route
    )
    checkpoint_matches = (
        reconciliation_checkpoint.current
        and reconciliation_checkpoint.capability_ref == active_request.capability_ref
        and reconciliation_checkpoint.capability_version == active_request.capability_version
        and reconciliation_checkpoint.scope == active_request.scope
        and reconciliation_checkpoint.requirement_set_ref == active_request.requirement_set_ref
    )
    if not proof_matches or not checkpoint_matches:
        return RecoveryGateResult(RecoveryDisposition.FROZEN, None, "PROOF_MISMATCH")
    return RecoveryGateResult(
        RecoveryDisposition.CLEAR_REQUESTED,
        ScopedClearRequest(
            active_request.capability_ref,
            active_request.capability_version,
            active_request.scope,
            recovery_proof.evidence_ref,
            reconciliation_checkpoint.evidence_ref,
        ),
        "RECOVERY_AND_RECONCILIATION_QUALIFIED",
    )


def _registry_fail(code: str, path: tuple[str | int, ...] = ()) -> None:
    raise CapabilityRegistryError(code, path=path)


def _evidence_fail(code: str, path: tuple[str | int, ...] = ()) -> None:
    raise MarketEvidenceError(code, path=path)


def _recovery_fail(code: str, path: tuple[str | int, ...] = ()) -> None:
    raise RecoveryEvaluationError(code, path=path)


def _recovery_ref(
    value: object,
    domain: str,
    kind: str,
    code: str,
) -> None:
    if (
        type(value) is not ContentRef
        or value.recipe is not ContentRecipe.V2
        or value.domain != domain
        or value.kind != kind
    ):
        _recovery_fail(code)


def _text(value: object, code: str, path: tuple[str | int, ...] = ()) -> None:
    if type(value) is not str or not value or not value.strip():
        _registry_fail(code, path)
    try:
        canonical_bytes(value)
    except Exception as error:
        raise CapabilityRegistryError(code, path=path) from error


def _texts(value: object, field: str) -> tuple[str, ...]:
    if type(value) not in (tuple, list) or not value:
        _registry_fail("MISSING_CAPABILITY_FIELD", (field,))
    frozen = tuple(value)
    for index, item in enumerate(frozen):
        _text(item, "MISSING_CAPABILITY_FIELD", (field, index))
    return frozen


def _commit(value: object, path: tuple[str | int, ...]) -> None:
    if value in ("master", "main"):
        _registry_fail("MOVING_DOCUMENTATION_REFERENCE", path)
    _hex(value, 40, "INVALID_DOCUMENTATION_COMMIT", path)


def _hex(value: object, length: int, code: str, path: tuple[str | int, ...]) -> None:
    if type(value) is not str or len(value) != length or any(character not in "0123456789abcdef" for character in value):
        _registry_fail(code, path)


def _utc(value: object, code: str, path: tuple[str | int, ...]) -> None:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _registry_fail(code, path)


def _evidence_text(value: object, path: tuple[str | int, ...]) -> None:
    if type(value) is not str or not value or not value.strip():
        _evidence_fail("INVALID_EVIDENCE_VALUE", path)
    try:
        canonical_bytes(value)
    except Exception as error:
        raise MarketEvidenceError("INVALID_EVIDENCE_VALUE", path=path) from error


def _evidence_texts(value: object, path: tuple[str | int, ...]) -> tuple[str, ...]:
    if type(value) not in (tuple, list) or not value:
        _evidence_fail("MISSING_EVIDENCE", path)
    frozen = tuple(value)
    for index, item in enumerate(frozen):
        _evidence_text(item, (*path, index))
    return frozen


def _evidence_utc(value: object, path: tuple[str | int, ...]) -> None:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _evidence_fail("INVALID_EVIDENCE_TIME", path)


def _freeze_evidence(value: object, expected: type, path: tuple[str | int, ...], *, nonempty: bool) -> tuple[Any, ...]:
    if type(value) not in (tuple, list):
        _evidence_fail("INVALID_EVIDENCE_VALUE", path)
    frozen = tuple(value)
    if nonempty and not frozen:
        _evidence_fail("MISSING_EVIDENCE", path)
    if any(type(item) is not expected for item in frozen):
        _evidence_fail("INVALID_EVIDENCE_VALUE", path)
    return frozen


class OrderBookSide(str, Enum):
    BID = "BID"
    ASK = "ASK"


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class EligibilityReason(str, Enum):
    QUALIFIED = "QUALIFIED"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    UNORDERED_DEPTH = "UNORDERED_DEPTH"
    INSUFFICIENT_DEPTH = "INSUFFICIENT_DEPTH"
    EXCEEDS_MAX_SPREAD = "EXCEEDS_MAX_SPREAD"
    NOT_UNIVERSE_MEMBER = "NOT_UNIVERSE_MEMBER"
    MIN_SIZE_BREACH = "MIN_SIZE_BREACH"
    SYSTEMIC_INTEGRITY_FAILURE = "SYSTEMIC_INTEGRITY_FAILURE"


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: ScaledInteger
    quantity: ScaledInteger

    def __post_init__(self) -> None:
        if type(self.price) is not ScaledInteger or type(self.quantity) is not ScaledInteger:
            _evidence_fail("INVALID_ORDERBOOK_LEVEL")

    def to_canonical_value(self) -> dict[str, dict[str, int]]:
        return {
            "price": {"units": self.price.units, "scale": self.price.scale},
            "quantity": {"units": self.quantity.units, "scale": self.quantity.scale},
        }


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    instrument_id: str
    event_at_utc: datetime
    received_at_utc: datetime
    venue_cursor: str | None
    ingest_cursor: str
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    snapshot_ref: ContentRef

    def __post_init__(self) -> None:
        _evidence_text(self.instrument_id, ("instrument_id",))
        _evidence_utc(self.event_at_utc, ("event_at_utc",))
        _evidence_utc(self.received_at_utc, ("received_at_utc",))
        _evidence_text(self.ingest_cursor, ("ingest_cursor",))
        if self.venue_cursor is not None:
            _evidence_text(self.venue_cursor, ("venue_cursor",))

    def calculate_executable_price(
        self, side: OrderBookSide, requested_size: ScaledInteger
    ) -> tuple[ScaledInteger, ScaledInteger]:
        levels = self.asks if side is OrderBookSide.ASK else self.bids
        total_capacity_units = sum(level.quantity.units for level in levels)
        total_units = 0
        total_cost_scaled = 0
        req_units = requested_size.units

        for level in levels:
            take_units = min(req_units - total_units, level.quantity.units)
            total_cost_scaled += take_units * level.price.units
            total_units += take_units
            if total_units >= req_units:
                break

        capacity = ScaledInteger(total_capacity_units, requested_size.scale)
        if total_units == 0:
            return capacity, ScaledInteger(0, levels[0].price.scale if levels else 2)

        avg_price_units = total_cost_scaled // total_units
        avg_price = ScaledInteger(avg_price_units, levels[0].price.scale)
        return capacity, avg_price

    @classmethod
    def create(
        cls,
        *,
        instrument_id: str,
        event_at_utc: datetime,
        received_at_utc: datetime,
        venue_cursor: str | None,
        ingest_cursor: str,
        bids: tuple[OrderBookLevel, ...] | list[OrderBookLevel],
        asks: tuple[OrderBookLevel, ...] | list[OrderBookLevel],
    ) -> MarketSnapshot:
        frozen_bids = tuple(bids)
        frozen_asks = tuple(asks)

        # Validate order: bids descending price
        for index in range(len(frozen_bids) - 1):
            if frozen_bids[index].price.units < frozen_bids[index + 1].price.units:
                _evidence_fail("UNORDERED_BIDS")

        # Validate order: asks ascending price
        for index in range(len(frozen_asks) - 1):
            if frozen_asks[index].price.units > frozen_asks[index + 1].price.units:
                _evidence_fail("UNORDERED_ASKS")

        value = {
            "instrument_id": instrument_id,
            "event_at_utc": event_at_utc,
            "received_at_utc": received_at_utc,
            "venue_cursor": venue_cursor,
            "ingest_cursor": ingest_cursor,
            "bids": tuple(level.to_canonical_value() for level in frozen_bids),
            "asks": tuple(level.to_canonical_value() for level in frozen_asks),
        }
        snapshot_ref = ContentRef.v2("market.snapshot", "market-snapshot", value)
        return cls(
            instrument_id=instrument_id,
            event_at_utc=event_at_utc,
            received_at_utc=received_at_utc,
            venue_cursor=venue_cursor,
            ingest_cursor=ingest_cursor,
            bids=frozen_bids,
            asks=frozen_asks,
            snapshot_ref=snapshot_ref,
        )


@dataclass(frozen=True, slots=True)
class InstrumentEligibility:
    instrument_id: str
    status: EligibilityStatus
    reason: EligibilityReason

    @classmethod
    def evaluate(
        cls,
        *,
        instrument_id: str,
        min_order_size: ScaledInteger,
        max_spread_ratio_bps: int,
        freshness_micros: int,
        max_freshness_micros: int,
        is_universe_member: bool,
        current_spread_ratio_bps: int,
        depth_capacity: ScaledInteger,
        requested_size: ScaledInteger,
    ) -> InstrumentEligibility:
        if not is_universe_member:
            return cls(instrument_id, EligibilityStatus.INELIGIBLE, EligibilityReason.NOT_UNIVERSE_MEMBER)
        if freshness_micros > max_freshness_micros:
            return cls(instrument_id, EligibilityStatus.INELIGIBLE, EligibilityReason.STALE_EVIDENCE)
        if current_spread_ratio_bps > max_spread_ratio_bps:
            return cls(instrument_id, EligibilityStatus.INELIGIBLE, EligibilityReason.EXCEEDS_MAX_SPREAD)
        if depth_capacity.units < requested_size.units:
            return cls(instrument_id, EligibilityStatus.INELIGIBLE, EligibilityReason.INSUFFICIENT_DEPTH)
        if requested_size.units < min_order_size.units:
            return cls(instrument_id, EligibilityStatus.INELIGIBLE, EligibilityReason.MIN_SIZE_BREACH)

        return cls(instrument_id, EligibilityStatus.ELIGIBLE, EligibilityReason.QUALIFIED)


__all__ = (
    "AffectedScope", "AuthScope", "AuthoritativeFieldEvidence", "CapabilityArtifact", "CapabilityEntry",
    "CapabilityLookup", "CapabilityRegistry", "ContinuityResult", "CursorCapability",
    "EligibilityReason", "EligibilityStatus", "EvidenceAdmission", "EvidenceDisposition", "EvidencePolicy",
    "EvidenceRequirement", "EvidenceRequirementSet", "FreezeRequest", "InstrumentEligibility",
    "MarketEvidence", "MarketSnapshot", "OrderBookLevel", "OrderBookSide", "ReconciliationCheckpoint",
    "ReconciliationRequest", "ProductFamily", "QualificationReason", "QualificationStatus", "RateLimitContract",
    "RateLimitStatus", "RecoveryContract", "RecoveryDisposition", "RecoveryGateResult", "RecoveryMode",
    "RecoveryProof", "RecoveryRequest", "ScopedClearRequest", "ScopeKind", "evaluate_recovery_gate",
    "TimestampContract", "TimestampUnit",
)
