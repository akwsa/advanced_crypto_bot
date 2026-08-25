from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum, IntEnum

import pytest

from autotrade_next.domain.encoding import (
    CANONICAL_ENCODING_VERSION,
    MAX_CANONICAL_DEPTH,
    CanonicalEncodingError,
    canonical_bytes,
)
from autotrade_next.domain.numeric import MAX_CANONICAL_INTEGER_BITS, ScaledInteger


class TextState(Enum):
    READY = "READY"


class NumericState(IntEnum):
    READY = 1


class DatetimeSubclass(datetime):
    pass


class ExplosiveComparison:
    def __eq__(self, other):
        raise AssertionError("foreign equality must not run")


class ExplosiveRepresentation:
    def __repr__(self):
        raise AssertionError("foreign repr must not run")


class DuplicateItemsMapping(Mapping):
    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(("same",))

    def __len__(self):
        return 1

    def items(self):
        return (("same", 1), ("same", 2))


class BrokenItemsMapping(DuplicateItemsMapping):
    def items(self):
        raise RuntimeError("mapping changed during snapshot")


def test_canonical_bytes_are_exact_utf8_and_order_independent():
    first = {
        "z": None,
        "a": [
            ScaledInteger(units=-120, scale=2),
            datetime(2026, 8, 26, tzinfo=timezone.utc),
            TextState.READY,
            "é",
        ],
    }
    second = {"a": first["a"], "z": None}
    expected = (
        '{"a":[{"scale":2,"units":-120},'
        '"2026-08-26T00:00:00.000000Z","READY","é"],"z":null}'
    ).encode("utf-8")

    assert CANONICAL_ENCODING_VERSION == "atr-json-v1"
    assert canonical_bytes(first) == expected
    assert canonical_bytes(second) == expected
    assert not expected.startswith(b"\xef\xbb\xbf")
    assert not expected.endswith(b"\n")
    for _ in range(100):
        assert canonical_bytes(first) == expected


@pytest.mark.parametrize(
    ("value", "code", "path"),
    [
        (1.5, "UNSUPPORTED_NUMERIC", ()),
        (float("nan"), "UNSUPPORTED_NUMERIC", ()),
        (float("inf"), "UNSUPPORTED_NUMERIC", ()),
        (Decimal("1.00"), "UNSUPPORTED_NUMERIC", ()),
        (b"bytes", "UNSUPPORTED_TYPE", ()),
        ({1: "not-a-string-key"}, "NON_STRING_KEY", ("<non-string-key>",)),
        ({"payload": ["e\u0301"]}, "INVALID_UNICODE", ("payload", 0)),
        ("\ud800", "INVALID_UNICODE", ()),
        (NumericState.READY, "UNSUPPORTED_ENUM", ()),
        (datetime(2026, 8, 26), "INVALID_TIMESTAMP", ()),
        (
            datetime(2026, 8, 26, tzinfo=timezone(timedelta(hours=7))),
            "INVALID_TIMESTAMP",
            (),
        ),
    ],
)
def test_canonical_bytes_reject_ambiguous_values(value, code, path):
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(value)

    assert caught.value.code == code
    assert caught.value.path == path
    assert caught.value.partial_bytes is None


def test_canonical_bytes_reject_invalid_version():
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes({}, version="atr-json-v2")

    assert caught.value.code == "UNSUPPORTED_ENCODING_VERSION"
    assert caught.value.path == ()


def test_version_guard_never_invokes_foreign_equality():
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes({}, version=ExplosiveComparison())

    assert caught.value.code == "UNSUPPORTED_ENCODING_VERSION"


@pytest.mark.parametrize(
    ("units", "scale", "code"),
    [
        (True, 2, "UNSUPPORTED_NUMERIC"),
        (1, False, "INVALID_SCALE"),
        (1, -1, "INVALID_SCALE"),
        (Decimal("1"), 2, "UNSUPPORTED_NUMERIC"),
    ],
)
def test_scaled_integer_rejects_implicit_or_invalid_numeric(units, scale, code):
    with pytest.raises(CanonicalEncodingError) as caught:
        ScaledInteger(units=units, scale=scale)

    assert caught.value.code == code


def test_list_and_tuple_share_array_encoding_but_order_is_preserved():
    assert canonical_bytes([1, 2, 3]) == canonical_bytes((1, 2, 3))
    assert canonical_bytes([1, 2, 3]) != canonical_bytes([3, 2, 1])


def test_bool_integer_and_zero_scaled_integer_have_distinct_exact_encodings():
    assert canonical_bytes(True) == b"true"
    assert canonical_bytes(1) == b"1"
    assert canonical_bytes(True) != canonical_bytes(1)
    assert canonical_bytes(ScaledInteger(units=0, scale=8)) == b'{"scale":8,"units":0}'


def test_integer_boundary_is_explicit_and_runtime_independent():
    largest = (1 << MAX_CANONICAL_INTEGER_BITS) - 1
    assert canonical_bytes(largest) == str(largest).encode("ascii")

    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(1 << MAX_CANONICAL_INTEGER_BITS)
    assert caught.value.code == "INTEGER_OUT_OF_RANGE"
    assert caught.value.path == ()

    with pytest.raises(CanonicalEncodingError) as caught:
        ScaledInteger(units=-(1 << MAX_CANONICAL_INTEGER_BITS), scale=0)
    assert caught.value.code == "INTEGER_OUT_OF_RANGE"
    assert caught.value.path == ("units",)


def test_datetime_uses_four_digit_year_and_rejects_subclasses():
    assert canonical_bytes(datetime(1, 1, 1, tzinfo=timezone.utc)) == (
        b'"0001-01-01T00:00:00.000000Z"'
    )

    subclass_value = DatetimeSubclass(2026, 8, 26, tzinfo=timezone.utc)
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(subclass_value)
    assert caught.value.code == "INVALID_TIMESTAMP"


def test_cycle_and_depth_are_rejected_with_structural_paths():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(cyclic)
    assert caught.value.code == "CYCLIC_VALUE"
    assert caught.value.path == (0,)

    nested = 0
    for _ in range(MAX_CANONICAL_DEPTH + 1):
        nested = [nested]
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(nested)
    assert caught.value.code == "MAX_DEPTH_EXCEEDED"
    assert len(caught.value.path) == MAX_CANONICAL_DEPTH + 1


def test_mapping_snapshot_rejects_duplicate_broken_and_unsafe_keys():
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(DuplicateItemsMapping())
    assert caught.value.code == "DUPLICATE_KEY"
    assert caught.value.path == ("same",)

    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(BrokenItemsMapping())
    assert caught.value.code == "INVALID_MAPPING"

    unsafe_key_mapping = DuplicateItemsMapping()
    unsafe_key_mapping.items = lambda: ((ExplosiveRepresentation(), 1),)
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes(unsafe_key_mapping)
    assert caught.value.code == "NON_STRING_KEY"
    assert caught.value.path == ("<non-string-key>",)


def test_non_nfc_mapping_key_and_error_metadata_are_stable():
    with pytest.raises(CanonicalEncodingError) as caught:
        canonical_bytes({"e\u0301": 1})

    error = caught.value
    assert error.code == error.error_code == "INVALID_UNICODE"
    assert error.path == ("e\u0301",)
    assert error.severity == "ERROR"
    assert error.retryable is False
    assert error.evidence_ref is None
    assert error.correlation_id is None
    assert error.partial_bytes is None
