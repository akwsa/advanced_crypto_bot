"""Contract tests for Story 3.5: Kill Switch and Emergency Zeroing State Machine."""

import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.kill_switch import KillState, KillSwitchStateMachine


def test_kill_switch_state_machine_flow():
    sm = KillSwitchStateMachine(state=KillState.ARMED)
    assert sm.state is KillState.ARMED

    # ARMED -> TRIGGERED
    sm = sm.trigger_kill()
    assert sm.state is KillState.TRIGGERED

    # TRIGGERED -> CANCEL_PENDING -> EXIT_PENDING -> RECONCILING -> LATCHED_SAFE
    sm = sm.advance_state(KillState.CANCEL_PENDING)
    assert sm.state is KillState.CANCEL_PENDING

    sm = sm.advance_state(KillState.EXIT_PENDING)
    assert sm.state is KillState.EXIT_PENDING

    sm = sm.advance_state(KillState.RECONCILING)
    assert sm.state is KillState.RECONCILING

    sm = sm.advance_state(KillState.LATCHED_SAFE)
    assert sm.state is KillState.LATCHED_SAFE


def test_kill_switch_invalid_transition_rejected():
    sm = KillSwitchStateMachine(state=KillState.ARMED)
    with pytest.raises(DecisionError) as exc_info:
        sm.advance_state(KillState.LATCHED_SAFE)
    assert exc_info.value.code == "INVALID_KILL_STATE_TRANSITION"
