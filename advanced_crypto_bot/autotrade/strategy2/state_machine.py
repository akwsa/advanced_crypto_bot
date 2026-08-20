"""Pure lifecycle validation and reduction for Strategy 2 positions."""

from __future__ import annotations

from .taxonomy import PositionState, TERMINAL_POSITION_STATES


class InvalidTransitionError(ValueError):
    def __init__(self, current_state: PositionState | None, next_state: PositionState) -> None:
        self.current_state = current_state
        self.next_state = next_state
        current = current_state.value if current_state is not None else "<NONE>"
        super().__init__(f"illegal Strategy 2 transition: {current} -> {next_state.value}")


_LEGAL_TRANSITIONS = {
    PositionState.CANDIDATE: frozenset(
        {PositionState.ARMED, PositionState.INVALIDATED, PositionState.CANCELLED, PositionState.DATA_STALE}
    ),
    PositionState.ARMED: frozenset(
        {PositionState.PENDING, PositionState.INVALIDATED, PositionState.CANCELLED, PositionState.DATA_STALE}
    ),
    PositionState.PENDING: frozenset(
        {PositionState.OPEN_RISK, PositionState.INVALIDATED, PositionState.CANCELLED, PositionState.DATA_STALE}
    ),
    PositionState.OPEN_RISK: frozenset(
        {PositionState.BREAK_EVEN, PositionState.CLOSED, PositionState.INVALIDATED}
    ),
    PositionState.BREAK_EVEN: frozenset(
        {PositionState.PROFIT_PROTECTED, PositionState.CLOSED, PositionState.INVALIDATED}
    ),
    PositionState.PROFIT_PROTECTED: frozenset(
        {PositionState.CLOSED, PositionState.INVALIDATED}
    ),
    **{state: frozenset() for state in TERMINAL_POSITION_STATES},
}


def _coerce_state(value: PositionState) -> PositionState:
    if isinstance(value, PositionState):
        return value
    try:
        return PositionState(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unknown Strategy 2 position state: {value!r}") from exc


def validate_transition(current_state: PositionState, next_state: PositionState) -> bool:
    """Return true for a legal transition, otherwise raise a typed domain error.

    A transition to the same state is an idempotent replay/no-op.
    """
    current = _coerce_state(current_state)
    next_ = _coerce_state(next_state)
    if current == next_ or next_ in _LEGAL_TRANSITIONS[current]:
        return True
    raise InvalidTransitionError(current, next_)


def reduce_state(current_state: PositionState, next_state: PositionState) -> PositionState:
    """Purely validate and return the requested next state."""
    current = _coerce_state(current_state)
    next_ = _coerce_state(next_state)
    validate_transition(current, next_)
    return next_
