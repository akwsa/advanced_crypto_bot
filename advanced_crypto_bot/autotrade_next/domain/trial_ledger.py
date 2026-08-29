"""Trial Ledger and Matured Outcome Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum

from .content import ContentRef


class MaturedOutcomeTaxonomy(str, Enum):
    SCORED_SUCCESS = "SCORED_SUCCESS"
    STALE_OR_GAPPED_SOURCE = "STALE_OR_GAPPED_SOURCE"
    DELISTING_OR_HALT = "DELISTING_OR_HALT"
    MISSING_REQUIRED_HORIZON_DATA = "MISSING_REQUIRED_HORIZON_DATA"
    INVALID_INSTRUMENT_METADATA = "INVALID_INSTRUMENT_METADATA"


@dataclass(frozen=True, slots=True)
class TrialLedgerEntry:
    trial_id: str
    experiment_id: str
    policy_id: str
    outcome: MaturedOutcomeTaxonomy
    evaluated_at_utc: datetime
    entry_ref: ContentRef

    @classmethod
    def record(
        cls,
        *,
        trial_id: str,
        experiment_id: str,
        policy_id: str,
        outcome: MaturedOutcomeTaxonomy,
        evaluated_at_utc: datetime,
    ) -> TrialLedgerEntry:
        value = {
            "trial_id": trial_id,
            "experiment_id": experiment_id,
            "policy_id": policy_id,
            "outcome": outcome.value,
            "evaluated_at_utc": evaluated_at_utc,
        }
        entry_ref = ContentRef.v2("trial.entry", "trial-ledger-entry", value)
        return cls(
            trial_id=trial_id,
            experiment_id=experiment_id,
            policy_id=policy_id,
            outcome=outcome,
            evaluated_at_utc=evaluated_at_utc,
            entry_ref=entry_ref,
        )


__all__ = (
    "MaturedOutcomeTaxonomy",
    "TrialLedgerEntry",
)
