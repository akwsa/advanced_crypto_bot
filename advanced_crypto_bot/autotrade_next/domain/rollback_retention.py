"""Additive Rollback and Evidence Retention Governance Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .content import ContentRef
from .errors import DecisionError
from .fencing import FencedWriterAuthority


@dataclass(frozen=True, slots=True)
class AdditiveRollbackRecord:
    rollback_id: str
    target_release_tag: str
    reason: str
    executed_authority: FencedWriterAuthority
    executed_at_utc: datetime
    rollback_ref: ContentRef

    @classmethod
    def execute(
        cls,
        *,
        rollback_id: str,
        target_release_tag: str,
        reason: str,
        current_authority: FencedWriterAuthority,
        new_token: str,
        executed_at_utc: datetime,
    ) -> AdditiveRollbackRecord:
        new_authority = current_authority.increment_epoch(new_token)
        value = {
            "rollback_id": rollback_id,
            "target_release_tag": target_release_tag,
            "reason": reason,
            "new_epoch": new_authority.active_epoch,
            "executed_at_utc": executed_at_utc,
        }
        rollback_ref = ContentRef.v2("rollback.record", "additive-rollback-record", value)
        return cls(
            rollback_id=rollback_id,
            target_release_tag=target_release_tag,
            reason=reason,
            executed_authority=new_authority,
            executed_at_utc=executed_at_utc,
            rollback_ref=rollback_ref,
        )


__all__ = ("AdditiveRollbackRecord",)
