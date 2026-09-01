"""Durable contract tests for Story 3.1 fenced command authority."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from autotrade_next.adapters.sqlite.fenced_journal import (
    AppendCommand,
    AppendStatus,
    AuthorityClaim,
    ClaimStatus,
    IndeterminateCommit,
    SQLiteFencedJournal,
)


NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


class ManualClock:
    def __init__(self, current: datetime = NOW) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def claim(*, claim_id: str = "claim-1", expected_epoch: int | None = None,
          token: str = "token-1", granted: datetime = NOW) -> AuthorityClaim:
    return AuthorityClaim(
        claim_id=claim_id,
        scope_id="global-writer",
        expected_epoch=expected_epoch,
        lease_token=token,
        granted_at_utc=granted,
        expires_at_utc=granted + timedelta(minutes=5),
    )


def command(*, command_id: str = "command-1", epoch: int = 1,
            token: str = "token-1",
            expected_sequence: int = 0, event_ref: str = "sha256:event-1",
            outbox_ref: str = "sha256:outbox-1") -> AppendCommand:
    return AppendCommand(
        command_id=command_id,
        scope_id="global-writer",
        epoch=epoch,
        lease_token=token,
        aggregate_id="order-1",
        expected_sequence=expected_sequence,
        event_ref=event_ref,
        outbox_ref=outbox_ref,
    )


def store(
    tmp_path: Path,
    *,
    clock: ManualClock | None = None,
    timeout: float = 0.0,
) -> SQLiteFencedJournal:
    result = SQLiteFencedJournal(
        tmp_path / "journal.sqlite3",
        clock=clock or ManualClock(),
        busy_timeout_seconds=timeout,
    )
    result.initialize_schema_for_test()
    return result


def counts(path: Path) -> tuple[int, int, int, int]:
    with sqlite3.connect(path) as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("command_journal", "canonical_events",
                                   "pending_outbox", "aggregate_high_water"))


def test_claim_is_single_row_monotonic_cas_and_token_never_reused(tmp_path: Path) -> None:
    clock = ManualClock()
    journal = store(tmp_path, clock=clock)
    first = journal.claim_authority(claim())
    retry = journal.claim_authority(claim())
    clock.current = NOW + timedelta(minutes=5)
    takeover = journal.claim_authority(claim(
        claim_id="claim-2", expected_epoch=1, token="token-2",
        granted=clock.current,
    ))
    lost_cas = journal.claim_authority(claim(
        claim_id="claim-3", expected_epoch=1, token="token-3",
        granted=clock.current,
    ))
    clock.current = NOW + timedelta(minutes=10)
    reused = journal.claim_authority(claim(
        claim_id="claim-4", expected_epoch=2, token="token-1",
        granted=clock.current,
    ))

    assert first.status is ClaimStatus.CLAIMED and first.epoch == 1
    assert retry.status is ClaimStatus.IDEMPOTENT and retry.epoch == 1
    assert takeover.status is ClaimStatus.TAKEN_OVER and takeover.epoch == 2
    assert lost_cas.status is ClaimStatus.AUTHORITY_CONFLICT
    assert reused.status is ClaimStatus.TOKEN_REUSE
    snapshot = journal.read_authority("global-writer")
    assert snapshot is not None
    assert (snapshot.epoch, snapshot.lease_token) == (2, "token-2")
    with sqlite3.connect(journal.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM writer_authority WHERE scope_id = ?",
            ("global-writer",),
        ).fetchone()[0] == 1


def test_claim_identity_reuse_and_backward_clock_fail_closed(tmp_path: Path) -> None:
    clock = ManualClock()
    journal = store(tmp_path, clock=clock)
    assert journal.claim_authority(claim()).status is ClaimStatus.CLAIMED
    identity_conflict = journal.claim_authority(claim(token="different"))
    clock.current = NOW - timedelta(microseconds=1)
    backward = journal.claim_authority(claim(
        claim_id="claim-2", expected_epoch=1, token="token-2",
        granted=NOW - timedelta(minutes=1),
    ))
    assert identity_conflict.status is ClaimStatus.IDENTITY_CONFLICT
    assert backward.status is ClaimStatus.CLOCK_ANOMALY
    assert journal.read_authority("global-writer").epoch == 1  # type: ignore[union-attr]


def test_takeover_before_active_lease_expiry_fails_closed(tmp_path: Path) -> None:
    clock = ManualClock()
    journal = store(tmp_path, clock=clock)
    assert journal.claim_authority(claim()).status is ClaimStatus.CLAIMED
    clock.current = NOW + timedelta(seconds=1)

    result = journal.claim_authority(claim(
        claim_id="claim-2",
        expected_epoch=1,
        token="token-2",
        granted=clock.current,
    ))

    assert result.status is ClaimStatus.LEASE_ACTIVE
    snapshot = journal.read_authority("global-writer")
    assert snapshot is not None
    assert (snapshot.epoch, snapshot.lease_token) == (1, "token-1")


def test_append_atomically_commits_journal_event_outbox_and_high_water(tmp_path: Path) -> None:
    journal = store(tmp_path)
    journal.claim_authority(claim())
    result = journal.append(command())

    assert result.status is AppendStatus.APPENDED
    assert result.sequence == 1
    assert counts(journal.path) == (1, 1, 1, 1)
    assert journal.aggregate_sequence("global-writer", "order-1") == 1


@pytest.mark.parametrize(
    ("change", "observed", "status"),
    (
        ({"epoch": 0}, NOW, AppendStatus.STALE_EPOCH),
        ({"epoch": 2, "token": "forged"}, NOW, AppendStatus.UNCLAIMED_EPOCH),
        ({"token": "forged"}, NOW, AppendStatus.FENCE_LOST),
        ({}, NOW - timedelta(microseconds=1), AppendStatus.CLOCK_ANOMALY),
        ({}, NOW + timedelta(minutes=5), AppendStatus.LEASE_EXPIRED),
        ({"expected_sequence": 1}, NOW, AppendStatus.SEQUENCE_CONFLICT),
    ),
)
def test_invalid_fence_or_sequence_has_zero_writes(
    tmp_path: Path,
    change: dict[str, object],
    observed: datetime,
    status: AppendStatus,
) -> None:
    clock = ManualClock()
    journal = store(tmp_path, clock=clock)
    journal.claim_authority(claim())
    clock.current = observed
    result = journal.append(command(**change))  # type: ignore[arg-type]
    assert result.status is status
    assert counts(journal.path) == (0, 0, 0, 0)


def test_retry_requires_same_command_identity_and_payload(tmp_path: Path) -> None:
    journal = store(tmp_path)
    journal.claim_authority(claim())
    assert journal.append(command()).status is AppendStatus.APPENDED
    assert journal.append(command()).status is AppendStatus.IDEMPOTENT
    conflict = journal.append(command(event_ref="sha256:different"))
    assert conflict.status is AppendStatus.IDENTITY_CONFLICT
    assert counts(journal.path) == (1, 1, 1, 1)


def test_committed_retry_is_idempotent_even_after_takeover(tmp_path: Path) -> None:
    clock = ManualClock()
    journal = store(tmp_path, clock=clock)
    journal.claim_authority(claim())
    assert journal.append(command()).status is AppendStatus.APPENDED
    clock.current = NOW + timedelta(minutes=5)
    journal.claim_authority(claim(
        claim_id="claim-2", expected_epoch=1, token="token-2",
        granted=clock.current,
    ))
    assert journal.append(command()).status is AppendStatus.IDEMPOTENT
    assert counts(journal.path) == (1, 1, 1, 1)


def test_sqlite_busy_is_typed_and_has_zero_stale_writes(tmp_path: Path) -> None:
    journal = store(tmp_path)
    journal.claim_authority(claim())
    blocker = sqlite3.connect(journal.path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        result = journal.append(command())
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert result.status is AppendStatus.BUSY
    assert counts(journal.path) == (0, 0, 0, 0)


def test_takeover_busy_is_typed_and_preserves_active_authority(tmp_path: Path) -> None:
    journal = store(tmp_path)
    journal.claim_authority(claim())
    blocker = sqlite3.connect(journal.path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        result = journal.claim_authority(claim(
            claim_id="claim-2", expected_epoch=1, token="token-2",
            granted=NOW + timedelta(seconds=1),
        ))
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert result.status is ClaimStatus.BUSY
    snapshot = journal.read_authority("global-writer")
    assert snapshot is not None
    assert (snapshot.epoch, snapshot.lease_token) == (1, "token-1")


class CrashBeforeCommitJournal(SQLiteFencedJournal):
    def _before_commit(self, operation: str, identity: str) -> None:
        if operation == "append":
            raise RuntimeError(f"simulated crash for {identity}")


class ClaimCrashBeforeCommitJournal(SQLiteFencedJournal):
    def _before_commit(self, operation: str, identity: str) -> None:
        if operation == "claim":
            raise RuntimeError(f"simulated claim crash for {identity}")


def test_crash_before_commit_rolls_back_and_same_identity_can_retry(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    healthy = SQLiteFencedJournal(path, clock=ManualClock())
    healthy.initialize_schema_for_test()
    healthy.claim_authority(claim())
    crashing = CrashBeforeCommitJournal(path, clock=ManualClock())

    with pytest.raises(RuntimeError, match="simulated crash"):
        crashing.append(command())
    assert counts(path) == (0, 0, 0, 0)
    assert healthy.append(command()).status is AppendStatus.APPENDED
    assert counts(path) == (1, 1, 1, 1)


def test_claim_crash_before_commit_leaves_no_authority_and_retries(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    healthy = SQLiteFencedJournal(path, clock=ManualClock())
    healthy.initialize_schema_for_test()
    crashing = ClaimCrashBeforeCommitJournal(path, clock=ManualClock())

    with pytest.raises(RuntimeError, match="simulated claim crash"):
        crashing.claim_authority(claim())
    assert healthy.read_authority("global-writer") is None
    assert healthy.claim_authority(claim()).status is ClaimStatus.CLAIMED


class CommitThenRaiseJournal(SQLiteFencedJournal):
    def _commit(self, connection: sqlite3.Connection) -> None:
        super()._commit(connection)
        raise IndeterminateCommit("commit return lost")


def test_indeterminate_commit_is_reconciled_by_command_identity(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    healthy = SQLiteFencedJournal(path, clock=ManualClock())
    healthy.initialize_schema_for_test()
    healthy.claim_authority(claim())
    uncertain = CommitThenRaiseJournal(path, clock=ManualClock())

    outcome = uncertain.append(command())
    assert outcome.status is AppendStatus.COMMITTED_AFTER_INDETERMINATE
    assert healthy.append(command()).status is AppendStatus.IDEMPOTENT
    assert counts(path) == (1, 1, 1, 1)


def test_indeterminate_claim_commit_is_reconciled_by_claim_identity(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    uncertain = CommitThenRaiseJournal(path, clock=ManualClock())
    uncertain.initialize_schema_for_test()
    result = uncertain.claim_authority(claim())
    assert result.status is ClaimStatus.COMMITTED_AFTER_INDETERMINATE
    healthy = SQLiteFencedJournal(path, clock=ManualClock())
    assert healthy.claim_authority(claim()).status is ClaimStatus.IDEMPOTENT


def test_invalid_clock_output_is_typed_and_has_zero_writes(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite3"
    healthy = SQLiteFencedJournal(path, clock=ManualClock())
    healthy.initialize_schema_for_test()
    assert healthy.claim_authority(claim()).status is ClaimStatus.CLAIMED
    invalid_clock = SQLiteFencedJournal(
        path,
        clock=lambda: NOW.replace(tzinfo=None),
    )

    claim_result = invalid_clock.claim_authority(claim(
        claim_id="claim-2",
        expected_epoch=1,
        token="token-2",
    ))
    assert claim_result.status is ClaimStatus.CLOCK_ANOMALY
    assert invalid_clock.append(command()).status is AppendStatus.CLOCK_ANOMALY
    assert counts(path) == (0, 0, 0, 0)


def test_missing_database_fails_closed_without_creating_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    journal = SQLiteFencedJournal(path, clock=ManualClock())

    result = journal.claim_authority(claim())

    assert result.status is ClaimStatus.STORAGE_FAILURE
    assert not path.exists()


def test_failed_reconciliation_keeps_commit_outcome_indeterminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = store(tmp_path)

    def unavailable_connection() -> sqlite3.Connection:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(journal, "_connect", unavailable_connection)

    claim_result = journal._reconcile_claim(claim())
    append_result = journal._reconcile_append(command())
    assert claim_result.status is ClaimStatus.INDETERMINATE_COMMIT
    assert append_result.status is AppendStatus.INDETERMINATE_COMMIT


def test_rollback_failure_does_not_mask_fail_closed_outcome() -> None:
    class BrokenRollbackConnection:
        in_transaction = True

        def execute(self, statement: str) -> None:
            assert statement == "ROLLBACK"
            raise sqlite3.OperationalError("disk I/O error")

    SQLiteFencedJournal._rollback(BrokenRollbackConnection())  # type: ignore[arg-type]


def test_inputs_require_exact_types_and_utc_times() -> None:
    with pytest.raises(ValueError, match="INVALID_EXPECTED_EPOCH"):
        claim(expected_epoch=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="INVALID_GRANTED_AT"):
        claim(granted=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="INVALID_EPOCH"):
        command(epoch=True)  # type: ignore[arg-type]


def test_transaction_adapter_has_no_network_or_redis_imports() -> None:
    source_path = Path(__file__).parents[3] / "autotrade_next/adapters/sqlite/fenced_journal.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint({"requests", "httpx", "aiohttp", "socket", "redis"})
    source = source_path.read_text(encoding="utf-8")
    assert 'connection.execute("BEGIN IMMEDIATE")' in source
