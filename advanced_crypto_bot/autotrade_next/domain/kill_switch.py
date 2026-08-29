"""Kill Switch and Emergency Zeroing State Machine Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import DecisionError


class KillState(str, Enum):
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    CANCEL_PENDING = "CANCEL_PENDING"
    EXIT_PENDING = "EXIT_PENDING"
    RECONCILING = "RECONCILING"
    LATCHED_SAFE = "LATCHED_SAFE"


@dataclass(frozen=True, slots=True)
class KillSwitchStateMachine:
    state: KillState

    def trigger_kill(self) -> KillSwitchStateMachine:
        if self.state is not KillState.ARMED:
            raise DecisionError("KILL_SWITCH_ALREADY_TRIGGERED")
        return KillSwitchStateMachine(state=KillState.TRIGGERED)

    def advance_state(self, next_state: KillState) -> KillSwitchStateMachine:
        allowed_transitions = {
            KillState.TRIGGERED: (KillState.CANCEL_PENDING,),
            KillState.CANCEL_PENDING: (KillState.EXIT_PENDING,),
            KillState.EXIT_PENDING: (KillState.RECONCILING,),
            KillState.RECONCILING: (KillState.LATCHED_SAFE,),
        }
        valid_next = allowed_transitions.get(self.state, ())
        if next_state not in valid_next:
            raise DecisionError("INVALID_KILL_STATE_TRANSITION")
        return KillSwitchStateMachine(state=next_state)


__all__ = (
    "KillState",
    "KillSwitchStateMachine",
)
