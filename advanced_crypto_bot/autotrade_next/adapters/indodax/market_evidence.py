"""Pure adapter from recorded Indodax input to immutable market evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.encoding import canonical_bytes
from autotrade_next.domain.errors import CanonicalEncodingError, MarketEvidenceError
from autotrade_next.domain.market import (
    AffectedScope,
    AuthoritativeFieldEvidence,
    CapabilityRegistry,
    ContinuityResult,
    CursorCapability,
    EvidenceAdmission,
    EvidenceDisposition,
    EvidencePolicy,
    FreezeRequest,
    MarketEvidence,
    ProductFamily,
    QualificationStatus,
    ReconciliationRequest,
    RecoveryRequest,
    ScopeKind,
    TimestampUnit,
)


_SECRET_NAMES = frozenset(("api_key", "apikey", "key", "secret", "sign", "token", "tapi_key", "tapi_secret"))


def qualify_recorded_input(
    *, registry: CapabilityRegistry, product: ProductFamily, resource: str,
    effective_at: datetime, instrument_id: str, scope: AffectedScope,
    payload: Mapping[str, object], event_at_utc: datetime, received_at_utc: datetime,
    evaluated_at_utc: datetime, venue_cursor: int | str | None, ingest_cursor: str,
    policy: EvidencePolicy, previous_evidence: MarketEvidence | None = None,
    connected: bool = True, local_clock_anomaly: bool = False,
    systemic_integrity_proven: bool = False,
) -> EvidenceAdmission:
    """Qualify caller-supplied bytes/times only; never reads clock, network, env, or state."""
    if type(registry) is not CapabilityRegistry or type(product) is not ProductFamily:
        _fail("INVALID_EVIDENCE_INPUT")
    _utc(effective_at, "effective_at")
    _utc(event_at_utc, "event_at_utc")
    _utc(received_at_utc, "received_at_utc")
    _utc(evaluated_at_utc, "evaluated_at_utc")
    if type(scope) is not AffectedScope or type(policy) is not EvidencePolicy:
        _fail("INVALID_EVIDENCE_INPUT")
    if type(instrument_id) is not str or not instrument_id or type(ingest_cursor) is not str or not ingest_cursor:
        _fail("INVALID_EVIDENCE_INPUT")
    if (
        type(connected) is not bool
        or type(local_clock_anomaly) is not bool
        or type(systemic_integrity_proven) is not bool
    ):
        _fail("INVALID_EVIDENCE_INPUT")
    if (
        scope.kind is ScopeKind.INSTRUMENT_CHANNEL
        and scope.instrument_id != instrument_id
    ):
        _fail("EVIDENCE_SCOPE_MISMATCH", ("scope", "instrument_id"))
    if (
        scope.kind is ScopeKind.AUTHORITY
        and not local_clock_anomaly
        and not systemic_integrity_proven
    ):
        _fail("UNPROVEN_AUTHORITY_SCOPE", ("scope",))
    if previous_evidence is not None and type(previous_evidence) is not MarketEvidence:
        _fail("INVALID_PREVIOUS_EVIDENCE")
    if not isinstance(payload, Mapping):
        _fail("INVALID_EVIDENCE_PAYLOAD")
    _reject_secrets(payload)
    try:
        canonical_bytes(dict(payload))
    except CanonicalEncodingError as error:
        raise MarketEvidenceError("INVALID_EVIDENCE_PAYLOAD") from error

    lookup = registry.lookup(product, resource, effective_at)
    if lookup.status is not QualificationStatus.QUALIFIED or lookup.entry is None:
        return EvidenceAdmission(EvidenceDisposition.UNQUALIFIED, lookup.reason.value, None, ())
    entry = lookup.entry
    if (
        scope.kind is ScopeKind.INSTRUMENT_CHANNEL
        and scope.channel != _scoped_resource(entry.resource, instrument_id)
    ):
        _fail("EVIDENCE_SCOPE_MISMATCH", ("scope", "channel"))
    _validate_documented_event_time(
        payload,
        entry.timestamp_contract.field,
        entry.timestamp_contract.unit,
        event_at_utc,
    )
    if previous_evidence is not None and (
        previous_evidence.capability_ref != entry.capability_ref
        or previous_evidence.instrument_id != instrument_id
        or previous_evidence.scope != scope
    ):
        _fail("FOREIGN_PREVIOUS_EVIDENCE", ("previous_evidence",))
    canonical_fields = tuple(sorted(entry.authoritative_fields))
    field_evidence_items: list[AuthoritativeFieldEvidence] = []
    for field in canonical_fields:
        value = _resolve_payload_path(
            payload,
            field,
            missing_code="MISSING_AUTHORITATIVE_FIELD",
        )
        field_evidence_items.append(
            AuthoritativeFieldEvidence(
                field,
                ContentRef.v2("market.authoritative-field", f"field-{field}", value),
            )
        )
    field_evidence = tuple(field_evidence_items)
    _validate_documented_scope(payload, entry.product, entry.resource, instrument_id)
    _validate_documented_instrument(payload, entry.authoritative_fields, instrument_id)
    external_ref = ContentRef.v2("market.external-response", "external-response", dict(payload))
    cursor = _cursor(
        entry.cursor_capability,
        venue_cursor,
        payload,
        entry.authoritative_fields,
    )
    freshness = _micros(evaluated_at_utc - received_at_utc)
    remote_delta = _signed_micros(received_at_utc - event_at_utc)
    skew = abs(remote_delta)
    continuity = _continuity(
        entry.cursor_capability, cursor, external_ref, event_at_utc, previous_evidence,
        connected=connected, local_clock_anomaly=local_clock_anomaly,
        freshness=freshness, remote_delta=remote_delta, policy=policy,
    )
    disposition = _disposition(continuity)
    effective_scope = (
        AffectedScope(ScopeKind.AUTHORITY, scope.authority_scope_id)
        if continuity is ContinuityResult.CLOCK_ANOMALY
        else scope
    )
    recovery_refs = (
        ContentRef.v2("market.recovery-route", "recovery-route", {
            "capability_ref": entry.capability_ref.to_canonical_value(),
            "route": entry.recovery_contract.route,
        }),
    ) if entry.recovery_contract.route is not None else ()
    values = {
        "capability_ref": entry.capability_ref,
        "capability_version": entry.version,
        "external_response_ref": external_ref,
        "instrument_id": instrument_id,
        "scope": effective_scope,
        "effective_at": effective_at,
        "event_at_utc": event_at_utc,
        "received_at_utc": received_at_utc,
        "evaluated_at_utc": evaluated_at_utc,
        "venue_cursor": cursor,
        "ingest_cursor": ingest_cursor,
        "continuity": continuity,
        "freshness_micros": max(0, freshness),
        "remote_skew_micros": skew,
        "policy": policy,
        "authoritative_fields": field_evidence,
        "recovery_evidence_refs": recovery_refs,
        "disposition": disposition,
    }
    binding = _evidence_binding(values)
    evidence = MarketEvidence(**values, evidence_ref=ContentRef.v2("market.evidence", "market-evidence", binding))
    if disposition is EvidenceDisposition.QUALIFIED:
        return EvidenceAdmission(disposition, continuity.value, evidence, canonical_fields)

    freeze = FreezeRequest(continuity, effective_scope, entry.capability_ref, evidence.evidence_ref)
    requirement_ref = ContentRef.v2("market.recovery-requirements", "recovery-requirement-set", {
        "capability_ref": entry.capability_ref.to_canonical_value(),
        "scope": effective_scope.to_canonical_value(),
        "policy": policy.to_canonical_value(),
    })
    route = entry.recovery_contract.route or entry.snapshot_source
    recovery = RecoveryRequest(entry.capability_ref, entry.version, effective_scope, route, requirement_ref, evidence.evidence_ref)
    reconciliation = ReconciliationRequest(
        entry.capability_ref,
        entry.version,
        effective_scope,
        requirement_ref,
        evidence.evidence_ref,
    )
    return EvidenceAdmission(disposition, continuity.value, evidence, canonical_fields, freeze, recovery, reconciliation)


def _continuity(
    capability: CursorCapability, cursor: str | None, response_ref: ContentRef,
    event_at: datetime, previous: MarketEvidence | None, *, connected: bool,
    local_clock_anomaly: bool, freshness: int, remote_delta: int, policy: EvidencePolicy,
) -> ContinuityResult:
    if local_clock_anomaly or freshness < 0:
        return ContinuityResult.CLOCK_ANOMALY
    if not connected:
        return ContinuityResult.DISCONNECTED
    if previous is not None and previous.disposition is not EvidenceDisposition.QUALIFIED:
        # A reconnect/new message cannot clear a supplied frozen cause. Only the
        # separate two-proof recovery gate may emit a scoped clear request.
        return previous.continuity
    if freshness > policy.maximum_age_micros:
        return ContinuityResult.STALE
    if remote_delta < -policy.maximum_remote_skew_micros:
        return ContinuityResult.FUTURE
    if remote_delta > policy.maximum_remote_skew_micros:
        return ContinuityResult.CLOCK_SKEW
    if capability is CursorCapability.NO_AUTHORITATIVE_SEQUENCE:
        return ContinuityResult.NO_AUTHORITATIVE_SEQUENCE
    if previous is None:
        return ContinuityResult.QUALIFIED
    current_number = int(cursor) if cursor is not None else None
    previous_number = int(previous.venue_cursor) if previous.venue_cursor is not None else None
    if current_number is None or previous_number is None:
        _fail("MISSING_VENUE_CURSOR")
    if current_number == previous_number:
        return (
            ContinuityResult.EXACT_DUPLICATE
            if response_ref == previous.external_response_ref
            else ContinuityResult.CONFLICT
        )
    if current_number < previous_number:
        return ContinuityResult.REGRESSION
    if event_at < previous.event_at_utc:
        return ContinuityResult.OUT_OF_ORDER
    if current_number - previous_number - 1 > policy.maximum_sequence_gap:
        return ContinuityResult.GAP
    return ContinuityResult.QUALIFIED


def _cursor(
    capability: CursorCapability,
    value: int | str | None,
    payload: Mapping[str, object],
    authoritative_fields: tuple[str, ...],
) -> str | None:
    if capability is CursorCapability.NO_AUTHORITATIVE_SEQUENCE:
        if value is not None:
            _fail("UNSUPPORTED_VENUE_CURSOR", ("venue_cursor",))
        return None
    if type(value) not in (int, str) or type(value) is bool:
        _fail("MISSING_VENUE_CURSOR", ("venue_cursor",))
    text = str(value)
    if not text.isdigit():
        _fail("INVALID_VENUE_CURSOR", ("venue_cursor",))
    cursor_fields = tuple(
        field for field in authoritative_fields
        if field == "offset" or field.endswith(".offset")
    )
    if len(cursor_fields) != 1:
        _fail("INVALID_CURSOR_CONTRACT")
    documented_cursor = _resolve_payload_path(
        payload,
        cursor_fields[0],
        missing_code="MISSING_VENUE_CURSOR",
    )
    if type(documented_cursor) is bool or type(documented_cursor) not in (int, str):
        _fail("INVALID_VENUE_CURSOR", ("payload", cursor_fields[0]))
    if str(documented_cursor) != text:
        _fail("VENUE_CURSOR_MISMATCH", ("venue_cursor",))
    return text


def _validate_documented_event_time(
    payload: Mapping[str, object],
    field_path: str | None,
    unit: TimestampUnit,
    event_at_utc: datetime,
) -> None:
    if unit is TimestampUnit.NONE:
        return
    if field_path is None:
        _fail("INVALID_TIMESTAMP_CONTRACT")
    value = _resolve_payload_path(
        payload,
        field_path,
        missing_code="MISSING_REMOTE_TIMESTAMP",
    )
    if "[]" in field_path:
        if type(value) is not tuple or len(value) != 1:
            _fail("AMBIGUOUS_REMOTE_TIMESTAMP", ("payload", field_path))
        value = value[0]
    if type(value) is not int:
        _fail("INVALID_REMOTE_TIMESTAMP", ("payload", *field_path.split(".")))
    divisor = 1 if unit is TimestampUnit.SECONDS else 1_000
    try:
        documented = datetime.fromtimestamp(value / divisor, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise MarketEvidenceError(
            "INVALID_REMOTE_TIMESTAMP",
            path=("payload", *field_path.split(".")),
        ) from error
    if documented != event_at_utc:
        _fail("REMOTE_TIMESTAMP_MISMATCH", ("payload", *field_path.split(".")))


def _resolve_payload_path(
    payload: Mapping[str, object],
    field_path: str,
    *,
    missing_code: str,
) -> object:
    """Resolve documented dotted paths, including JSON-array ``[]`` segments."""
    parts = field_path.split(".")

    def resolve(value: object, index: int) -> object:
        if index == len(parts):
            return value
        part = parts[index]
        if part.endswith("[]"):
            key = part[:-2]
            if not isinstance(value, Mapping) or key not in value:
                _fail(missing_code, ("payload", *parts[: index + 1]))
            sequence = value[key]
            if type(sequence) not in (list, tuple) or not sequence:
                _fail(missing_code, ("payload", *parts[: index + 1]))
            return tuple(resolve(item, index + 1) for item in sequence)
        if type(value) in (list, tuple) and part.isdigit():
            item_index = int(part)
            if item_index >= len(value):
                _fail(missing_code, ("payload", *parts[: index + 1]))
            return resolve(value[item_index], index + 1)
        if not isinstance(value, Mapping) or part not in value:
            _fail(missing_code, ("payload", *parts[: index + 1]))
        return resolve(value[part], index + 1)

    return resolve(payload, 0)


def _validate_documented_scope(
    payload: Mapping[str, object],
    product: ProductFamily,
    resource: str,
    instrument_id: str,
) -> None:
    if product is not ProductFamily.MARKET_DATA_WEBSOCKET:
        return
    channel = _resolve_payload_path(
        payload,
        "result.channel",
        missing_code="MISSING_AUTHORITATIVE_FIELD",
    )
    if channel != _scoped_resource(resource, instrument_id):
        _fail("EVIDENCE_SCOPE_MISMATCH", ("payload", "result", "channel"))


def _validate_documented_instrument(
    payload: Mapping[str, object],
    authoritative_fields: tuple[str, ...],
    instrument_id: str,
) -> None:
    instrument_paths = tuple(
        field for field in authoritative_fields
        if field.endswith(".pair")
        or field.endswith(".symbol")
        or field == "result.data.data[].0"
    )
    expected = "".join(
        character for character in instrument_id.casefold() if character.isalnum()
    )
    for field_path in instrument_paths:
        value = _resolve_payload_path(
            payload,
            field_path,
            missing_code="MISSING_AUTHORITATIVE_FIELD",
        )
        values = value if type(value) is tuple else (value,)
        if not values or any(
            type(item) is not str
            or "".join(character for character in item.casefold() if character.isalnum())
            != expected
            for item in values
        ):
            _fail("EVIDENCE_INSTRUMENT_MISMATCH", ("payload", field_path))


def _scoped_resource(resource: str, instrument_id: str) -> str:
    pair = "".join(character for character in instrument_id.casefold() if character.isalnum())
    return resource.replace("{pair}", pair)


def _evidence_binding(values: dict[str, object]) -> dict[str, object]:
    return {
        "capability_ref": values["capability_ref"].to_canonical_value(),
        "capability_version": values["capability_version"],
        "external_response_ref": values["external_response_ref"].to_canonical_value(),
        "instrument_id": values["instrument_id"],
        "scope": values["scope"].to_canonical_value(),
        "effective_at": values["effective_at"],
        "event_at_utc": values["event_at_utc"], "received_at_utc": values["received_at_utc"],
        "evaluated_at_utc": values["evaluated_at_utc"], "venue_cursor": values["venue_cursor"],
        "ingest_cursor": values["ingest_cursor"], "continuity": values["continuity"].value,
        "freshness_micros": values["freshness_micros"], "remote_skew_micros": values["remote_skew_micros"],
        "policy": values["policy"].to_canonical_value(),
        "authoritative_fields": tuple(item.to_canonical_value() for item in values["authoritative_fields"]),
        "recovery_evidence_refs": tuple(item.to_canonical_value() for item in values["recovery_evidence_refs"]),
        "disposition": values["disposition"].value,
    }


def _disposition(result: ContinuityResult) -> EvidenceDisposition:
    if result is ContinuityResult.CLOCK_ANOMALY:
        return EvidenceDisposition.SAFE_LATCHED
    if result in (ContinuityResult.QUALIFIED, ContinuityResult.EXACT_DUPLICATE, ContinuityResult.NO_AUTHORITATIVE_SEQUENCE):
        return EvidenceDisposition.QUALIFIED
    return EvidenceDisposition.UNQUALIFIED


def _reject_secrets(value: object, path: tuple[str | int, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                _fail("INVALID_EVIDENCE_PAYLOAD", path)
            if key.casefold() in _SECRET_NAMES:
                _fail("SECRET_BEARING_EVIDENCE", (*path, key))
            _reject_secrets(item, (*path, key))
    elif type(value) in (list, tuple):
        for index, item in enumerate(value):
            _reject_secrets(item, (*path, index))


def _utc(value: object, field: str) -> None:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _fail("INVALID_EVIDENCE_TIME", (field,))


def _signed_micros(value) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _micros(value) -> int:
    return _signed_micros(value)


def _fail(code: str, path: tuple[str | int, ...] = ()) -> None:
    raise MarketEvidenceError(code, path=path)


__all__ = ("qualify_recorded_input",)
