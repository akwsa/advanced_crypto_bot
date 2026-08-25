"""Strict byte-level canonical encoding for AutoTrade Replacement."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
import json
import unicodedata
from typing import Any

from .errors import CanonicalEncodingError, CanonicalPath
from .numeric import MAX_CANONICAL_INTEGER_BITS, ScaledInteger


CANONICAL_ENCODING_VERSION = "atr-json-v1"
MAX_CANONICAL_DEPTH = 64
_NON_STRING_KEY_PATH = "<non-string-key>"


def canonical_bytes(value: Any, *, version: str = CANONICAL_ENCODING_VERSION) -> bytes:
    """Return the sole canonical byte representation for a supported value tree."""

    if type(version) is not str or version != CANONICAL_ENCODING_VERSION:
        raise CanonicalEncodingError("UNSUPPORTED_ENCODING_VERSION")
    normalized = _normalize(value, (), active_ids=set(), depth=0)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return encoded.encode("utf-8", errors="strict")


def _normalize(
    value: Any,
    path: CanonicalPath,
    *,
    active_ids: set[int],
    depth: int,
) -> Any:
    if depth > MAX_CANONICAL_DEPTH:
        raise CanonicalEncodingError("MAX_DEPTH_EXCEEDED", path=path)

    if value is None or type(value) is bool:
        return value

    if isinstance(value, Enum):
        if type(value.value) is not str:
            raise CanonicalEncodingError("UNSUPPORTED_ENUM", path=path)
        _validate_text(value.value, path)
        return value.value

    if type(value) is int:
        _validate_integer(value, path)
        return value

    if isinstance(value, (float, Decimal)):
        raise CanonicalEncodingError("UNSUPPORTED_NUMERIC", path=path)

    if type(value) is str:
        _validate_text(value, path)
        return value

    if type(value) is datetime:
        return _normalize_datetime(value, path)

    if isinstance(value, datetime):
        raise CanonicalEncodingError("INVALID_TIMESTAMP", path=path)

    if type(value) is ScaledInteger:
        return {"scale": value.scale, "units": value.units}

    if type(value) in (list, tuple):
        return _normalize_sequence(value, path, active_ids=active_ids, depth=depth)

    if isinstance(value, Mapping):
        return _normalize_mapping(value, path, active_ids=active_ids, depth=depth)

    raise CanonicalEncodingError("UNSUPPORTED_TYPE", path=path)


def _validate_text(value: str, path: CanonicalPath) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise CanonicalEncodingError("INVALID_UNICODE", path=path)
    if unicodedata.normalize("NFC", value) != value:
        raise CanonicalEncodingError("INVALID_UNICODE", path=path)


def _validate_integer(value: int, path: CanonicalPath) -> None:
    if abs(value).bit_length() > MAX_CANONICAL_INTEGER_BITS:
        raise CanonicalEncodingError("INTEGER_OUT_OF_RANGE", path=path)


def _normalize_sequence(
    value: list[Any] | tuple[Any, ...],
    path: CanonicalPath,
    *,
    active_ids: set[int],
    depth: int,
) -> list[Any]:
    container_id = id(value)
    if container_id in active_ids:
        raise CanonicalEncodingError("CYCLIC_VALUE", path=path)
    active_ids.add(container_id)
    try:
        return [
            _normalize(
                item,
                (*path, index),
                active_ids=active_ids,
                depth=depth + 1,
            )
            for index, item in enumerate(value)
        ]
    finally:
        active_ids.remove(container_id)


def _normalize_mapping(
    value: Mapping[Any, Any],
    path: CanonicalPath,
    *,
    active_ids: set[int],
    depth: int,
) -> dict[str, Any]:
    container_id = id(value)
    if container_id in active_ids:
        raise CanonicalEncodingError("CYCLIC_VALUE", path=path)
    active_ids.add(container_id)
    try:
        try:
            entries = tuple(value.items())
        except Exception as error:
            raise CanonicalEncodingError("INVALID_MAPPING", path=path) from error

        normalized: dict[str, Any] = {}
        seen: set[str] = set()
        for entry in entries:
            try:
                key, item = entry
            except Exception as error:
                raise CanonicalEncodingError("INVALID_MAPPING", path=path) from error
            if type(key) is not str:
                raise CanonicalEncodingError(
                    "NON_STRING_KEY", path=(*path, _NON_STRING_KEY_PATH)
                )
            key_path = (*path, key)
            _validate_text(key, key_path)
            if key in seen:
                raise CanonicalEncodingError("DUPLICATE_KEY", path=key_path)
            seen.add(key)
            normalized[key] = _normalize(
                item,
                key_path,
                active_ids=active_ids,
                depth=depth + 1,
            )
        return normalized
    finally:
        active_ids.remove(container_id)


def _normalize_datetime(value: datetime, path: CanonicalPath) -> str:
    try:
        is_utc = value.tzinfo is not None and value.utcoffset() == timedelta(0)
    except Exception as error:
        raise CanonicalEncodingError("INVALID_TIMESTAMP", path=path) from error
    if not is_utc:
        raise CanonicalEncodingError("INVALID_TIMESTAMP", path=path)
    return (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}T"
        f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}."
        f"{value.microsecond:06d}Z"
    )


__all__ = (
    "CANONICAL_ENCODING_VERSION",
    "MAX_CANONICAL_DEPTH",
    "CanonicalEncodingError",
    "canonical_bytes",
)
