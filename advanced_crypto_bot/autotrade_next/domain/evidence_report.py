"""Sealed Evidence Report Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .content import ContentRef
from .numeric import ScaledInteger


@dataclass(frozen=True, slots=True)
class SealedEvidenceReport:
    report_id: str
    experiment_id: str
    policy_id: str
    net_expectancy: ScaledInteger
    is_conjunctive_pass: bool
    sealed_at_utc: datetime
    report_ref: ContentRef

    @classmethod
    def seal(
        cls,
        *,
        report_id: str,
        experiment_id: str,
        policy_id: str,
        net_expectancy: ScaledInteger,
        is_conjunctive_pass: bool,
        sealed_at_utc: datetime,
    ) -> SealedEvidenceReport:
        value = {
            "report_id": report_id,
            "experiment_id": experiment_id,
            "policy_id": policy_id,
            "net_expectancy": {"units": net_expectancy.units, "scale": net_expectancy.scale},
            "is_conjunctive_pass": is_conjunctive_pass,
            "sealed_at_utc": sealed_at_utc,
        }
        report_ref = ContentRef.v2("evidence.report", "sealed-evidence-report", value)
        return cls(
            report_id=report_id,
            experiment_id=experiment_id,
            policy_id=policy_id,
            net_expectancy=net_expectancy,
            is_conjunctive_pass=is_conjunctive_pass,
            sealed_at_utc=sealed_at_utc,
            report_ref=report_ref,
        )


__all__ = ("SealedEvidenceReport",)
