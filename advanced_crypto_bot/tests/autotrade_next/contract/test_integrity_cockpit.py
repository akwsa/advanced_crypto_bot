"""Contract tests for Story 3.7: Integrity Cockpit Read-Only Projection."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.degradation import DegradationLevel
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.projections.integrity_cockpit import SystemIntegrityView


def test_system_integrity_view_creation():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    view = SystemIntegrityView(
        active_epoch=1,
        degradation_level=DegradationLevel.HEALTHY,
        active_safety_cause_count=0,
        total_equity=ScaledInteger(1000000, 2),
        allocated_exposure=ScaledInteger(200000, 2),
        generated_at_utc=now,
    )

    assert view.active_epoch == 1
    assert view.degradation_level is DegradationLevel.HEALTHY
    assert view.active_safety_cause_count == 0
    assert view.to_canonical_value()["degradation_level"] == "HEALTHY"
