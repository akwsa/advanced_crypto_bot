"""Approved External Fact and Ambiguity Quarantine Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .content import ContentRef
from .errors import DecisionError


@dataclass(frozen=True, slots=True)
class ApprovedExternalFact:
    fact_id: str
    legacy_reference_id: str
    instrument_id: str
    fact_type: str
    imported_at_utc: datetime
    fact_ref: ContentRef

    @classmethod
    def import_proven(
        cls,
        *,
        fact_id: str,
        legacy_reference_id: str,
        instrument_id: str,
        fact_type: str,
        imported_at_utc: datetime,
        is_proven: bool,
    ) -> ApprovedExternalFact:
        if not is_proven:
            raise DecisionError("UNPROVEN_LEGACY_FACT_DENIED")
        value = {
            "fact_id": fact_id,
            "legacy_reference_id": legacy_reference_id,
            "instrument_id": instrument_id,
            "fact_type": fact_type,
            "imported_at_utc": imported_at_utc,
        }
        fact_ref = ContentRef.v2("fact.import", "approved-external-fact", value)
        return cls(
            fact_id=fact_id,
            legacy_reference_id=legacy_reference_id,
            instrument_id=instrument_id,
            fact_type=fact_type,
            imported_at_utc=imported_at_utc,
            fact_ref=fact_ref,
        )


__all__ = ("ApprovedExternalFact",)
