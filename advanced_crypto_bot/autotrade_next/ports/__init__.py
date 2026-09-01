"""Typed I/O boundaries for AutoTrade Next."""

from .query import ReadOnlyQueryPort
from .market import MarketEvidenceAdapterPort, RecoveryGatePort
from .venue import VenuePort
from .settlement import (
    PreparationCommitBundle, SettlementCommitBundle, SettlementUnitOfWork,
)
from .exit import ExitCommitBundle, ExitUnitOfWork
from .portfolio_allocation import (
    AllocationCommitBundle,
    AllocationCommitResult,
    AllocationCommitStatus,
    AllocationContentRecord,
    PortfolioAllocationJournal,
)
from .recovery import CorrectionApprovalVerifier

__all__ = (
    "AllocationCommitBundle", "AllocationCommitResult", "AllocationCommitStatus",
    "AllocationContentRecord", "ExitCommitBundle", "ExitUnitOfWork",
    "MarketEvidenceAdapterPort", "PortfolioAllocationJournal",
    "PreparationCommitBundle", "ReadOnlyQueryPort",
    "CorrectionApprovalVerifier", "RecoveryGatePort", "SettlementCommitBundle",
    "SettlementUnitOfWork", "VenuePort",
)
