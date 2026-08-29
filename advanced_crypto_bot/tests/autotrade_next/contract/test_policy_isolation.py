"""Contract tests for Story 4.2: Champion and Challenger Isolation."""

import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.policy_isolation import PolicyExecutionFrame, PolicyRole


def test_champion_live_execution_allowed():
    frame = PolicyExecutionFrame(policy_id="pol-champ", role=PolicyRole.CHAMPION, is_live_executable=True)
    assert frame.policy_id == "pol-champ"


def test_challenger_live_execution_denied():
    with pytest.raises(DecisionError) as exc_info:
        PolicyExecutionFrame(policy_id="pol-chall", role=PolicyRole.CHALLENGER, is_live_executable=True)
    assert exc_info.value.code == "CHALLENGER_LIVE_EXECUTION_DENIED"
