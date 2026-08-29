"""Contract tests for Story 4.6: Policy Promotion and Governance."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.promotion import PolicyAuthorityState, PolicyPromotionRecord


def test_policy_promotion_success():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    rec = PolicyPromotionRecord.promote(
        policy_id="pol-001",
        report_id="rep-100",
        approved_by_actor="Officer-John",
        reason="Passed all conjunctive requirements",
        promoted_at_utc=now,
        is_conjunctive_pass=True,
    )

    assert rec.policy_id == "pol-001"
    assert rec.state is PolicyAuthorityState.PROMOTED_LIVE
    assert rec.approved_by_actor == "Officer-John"


def test_policy_promotion_rejected_without_conjunctive_pass():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    with pytest.raises(DecisionError) as exc_info:
        PolicyPromotionRecord.promote(
            policy_id="pol-001",
            report_id="rep-100",
            approved_by_actor="Officer-John",
            reason="Failed requirements",
            promoted_at_utc=now,
            is_conjunctive_pass=False,
        )
    assert exc_info.value.code == "NON_PROMOTABLE_REPORT_DENIED"
