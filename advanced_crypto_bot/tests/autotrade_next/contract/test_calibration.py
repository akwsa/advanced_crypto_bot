"""Contract tests for Story 2.7: Execution Calibration Evidence."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.calibration import ExecutionCalibrationReport


def test_execution_calibration_report_creation():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    report = ExecutionCalibrationReport.create(
        report_id="rep-001",
        instrument_id="BTC-IDR",
        predicted_slippage_bps=5,
        observed_slippage_bps=7,
        predicted_latency_micros=100000,
        observed_latency_micros=120000,
        evaluated_at_utc=now,
    )

    assert report.report_id == "rep-001"
    assert report.instrument_id == "BTC-IDR"
    assert report.predicted_slippage_bps == 5
    assert report.observed_slippage_bps == 7
    assert report.report_ref.domain == "calibration.report"
