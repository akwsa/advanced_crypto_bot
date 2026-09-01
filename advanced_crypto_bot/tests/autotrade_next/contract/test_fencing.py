"""Contract tests for Story 3.1: Fenced Writer Authority."""

from datetime import UTC, datetime, timedelta
import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.fencing import FencedWriterAuthority, FencedWriterLease


def test_fenced_writer_authority_valid_lease():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    authority = FencedWriterAuthority(scope_id="global-writer", active_epoch=1, active_token="tok-100")
    lease = FencedWriterLease(
        scope_id="global-writer",
        epoch=1,
        lease_token="tok-100",
        granted_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
    )

    authority.validate_lease(lease, current_time_utc=now)


def test_fenced_writer_authority_stale_epoch_rejected():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    authority = FencedWriterAuthority(scope_id="global-writer", active_epoch=2, active_token="tok-200")
    lease = FencedWriterLease(
        scope_id="global-writer",
        epoch=1,  # Stale epoch
        lease_token="tok-100",
        granted_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
    )

    with pytest.raises(DecisionError) as exc_info:
        authority.validate_lease(lease, current_time_utc=now)
    assert exc_info.value.code == "STALE_EPOCH_DENIED"


def test_fenced_writer_authority_rejects_unclaimed_future_epoch():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    authority = FencedWriterAuthority(
        scope_id="global-writer", active_epoch=2, active_token="tok-200",
    )
    lease = FencedWriterLease(
        scope_id="global-writer",
        epoch=3,
        lease_token="forged",
        granted_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
    )

    with pytest.raises(DecisionError) as exc_info:
        authority.validate_lease(lease, current_time_utc=now)
    assert exc_info.value.code == "UNCLAIMED_EPOCH_DENIED"


def test_fenced_writer_authority_rejects_clock_rollback_and_token_reuse():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    authority = FencedWriterAuthority(
        scope_id="global-writer", active_epoch=2, active_token="tok-200",
    )
    lease = FencedWriterLease(
        scope_id="global-writer",
        epoch=2,
        lease_token="tok-200",
        granted_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
    )

    with pytest.raises(DecisionError) as exc_info:
        authority.validate_lease(
            lease,
            current_time_utc=now - timedelta(microseconds=1),
        )
    assert exc_info.value.code == "CLOCK_ANOMALY"

    with pytest.raises(DecisionError) as exc_info:
        authority.increment_epoch("tok-200")
    assert exc_info.value.code == "LEASE_TOKEN_REUSE"


@pytest.mark.parametrize(
    ("factory", "code"),
    (
        (lambda: FencedWriterAuthority("", 1, "tok-100"), "INVALID_AUTHORITY_SCOPE"),
        (lambda: FencedWriterAuthority("global-writer", True, "tok-100"), "INVALID_WRITER_EPOCH"),
        (
            lambda: FencedWriterLease(
                "global-writer", 1, "tok-100",
                datetime(2026, 8, 29, 12, 0, 0),
                datetime(2026, 8, 29, 12, 5, 0),
            ),
            "INVALID_GRANTED_AT",
        ),
    ),
)
def test_fencing_value_objects_reject_invalid_state(factory, code):
    with pytest.raises(DecisionError) as exc_info:
        factory()
    assert exc_info.value.code == code
