"""Execution Calibration Evidence Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum

from .content import ContentRef
from .numeric import ScaledInteger


@dataclass(frozen=True, slots=True)
class ExecutionCalibrationReport:
    report_id: str
    instrument_id: str
    predicted_slippage_bps: int
    observed_slippage_bps: int
    predicted_latency_micros: int
    observed_latency_micros: int
    evaluated_at_utc: datetime
    report_ref: ContentRef

    @classmethod
    def create(
        cls,
        *,
        report_id: str,
        instrument_id: str,
        predicted_slippage_bps: int,
        observed_slippage_bps: int,
        predicted_latency_micros: int,
        observed_latency_micros: int,
        evaluated_at_utc: datetime,
    ) -> ExecutionCalibrationReport:
        value = {
            "report_id": report_id,
            "instrument_id": instrument_id,
            "predicted_slippage_bps": predicted_slippage_bps,
            "observed_slippage_bps": observed_slippage_bps,
            "predicted_latency_micros": predicted_latency_micros,
            "observed_latency_micros": observed_latency_micros,
            "evaluated_at_utc": evaluated_at_utc,
        }
        report_ref = ContentRef.v2("calibration.report", "execution-calibration-report", value)
        return cls(
            report_id=report_id,
            instrument_id=instrument_id,
            predicted_slippage_bps=predicted_slippage_bps,
            observed_slippage_bps=observed_slippage_bps,
            predicted_latency_micros=predicted_latency_micros,
            observed_latency_micros=observed_latency_micros,
            evaluated_at_utc=evaluated_at_utc,
            report_ref=report_ref,
        )


__all__ = ("ExecutionCalibrationReport",)
