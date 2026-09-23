"""Isolated, default-off Strategy 2 domain foundation."""

from .contracts import (
    CostAssumptions,
    FeatureSnapshot,
    MarketSnapshot,
    Strategy2Decision,
    StrategyVersion,
    stable_idempotency_key,
)
from .shadow_runtime import (
    EXPERIMENT_ID,
    ShadowObservation,
    observe_intent,
    observe_intent_safely,
    prepare_runtime_signal,
)
from .state_machine import InvalidTransitionError, reduce_state, validate_transition
from .taxonomy import DecisionStatus, PositionState, ReasonCode, TERMINAL_POSITION_STATES

__all__ = [
    "CostAssumptions",
    "DecisionStatus",
    "EXPERIMENT_ID",
    "FeatureSnapshot",
    "InvalidTransitionError",
    "MarketSnapshot",
    "PositionState",
    "ReasonCode",
    "ShadowObservation",
    "Strategy2Decision",
    "StrategyVersion",
    "TERMINAL_POSITION_STATES",
    "reduce_state",
    "stable_idempotency_key",
    "observe_intent",
    "observe_intent_safely",
    "prepare_runtime_signal",
    "validate_transition",
]
