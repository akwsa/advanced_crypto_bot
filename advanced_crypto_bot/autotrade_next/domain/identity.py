"""Versioned deterministic identity recipes over canonical domain bytes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Final

from .encoding import CANONICAL_ENCODING_VERSION, canonical_bytes
from .errors import IdentityError


IDENTITY_DOMAIN: Final = "autotrade-next.identity"


@dataclass(frozen=True, slots=True)
class IdentityRecipe:
    recipe_version: int
    domain: str
    canonical_version: str
    hash_name: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeterministicIdentity:
    kind: str
    recipe_version: int
    digest: str

    def __post_init__(self) -> None:
        kind = self.kind if type(self.kind) is str else "<non-string-kind>"
        if type(self.recipe_version) is not int:
            raise IdentityError("UNSUPPORTED_RECIPE_VERSION", kind=kind)
        recipes = _RECIPE_REGISTRY.get(self.recipe_version)
        if recipes is None:
            raise IdentityError("UNSUPPORTED_RECIPE_VERSION", kind=kind)
        if type(self.kind) is not str or self.kind not in recipes:
            raise IdentityError("UNKNOWN_IDENTITY_KIND", kind=kind)
        if (
            type(self.digest) is not str
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise IdentityError("INVALID_IDENTITY_DIGEST", kind=kind)

    @property
    def key(self) -> str:
        return f"{self.kind}:v{self.recipe_version}:{self.digest}"


_V1_RECIPES = MappingProxyType(
    {
        "candidate": IdentityRecipe(
            recipe_version=1,
            domain="autotrade-next.identity",
            canonical_version="atr-json-v1",
            hash_name="sha256",
            required_fields=(
                "instrument_id",
                "horizon_id",
                "trigger_kind",
                "trigger_at_utc",
                "scan_trigger_version",
                "data_revision",
            ),
            optional_fields=("parent_position_id",),
        ),
        "decision": IdentityRecipe(
            recipe_version=1,
            domain="autotrade-next.identity",
            canonical_version="atr-json-v1",
            hash_name="sha256",
            required_fields=("candidate_id", "policy_version"),
        ),
        "intent": IdentityRecipe(
            recipe_version=1,
            domain="autotrade-next.identity",
            canonical_version="atr-json-v1",
            hash_name="sha256",
            required_fields=("decision_id",),
        ),
        "event": IdentityRecipe(
            recipe_version=1,
            domain="autotrade-next.identity",
            canonical_version="atr-json-v1",
            hash_name="sha256",
            required_fields=(
                "authority_scope_id",
                "aggregate_id",
                "aggregate_seq",
                "event_type",
                "schema_version",
            )
        ),
        "client_order": IdentityRecipe(
            recipe_version=1,
            domain="autotrade-next.identity",
            canonical_version="atr-json-v1",
            hash_name="sha256",
            required_fields=("authority_scope_id", "intent_id", "order_ordinal")
        ),
    }
)

_RECIPE_REGISTRY = MappingProxyType({1: _V1_RECIPES})


def identity_preimage(
    kind: str,
    fields: Mapping[str, Any],
    *,
    recipe_version: int = 1,
) -> bytes:
    recipe = _resolve_recipe(kind, recipe_version)
    projected = _project_fields(kind, fields, recipe)
    envelope = {
        "canonical_version": recipe.canonical_version,
        "domain": recipe.domain,
        "fields": projected,
        "kind": kind,
        "recipe_version": recipe.recipe_version,
    }
    return canonical_bytes(envelope, version=recipe.canonical_version)


def build_identity(
    kind: str,
    fields: Mapping[str, Any],
    *,
    recipe_version: int = 1,
) -> DeterministicIdentity:
    recipe = _resolve_recipe(kind, recipe_version)
    preimage = identity_preimage(kind, fields, recipe_version=recipe_version)
    if recipe.hash_name != "sha256":
        raise IdentityError("UNSUPPORTED_HASH_ALGORITHM", kind=kind)
    return DeterministicIdentity(
        kind=kind,
        recipe_version=recipe_version,
        digest=sha256(preimage).hexdigest(),
    )


def _resolve_recipe(kind: str, recipe_version: int) -> IdentityRecipe:
    safe_kind = kind if type(kind) is str else "<non-string-kind>"
    if type(recipe_version) is not int:
        raise IdentityError("UNSUPPORTED_RECIPE_VERSION", kind=safe_kind)
    if type(kind) is not str:
        raise IdentityError("UNKNOWN_IDENTITY_KIND", kind=safe_kind)
    version_recipes = _RECIPE_REGISTRY.get(recipe_version)
    if version_recipes is None:
        raise IdentityError(
            "UNSUPPORTED_RECIPE_VERSION", kind=kind
        )
    recipe = version_recipes.get(kind)
    if recipe is None:
        raise IdentityError("UNKNOWN_IDENTITY_KIND", kind=kind)
    return recipe


def _project_fields(
    kind: str,
    fields: Mapping[str, Any],
    recipe: IdentityRecipe,
) -> list[list[Any]]:
    if not isinstance(fields, Mapping):
        raise IdentityError("UNEXPECTED_IDENTITY_FIELD", kind=kind)
    allowed = frozenset((*recipe.required_fields, *recipe.optional_fields))
    try:
        entries = tuple(fields.items())
    except Exception as error:
        raise IdentityError("INVALID_IDENTITY_FIELDS", kind=kind) from error
    snapshot: dict[str, Any] = {}
    for entry in entries:
        try:
            field, value = entry
        except Exception as error:
            raise IdentityError("INVALID_IDENTITY_FIELDS", kind=kind) from error
        if type(field) is not str:
            raise IdentityError(
                "UNEXPECTED_IDENTITY_FIELD", kind=kind, field="<non-string-field>"
            )
        if field in snapshot:
            raise IdentityError("DUPLICATE_IDENTITY_FIELD", kind=kind, field=field)
        if field not in allowed:
            raise IdentityError("UNEXPECTED_IDENTITY_FIELD", kind=kind, field=field)
        snapshot[field] = value
    for field in recipe.required_fields:
        if field not in snapshot:
            raise IdentityError("MISSING_IDENTITY_FIELD", kind=kind, field=field)
    projection = [[field, snapshot[field]] for field in recipe.required_fields]
    projection.extend(
        [field, snapshot[field]] for field in recipe.optional_fields if field in snapshot
    )
    return projection


__all__ = (
    "DeterministicIdentity",
    "IdentityError",
    "build_identity",
    "identity_preimage",
)
