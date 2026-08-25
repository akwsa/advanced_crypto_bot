"""Explicit numeric values that retain storage scale without binary floats."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import CanonicalEncodingError


MAX_CANONICAL_INTEGER_BITS = 2048


@dataclass(frozen=True, slots=True)
class ScaledInteger:
    """An exact integer value paired with an explicit non-negative scale."""

    units: int
    scale: int

    def __post_init__(self) -> None:
        if type(self.units) is not int:
            raise CanonicalEncodingError("UNSUPPORTED_NUMERIC", path=("units",))
        if type(self.scale) is not int or self.scale < 0:
            raise CanonicalEncodingError("INVALID_SCALE", path=("scale",))
        if abs(self.units).bit_length() > MAX_CANONICAL_INTEGER_BITS:
            raise CanonicalEncodingError("INTEGER_OUT_OF_RANGE", path=("units",))
        if self.scale.bit_length() > MAX_CANONICAL_INTEGER_BITS:
            raise CanonicalEncodingError("INTEGER_OUT_OF_RANGE", path=("scale",))


__all__ = ("MAX_CANONICAL_INTEGER_BITS", "ScaledInteger")
