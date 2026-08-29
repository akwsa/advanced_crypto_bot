"""Contract tests for Story 5.5: Stop-The-World Cutover."""

import pytest

from autotrade_next.domain.cutover import CutoverState, CutoverStep
from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.fencing import FencedWriterAuthority


def test_cutover_higher_epoch_claim_success():
    auth = FencedWriterAuthority(scope_id="global-writer", active_epoch=1, active_token="tok-100")
    state = CutoverState(step=CutoverStep.CHECKPOINT_BACKUP, current_authority=auth)

    new_state = state.execute_higher_epoch_claim("tok-200")

    assert new_state.step is CutoverStep.CLAIM_HIGHER_EPOCH
    assert new_state.current_authority.active_epoch == 2
    assert new_state.current_authority.active_token == "tok-200"


def test_cutover_claim_invalid_step_rejected():
    auth = FencedWriterAuthority(scope_id="global-writer", active_epoch=1, active_token="tok-100")
    state = CutoverState(step=CutoverStep.INITIATED, current_authority=auth)

    with pytest.raises(DecisionError) as exc_info:
        state.execute_higher_epoch_claim("tok-200")
    assert exc_info.value.code == "INVALID_CUTOVER_STEP_FOR_CLAIM"
