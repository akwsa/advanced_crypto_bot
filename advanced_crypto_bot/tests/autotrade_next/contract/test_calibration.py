from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from autotrade_next.domain.calibration import (
    CalibrationContext, CalibrationError, CalibrationMetric, CalibrationPoint,
    CalibrationTolerance, CalibrationVerdict, EvidenceAuthority, EvidenceLabel,
    ExecutionCalibrationReport,
)
from autotrade_next.domain.numeric import ScaledInteger

AT = datetime(2026, 8, 30, 14, 0, tzinfo=UTC)


def amount(units, scale=4):
    return ScaledInteger(units, scale)


def context():
    return CalibrationContext(
        "BTCIDR", "4h", "size:small", "regime:normal", "estimator:v3",
        AT - timedelta(days=30), AT, "tolerance:v2", "scenario-corpus:v5",
    )


def points(label=EvidenceLabel.OBSERVED, authority=EvidenceAuthority.SHADOW):
    return tuple(
        CalibrationPoint(metric, amount(100), amount(110), label, authority,
                         50, f"evidence:{metric.value}")
        for metric in CalibrationMetric
    )


def tolerances():
    return tuple(CalibrationTolerance(metric, amount(20)) for metric in CalibrationMetric)


def test_complete_observed_report_is_deterministic_grouped_and_scored():
    first = ExecutionCalibrationReport.create(
        context=context(), points=points(), tolerances=tolerances(), evaluated_at_utc=AT,
    )
    second = ExecutionCalibrationReport.create(
        context=context(), points=points(), tolerances=tolerances(), evaluated_at_utc=AT,
    )
    assert first == second
    assert first.verdict is CalibrationVerdict.PASS
    assert first.venue_calibration_qualified is True
    assert first.report_id == first.report_ref.key
    assert first.report_ref.verify(first.binding_value())
    assert {point.metric for point in first.points} == set(CalibrationMetric)


def test_nonobserved_evidence_is_never_venue_calibration_even_when_error_is_small():
    mixed = list(points())
    mixed[0] = replace(
        mixed[0], label=EvidenceLabel.SIMULATED,
        authority=EvidenceAuthority.SIMULATOR,
    )
    report = ExecutionCalibrationReport.create(
        context=context(), points=tuple(mixed), tolerances=tolerances(),
        evaluated_at_utc=AT,
    )
    assert report.verdict is CalibrationVerdict.UNSCORABLE
    assert report.venue_calibration_qualified is False


def test_observed_label_requires_venue_or_shadow_authority():
    with pytest.raises(CalibrationError, match="LABEL_AUTHORITY_MISMATCH"):
        CalibrationPoint(
            CalibrationMetric.LATENCY, amount(1), amount(1), EvidenceLabel.OBSERVED,
            EvidenceAuthority.MODEL, 1, "evidence:model",
        )


def test_missing_duplicate_metric_and_tolerance_fail_closed():
    with pytest.raises(CalibrationError, match="INCOMPLETE_CALIBRATION_METRICS"):
        ExecutionCalibrationReport.create(
            context=context(), points=points()[:-1], tolerances=tolerances(),
            evaluated_at_utc=AT,
        )
    duplicate = (*points()[:-1], points()[0])
    with pytest.raises(CalibrationError, match="DUPLICATE_CALIBRATION_METRIC"):
        ExecutionCalibrationReport.create(
            context=context(), points=duplicate, tolerances=tolerances(),
            evaluated_at_utc=AT,
        )


def test_observed_report_fails_when_any_absolute_error_exceeds_frozen_tolerance():
    changed = list(points())
    changed[0] = replace(changed[0], observed=amount(500))
    report = ExecutionCalibrationReport.create(
        context=context(), points=tuple(changed), tolerances=tolerances(),
        evaluated_at_utc=AT,
    )
    assert report.verdict is CalibrationVerdict.FAIL


def test_context_window_scale_sample_and_direct_verdict_forgery_fail_closed():
    with pytest.raises(CalibrationError, match="INVALID_CALIBRATION_WINDOW"):
        replace(context(), window_start_utc=AT + timedelta(seconds=1))
    with pytest.raises(CalibrationError, match="INVALID_CALIBRATION_SCALE"):
        CalibrationPoint(
            CalibrationMetric.SPREAD, ScaledInteger(1, 2048), amount(1),
            EvidenceLabel.SIMULATED, EvidenceAuthority.SIMULATOR, 1, "evidence:1",
        )
    with pytest.raises(CalibrationError, match="INVALID_CALIBRATION_RATE"):
        CalibrationPoint(
            CalibrationMetric.FILL_PROBABILITY, amount(10001), amount(1),
            EvidenceLabel.SIMULATED, EvidenceAuthority.SIMULATOR, 1, "evidence:rate",
        )
    report = ExecutionCalibrationReport.create(
        context=context(), points=points(), tolerances=tolerances(), evaluated_at_utc=AT,
    )
    with pytest.raises(CalibrationError, match="CALIBRATION_VERDICT_MISMATCH"):
        replace(report, verdict=CalibrationVerdict.FAIL)
