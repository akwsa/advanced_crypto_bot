"""Fenced Writer Authority and Single Writer Fencing Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .errors import DecisionError


@dataclass(frozen=True, slots=True)
class FencedWriterLease:
    scope_id: str
    epoch: int
    lease_token: str
    granted_at_utc: datetime
    expires_at_utc: datetime


@dataclass(frozen=True, slots=True)
class FencedWriterAuthority:
    scope_id: str
    active_epoch: int
    active_token: str

    def validate_lease(self, lease: FencedWriterLease, current_time_utc: datetime) -> None:
        if lease.scope_id != self.scope_id:
            raise DecisionError("FENCE_SCOPE_MISMATCH")
        if lease.epoch < self.active_epoch:
            raise DecisionError("STALE_EPOCH_DENIED")
        if lease.epoch == self.active_epoch and lease.lease_token != self.active_token:
            raise DecisionError("INVALID_LEASE_TOKEN")
        if current_time_utc >= lease.expires_at_utc:
            raise DecisionError("EXPIRED_LEASE_TOKEN")

    def increment_epoch(self, new_token: str) -> FencedWriterAuthority:
        return FencedWriterAuthority(
            scope_id=self.scope_id,
            active_epoch=self.active_epoch + 1,
            active_token=new_token,
        )


__all__ = (
    "FencedWriterAuthority",
    "FencedWriterLease",
)
