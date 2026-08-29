from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha1, sha256
import json
from pathlib import Path

import pytest

from autotrade_next.domain.content import ContentRecipe, ContentRef
from autotrade_next.domain.encoding import canonical_bytes
from autotrade_next.domain.errors import CapabilityRegistryError, MarketEvidenceError
from autotrade_next.domain.market import (
    AffectedScope,
    AuthScope,
    CapabilityArtifact,
    CapabilityEntry,
    CapabilityRegistry,
    CursorCapability,
    EvidenceRequirement,
    EvidenceRequirementSet,
    ProductFamily,
    QualificationStatus,
    RateLimitContract,
    RateLimitStatus,
    RecoveryContract,
    RecoveryMode,
    ScopeKind,
    TimestampContract,
    TimestampUnit,
)


NOW = datetime(2026, 8, 27, tzinfo=UTC)
LATER = datetime(2027, 1, 1, tzinfo=UTC)
COMMIT = "2e0c1fecb04cd30465ad81fd4be11ae66b5d0e19"
COMMIT_AUTHORED_AT = datetime(2026, 3, 3, 8, 12, 12, tzinfo=UTC)
DOCUMENT_COORDINATES = {
    "Public-RestAPI.md": (
        "9694c93b309dc9ba0c2d427190c37655e7cd4008",
        "aa5b9d30d9d07d196fae2cbdce26a0e71887f4f6c62d5af3d491aae943e2972c",
    ),
    "Private-RestAPI.md": (
        "26a9ddea4c8da0df9004466c7d51ae0811236cf0",
        "051d5c1437c4f3d756c2dfe13f9ba3c649f304323be3e62a448d348a85574e23",
    ),
    "INDODAX-TradeAPI-2.md": (
        "205ecaead0aa22b85bfdbff086cf4cb9bab780eb",
        "b094830f2993a877253a8c5592b59f0429b2dc6e5fccfd2c9d911512ec47efa4",
    ),
    "Marketdata-websocket.md": (
        "fb28a8009f706c2d2863f6b1da569fe81061833f",
        "0bd22b40559d1adb26b5b9097b9d1201d3abf8f08910acdf071563afbeeda46f",
    ),
    "Private-websocket.md": (
        "ea9e31464c769d48939321809c6eebed5651c128",
        "aca2ffc60b73a26aeba141a9ff9091e99bd9cb1fddc828784cad7f2223f2568f",
    ),
}


def _artifact(resource: str = "/api/depth/{pair}") -> CapabilityArtifact:
    assertions = ("buy and sell are authoritative depth fields",)
    fields = ("buy", "sell")
    payload_digest = sha256(b'{"buy":[],"sell":[]}').hexdigest()
    content = {
        "artifact_id": f"fixture:{resource}",
        "repository_commit": COMMIT,
        "document_path": "Public-RestAPI.md",
        "git_blob_digest": "1" * 40,
        "document_content_digest": "2" * 64,
        "extracted_assertions": assertions,
        "authoritative_fields": fields,
        "sanitized_payload_digest": payload_digest,
    }
    return CapabilityArtifact(
        artifact_id=f"fixture:{resource}",
        repository_commit=COMMIT,
        document_path="Public-RestAPI.md",
        git_blob_digest="1" * 40,
        document_content_digest="2" * 64,
        extracted_assertions=assertions,
        authoritative_fields=fields,
        sanitized_payload_digest=payload_digest,
        contract_ref=ContentRef.v2("indodax.contract-artifact", "capability-artifact", content),
    )


def _entry(*, effective_from: datetime = NOW, effective_until: datetime | None = LATER,
           resource: str = "/api/depth/{pair}") -> CapabilityEntry:
    artifact = _artifact(resource)
    return CapabilityEntry(
        capability_id=f"indodax.public-rest.depth:{effective_from.isoformat()}",
        version="2026-08-27",
        product=ProductFamily.PUBLIC_REST,
        base_url="https://indodax.com",
        resource=resource,
        documentation_commit=COMMIT,
        document_path="Public-RestAPI.md",
        git_blob_digest=artifact.git_blob_digest,
        document_content_digest=artifact.document_content_digest,
        effective_from=effective_from,
        effective_until=effective_until,
        auth_scope=AuthScope.PUBLIC,
        authoritative_fields=("buy", "sell"),
        cursor_capability=CursorCapability.NO_AUTHORITATIVE_SEQUENCE,
        snapshot_source=resource,
        timestamp_contract=TimestampContract(TimestampUnit.NONE, None),
        rate_limit_contract=RateLimitContract(
            RateLimitStatus.DOCUMENTED, 180, 60_000_000
        ),
        recovery_contract=RecoveryContract(RecoveryMode.SNAPSHOT, resource),
        qualification_status=QualificationStatus.QUALIFIED,
        artifact=artifact,
    )


def test_content_ref_v1_is_replay_compatible_and_v2_is_domain_separated() -> None:
    value = {"a": 1, "b": "dua"}
    expected = sha256(canonical_bytes(value)).hexdigest()
    assert ContentRef.v1("source-cursor", value).key == f"source-cursor:v1:{expected}"

    left = ContentRef.v2("market.evidence", "payload", value)
    right = ContentRef.v2("market.contract", "payload", value)
    assert left.recipe is ContentRecipe.V2
    assert left != right
    assert left.verify(value)
    assert not left.verify({"a": 2, "b": "dua"})


def test_registry_is_immutable_and_lookup_is_half_open_exact_one() -> None:
    entry = _entry()
    registry = CapabilityRegistry((entry,))
    assert registry.lookup(ProductFamily.PUBLIC_REST, entry.resource, NOW).entry == entry
    before = registry.lookup(ProductFamily.PUBLIC_REST, entry.resource, NOW - timedelta(microseconds=1))
    assert before.status is QualificationStatus.UNQUALIFIED
    assert before.reason.value == "NO_MATCH"
    assert before.entry is None
    assert registry.lookup(ProductFamily.PUBLIC_REST, entry.resource, LATER).reason.value == "NO_MATCH"
    assert registry.lookup(ProductFamily.PUBLIC_REST, "/api/unknown", NOW).entry is None
    assert registry.qualifies_field(entry, "buy", NOW)
    assert not registry.qualifies_field(entry, "last", NOW)
    with pytest.raises(FrozenInstanceError):
        entry.version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"base_url": ""}, "MISSING_CAPABILITY_FIELD"),
        ({"authoritative_fields": ()}, "MISSING_CAPABILITY_FIELD"),
        ({"effective_from": datetime(2026, 8, 27)}, "INVALID_EFFECTIVE_TIME"),
        ({"effective_until": NOW}, "INVALID_EFFECTIVE_INTERVAL"),
        ({"timestamp_contract": None}, "MISSING_CAPABILITY_FIELD"),
    ],
)
def test_registry_entry_rejects_missing_or_structurally_invalid_contract_fields(
    changes: dict[str, object], code: str
) -> None:
    with pytest.raises(CapabilityRegistryError) as caught:
        replace(_entry(), **changes)
    assert caught.value.code == code
    assert caught.value.partial_result is None


def test_registry_rejects_overlap_duplicate_moving_branch_and_artifact_drift() -> None:
    with pytest.raises(CapabilityRegistryError) as overlap:
        CapabilityRegistry((_entry(), _entry(effective_from=datetime(2026, 12, 1, tzinfo=UTC), effective_until=None)))
    assert overlap.value.code == "OVERLAPPING_CAPABILITY_INTERVAL"
    assert overlap.value.partial_result is None

    with pytest.raises(CapabilityRegistryError) as duplicate:
        CapabilityRegistry((_entry(), _entry()))
    assert duplicate.value.code == "DUPLICATE_CAPABILITY_KEY"

    values = {field: getattr(_entry(), field) for field in _entry().__dataclass_fields__}
    values["documentation_commit"] = "master"
    with pytest.raises(CapabilityRegistryError) as moving:
        CapabilityEntry(**values)
    assert moving.value.code == "MOVING_DOCUMENTATION_REFERENCE"

    values = {field: getattr(_entry(), field) for field in _entry().__dataclass_fields__}
    values["document_content_digest"] = "f" * 64
    with pytest.raises(CapabilityRegistryError) as drift:
        CapabilityEntry(**values)
    assert drift.value.code == "ARTIFACT_MISMATCH"


def test_registry_rejects_reused_artifact_and_wrong_content_reference_recipe() -> None:
    first = _entry()
    second = _entry(resource="/api/depth/other/{pair}")
    second_values = {
        field: getattr(second, field) for field in second.__dataclass_fields__
    }
    second_values["artifact"] = first.artifact
    reused = CapabilityEntry(**second_values)
    with pytest.raises(CapabilityRegistryError) as duplicate_artifact:
        CapabilityRegistry((first, reused))
    assert duplicate_artifact.value.code == "DUPLICATE_CAPABILITY_ARTIFACT"

    artifact = first.artifact
    artifact_values = {
        field: getattr(artifact, field) for field in artifact.__dataclass_fields__
    }
    artifact_values["contract_ref"] = ContentRef.v2(
        "foreign.contract-artifact", "capability-artifact", artifact.binding_value()
    )
    with pytest.raises(CapabilityRegistryError) as foreign_domain:
        CapabilityArtifact(**artifact_values)
    assert foreign_domain.value.code == "INVALID_ARTIFACT_REFERENCE"


def test_cross_product_recovery_route_is_bound_to_a_qualified_capability() -> None:
    target = replace(
        _entry(resource="/api/recovery"),
        capability_id="indodax.trade-api-v2.recovery:v1",
    )
    dependent = replace(
        _entry(resource="private:updates"),
        capability_id="indodax.private-ws.updates:v1",
        recovery_contract=RecoveryContract(
            RecoveryMode.REST_RECONCILIATION,
            target.resource,
            target.capability_id,
        ),
    )
    assert CapabilityRegistry((dependent, target)).entries == (dependent, target)

    with pytest.raises(CapabilityRegistryError) as missing:
        CapabilityRegistry((
            replace(
                dependent,
                recovery_contract=RecoveryContract(
                    RecoveryMode.REST_RECONCILIATION,
                    target.resource,
                    "missing-capability",
                ),
            ),
            target,
        ))
    assert missing.value.code == "INVALID_RECOVERY_CAPABILITY_BINDING"

    with pytest.raises(CapabilityRegistryError) as wrong_route:
        CapabilityRegistry((
            replace(
                dependent,
                recovery_contract=RecoveryContract(
                    RecoveryMode.REST_RECONCILIATION,
                    "/api/foreign",
                    target.capability_id,
                ),
            ),
            target,
        ))
    assert wrong_route.value.code == "INVALID_RECOVERY_CAPABILITY_BINDING"


def test_nested_values_are_defensively_frozen() -> None:
    assertions = ["documented"]
    fields = ["buy"]
    artifact = _artifact()
    values = {field: getattr(artifact, field) for field in artifact.__dataclass_fields__}
    values["extracted_assertions"] = assertions
    values["authoritative_fields"] = fields
    values["contract_ref"] = ContentRef.v2(
        "indodax.contract-artifact",
        "capability-artifact",
        {
            "artifact_id": values["artifact_id"],
            "repository_commit": values["repository_commit"],
            "document_path": values["document_path"],
            "git_blob_digest": values["git_blob_digest"],
            "document_content_digest": values["document_content_digest"],
            "extracted_assertions": tuple(assertions),
            "authoritative_fields": tuple(fields),
            "sanitized_payload_digest": values["sanitized_payload_digest"],
        },
    )
    frozen = CapabilityArtifact(**values)
    assertions.append("mutated")
    fields.append("sell")
    assert frozen.extracted_assertions == ("documented",)
    assert frozen.authoritative_fields == ("buy",)


def test_requirement_set_is_content_bound_and_enforces_exact_capability_set() -> None:
    entry = _entry()
    requirement = EvidenceRequirement(
        entry.capability_ref, entry.version, entry.resource, ("buy", "sell")
    )
    scope = AffectedScope(
        ScopeKind.INSTRUMENT_CHANNEL, "authority:idr", "BTC-IDR", entry.resource
    )
    policy_ref = ContentRef.v2("market.policy", "evidence-policy", {"version": "v1"})
    requirement_set = EvidenceRequirementSet.create(
        trigger="CLOSED_BAR",
        horizon_id="1m",
        instrument_id="BTC-IDR",
        scope=scope,
        effective_at=NOW,
        requirements=(requirement,),
        policy_ref=policy_ref,
    )
    requirement_set.assert_exact_capabilities((entry.capability_ref,))
    with pytest.raises(MarketEvidenceError) as missing:
        requirement_set.assert_exact_capabilities(())
    assert missing.value.code == "MISSING_REQUIRED_EVIDENCE"
    with pytest.raises(MarketEvidenceError) as duplicate:
        requirement_set.assert_exact_capabilities((entry.capability_ref, entry.capability_ref))
    assert duplicate.value.code == "DUPLICATE_EVIDENCE"
    foreign = ContentRef.v2("market.capability", "capability-entry", {"foreign": True})
    with pytest.raises(MarketEvidenceError) as extra:
        requirement_set.assert_exact_capabilities((entry.capability_ref, foreign))
    assert extra.value.code == "EXTRA_OR_FOREIGN_EVIDENCE"

    values = {
        field: getattr(requirement_set, field)
        for field in requirement_set.__dataclass_fields__
    }
    values["requirement_set_ref"] = ContentRef.v1(
        "requirement-set", requirement_set.binding_value()
    )
    with pytest.raises(MarketEvidenceError) as compatibility_recipe:
        EvidenceRequirementSet(**values)
    assert compatibility_recipe.value.code == "REQUIREMENT_SET_MISMATCH"


def test_offline_manifest_is_exactly_bound_to_every_registry_entry() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "indodax"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "indodax-capability-fixture-manifest:v2"
    assert manifest["upstream_repository"] == "https://github.com/btcid/indodax-official-api-docs.git"
    assert manifest["repository_commit"] == COMMIT
    assert manifest["repository_commit_authored_at"] == "2026-03-03T08:12:12Z"
    assert set(manifest["documents"]) == set(DOCUMENT_COORDINATES)
    rows = {row["capability_id"]: row for row in manifest["entries"]}
    from autotrade_next.adapters.indodax.capability_registry import INDODAX_CAPABILITY_REGISTRY

    assert set(rows) == {entry.capability_id for entry in INDODAX_CAPABILITY_REGISTRY.entries}
    for entry in INDODAX_CAPABILITY_REGISTRY.entries:
        row = rows[entry.capability_id]
        artifact = entry.artifact
        document = fixture_root / manifest["documents"][artifact.document_path]
        document_bytes = document.read_bytes()
        git_blob_preimage = (
            f"blob {len(document_bytes)}\0".encode("ascii") + document_bytes
        )
        payload = json.loads((fixture_root / row["fixture_path"]).read_text(encoding="utf-8"))
        assert row["repository_commit"] == artifact.repository_commit
        assert row["document_path"] == artifact.document_path
        assert row["git_blob_digest"] == artifact.git_blob_digest
        assert row["document_content_digest"] == artifact.document_content_digest
        assert tuple(row["extracted_assertions"]) == artifact.extracted_assertions
        assert tuple(row["authoritative_fields"]) == artifact.authoritative_fields
        assert row["artifact_ref"] == artifact.contract_ref.key
        assert row["qualification_status"] == entry.qualification_status.value
        assert sha1(git_blob_preimage).hexdigest() == artifact.git_blob_digest
        assert sha256(document_bytes).hexdigest() == artifact.document_content_digest
        assert (
            artifact.git_blob_digest,
            artifact.document_content_digest,
        ) == DOCUMENT_COORDINATES[artifact.document_path]
        assert sha256(canonical_bytes(payload)).hexdigest() == artifact.sanitized_payload_digest
        assert all(term not in canonical_bytes(payload).lower() for term in (b"api_key", b"secret", b"token"))


def test_verified_document_coordinates_replace_every_synthetic_coordinate() -> None:
    from autotrade_next.adapters.indodax.capability_registry import INDODAX_CAPABILITY_REGISTRY

    for entry in INDODAX_CAPABILITY_REGISTRY.entries:
        synthetic_blob = sha1(
            f"git-blob:{entry.document_path}@{entry.documentation_commit}".encode()
        ).hexdigest()
        synthetic_content = sha256(
            f"document:{entry.document_path}@{entry.documentation_commit}".encode()
        ).hexdigest()
        assert entry.git_blob_digest != synthetic_blob
        assert entry.document_content_digest != synthetic_content
        expected = (
            QualificationStatus.UNQUALIFIED
            if entry.capability_id == "private-rest.trade-history.deprecated"
            else QualificationStatus.QUALIFIED
        )
        assert entry.qualification_status is expected


def test_pinned_product_metadata_does_not_inherit_foreign_contracts() -> None:
    from autotrade_next.adapters.indodax.capability_registry import INDODAX_CAPABILITY_REGISTRY

    entries = {entry.capability_id: entry for entry in INDODAX_CAPABILITY_REGISTRY.entries}
    public = entries["public-rest.depth.v1"]
    private = entries["private-rest.get-info.v1"]
    trade = entries["trade-api-v2.my-trades.v1"]
    private_ws = entries["private-ws.order-update.v1"]

    assert public.rate_limit_contract == RateLimitContract(
        RateLimitStatus.DOCUMENTED, 180, 60_000_000
    )
    assert private.rate_limit_contract == RateLimitContract(
        RateLimitStatus.NOT_DOCUMENTED
    )
    assert trade.rate_limit_contract == RateLimitContract(
        RateLimitStatus.NOT_DOCUMENTED
    )
    assert trade.base_url == "https://tapi.indodax.com"
    assert trade.artifact.extracted_assertions == (
        "Trade API 2.0 uses X-APIKEY and HMAC-SHA512",
    )
    assert all(entry.effective_from == COMMIT_AUTHORED_AT for entry in entries.values())
    assert private.timestamp_contract == TimestampContract(
        TimestampUnit.SECONDS, "return.server_time"
    )
    assert trade.timestamp_contract == TimestampContract(
        TimestampUnit.MILLISECONDS, "data[].time"
    )
    assert private_ws.base_url == (
        "wss://pws.indodax.com/ws/?cf_ws_frame_ping_pong=true"
    )


@pytest.mark.parametrize(
    "contract",
    [
        lambda: RateLimitContract(RateLimitStatus.NOT_DOCUMENTED, 180, 60_000_000),
        lambda: RateLimitContract(RateLimitStatus.DOCUMENTED),
        lambda: RateLimitContract(RateLimitStatus.DOCUMENTED, 0, 60_000_000),
    ],
)
def test_rate_limit_contract_rejects_documentation_overclaims(contract) -> None:
    with pytest.raises(CapabilityRegistryError) as caught:
        contract()
    assert caught.value.code == "INVALID_RATE_LIMIT_CONTRACT"
