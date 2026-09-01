"""Commit accepted portfolio allocations through the fenced journal boundary."""

from __future__ import annotations

from dataclasses import dataclass

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.portfolio_allocation import (
    AllocationProposal,
    ConstituentCheckpoint,
    PortfolioAllocation,
    PortfolioConsistencyCut,
    build_portfolio_allocation,
)
from autotrade_next.ports.portfolio_allocation import (
    AllocationCommitBundle,
    AllocationCommitResult,
    AllocationContentRecord,
    PortfolioAllocationJournal,
)


@dataclass(frozen=True, slots=True)
class AllocatePortfolioCommand:
    authority_scope_id: str
    writer_epoch: int
    lease_token: str
    aggregate_id: str
    consistency_cut: PortfolioConsistencyCut
    proposals: tuple[AllocationProposal, ...]
    observed_constituents: tuple[ConstituentCheckpoint, ...]
    expected_sequence: int
    decisions: tuple[AllocationContentRecord, ...]
    next_risk_state: AllocationContentRecord

    def __post_init__(self) -> None:
        if type(self.authority_scope_id) is not str or not self.authority_scope_id.strip():
            raise DecisionError("INVALID_ALLOCATION_SCOPE")
        if type(self.writer_epoch) is not int or self.writer_epoch < 1:
            raise DecisionError("INVALID_ALLOCATION_WRITER_EPOCH")
        if type(self.lease_token) is not str or not self.lease_token.strip():
            raise DecisionError("INVALID_ALLOCATION_LEASE_TOKEN")
        if type(self.aggregate_id) is not str or not self.aggregate_id.strip():
            raise DecisionError("INVALID_ALLOCATION_AGGREGATE")
        if type(self.consistency_cut) is not PortfolioConsistencyCut:
            raise DecisionError("INVALID_CONSISTENCY_CUT")
        if (type(self.proposals) is not tuple
                or any(type(item) is not AllocationProposal for item in self.proposals)):
            raise DecisionError("INVALID_ALLOCATION_PROPOSALS")
        if (type(self.observed_constituents) is not tuple
                or any(type(item) is not ConstituentCheckpoint
                       for item in self.observed_constituents)):
            raise DecisionError("INVALID_OBSERVED_CHECKPOINTS")
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise DecisionError("INVALID_EXPECTED_SEQUENCE")
        if (type(self.decisions) is not tuple
                or any(type(item) is not AllocationContentRecord
                       for item in self.decisions)):
            raise DecisionError("INVALID_ALLOCATION_DECISIONS")
        if type(self.next_risk_state) is not AllocationContentRecord:
            raise DecisionError("INVALID_ALLOCATION_RISK_STATE")


@dataclass(frozen=True, slots=True)
class AllocatePortfolioResult:
    allocation: PortfolioAllocation
    commit: AllocationCommitResult | None

    @property
    def committed(self) -> bool:
        return self.commit is not None and self.commit.committed


def allocate_portfolio(
    command: AllocatePortfolioCommand,
    journal: PortfolioAllocationJournal,
) -> AllocatePortfolioResult:
    """Build once, then durably commit every executable effect in one CAS."""
    if type(command) is not AllocatePortfolioCommand:
        raise DecisionError("INVALID_ALLOCATION_COMMAND")
    allocation = build_portfolio_allocation(
        consistency_cut=command.consistency_cut,
        proposals=command.proposals,
        observed_constituents=command.observed_constituents,
        expected_sequence=command.expected_sequence,
        next_risk_state_ref=command.next_risk_state.reference,
    )
    if not allocation.executable:
        return AllocatePortfolioResult(allocation, None)

    records_by_ref = {item.reference.key: item for item in command.decisions}
    if len(records_by_ref) != len(command.decisions):
        raise DecisionError("DUPLICATE_ALLOCATION_DECISION_RECORD")
    try:
        ordered_records = tuple(
            records_by_ref[item.decision_ref.key] for item in allocation.proposals
        )
    except KeyError as error:
        raise DecisionError("ALLOCATION_DECISION_SET_MISMATCH") from error
    if len(ordered_records) != len(records_by_ref):
        raise DecisionError("ALLOCATION_DECISION_SET_MISMATCH")

    bundle = AllocationCommitBundle(
        authority_scope_id=command.authority_scope_id,
        writer_epoch=command.writer_epoch,
        lease_token=command.lease_token,
        aggregate_id=command.aggregate_id,
        allocation=allocation,
        decisions=ordered_records,
        next_risk_state=command.next_risk_state,
    )
    commit = journal.append_allocation(bundle)
    if type(commit) is not AllocationCommitResult:
        raise DecisionError("INVALID_ALLOCATION_COMMIT_RESULT")
    return AllocatePortfolioResult(allocation, commit)


__all__ = (
    "AllocatePortfolioCommand",
    "AllocatePortfolioResult",
    "allocate_portfolio",
)
