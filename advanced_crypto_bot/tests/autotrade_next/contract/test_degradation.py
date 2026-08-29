"""Contract tests for Story 3.6: Degradation Mode State Machine."""

import pytest

from autotrade_next.domain.degradation import DegradationGovernor, DegradationLevel


def test_degradation_governor_flow():
    gov = DegradationGovernor(level=DegradationLevel.HEALTHY)
    assert gov.can_enter_new_positions is True

    # Degrade to ENTRY_FROZEN
    gov = gov.degrade_to(DegradationLevel.ENTRY_FROZEN)
    assert gov.can_enter_new_positions is False
    assert gov.level is DegradationLevel.ENTRY_FROZEN

    # Degrade to SAFE_LATCHED
    gov = gov.degrade_to(DegradationLevel.SAFE_LATCHED)
    assert gov.level is DegradationLevel.SAFE_LATCHED

    # Attempting to upgrade via degrade_to fails silently / returns self
    gov2 = gov.degrade_to(DegradationLevel.HEALTHY)
    assert gov2.level is DegradationLevel.SAFE_LATCHED
