"""Contract tests for Story 5.3: Migration and Backup Restore Gate."""

import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.migration_gate import MigrationVerificationResult


def test_migration_verification_passed():
    res = MigrationVerificationResult(
        migration_id="mig-001",
        target_schema_version="v2.1",
        is_integrity_check_passed=True,
        is_fk_check_passed=True,
        is_restorable=True,
    )
    res.validate_for_cutover()


def test_migration_verification_failed_integrity():
    res = MigrationVerificationResult(
        migration_id="mig-002",
        target_schema_version="v2.1",
        is_integrity_check_passed=False,
        is_fk_check_passed=True,
        is_restorable=True,
    )
    with pytest.raises(DecisionError) as exc_info:
        res.validate_for_cutover()
    assert exc_info.value.code == "MIGRATION_RESTORE_GATE_FAILED"
