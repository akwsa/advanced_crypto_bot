"""Contract-only ports for pure market evidence and recovery evaluation."""

from __future__ import annotations

from typing import Protocol

from autotrade_next.domain.market import EvidenceAdmission, RecoveryGateResult


class MarketEvidenceAdapterPort(Protocol):
    def qualify(self, **recorded_inputs: object) -> EvidenceAdmission: ...


class RecoveryGatePort(Protocol):
    def evaluate(self, **proofs: object) -> RecoveryGateResult: ...


__all__ = ("MarketEvidenceAdapterPort", "RecoveryGatePort")
