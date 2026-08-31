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

    def rescale(self, target_scale: int) -> ScaledInteger:
        if target_scale < 0:
            raise CanonicalEncodingError("INVALID_SCALE", path=("target_scale",))
        if target_scale == self.scale:
            return self
        if target_scale > self.scale:
            factor = 10 ** (target_scale - self.scale)
            return ScaledInteger(self.units * factor, target_scale)
        else:
            factor = 10 ** (self.scale - target_scale)
            return ScaledInteger(self.units // factor, target_scale)

    def add(self, other: ScaledInteger) -> ScaledInteger:
        max_scale = max(self.scale, other.scale)
        s1 = self.rescale(max_scale)
        s2 = other.rescale(max_scale)
        return ScaledInteger(s1.units + s2.units, max_scale)

    def subtract(self, other: ScaledInteger) -> ScaledInteger:
        max_scale = max(self.scale, other.scale)
        s1 = self.rescale(max_scale)
        s2 = other.rescale(max_scale)
        return ScaledInteger(s1.units - s2.units, max_scale)

    def multiply(self, other: ScaledInteger, target_scale: int | None = None) -> ScaledInteger:
        combined_scale = self.scale + other.scale
        raw_units = self.units * other.units
        res = ScaledInteger(raw_units, combined_scale)
        if target_scale is not None:
            return res.rescale(target_scale)
        return res


__all__ = ("MAX_CANONICAL_INTEGER_BITS", "ScaledInteger")
