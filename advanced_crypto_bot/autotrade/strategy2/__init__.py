"""Isolated, default-off Strategy 2 domain foundation."""

from .contracts import (
    CostAssumptions,
    FeatureSnapshot,
    MarketSnapshot,
    Strategy2Decision,
    StrategyVersion,
    stable_idempotency_key,
)
from .state_machine import InvalidTransitionError, reduce_state, validate_transition
from .taxonomy import DecisionStatus, PositionState, ReasonCode, TERMINAL_POSITION_STATES

__all__ = [
    "CostAssumptions",
    "DecisionStatus",
    "FeatureSnapshot",
    "InvalidTransitionError",
    "MarketSnapshot",
    "PositionState",
    "ReasonCode",
    "Strategy2Decision",
    "StrategyVersion",
    "TERMINAL_POSITION_STATES",
    "reduce_state",
    "stable_idempotency_key",
    "validate_transition",
]
