"""Experiment Specification and Universe Freezing Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .content import ContentRef
from .errors import DecisionError


@dataclass(frozen=True, slots=True)
class EvidenceSpecification:
    experiment_id: str
    version: int
    opportunity_universe: tuple[str, ...]
    horizon_minutes: int
    seed: int
    spec_ref: ContentRef

    @classmethod
    def freeze(
        cls,
        *,
        experiment_id: str,
        version: int,
        opportunity_universe: tuple[str, ...],
        horizon_minutes: int,
        seed: int,
    ) -> EvidenceSpecification:
        if not opportunity_universe:
            raise DecisionError("EMPTY_OPPORTUNITY_UNIVERSE")
        value = {
            "experiment_id": experiment_id,
            "version": version,
            "opportunity_universe": list(opportunity_universe),
            "horizon_minutes": horizon_minutes,
            "seed": seed,
        }
        spec_ref = ContentRef.v2("experiment.spec", "evidence-specification", value)
        return cls(
            experiment_id=experiment_id,
            version=version,
            opportunity_universe=opportunity_universe,
            horizon_minutes=horizon_minutes,
            seed=seed,
            spec_ref=spec_ref,
        )


__all__ = ("EvidenceSpecification",)
