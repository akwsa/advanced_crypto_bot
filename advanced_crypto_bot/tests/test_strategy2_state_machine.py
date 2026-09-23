import pytest

from autotrade.strategy2.state_machine import (
    InvalidTransitionError,
    reduce_state,
    validate_transition,
)
from autotrade.strategy2.taxonomy import PositionState, TERMINAL_POSITION_STATES


def test_happy_path_is_legal_and_pure():
    path = (
        PositionState.CANDIDATE,
        PositionState.ARMED,
        PositionState.PENDING,
        PositionState.OPEN_RISK,
        PositionState.BREAK_EVEN,
        PositionState.PROFIT_PROTECTED,
        PositionState.CLOSED,
    )
    current = path[0]
    for next_state in path[1:]:
        assert validate_transition(current, next_state) is True
        current = reduce_state(current, next_state)
    assert current is PositionState.CLOSED


def test_replay_of_same_state_is_an_idempotent_noop():
    assert reduce_state(PositionState.ARMED, PositionState.ARMED) is PositionState.ARMED


@pytest.mark.parametrize("terminal", sorted(TERMINAL_POSITION_STATES, key=lambda item: item.value))
def test_terminal_states_cannot_be_reopened(terminal):
    with pytest.raises(InvalidTransitionError) as error:
        reduce_state(terminal, PositionState.OPEN_RISK)
    assert error.value.current_state is terminal
    assert error.value.next_state is PositionState.OPEN_RISK


def test_skipping_lifecycle_stage_is_rejected():
    with pytest.raises(InvalidTransitionError):
        reduce_state(PositionState.CANDIDATE, PositionState.OPEN_RISK)


def test_hard_invalidation_is_available_while_position_has_risk():
    for state in (
        PositionState.OPEN_RISK,
        PositionState.BREAK_EVEN,
        PositionState.PROFIT_PROTECTED,
    ):
        assert reduce_state(state, PositionState.INVALIDATED) is PositionState.INVALIDATED

