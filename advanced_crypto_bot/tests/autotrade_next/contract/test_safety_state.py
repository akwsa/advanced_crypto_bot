"""Contract tests for Story 3.4: Safety Cause Matrix and Lattice."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.safety_state import SafetyCause, SafetyCauseKind, SafetyScopeLevel, SafetyStateLattice


def test_safety_state_lattice_highest_level_and_no_premature_clear():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)

    c1 = SafetyCause("c-1", SafetyCauseKind.STALE_DATA, SafetyScopeLevel.INSTRUMENT, "ev-1", now)
    c2 = SafetyCause("c-2", SafetyCauseKind.FENCE_LOSS, SafetyScopeLevel.AUTHORITY, "ev-2", now)

    lattice = SafetyStateLattice(causes=()).add_cause(c1).add_cause(c2)

    assert lattice.highest_effective_level is SafetyScopeLevel.AUTHORITY
    assert lattice.is_entry_frozen is True

    # Clearing c1 does NOT clear c2 (no premature clear)
    cleared_lattice = lattice.clear_cause("c-1")
    assert cleared_lattice.highest_effective_level is SafetyScopeLevel.AUTHORITY
    assert cleared_lattice.is_entry_frozen is True

    # Clearing c2 resets
    empty_lattice = cleared_lattice.clear_cause("c-2")
    assert empty_lattice.highest_effective_level is None
    assert empty_lattice.is_entry_frozen is False
