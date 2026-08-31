"""Immutable labeled execution-calibration evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from .content import ContentRecipe, ContentRef
from .numeric import ScaledInteger


MAX_CALIBRATION_SCALE = 18
CALIBRATION_REPORT_DOMAIN = "calibration.report"
CALIBRATION_REPORT_KIND = "execution-calibration-report"


class CalibrationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = self.error_code = code
        self.partial_result = None
        super().__init__(code)


def _fail(code: str) -> None:
    raise CalibrationError(code)


def _reference(value: object) -> str:
    if type(value) is not str or not value.strip():
        _fail("INVALID_CALIBRATION_REFERENCE")
    return value


def _utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        _fail("INVALID_CALIBRATION_TIME")
    return value


def _scaled(value: object, *, allow_negative: bool = False) -> ScaledInteger:
    if (type(value) is not ScaledInteger or value.scale > MAX_CALIBRATION_SCALE
            or (not allow_negative and value.units < 0)):
        _fail("INVALID_CALIBRATION_SCALE")
    return value


def _at_scale(value: ScaledInteger, scale: int) -> int:
    if scale < value.scale or scale > MAX_CALIBRATION_SCALE:
        _fail("INVALID_CALIBRATION_SCALE")
    return value.units * 10 ** (scale - value.scale)


def _absolute_error(left: ScaledInteger, right: ScaledInteger) -> ScaledInteger:
    scale = max(left.scale, right.scale)
    return ScaledInteger(abs(_at_scale(left, scale) - _at_scale(right, scale)), scale)


def _greater(left: ScaledInteger, right: ScaledInteger) -> bool:
    scale = max(left.scale, right.scale)
    return _at_scale(left, scale) > _at_scale(right, scale)


def _number(value: ScaledInteger) -> dict[str, int]:
    return {"units": value.units, "scale": value.scale}


class CalibrationMetric(str, Enum):
    FILL_PROBABILITY = "FILL_PROBABILITY"
    LATENCY = "LATENCY"
    SPREAD = "SPREAD"
    SLIPPAGE = "SLIPPAGE"
    IMPLEMENTATION_SHORTFALL = "IMPLEMENTATION_SHORTFALL"
    REJECT_RATE = "REJECT_RATE"
    PARTIAL_RATE = "PARTIAL_RATE"
    CANCEL_RATE = "CANCEL_RATE"


class EvidenceLabel(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    SIMULATED = "SIMULATED"
    COUNTERFACTUAL = "COUNTERFACTUAL"


class EvidenceAuthority(str, Enum):
    VENUE = "VENUE"
    SHADOW = "SHADOW"
    MODEL = "MODEL"
    SIMULATOR = "SIMULATOR"
    COUNTERFACTUAL = "COUNTERFACTUAL"


class CalibrationVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNSCORABLE = "UNSCORABLE"


_RATE_METRICS = {
    CalibrationMetric.FILL_PROBABILITY,
    CalibrationMetric.REJECT_RATE,
    CalibrationMetric.PARTIAL_RATE,
    CalibrationMetric.CANCEL_RATE,
}

_SIGNED_METRICS = {
    CalibrationMetric.SLIPPAGE,
    CalibrationMetric.IMPLEMENTATION_SHORTFALL,
}


_LABEL_AUTHORITIES = {
    EvidenceLabel.OBSERVED: {EvidenceAuthority.VENUE, EvidenceAuthority.SHADOW},
    EvidenceLabel.INFERRED: {EvidenceAuthority.MODEL},
    EvidenceLabel.SIMULATED: {EvidenceAuthority.SIMULATOR},
    EvidenceLabel.COUNTERFACTUAL: {EvidenceAuthority.COUNTERFACTUAL},
}


@dataclass(frozen=True, slots=True)
class CalibrationContext:
    instrument_id: str
    horizon_id: str
    size_bucket: str
    regime_id: str
    estimator_version: str
    window_start_utc: datetime
    window_end_utc: datetime
    tolerance_version: str
    scenario_corpus_ref: str

    def __post_init__(self) -> None:
        for value in (self.instrument_id, self.horizon_id, self.size_bucket,
                      self.regime_id, self.estimator_version,
                      self.tolerance_version, self.scenario_corpus_ref):
            _reference(value)
        _utc(self.window_start_utc)
        _utc(self.window_end_utc)
        if self.window_start_utc >= self.window_end_utc:
            _fail("INVALID_CALIBRATION_WINDOW")

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "horizon_id": self.horizon_id,
            "size_bucket": self.size_bucket,
            "regime_id": self.regime_id,
            "estimator_version": self.estimator_version,
            "window_start_utc": self.window_start_utc,
            "window_end_utc": self.window_end_utc,
            "tolerance_version": self.tolerance_version,
            "scenario_corpus_ref": self.scenario_corpus_ref,
        }


@dataclass(frozen=True, slots=True)
class CalibrationPoint:
    metric: CalibrationMetric
    predicted: ScaledInteger
    observed: ScaledInteger
    label: EvidenceLabel
    authority: EvidenceAuthority
    sample_count: int
    evidence_ref: str

    def __post_init__(self) -> None:
        if (type(self.metric) is not CalibrationMetric
                or type(self.label) is not EvidenceLabel
                or type(self.authority) is not EvidenceAuthority):
            _fail("INVALID_CALIBRATION_POINT")
        allow_negative = self.metric in _SIGNED_METRICS
        _scaled(self.predicted, allow_negative=allow_negative)
        _scaled(self.observed, allow_negative=allow_negative)
        if (self.metric in _RATE_METRICS
                and (_greater(self.predicted, ScaledInteger(1, 0))
               or _greater(self.observed, ScaledInteger(1, 0)))):
            _fail("INVALID_CALIBRATION_RATE")
        if self.authority not in _LABEL_AUTHORITIES[self.label]:
            _fail("LABEL_AUTHORITY_MISMATCH")
        if type(self.sample_count) is not int or self.sample_count <= 0:
            _fail("INVALID_CALIBRATION_SAMPLE")
        _reference(self.evidence_ref)

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "metric": self.metric.value,
            "predicted": _number(self.predicted),
            "observed": _number(self.observed),
            "label": self.label.value,
            "authority": self.authority.value,
            "sample_count": self.sample_count,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class CalibrationTolerance:
    metric: CalibrationMetric
    maximum_absolute_error: ScaledInteger

    def __post_init__(self) -> None:
        if type(self.metric) is not CalibrationMetric:
            _fail("INVALID_CALIBRATION_TOLERANCE")
        _scaled(self.maximum_absolute_error)
        if (self.metric in _RATE_METRICS
                and _greater(self.maximum_absolute_error, ScaledInteger(1, 0))):
            _fail("INVALID_CALIBRATION_RATE")

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "metric": self.metric.value,
            "maximum_absolute_error": _number(self.maximum_absolute_error),
        }


def _validate_complete(points, tolerances) -> None:
    point_metrics = tuple(item.metric for item in points)
    tolerance_metrics = tuple(item.metric for item in tolerances)
    if len(set(point_metrics)) != len(point_metrics) or len(set(tolerance_metrics)) != len(
            tolerance_metrics):
        _fail("DUPLICATE_CALIBRATION_METRIC")
    required = tuple(CalibrationMetric)
    if point_metrics != required or tolerance_metrics != required:
        _fail("INCOMPLETE_CALIBRATION_METRICS")


def _verdict(points, tolerances) -> CalibrationVerdict:
    if any(item.label is not EvidenceLabel.OBSERVED for item in points):
        return CalibrationVerdict.UNSCORABLE
    for point, tolerance in zip(points, tolerances, strict=True):
        if _greater(
            _absolute_error(point.predicted, point.observed),
            tolerance.maximum_absolute_error,
        ):
            return CalibrationVerdict.FAIL
    return CalibrationVerdict.PASS


@dataclass(frozen=True, slots=True)
class ExecutionCalibrationReport:
    report_id: str
    context: CalibrationContext
    points: tuple[CalibrationPoint, ...]
    tolerances: tuple[CalibrationTolerance, ...]
    evaluated_at_utc: datetime
    verdict: CalibrationVerdict
    report_ref: ContentRef

    def __post_init__(self) -> None:
        if (type(self.context) is not CalibrationContext
                or type(self.points) is not tuple
                or any(type(item) is not CalibrationPoint for item in self.points)
                or type(self.tolerances) is not tuple
                or any(type(item) is not CalibrationTolerance for item in self.tolerances)
                or type(self.verdict) is not CalibrationVerdict):
            _fail("INVALID_CALIBRATION_REPORT")
        _utc(self.evaluated_at_utc)
        if self.evaluated_at_utc < self.context.window_end_utc:
            _fail("INVALID_CALIBRATION_TIME")
        _validate_complete(self.points, self.tolerances)
        if self.verdict is not _verdict(self.points, self.tolerances):
            _fail("CALIBRATION_VERDICT_MISMATCH")
        if (type(self.report_ref) is not ContentRef
                or self.report_ref.recipe is not ContentRecipe.V2
                or self.report_ref.domain != CALIBRATION_REPORT_DOMAIN
                or self.report_ref.kind != CALIBRATION_REPORT_KIND
                or self.report_id != self.report_ref.key
                or not self.report_ref.verify(self.binding_value())):
            _fail("CALIBRATION_REPORT_REFERENCE_MISMATCH")

    @property
    def venue_calibration_qualified(self) -> bool:
        return self.verdict is CalibrationVerdict.PASS

    def binding_value(self) -> dict[str, object]:
        return {
            "schema_version": "execution-calibration-report:v2",
            "context": self.context.to_canonical_value(),
            "points": tuple(item.to_canonical_value() for item in self.points),
            "tolerances": tuple(item.to_canonical_value() for item in self.tolerances),
            "evaluated_at_utc": self.evaluated_at_utc,
            "verdict": self.verdict.value,
        }

    @classmethod
    def create(cls, *, context: CalibrationContext,
               points: tuple[CalibrationPoint, ...],
               tolerances: tuple[CalibrationTolerance, ...],
               evaluated_at_utc: datetime) -> ExecutionCalibrationReport:
        if (type(context) is not CalibrationContext or type(points) is not tuple
                or any(type(item) is not CalibrationPoint for item in points)
                or type(tolerances) is not tuple
                or any(type(item) is not CalibrationTolerance for item in tolerances)):
            _fail("INVALID_CALIBRATION_REPORT")
        _validate_complete(points, tolerances)
        verdict = _verdict(points, tolerances)
        value = {
            "schema_version": "execution-calibration-report:v2",
            "context": context.to_canonical_value(),
            "points": tuple(item.to_canonical_value() for item in points),
            "tolerances": tuple(item.to_canonical_value() for item in tolerances),
            "evaluated_at_utc": evaluated_at_utc,
            "verdict": verdict.value,
        }
        reference = ContentRef.v2(
            CALIBRATION_REPORT_DOMAIN, CALIBRATION_REPORT_KIND, value,
        )
        return cls(
            reference.key, context, points, tolerances, evaluated_at_utc,
            verdict, reference,
        )


__all__ = (
    "CalibrationContext", "CalibrationError", "CalibrationMetric",
    "CalibrationPoint", "CalibrationTolerance", "CalibrationVerdict",
    "EvidenceAuthority", "EvidenceLabel", "ExecutionCalibrationReport",
)
