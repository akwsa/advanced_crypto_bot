"""Integrity Cockpit Read-Only Projection Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from autotrade_next.domain.degradation import DegradationLevel
from autotrade_next.domain.numeric import ScaledInteger


@dataclass(frozen=True, slots=True)
class SystemIntegrityView:
    active_epoch: int
    degradation_level: DegradationLevel
    active_safety_cause_count: int
    total_equity: ScaledInteger
    allocated_exposure: ScaledInteger
    generated_at_utc: datetime

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "active_epoch": self.active_epoch,
            "degradation_level": self.degradation_level.name,
            "active_safety_cause_count": self.active_safety_cause_count,
            "total_equity": {"units": self.total_equity.units, "scale": self.total_equity.scale},
            "allocated_exposure": {"units": self.allocated_exposure.units, "scale": self.allocated_exposure.scale},
            "generated_at_utc": self.generated_at_utc,
        }


__all__ = ("SystemIntegrityView",)
