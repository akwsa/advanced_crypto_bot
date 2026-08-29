"""Public, versioned content-reference recipes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from hmac import compare_digest

from .encoding import canonical_bytes
from .errors import CanonicalEncodingError


class ContentRecipe(str, Enum):
    V1 = "v1"
    V2 = "v2"


@dataclass(frozen=True, slots=True)
class ContentRef:
    """A typed SHA-256 reference with an explicit preimage recipe."""

    domain: str
    kind: str
    recipe: ContentRecipe
    digest: str

    def __post_init__(self) -> None:
        for value in (self.domain, self.kind):
            if type(value) is not str or not value or not value.strip():
                raise ValueError("INVALID_CONTENT_REFERENCE")
        if type(self.recipe) is not ContentRecipe:
            raise ValueError("INVALID_CONTENT_RECIPE")
        if (
            type(self.digest) is not str
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise ValueError("INVALID_CONTENT_DIGEST")
        if self.recipe is ContentRecipe.V2 and self.domain == "compatibility":
            raise ValueError("INVALID_CONTENT_DOMAIN")

    @classmethod
    def v1(cls, kind: str, value: object) -> ContentRef:
        """Compatibility-exact replay recipe: sha256(canonical_bytes(value))."""
        return cls(
            domain="compatibility",
            kind=kind,
            recipe=ContentRecipe.V1,
            digest=sha256(canonical_bytes(value)).hexdigest(),
        )

    @classmethod
    def v2(cls, domain: str, kind: str, value: object) -> ContentRef:
        envelope = {
            "domain": domain,
            "kind": kind,
            "recipe_version": ContentRecipe.V2.value,
            "value": value,
        }
        return cls(
            domain=domain,
            kind=kind,
            recipe=ContentRecipe.V2,
            digest=sha256(canonical_bytes(envelope)).hexdigest(),
        )

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.recipe.value}:{self.digest}"

    def verify(self, value: object) -> bool:
        try:
            expected = (
                ContentRef.v1(self.kind, value)
                if self.recipe is ContentRecipe.V1
                else ContentRef.v2(self.domain, self.kind, value)
            )
        except (CanonicalEncodingError, ValueError):
            return False
        return compare_digest(self.key, expected.key) and self.domain == expected.domain

    def to_canonical_value(self) -> dict[str, str]:
        return {
            "domain": self.domain,
            "kind": self.kind,
            "recipe": self.recipe.value,
            "digest": self.digest,
        }


def content_ref_v1(kind: str, value: object) -> ContentRef:
    return ContentRef.v1(kind, value)


def content_ref_v2(domain: str, kind: str, value: object) -> ContentRef:
    return ContentRef.v2(domain, kind, value)


__all__ = ("ContentRecipe", "ContentRef", "content_ref_v1", "content_ref_v2")
