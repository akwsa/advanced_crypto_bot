"""Degradation Mode State Machine Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum

from .errors import DecisionError


class DegradationLevel(IntEnum):
    HEALTHY = 1
    ENTRY_FROZEN = 2
    SHADOW_ONLY = 3
    SAFE_LATCHED = 4


@dataclass(frozen=True, slots=True)
class DegradationGovernor:
    level: DegradationLevel

    def degrade_to(self, target_level: DegradationLevel) -> DegradationGovernor:
        if target_level <= self.level:
            return self
        return DegradationGovernor(level=target_level)

    @property
    def can_enter_new_positions(self) -> bool:
        return self.level is DegradationLevel.HEALTHY


__all__ = (
    "DegradationGovernor",
    "DegradationLevel",
)
