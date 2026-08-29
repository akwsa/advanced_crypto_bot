"""Contract tests for Story 4.5: Sealed Evidence Report."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.evidence_report import SealedEvidenceReport
from autotrade_next.domain.numeric import ScaledInteger


def test_sealed_evidence_report_creation():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    report = SealedEvidenceReport.seal(
        report_id="rep-100",
        experiment_id="exp-001",
        policy_id="pol-001",
        net_expectancy=ScaledInteger(150, 2),  # 1.50%
        is_conjunctive_pass=True,
        sealed_at_utc=now,
    )

    assert report.report_id == "rep-100"
    assert report.is_conjunctive_pass is True
    assert report.report_ref.domain == "evidence.report"
