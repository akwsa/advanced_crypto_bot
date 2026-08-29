"""Offline Migration and Backup Restore Gate Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .errors import DecisionError


@dataclass(frozen=True, slots=True)
class MigrationVerificationResult:
    migration_id: str
    target_schema_version: str
    is_integrity_check_passed: bool
    is_fk_check_passed: bool
    is_restorable: bool

    def validate_for_cutover(self) -> None:
        if not (self.is_integrity_check_passed and self.is_fk_check_passed and self.is_restorable):
            raise DecisionError("MIGRATION_RESTORE_GATE_FAILED")


__all__ = ("MigrationVerificationResult",)
