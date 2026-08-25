import ast
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autotrade_next.domain import identity as identity_module
from autotrade_next.domain.identity import (
    DeterministicIdentity,
    IdentityError,
    build_identity,
    identity_preimage,
)


class DuplicateFieldsMapping(Mapping):
    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(("decision_id",))

    def __len__(self):
        return 1

    def items(self):
        return (("decision_id", "d1"), ("decision_id", "d2"))


class BrokenFieldsMapping(DuplicateFieldsMapping):
    def items(self):
        raise RuntimeError("mapping mutated")


class ExplosiveRepresentation:
    def __repr__(self):
        raise AssertionError("foreign repr must not run")


CANDIDATE_FIELDS = {
    "instrument_id": "BTCIDR",
    "horizon_id": "1H",
    "trigger_kind": "CLOSED_BAR",
    "trigger_at_utc": datetime(2026, 8, 26, tzinfo=timezone.utc),
    "scan_trigger_version": "scan-v1",
    "data_revision": 1,
}

CANDIDATE_PREIMAGE = (
    '{"canonical_version":"atr-json-v1","domain":"autotrade-next.identity",'
    '"fields":[["instrument_id","BTCIDR"],["horizon_id","1H"],'
    '["trigger_kind","CLOSED_BAR"],'
    '["trigger_at_utc","2026-08-26T00:00:00.000000Z"],'
    '["scan_trigger_version","scan-v1"],["data_revision",1]],'
    '"kind":"candidate","recipe_version":1}'
).encode("utf-8")

CANDIDATE_DIGEST = "fd4bd6197684cf8ede801abe33a14859b0096746411805d267783201fe549d96"

OTHER_IDENTITY_VECTORS = (
    (
        "decision",
        {"candidate_id": "candidate:v1:abc", "policy_version": "p1"},
        b'{"canonical_version":"atr-json-v1","domain":"autotrade-next.identity",'
        b'"fields":[["candidate_id","candidate:v1:abc"],["policy_version","p1"]],'
        b'"kind":"decision","recipe_version":1}',
        "63fe2dbac634514dc1ce4bd07c3ec6998aa03b7dd71616e48bb2da4a2ebd05f0",
    ),
    (
        "intent",
        {"decision_id": "decision:v1:def"},
        b'{"canonical_version":"atr-json-v1","domain":"autotrade-next.identity",'
        b'"fields":[["decision_id","decision:v1:def"]],'
        b'"kind":"intent","recipe_version":1}',
        "e53275026c9fd685d42c7a2fe4bcdc2717ebe58b65d81f20256f4d3370c48526",
    ),
    (
        "event",
        {
            "authority_scope_id": "dryrun",
            "aggregate_id": "position:1",
            "aggregate_seq": 3,
            "event_type": "FillRecorded",
            "schema_version": 1,
        },
        b'{"canonical_version":"atr-json-v1","domain":"autotrade-next.identity",'
        b'"fields":[["authority_scope_id","dryrun"],["aggregate_id","position:1"],'
        b'["aggregate_seq",3],["event_type","FillRecorded"],["schema_version",1]],'
        b'"kind":"event","recipe_version":1}',
        "dc64a9c5559a5d09dd82fb02b792cdd1fe9609edbaa1cc62fad81f9210604c91",
    ),
    (
        "client_order",
        {
            "authority_scope_id": "dryrun",
            "intent_id": "intent:v1:ghi",
            "order_ordinal": 0,
        },
        b'{"canonical_version":"atr-json-v1","domain":"autotrade-next.identity",'
        b'"fields":[["authority_scope_id","dryrun"],["intent_id","intent:v1:ghi"],'
        b'["order_ordinal",0]],"kind":"client_order","recipe_version":1}',
        "0b3954023567e5856ee2e74f93b0060170fb7bc641844c120cb0f5491b23818d",
    ),
)


def test_candidate_identity_matches_exact_golden_vector():
    result = build_identity("candidate", dict(reversed(tuple(CANDIDATE_FIELDS.items()))))

    assert identity_preimage("candidate", CANDIDATE_FIELDS) == CANDIDATE_PREIMAGE
    assert result.kind == "candidate"
    assert result.recipe_version == 1
    assert result.digest == CANDIDATE_DIGEST
    assert result.key == f"candidate:v1:{CANDIDATE_DIGEST}"
    for _ in range(100):
        assert build_identity("candidate", CANDIDATE_FIELDS) == result


@pytest.mark.parametrize(("kind", "fields", "preimage", "digest"), OTHER_IDENTITY_VECTORS)
def test_every_identity_kind_matches_exact_golden_vector(kind, fields, preimage, digest):
    result = build_identity(kind, dict(reversed(tuple(fields.items()))))

    assert identity_preimage(kind, fields) == preimage
    assert result.digest == digest
    assert result.key == f"{kind}:v1:{digest}"
    for _ in range(100):
        assert build_identity(kind, fields) == result


def test_identity_separates_kind_field_name_optional_null_and_order_ordinal():
    candidate = build_identity("candidate", CANDIDATE_FIELDS)
    with_parent_null = build_identity(
        "candidate", {**CANDIDATE_FIELDS, "parent_position_id": None}
    )
    decision = build_identity(
        "decision", {"candidate_id": candidate.key, "policy_version": "p1"}
    )
    intent = build_identity("intent", {"decision_id": decision.key})
    first_order = build_identity(
        "client_order",
        {"authority_scope_id": "dryrun", "intent_id": intent.key, "order_ordinal": 0},
    )
    replacement_order = build_identity(
        "client_order",
        {"authority_scope_id": "dryrun", "intent_id": intent.key, "order_ordinal": 1},
    )

    assert candidate != with_parent_null
    assert len({candidate.digest, decision.digest, intent.digest, first_order.digest}) == 4
    assert first_order != replacement_order


def test_ordered_field_projection_prevents_separator_collision():
    left = build_identity(
        "decision",
        {"candidate_id": "x|policy_version=y", "policy_version": "z"},
    )
    right = build_identity(
        "decision",
        {"candidate_id": "x", "policy_version": "y|z"},
    )

    assert left != right


def test_recipe_metadata_is_pinned_inside_v1_registry(monkeypatch):
    expected = identity_preimage("candidate", CANDIDATE_FIELDS)
    monkeypatch.setattr(identity_module, "IDENTITY_DOMAIN", "mutated-domain")
    monkeypatch.setattr(identity_module, "CANONICAL_ENCODING_VERSION", "mutated-version")

    assert identity_preimage("candidate", CANDIDATE_FIELDS) == expected


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"kind": "unknown", "recipe_version": 1, "digest": "0" * 64}, "UNKNOWN_IDENTITY_KIND"),
        ({"kind": "intent", "recipe_version": True, "digest": "0" * 64}, "UNSUPPORTED_RECIPE_VERSION"),
        ({"kind": "intent", "recipe_version": 1, "digest": "A" * 64}, "INVALID_IDENTITY_DIGEST"),
        ({"kind": "intent", "recipe_version": 1, "digest": "0" * 63}, "INVALID_IDENTITY_DIGEST"),
    ],
)
def test_public_identity_result_rejects_invalid_state(kwargs, code):
    with pytest.raises(IdentityError) as caught:
        DeterministicIdentity(**kwargs)

    assert caught.value.code == code


@pytest.mark.parametrize(
    ("kind", "fields", "version", "code"),
    [
        ("unknown", {}, 1, "UNKNOWN_IDENTITY_KIND"),
        ("intent", {}, 1, "MISSING_IDENTITY_FIELD"),
        ("intent", {"decision_id": "d", "extra": 1}, 1, "UNEXPECTED_IDENTITY_FIELD"),
        ("intent", {"decision_id": "d"}, 2, "UNSUPPORTED_RECIPE_VERSION"),
        ("intent", {"decision_id": "d"}, True, "UNSUPPORTED_RECIPE_VERSION"),
    ],
)
def test_identity_rejects_unknown_recipe_or_projection(kind, fields, version, code):
    with pytest.raises(IdentityError) as caught:
        build_identity(kind, fields, recipe_version=version)

    assert caught.value.code == code


def test_identity_projection_snapshots_mapping_and_never_formats_foreign_values():
    with pytest.raises(IdentityError) as caught:
        build_identity("intent", DuplicateFieldsMapping())
    assert caught.value.code == "DUPLICATE_IDENTITY_FIELD"
    assert caught.value.field == "decision_id"

    with pytest.raises(IdentityError) as caught:
        build_identity("intent", BrokenFieldsMapping())
    assert caught.value.code == "INVALID_IDENTITY_FIELDS"

    unsafe = DuplicateFieldsMapping()
    unsafe.items = lambda: ((ExplosiveRepresentation(), "d"),)
    with pytest.raises(IdentityError) as caught:
        build_identity("intent", unsafe)
    assert caught.value.code == "UNEXPECTED_IDENTITY_FIELD"
    assert caught.value.field == "<non-string-field>"

    with pytest.raises(IdentityError) as caught:
        build_identity(ExplosiveRepresentation(), {})
    assert caught.value.code == "UNKNOWN_IDENTITY_KIND"
    assert caught.value.kind == "<non-string-kind>"


def test_identity_error_metadata_matches_domain_error_convention():
    with pytest.raises(IdentityError) as caught:
        build_identity("intent", {})

    error = caught.value
    assert error.code == error.error_code == "MISSING_IDENTITY_FIELD"
    assert error.severity == "ERROR"
    assert error.retryable is False
    assert error.evidence_ref is None
    assert error.correlation_id is None


def test_event_and_client_order_recipes_exclude_writer_epoch():
    event = build_identity(
        "event",
        {
            "authority_scope_id": "dryrun",
            "aggregate_id": "position:1",
            "aggregate_seq": 3,
            "event_type": "FillRecorded",
            "schema_version": 1,
        },
    )
    assert event.key.startswith("event:v1:")

    with pytest.raises(IdentityError) as caught:
        build_identity(
            "client_order",
            {
                "authority_scope_id": "dryrun",
                "intent_id": "intent:v1:abc",
                "order_ordinal": 0,
                "writer_epoch": 9,
            },
        )
    assert caught.value.code == "UNEXPECTED_IDENTITY_FIELD"


def test_domain_package_only_imports_stdlib_or_relative_domain_modules():
    source_root = Path(__file__).parents[3] / "autotrade_next" / "domain"
    allowed_absolute_roots = {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "hashlib",
        "json",
        "types",
        "typing",
        "unicodedata",
    }
    allowed_relative_modules = {"encoding", "errors", "identity", "numeric"}

    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                assert roots <= allowed_absolute_roots, (
                    path,
                    roots - allowed_absolute_roots,
                )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1, (path, "parent-relative import")
                    assert node.module in allowed_relative_modules, (path, node.module)
                elif node.module:
                    root = node.module.split(".", 1)[0]
                    assert root in allowed_absolute_roots, (path, node.module)
            elif isinstance(node, ast.Call):
                is_dunder_import = (
                    isinstance(node.func, ast.Name) and node.func.id == "__import__"
                )
                is_import_module = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                )
                assert not (is_dunder_import or is_import_module), (
                    path,
                    "dynamic import",
                )
