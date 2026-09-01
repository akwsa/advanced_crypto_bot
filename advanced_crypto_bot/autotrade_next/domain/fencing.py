"""Fenced Writer Authority and Single Writer Fencing Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .errors import DecisionError


def _required_text(value: object, code: str) -> None:
    if type(value) is not str or not value.strip():
        raise DecisionError(code)


def _utc_time(value: object, code: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise DecisionError(code)
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise DecisionError(code)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class FencedWriterLease:
    scope_id: str
    epoch: int
    lease_token: str
    granted_at_utc: datetime
    expires_at_utc: datetime

    def __post_init__(self) -> None:
        _required_text(self.scope_id, "INVALID_AUTHORITY_SCOPE")
        if type(self.epoch) is not int or self.epoch < 1:
            raise DecisionError("INVALID_WRITER_EPOCH")
        _required_text(self.lease_token, "INVALID_LEASE_TOKEN")
        granted = _utc_time(self.granted_at_utc, "INVALID_GRANTED_AT")
        expires = _utc_time(self.expires_at_utc, "INVALID_EXPIRES_AT")
        if expires <= granted:
            raise DecisionError("INVALID_LEASE_WINDOW")


@dataclass(frozen=True, slots=True)
class FencedWriterAuthority:
    scope_id: str
    active_epoch: int
    active_token: str

    def __post_init__(self) -> None:
        _required_text(self.scope_id, "INVALID_AUTHORITY_SCOPE")
        if type(self.active_epoch) is not int or self.active_epoch < 1:
            raise DecisionError("INVALID_WRITER_EPOCH")
        _required_text(self.active_token, "INVALID_LEASE_TOKEN")

    def validate_lease(self, lease: FencedWriterLease, current_time_utc: datetime) -> None:
        if type(lease) is not FencedWriterLease:
            raise DecisionError("INVALID_WRITER_LEASE")
        current_time = _utc_time(current_time_utc, "INVALID_CURRENT_TIME")
        if lease.scope_id != self.scope_id:
            raise DecisionError("FENCE_SCOPE_MISMATCH")
        if lease.epoch != self.active_epoch:
            raise DecisionError("STALE_EPOCH_DENIED" if lease.epoch < self.active_epoch else "UNCLAIMED_EPOCH_DENIED")
        if lease.lease_token != self.active_token:
            raise DecisionError("INVALID_LEASE_TOKEN")
        if current_time < lease.granted_at_utc:
            raise DecisionError("CLOCK_ANOMALY")
        if current_time >= lease.expires_at_utc:
            raise DecisionError("EXPIRED_LEASE_TOKEN")

    def increment_epoch(self, new_token: str) -> FencedWriterAuthority:
        _required_text(new_token, "INVALID_LEASE_TOKEN")
        if new_token == self.active_token:
            raise DecisionError("LEASE_TOKEN_REUSE")
        return FencedWriterAuthority(
            scope_id=self.scope_id,
            active_epoch=self.active_epoch + 1,
            active_token=new_token,
        )


__all__ = (
    "FencedWriterAuthority",
    "FencedWriterLease",
)
