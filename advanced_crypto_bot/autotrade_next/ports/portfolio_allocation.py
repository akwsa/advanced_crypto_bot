"""Fenced atomic persistence boundary for portfolio allocation batches."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.encoding import canonical_bytes
from autotrade_next.domain.portfolio_allocation import PortfolioAllocation


def _required_text(value: object, code: str) -> None:
    if type(value) is not str or not value.strip():
        raise TypeError(code)


@dataclass(frozen=True, slots=True, init=False)
class AllocationContentRecord:
    """Immutable canonical payload captured together with its verified reference."""

    reference: ContentRef
    payload: bytes

    def __init__(self, reference: ContentRef, value: object) -> None:
        if type(reference) is not ContentRef or not reference.verify(value):
            raise TypeError("ALLOCATION_CONTENT_REFERENCE_MISMATCH")
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "payload", canonical_bytes(value))


@dataclass(frozen=True, slots=True)
class AllocationCommitBundle:
    authority_scope_id: str
    writer_epoch: int
    lease_token: str
    aggregate_id: str
    allocation: PortfolioAllocation
    decisions: tuple[AllocationContentRecord, ...]
    next_risk_state: AllocationContentRecord

    def __post_init__(self) -> None:
        for value, code in (
            (self.authority_scope_id, "INVALID_ALLOCATION_SCOPE"),
            (self.lease_token, "INVALID_ALLOCATION_LEASE_TOKEN"),
            (self.aggregate_id, "INVALID_ALLOCATION_AGGREGATE"),
        ):
            _required_text(value, code)
        if type(self.writer_epoch) is not int or self.writer_epoch < 1:
            raise TypeError("INVALID_ALLOCATION_WRITER_EPOCH")
        if type(self.allocation) is not PortfolioAllocation or not self.allocation.executable:
            raise TypeError("INVALID_EXECUTABLE_ALLOCATION")
        if (type(self.decisions) is not tuple
                or any(type(item) is not AllocationContentRecord
                       for item in self.decisions)):
            raise TypeError("INVALID_ALLOCATION_DECISIONS")
        if type(self.next_risk_state) is not AllocationContentRecord:
            raise TypeError("INVALID_ALLOCATION_RISK_STATE")
        expected_decisions = tuple(
            proposal.decision_ref for proposal in self.allocation.proposals
        )
        if tuple(item.reference for item in self.decisions) != expected_decisions:
            raise TypeError("ALLOCATION_DECISION_SET_MISMATCH")
        if self.next_risk_state.reference != self.allocation.next_risk_state_ref:
            raise TypeError("ALLOCATION_RISK_STATE_MISMATCH")
        if self.allocation.event_ref is None or self.allocation.outbox_ref is None:
            raise TypeError("INCOMPLETE_EXECUTABLE_ALLOCATION")
        if not self.allocation.batch_ref.verify(
                self.allocation.batch_content_value()):
            raise TypeError("ALLOCATION_BATCH_REFERENCE_MISMATCH")
        if not self.allocation.event_ref.verify(self.event_value):
            raise TypeError("ALLOCATION_EVENT_REFERENCE_MISMATCH")
        if not self.allocation.outbox_ref.verify(self.outbox_value):
            raise TypeError("ALLOCATION_OUTBOX_REFERENCE_MISMATCH")

    @property
    def command_id(self) -> str:
        return self.allocation.batch_ref.key

    @property
    def expected_sequence(self) -> int:
        return self.allocation.expected_sequence

    @property
    def event_value(self) -> dict[str, object]:
        return {
            "batch_ref": self.allocation.batch_ref.to_canonical_value(),
            "sequence": self.allocation.expected_sequence + 1,
        }

    @property
    def outbox_value(self) -> dict[str, object]:
        event_ref = self.allocation.event_ref
        if event_ref is None:
            raise TypeError("INCOMPLETE_EXECUTABLE_ALLOCATION")
        return {
            "event_ref": event_ref.to_canonical_value(),
            "status": "PENDING",
        }

    @property
    def batch_payload(self) -> bytes:
        return canonical_bytes(self.allocation.batch_content_value())

    @property
    def event_payload(self) -> bytes:
        return canonical_bytes(self.event_value)

    @property
    def outbox_payload(self) -> bytes:
        return canonical_bytes(self.outbox_value)

    @property
    def reservation_rows(self) -> tuple[tuple[str, str, str, bytes], ...]:
        return tuple(
            (
                item.reservation.reservation_id,
                item.pair_id,
                item.horizon,
                canonical_bytes(item.reservation.to_canonical_value()),
            )
            for item in self.allocation.proposals
        )


class AllocationCommitStatus(str, Enum):
    COMMITTED = "COMMITTED"
    IDEMPOTENT = "IDEMPOTENT"
    COMMITTED_AFTER_INDETERMINATE = "COMMITTED_AFTER_INDETERMINATE"
    AUTHORITY_MISSING = "AUTHORITY_MISSING"
    STALE_EPOCH = "STALE_EPOCH"
    UNCLAIMED_EPOCH = "UNCLAIMED_EPOCH"
    FENCE_LOST = "FENCE_LOST"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"
    SEQUENCE_CONFLICT = "SEQUENCE_CONFLICT"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    BUSY = "BUSY"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    INDETERMINATE_COMMIT = "INDETERMINATE_COMMIT"


@dataclass(frozen=True, slots=True)
class AllocationCommitResult:
    status: AllocationCommitStatus
    command_id: str
    sequence: int | None = None

    @property
    def committed(self) -> bool:
        return self.status in {
            AllocationCommitStatus.COMMITTED,
            AllocationCommitStatus.IDEMPOTENT,
            AllocationCommitStatus.COMMITTED_AFTER_INDETERMINATE,
        }


class PortfolioAllocationJournal(Protocol):
    def append_allocation(
        self, bundle: AllocationCommitBundle,
    ) -> AllocationCommitResult: ...


__all__ = (
    "AllocationCommitBundle",
    "AllocationCommitResult",
    "AllocationCommitStatus",
    "AllocationContentRecord",
    "PortfolioAllocationJournal",
)
