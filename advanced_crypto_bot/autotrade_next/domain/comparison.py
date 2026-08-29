"""Leakage-Safe Strategy Comparison Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .errors import DecisionError


@dataclass(frozen=True, slots=True)
class CommonComparisonResult:
    experiment_id: str
    total_samples: int
    unscorable_samples: int
    is_promotable: bool

    @classmethod
    def evaluate(
        cls,
        *,
        experiment_id: str,
        total_samples: int,
        unscorable_samples: int,
    ) -> CommonComparisonResult:
        if total_samples <= 0:
            raise DecisionError("INVALID_TOTAL_SAMPLES")

        unscorable_ratio_bps = (unscorable_samples * 10000) // total_samples
        # Promotable only if UNSCORABLE <= 5% (500 bps)
        is_promotable = unscorable_ratio_bps <= 500

        return cls(
            experiment_id=experiment_id,
            total_samples=total_samples,
            unscorable_samples=unscorable_samples,
            is_promotable=is_promotable,
        )


__all__ = ("CommonComparisonResult",)
