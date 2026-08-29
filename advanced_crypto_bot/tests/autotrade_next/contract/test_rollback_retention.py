"""Contract tests for Story 5.6: Additive Rollback."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.fencing import FencedWriterAuthority
from autotrade_next.domain.rollback_retention import AdditiveRollbackRecord


def test_additive_rollback_record_execution():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    current_auth = FencedWriterAuthority(scope_id="global-writer", active_epoch=5, active_token="tok-500")

    rollback = AdditiveRollbackRecord.execute(
        rollback_id="rb-001",
        target_release_tag="v1.9.0",
        reason="Post-cutover latency anomaly detected",
        current_authority=current_auth,
        new_token="tok-600",
        executed_at_utc=now,
    )

    assert rollback.rollback_id == "rb-001"
    assert rollback.target_release_tag == "v1.9.0"
    assert rollback.executed_authority.active_epoch == 6
    assert rollback.executed_authority.active_token == "tok-600"
    assert rollback.rollback_ref.domain == "rollback.record"
