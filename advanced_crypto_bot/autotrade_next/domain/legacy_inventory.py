"""Legacy Inventory Classification Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import DecisionError


class LegacyEntityDisposition(str, Enum):
    PROVEN_OPEN = "PROVEN_OPEN"
    PROVEN_CLOSED = "PROVEN_CLOSED"
    AMBIGUOUS = "AMBIGUOUS"
    NON_CANONICAL_HISTORY = "NON_CANONICAL_HISTORY"


@dataclass(frozen=True, slots=True)
class LegacyInventoryRecord:
    entity_id: str
    entity_type: str
    disposition: LegacyEntityDisposition
    evidence_ref: str


class LegacyInventoryClassifier:
    @staticmethod
    def audit_readiness(records: tuple[LegacyInventoryRecord, ...]) -> bool:
        for r in records:
            if r.disposition is LegacyEntityDisposition.AMBIGUOUS:
                return False
        return True


__all__ = (
    "LegacyEntityDisposition",
    "LegacyInventoryClassifier",
    "LegacyInventoryRecord",
)
