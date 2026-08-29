"""Stop-The-World Fenced Cutover Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import DecisionError
from .fencing import FencedWriterAuthority


class CutoverStep(str, Enum):
    INITIATED = "INITIATED"
    FREEZE_ENTRIES = "FREEZE_ENTRIES"
    STOP_LEGACY_WRITERS = "STOP_LEGACY_WRITERS"
    DRAIN_OUTBOX = "DRAIN_OUTBOX"
    CHECKPOINT_BACKUP = "CHECKPOINT_BACKUP"
    CLAIM_HIGHER_EPOCH = "CLAIM_HIGHER_EPOCH"
    ENABLE_TARGET_SYSTEM = "ENABLE_TARGET_SYSTEM"


@dataclass(frozen=True, slots=True)
class CutoverState:
    step: CutoverStep
    current_authority: FencedWriterAuthority

    def execute_higher_epoch_claim(self, new_token: str) -> CutoverState:
        if self.step is not CutoverStep.CHECKPOINT_BACKUP:
            raise DecisionError("INVALID_CUTOVER_STEP_FOR_CLAIM")
        new_authority = self.current_authority.increment_epoch(new_token)
        return CutoverState(
            step=CutoverStep.CLAIM_HIGHER_EPOCH,
            current_authority=new_authority,
        )


__all__ = (
    "CutoverState",
    "CutoverStep",
)
