"""Policy Execution Isolation Contracts (Champion / Challenger)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import DecisionError


class PolicyRole(str, Enum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"
    BASELINE = "BASELINE"


@dataclass(frozen=True, slots=True)
class PolicyExecutionFrame:
    policy_id: str
    role: PolicyRole
    is_live_executable: bool

    def __post_init__(self) -> None:
        if self.role is PolicyRole.CHALLENGER and self.is_live_executable:
            raise DecisionError("CHALLENGER_LIVE_EXECUTION_DENIED")


__all__ = (
    "PolicyExecutionFrame",
    "PolicyRole",
)
