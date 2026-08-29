from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

import pytest

from autotrade_next.domain.candidate import (
    CandidateCaptureError,
    CandidateEligibility,
    CandidateProvenance,
    CandidateProvenanceV2,
    CandidateSourceV2,
    CandidateSnapshot,
    CandidateTrigger,
    ClockRead,
    EligibilityReason,
    RngRef,
    RuntimeManifestRef,
    SourceCursor,
    StableRef,
    capture_candidate,
    capture_candidate_v2,
    derive_revision_token,
    revise_candidate,
)
from autotrade_next.domain.encoding import canonical_bytes
from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.identity import build_identity
from autotrade_next.domain.market import (
    AffectedScope,
    EvidencePolicy,
    EvidenceRequirement,
    EvidenceRequirementSet,
    ProductFamily,
    ScopeKind,
)
from autotrade_next.adapters.indodax.capability_registry import INDODAX_CAPABILITY_REGISTRY
from autotrade_next.adapters.indodax.market_evidence import qualify_recorded_input


TRIGGER_AT = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 8, 26, 0, 0, 0, 125000, tzinfo=UTC)
LOGIC_TEST_REGISTRY = INDODAX_CAPABILITY_REGISTRY


def _provenance(**overrides: object) -> CandidateProvenance:
    values: dict[str, object] = {
        "authority_scope_id": "virtual-autotrade",
        "portfolio_id": "dryrun-main",
        "experiment_id": "experiment:no-entry-v1",
        "strategy_version": "no-entry:v1",
        "correlation_id": "corr:scan-001",
        "causation_id": "trigger:bar-001",
        "ordered_input_ids": ["bar:btc:001", "book:btc:001"],
        "event_at_utc": TRIGGER_AT,
        "received_at_utc": RECEIVED_AT,
        "source_cursors": [
            SourceCursor(
                source_id="indodax-public-rest",
                venue_cursor=None,
                ingest_cursor="ingest:0001",
                cursor_capability="NO_AUTHORITATIVE_SEQUENCE",
                freshness_micros=125000,
                quality="QUALIFIED",
            )
        ],
        "eligibility": CandidateEligibility(executable=True),
        "universe_ref": StableRef("universe", "spot-idr:v1"),
        "instrument_rules_ref": StableRef("instrument-rules", "btc_idr:v7"),
        "scheduler_ref": StableRef("scheduler", "closed-bar:v2"),
        "clock_reads": [ClockRead("policy-clock", TRIGGER_AT)],
        "rng_ref": RngRef("pcg64", "sha256:seed-state-001"),
        "runtime_ref": RuntimeManifestRef(
            runtime_version="cpython:3.12.14",
            numeric_version="scaled-integer:v1",
            environment_ref="env:dryrun:v1",
            code_commit="13b54a97dd0781613b73e6797bfaa7a289b42927",
            image_digest="sha256:image001",
            dependency_lock_ref="uv-lock:001",
        ),
        "data_ref": StableRef("data", "dataset:001"),
        "feature_ref": StableRef("feature", "features:v1"),
        "model_ref": StableRef("model", "no-model:v1"),
        "config_ref": StableRef("config", "sha256:config001"),
        "external_response_ids": ["response:market:001"],
    }
    values.update(overrides)
    return CandidateProvenance(**values)  # type: ignore[arg-type]


def _capture(**overrides: object) -> CandidateSnapshot:
    values: dict[str, object] = {
        "instrument_id": "btc_idr",
        "horizon_id": "1H",
        "trigger_kind": CandidateTrigger.CLOSED_BAR,
        "trigger_at_utc": TRIGGER_AT,
        "scan_trigger_version": "closed-bar:v2",
        "data_revision": "revision:001",
        "provenance": _provenance(),
    }
    values.update(overrides)
    return capture_candidate(**values)  # type: ignore[arg-type]


def test_closed_bar_capture_is_exact_and_deterministic() -> None:
    candidate = _capture()
    expected_id = build_identity(
        "candidate",
        {
            "instrument_id": "btc_idr",
            "horizon_id": "1H",
            "trigger_kind": "CLOSED_BAR",
            "trigger_at_utc": TRIGGER_AT,
            "scan_trigger_version": "closed-bar:v2",
            "data_revision": "revision:001",
        },
    )

    assert candidate.candidate_id == expected_id
    assert candidate.executable is True
    assert candidate.original_candidate_id is None
    assert canonical_bytes(candidate.to_canonical_value()) == candidate.canonical_bytes()
    expected_bytes = candidate.canonical_bytes()
    for _ in range(100):
        duplicate = _capture()
        assert duplicate.candidate_id == candidate.candidate_id
        assert duplicate.canonical_bytes() == expected_bytes


def test_protective_trigger_requires_parent_and_uses_existing_recipe() -> None:
    candidate = _capture(
        trigger_kind=CandidateTrigger.PROTECTIVE_EVENT,
        parent_position_id="position:btc:001",
        scan_trigger_version="protective:v1",
    )
    assert candidate.candidate_id == build_identity(
        "candidate",
        {
            "instrument_id": "btc_idr",
            "horizon_id": "1H",
            "trigger_kind": "PROTECTIVE_EVENT",
            "trigger_at_utc": TRIGGER_AT,
            "scan_trigger_version": "protective:v1",
            "data_revision": "revision:001",
            "parent_position_id": "position:btc:001",
        },
    )


@pytest.mark.parametrize(
    ("trigger", "parent"),
    [
        (CandidateTrigger.CLOSED_BAR, "position:unexpected"),
        (CandidateTrigger.PROTECTIVE_EVENT, None),
    ],
)
def test_trigger_parent_contract_is_fail_closed(
    trigger: CandidateTrigger, parent: str | None
) -> None:
    with pytest.raises(CandidateCaptureError) as caught:
        _capture(trigger_kind=trigger, parent_position_id=parent)
    assert caught.value.error_code == "INVALID_CANDIDATE_PARENT"
    assert caught.value.path == ("parent_position_id",)
    assert caught.value.partial_snapshot is None


def test_complete_bad_evidence_is_immutable_non_executable_fact() -> None:
    provenance = _provenance(
        eligibility=CandidateEligibility(
            executable=False,
            reason=EligibilityReason.GAPPED,
            evidence_ref="gap:market:001",
        )
    )
    candidate = _capture(provenance=provenance)
    assert candidate.executable is False
    assert candidate.eligibility_reason is EligibilityReason.GAPPED
    assert candidate.canonical_bytes()


def test_revision_is_new_deterministic_audit_only_fact_with_root_lineage() -> None:
    original = _capture()
    original_bytes = original.canonical_bytes()
    corrected_provenance = _provenance(
        ordered_input_ids=["bar:btc:001:corrected", "book:btc:001"]
    )
    corrected = revise_candidate(
        original,
        data_revision=derive_revision_token(original, corrected_provenance),
        provenance=corrected_provenance,
    )
    repeated = revise_candidate(
        original,
        data_revision=derive_revision_token(original, corrected_provenance),
        provenance=corrected_provenance,
    )
    chained = revise_candidate(
        corrected,
        data_revision=derive_revision_token(corrected, corrected_provenance),
        provenance=corrected_provenance,
    )

    assert corrected.candidate_id != original.candidate_id
    assert corrected.original_candidate_id == original.candidate_id
    assert corrected.executable is False
    assert corrected.eligibility_reason is EligibilityReason.LATE_CORRECTION
    assert repeated.canonical_bytes() == corrected.canonical_bytes()
    assert chained.original_candidate_id == original.candidate_id
    assert original.canonical_bytes() == original_bytes


def test_revision_rejects_same_revision_and_scope_change() -> None:
    original = _capture()
    with pytest.raises(CandidateCaptureError) as same_revision:
        revise_candidate(original, data_revision="revision:001", provenance=_provenance())
    assert same_revision.value.error_code == "INVALID_CANDIDATE_REVISION"

    changed_scope = _provenance(portfolio_id="dryrun-other")
    with pytest.raises(CandidateCaptureError) as scope_mismatch:
        revise_candidate(
            original,
            data_revision=derive_revision_token(original, changed_scope),
            provenance=changed_scope,
        )
    assert scope_mismatch.value.error_code == "CANDIDATE_SCOPE_MISMATCH"


def test_revision_lineage_cannot_be_forged_or_return_to_root_identity() -> None:
    original = _capture()
    late = CandidateEligibility(
        executable=False,
        reason=EligibilityReason.LATE_CORRECTION,
        evidence_ref=original.candidate_id.key,
    )
    with pytest.raises(CandidateCaptureError) as missing_original:
        _capture(provenance=_provenance(eligibility=late))
    assert missing_original.value.error_code == "INVALID_CANDIDATE_REVISION"

    corrected = revise_candidate(
        original,
        data_revision=derive_revision_token(original, _provenance()),
        provenance=_provenance(),
    )
    with pytest.raises(CandidateCaptureError) as reused_root:
        revise_candidate(
            corrected, data_revision="revision:001", provenance=_provenance()
        )
    assert reused_root.value.error_code == "INVALID_CANDIDATE_REVISION"


def test_nested_inputs_are_defensively_frozen_and_order_is_semantic() -> None:
    input_ids = ["bar:1", "book:1"]
    response_ids = ["response:1"]
    provenance = _provenance(
        ordered_input_ids=input_ids,
        external_response_ids=response_ids,
    )
    candidate = _capture(provenance=provenance)
    before = candidate.canonical_bytes()
    input_ids.append("bar:late")
    response_ids[0] = "response:changed"

    assert candidate.provenance.ordered_input_ids == ("bar:1", "book:1")
    assert candidate.provenance.external_response_ids == ("response:1",)
    assert candidate.canonical_bytes() == before
    with pytest.raises(FrozenInstanceError):
        candidate.instrument_id = "eth_idr"  # type: ignore[misc]

    reordered = _capture(
        provenance=_provenance(ordered_input_ids=["book:1", "bar:1"])
    )
    assert reordered.candidate_id == candidate.candidate_id
    assert reordered.canonical_bytes() != candidate.canonical_bytes()


@pytest.mark.parametrize("field", ["authority_scope_id", "correlation_id"])
def test_missing_or_blank_required_reference_is_typed(field: str) -> None:
    with pytest.raises(CandidateCaptureError) as caught:
        _capture(provenance=_provenance(**{field: ""}))
    assert caught.value.error_code == "INVALID_CANDIDATE_REFERENCE"
    assert caught.value.path == (field,)


@pytest.mark.parametrize(
    "bad_timestamp",
    [datetime(2026, 8, 26), datetime(2026, 8, 26, tzinfo=timezone(timedelta(hours=7)))],
)
def test_non_utc_timestamp_is_rejected(bad_timestamp: datetime) -> None:
    with pytest.raises(CandidateCaptureError) as caught:
        _capture(trigger_at_utc=bad_timestamp)
    assert caught.value.error_code == "INVALID_CANDIDATE_TIMESTAMP"
    assert caught.value.path == ("trigger_at_utc",)


@pytest.mark.parametrize("bad", [1.5, Decimal("1.5"), {"secret": "credential"}])
def test_unsupported_or_secret_bearing_reference_is_rejected(bad: object) -> None:
    with pytest.raises(CandidateCaptureError) as caught:
        _capture(provenance=_provenance(config_ref=bad))
    assert caught.value.error_code == "INVALID_CANDIDATE_VALUE"
    assert caught.value.partial_snapshot is None


def test_candidate_snapshot_cannot_be_constructed_with_inconsistent_identity() -> None:
    valid = _capture()
    other_id = build_identity(
        "candidate",
        {
            "instrument_id": "eth_idr",
            "horizon_id": "1H",
            "trigger_kind": "CLOSED_BAR",
            "trigger_at_utc": TRIGGER_AT,
            "scan_trigger_version": "closed-bar:v2",
            "data_revision": "revision:001",
        },
    )
    with pytest.raises(CandidateCaptureError):
        replace(valid, candidate_id=other_id)


def test_source_quality_freshness_and_rng_algorithm_are_canonical() -> None:
    candidate = _capture()
    cursor = candidate.provenance.source_cursors[0]
    assert cursor.freshness_micros == 125000
    assert cursor.quality == "QUALIFIED"
    assert candidate.provenance.rng_ref.algorithm == "pcg64"
    assert b'"freshness_micros":125000' in candidate.canonical_bytes()
    assert b'"algorithm":"pcg64"' in candidate.canonical_bytes()


@pytest.mark.parametrize("bad", ["   ", "e\u0301", "\ud800"])
def test_invalid_reference_is_rejected_at_capture_boundary(bad: str) -> None:
    with pytest.raises(CandidateCaptureError) as caught:
        _capture(instrument_id=bad)
    assert caught.value.error_code == "INVALID_CANDIDATE_REFERENCE"
    assert caught.value.path == ("instrument_id",)
    assert caught.value.partial_snapshot is None


@pytest.mark.parametrize(
    "config_ref",
    [
        StableRef("config", "password=hunter2"),
        StableRef("config", "raw-json:{secret:true}"),
        StableRef("other", "sha256:config001"),
    ],
)
def test_config_ref_must_be_opaque_version_or_hash(config_ref: StableRef) -> None:
    with pytest.raises(CandidateCaptureError) as caught:
        _capture(provenance=_provenance(config_ref=config_ref))
    assert caught.value.error_code == "INVALID_CANDIDATE_REFERENCE"
    assert caught.value.path == ("config_ref",)


def test_revision_chain_is_complete_and_branch_tokens_do_not_collide() -> None:
    root = _capture()
    provenance = _provenance(ordered_input_ids=["corrected:1"])
    revision_two_token = derive_revision_token(root, provenance)
    revision_two = revise_candidate(
        root, data_revision=revision_two_token, provenance=provenance
    )
    root_branch_token = derive_revision_token(root, provenance)
    chained_token = derive_revision_token(revision_two, provenance)

    assert revision_two.revision_lineage == (root.candidate_id,)
    assert root_branch_token != chained_token

    revision_three = revise_candidate(
        revision_two, data_revision=chained_token, provenance=provenance
    )
    assert revision_three.revision_lineage == (
        root.candidate_id,
        revision_two.candidate_id,
    )

    with pytest.raises(CandidateCaptureError) as reused:
        revise_candidate(
            revision_two,
            data_revision=revision_two_token,
            provenance=provenance,
        )
    assert reused.value.error_code == "INVALID_CANDIDATE_REVISION"

    with pytest.raises(CandidateCaptureError) as forged:
        replace(
            revision_three,
            revision_lineage=(root.candidate_id, other_candidate_id()),
        )
    assert forged.value.error_code == "INVALID_CANDIDATE_REVISION"


def other_candidate_id() -> object:
    return build_identity(
        "candidate",
        {
            "instrument_id": "eth_idr",
            "horizon_id": "1H",
            "trigger_kind": "CLOSED_BAR",
            "trigger_at_utc": TRIGGER_AT,
            "scan_trigger_version": "closed-bar:v2",
            "data_revision": "revision:001",
        },
    )


def _v2_evidence(*, connected: bool = True):
    policy = EvidencePolicy("market-policy:v1")
    scope = AffectedScope(
        ScopeKind.INSTRUMENT_CHANNEL,
        "authority:indodax",
        "BTC-IDR",
        "market:order-book-btcidr",
    )
    admission = qualify_recorded_input(
        registry=LOGIC_TEST_REGISTRY,
        product=ProductFamily.MARKET_DATA_WEBSOCKET,
        resource="market:order-book-{pair}",
        effective_at=TRIGGER_AT,
        instrument_id="BTC-IDR",
        scope=scope,
        payload={
            "result": {
                "channel": "market:order-book-btcidr",
                "data": {
                    "data": {"pair": "btcidr", "ask": [], "bid": []},
                    "offset": 7,
                },
            },
        },
        event_at_utc=TRIGGER_AT,
        received_at_utc=TRIGGER_AT,
        evaluated_at_utc=TRIGGER_AT,
        venue_cursor=7,
        ingest_cursor="ingest:7",
        policy=policy,
        connected=connected,
    )
    assert admission.evidence is not None
    entry = LOGIC_TEST_REGISTRY.lookup(
        ProductFamily.MARKET_DATA_WEBSOCKET,
        "market:order-book-{pair}",
        TRIGGER_AT,
    ).entry
    assert entry is not None
    requirement = EvidenceRequirement(
        entry.capability_ref,
        entry.version,
        entry.resource,
        tuple(field.field for field in admission.evidence.authoritative_fields),
    )
    policy_ref = ContentRef.v2("market.policy", "evidence-policy", policy.to_canonical_value())
    requirement_set = EvidenceRequirementSet.create(
        trigger=CandidateTrigger.CLOSED_BAR.value,
        horizon_id="1m",
        instrument_id="BTC-IDR",
        scope=scope,
        effective_at=TRIGGER_AT,
        requirements=(requirement,),
        policy_ref=policy_ref,
    )
    return admission.evidence, requirement_set


def _provenance_v2(*, sources=None, requirements=None, eligibility=None) -> CandidateProvenanceV2:
    evidence, default_requirements = _v2_evidence()
    return CandidateProvenanceV2(
        authority_scope_id="authority:indodax",
        portfolio_id="dryrun-main",
        experiment_id="experiment:no-entry-v1",
        strategy_version="no-entry:v1",
        correlation_id="corr:v2",
        causation_id="cause:v2",
        ordered_input_ids=("bar:btc:001", evidence.evidence_ref.key),
        event_at_utc=TRIGGER_AT,
        received_at_utc=TRIGGER_AT,
        sources=(CandidateSourceV2("indodax-market-ws", evidence),) if sources is None else sources,
        evidence_requirements=default_requirements if requirements is None else requirements,
        eligibility=CandidateEligibility(True) if eligibility is None else eligibility,
        universe_ref=StableRef("universe", "spot-idr:v1"),
        instrument_rules_ref=StableRef("instrument-rules", "btc_idr:v7"),
        scheduler_ref=StableRef("scheduler", "closed-bar:v2"),
        clock_reads=(ClockRead("policy-clock", TRIGGER_AT),),
        rng_ref=RngRef("pcg64", "sha256:seed-state-001"),
        runtime_ref=RuntimeManifestRef(
            "cpython:3.12.14", "scaled-integer:v1", "env:dryrun:v1",
            "13b54a97dd0781613b73e6797bfaa7a289b42927", "sha256:image001", "uv-lock:001",
        ),
        data_ref=StableRef("data", "dataset:001"),
        feature_ref=StableRef("feature", "features:v1"),
        model_ref=StableRef("model", "no-model:v1"),
        config_ref=StableRef("config", "sha256:config001"),
    )


def _capture_v2(**overrides: object) -> CandidateSnapshot:
    values: dict[str, object] = {
        "instrument_id": "BTC-IDR",
        "horizon_id": "1m",
        "trigger_kind": CandidateTrigger.CLOSED_BAR,
        "trigger_at_utc": TRIGGER_AT,
        "scan_trigger_version": "closed-bar:v2",
        "data_revision": "revision:001",
        "provenance": _provenance_v2(),
    }
    values.update(overrides)
    return capture_candidate_v2(**values)  # type: ignore[arg-type]


def test_v2_candidate_is_same_class_new_serializer_and_identity_recipe_stays_v1() -> None:
    candidate = _capture_v2()
    assert type(candidate) is CandidateSnapshot
    assert candidate.provenance_version == "v2"
    assert candidate.to_canonical_value()["schema_version"] == "candidate-snapshot:v2"
    assert candidate.candidate_id == build_identity(
        "candidate",
        {
            "instrument_id": "BTC-IDR",
            "horizon_id": "1m",
            "trigger_kind": "CLOSED_BAR",
            "trigger_at_utc": TRIGGER_AT,
            "scan_trigger_version": "closed-bar:v2",
            "data_revision": "revision:001",
        },
    )
    assert b'"evidence_requirements"' in candidate.canonical_bytes()


def test_v2_candidate_golden_digest_is_stable() -> None:
    candidate = _capture_v2()
    assert sha256(candidate.canonical_bytes()).hexdigest() == (
        "f0735d7f58b93939e7784a8d9b06c48c485eb399e237acfca088590fd6ec4084"
    )


def test_v2_executable_admission_rejects_missing_duplicate_and_foreign_proof() -> None:
    evidence, requirements = _v2_evidence()
    with pytest.raises(CandidateCaptureError) as missing:
        _provenance_v2(sources=(), requirements=requirements)
    assert missing.value.code == "MISSING_CANDIDATE_PROVENANCE"
    with pytest.raises(CandidateCaptureError) as duplicate:
        _provenance_v2(
            sources=(CandidateSourceV2("one", evidence), CandidateSourceV2("two", evidence)),
            requirements=requirements,
        )
    assert duplicate.value.code == "DUPLICATE_CANDIDATE_EVIDENCE"

    foreign_requirements = EvidenceRequirementSet.create(
        trigger=requirements.trigger,
        horizon_id=requirements.horizon_id,
        instrument_id="ETH-IDR",
        scope=requirements.scope,
        effective_at=requirements.effective_at,
        requirements=requirements.requirements,
        policy_ref=requirements.policy_ref,
    )
    with pytest.raises(CandidateCaptureError) as foreign:
        _capture_v2(provenance=_provenance_v2(requirements=foreign_requirements))
    assert foreign.value.code == "CANDIDATE_EVIDENCE_SCOPE_MISMATCH"

    with pytest.raises(CandidateCaptureError) as foreign_authority:
        replace(_provenance_v2(), authority_scope_id="authority:foreign")
    assert foreign_authority.value.code == "CANDIDATE_EVIDENCE_SCOPE_MISMATCH"

    extra_admission = qualify_recorded_input(
        registry=LOGIC_TEST_REGISTRY,
        product=ProductFamily.PUBLIC_REST,
        resource="/api/depth/{pair}",
        effective_at=TRIGGER_AT,
        instrument_id="BTC-IDR",
        scope=AffectedScope(
            ScopeKind.INSTRUMENT_CHANNEL,
            "authority:indodax",
            "BTC-IDR",
            "/api/depth/btcidr",
        ),
        payload={"buy": [], "sell": []},
        event_at_utc=TRIGGER_AT,
        received_at_utc=TRIGGER_AT,
        evaluated_at_utc=TRIGGER_AT,
        venue_cursor=None,
        ingest_cursor="ingest:public-depth",
        policy=evidence.policy,
    )
    assert extra_admission.evidence is not None
    with pytest.raises(CandidateCaptureError) as extra:
        _capture_v2(
            provenance=_provenance_v2(
                sources=(
                    CandidateSourceV2("indodax-market-ws", evidence),
                    CandidateSourceV2("indodax-public-rest", extra_admission.evidence),
                ),
                requirements=requirements,
            )
        )
    assert extra.value.code == "EXTRA_OR_FOREIGN_EVIDENCE"


def test_v2_admission_rejects_foreign_policy_and_inexact_authoritative_field_set() -> None:
    evidence, requirements = _v2_evidence()
    foreign_policy_requirements = EvidenceRequirementSet.create(
        trigger=requirements.trigger,
        horizon_id=requirements.horizon_id,
        instrument_id=requirements.instrument_id,
        scope=requirements.scope,
        effective_at=requirements.effective_at,
        requirements=requirements.requirements,
        policy_ref=ContentRef.v2(
            "market.policy",
            "evidence-policy",
            EvidencePolicy("foreign-policy:v1").to_canonical_value(),
        ),
    )
    with pytest.raises(CandidateCaptureError) as foreign_policy:
        _capture_v2(
            provenance=_provenance_v2(
                sources=(CandidateSourceV2("indodax-market-ws", evidence),),
                requirements=foreign_policy_requirements,
            )
        )
    assert foreign_policy.value.code == "FOREIGN_EVIDENCE_POLICY"

    inexact_requirement = EvidenceRequirement(
        requirements.requirements[0].capability_ref,
        requirements.requirements[0].capability_version,
        requirements.requirements[0].resource,
        ("ask", "bid", "pair"),
    )
    inexact_field_requirements = EvidenceRequirementSet.create(
        trigger=requirements.trigger,
        horizon_id=requirements.horizon_id,
        instrument_id=requirements.instrument_id,
        scope=requirements.scope,
        effective_at=requirements.effective_at,
        requirements=(inexact_requirement,),
        policy_ref=requirements.policy_ref,
    )
    with pytest.raises(CandidateCaptureError) as inexact_fields:
        _capture_v2(
            provenance=_provenance_v2(
                sources=(CandidateSourceV2("indodax-market-ws", evidence),),
                requirements=inexact_field_requirements,
            )
        )
    assert inexact_fields.value.code == "EVIDENCE_FIELD_SET_MISMATCH"


def test_v2_admission_binds_capability_version_and_evaluation_time() -> None:
    evidence, requirements = _v2_evidence()

    version_binding = evidence.binding_value()
    version_binding["capability_version"] = "foreign-version"
    foreign_version = replace(
        evidence,
        capability_version="foreign-version",
        evidence_ref=ContentRef.v2(
            "market.evidence", "market-evidence", version_binding
        ),
    )
    with pytest.raises(CandidateCaptureError) as version:
        _capture_v2(
            provenance=_provenance_v2(
                sources=(CandidateSourceV2("indodax-market-ws", foreign_version),),
                requirements=requirements,
            )
        )
    assert version.value.code == "FOREIGN_CAPABILITY_VERSION"

    later = TRIGGER_AT + timedelta(microseconds=1)
    time_binding = evidence.binding_value()
    time_binding["effective_at"] = later
    stale = replace(
        evidence,
        effective_at=later,
        evidence_ref=ContentRef.v2(
            "market.evidence", "market-evidence", time_binding
        ),
    )
    with pytest.raises(CandidateCaptureError) as reused:
        _capture_v2(
            provenance=_provenance_v2(
                sources=(CandidateSourceV2("indodax-market-ws", stale),),
                requirements=requirements,
            )
        )
    assert reused.value.code == "STALE_CANDIDATE_EVIDENCE"


def test_complete_bad_evidence_is_auditable_but_never_executable() -> None:
    bad, requirements = _v2_evidence(connected=False)
    provenance = _provenance_v2(
        sources=(CandidateSourceV2("indodax-market-ws", bad),),
        requirements=requirements,
        eligibility=CandidateEligibility(False, EligibilityReason.GAPPED, bad.evidence_ref.key),
    )
    candidate = _capture_v2(provenance=provenance)
    assert not candidate.executable
    assert bad.evidence_ref.key.encode() in candidate.canonical_bytes()

    with pytest.raises(CandidateCaptureError) as claimed:
        _capture_v2(provenance=replace(provenance, eligibility=CandidateEligibility(True)))
    assert claimed.value.code == "UNQUALIFIED_CANDIDATE_EVIDENCE"
