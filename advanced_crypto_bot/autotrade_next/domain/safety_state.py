"""Safety State and Cause Lattice Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum, IntEnum

from .errors import DecisionError


class SafetyScopeLevel(IntEnum):
    ORDER = 1
    INSTRUMENT = 2
    PORTFOLIO = 3
    AUTHORITY = 4


class SafetyCauseKind(str, Enum):
    STALE_DATA = "STALE_DATA"
    CONTINUITY_GAP = "CONTINUITY_GAP"
    UNKNOWN_ORDER = "UNKNOWN_ORDER"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    DELIVERY_FAILURE = "DELIVERY_FAILURE"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    FENCE_LOSS = "FENCE_LOSS"


@dataclass(frozen=True, slots=True)
class SafetyCause:
    cause_id: str
    kind: SafetyCauseKind
    level: SafetyScopeLevel
    evidence_ref: str
    recorded_at_utc: datetime


@dataclass(frozen=True, slots=True)
class SafetyStateLattice:
    causes: tuple[SafetyCause, ...]

    def add_cause(self, cause: SafetyCause) -> SafetyStateLattice:
        return SafetyStateLattice(causes=(*self.causes, cause))

    def clear_cause(self, cause_id: str) -> SafetyStateLattice:
        return SafetyStateLattice(causes=tuple(c for c in self.causes if c.cause_id != cause_id))

    @property
    def highest_effective_level(self) -> SafetyScopeLevel | None:
        if not self.causes:
            return None
        return max(c.level for c in self.causes)

    @property
    def is_entry_frozen(self) -> bool:
        return bool(self.causes)


__all__ = (
    "SafetyCause",
    "SafetyCauseKind",
    "SafetyScopeLevel",
    "SafetyStateLattice",
)
