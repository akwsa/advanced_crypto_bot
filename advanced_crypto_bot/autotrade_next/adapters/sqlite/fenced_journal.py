"""SQLite single-writer authority and atomic canonical append adapter.

The adapter owns the complete transaction boundary.  Callers supply immutable
identities and content references; no callback or network operation runs inside
the transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import math
from pathlib import Path
import sqlite3


_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ClaimStatus(str, Enum):
    CLAIMED = "CLAIMED"
    TAKEN_OVER = "TAKEN_OVER"
    IDEMPOTENT = "IDEMPOTENT"
    COMMITTED_AFTER_INDETERMINATE = "COMMITTED_AFTER_INDETERMINATE"
    AUTHORITY_CONFLICT = "AUTHORITY_CONFLICT"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    TOKEN_REUSE = "TOKEN_REUSE"
    LEASE_ACTIVE = "LEASE_ACTIVE"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"
    BUSY = "BUSY"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    INDETERMINATE_COMMIT = "INDETERMINATE_COMMIT"


class AppendStatus(str, Enum):
    APPENDED = "APPENDED"
    IDEMPOTENT = "IDEMPOTENT"
    COMMITTED_AFTER_INDETERMINATE = "COMMITTED_AFTER_INDETERMINATE"
    AUTHORITY_MISSING = "AUTHORITY_MISSING"
    STALE_EPOCH = "STALE_EPOCH"
    UNCLAIMED_EPOCH = "UNCLAIMED_EPOCH"
    FENCE_LOST = "FENCE_LOST"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    CLOCK_ANOMALY = "CLOCK_ANOMALY"
    SEQUENCE_CONFLICT = "SEQUENCE_CONFLICT"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    BUSY = "BUSY"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    INDETERMINATE_COMMIT = "INDETERMINATE_COMMIT"


class IndeterminateCommit(RuntimeError):
    """Signals that COMMIT may have succeeded but its return was lost."""


class _ClockAnomaly(RuntimeError):
    """Internal marker used to map an untrusted clock result fail-closed."""


def _required_text(value: object, code: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(code)


def _utc_microseconds(value: datetime, code: str) -> int:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError(code)
    if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError(code)
    canonical = value.astimezone(UTC)
    delta = canonical - _UNIX_EPOCH
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000
            + delta.microseconds)


@dataclass(frozen=True, slots=True)
class AuthorityClaim:
    claim_id: str
    scope_id: str
    expected_epoch: int | None
    lease_token: str
    granted_at_utc: datetime
    expires_at_utc: datetime

    def __post_init__(self) -> None:
        _required_text(self.claim_id, "INVALID_CLAIM_ID")
        _required_text(self.scope_id, "INVALID_SCOPE_ID")
        _required_text(self.lease_token, "INVALID_LEASE_TOKEN")
        if (self.expected_epoch is not None
                and (type(self.expected_epoch) is not int or self.expected_epoch < 0)):
            raise ValueError("INVALID_EXPECTED_EPOCH")
        granted = _utc_microseconds(self.granted_at_utc, "INVALID_GRANTED_AT")
        expires = _utc_microseconds(self.expires_at_utc, "INVALID_EXPIRES_AT")
        if expires <= granted:
            raise ValueError("INVALID_LEASE_WINDOW")


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    scope_id: str
    epoch: int
    lease_token: str
    granted_at_microseconds: int
    expires_at_microseconds: int


@dataclass(frozen=True, slots=True)
class ClaimResult:
    status: ClaimStatus
    scope_id: str
    epoch: int | None = None
    lease_token: str | None = None


@dataclass(frozen=True, slots=True)
class AppendCommand:
    command_id: str
    scope_id: str
    epoch: int
    lease_token: str
    aggregate_id: str
    expected_sequence: int
    event_ref: str
    outbox_ref: str

    def __post_init__(self) -> None:
        for value, code in (
            (self.command_id, "INVALID_COMMAND_ID"),
            (self.scope_id, "INVALID_SCOPE_ID"),
            (self.lease_token, "INVALID_LEASE_TOKEN"),
            (self.aggregate_id, "INVALID_AGGREGATE_ID"),
            (self.event_ref, "INVALID_EVENT_REF"),
            (self.outbox_ref, "INVALID_OUTBOX_REF"),
        ):
            _required_text(value, code)
        if type(self.epoch) is not int or self.epoch < 0:
            raise ValueError("INVALID_EPOCH")
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise ValueError("INVALID_EXPECTED_SEQUENCE")


@dataclass(frozen=True, slots=True)
class AppendResult:
    status: AppendStatus
    command_id: str
    sequence: int | None = None


class SQLiteFencedJournal:
    """Own a durable writer fence and append facts under one SQLite lock."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime],
        busy_timeout_seconds: float = 0.0,
    ) -> None:
        if not isinstance(path, (str, Path)) or not str(path):
            raise ValueError("INVALID_SQLITE_PATH")
        if str(path) == ":memory:":
            raise ValueError("SHARED_DURABLE_PATH_REQUIRED")
        if (type(busy_timeout_seconds) not in (int, float)
                or not math.isfinite(busy_timeout_seconds)
                or busy_timeout_seconds < 0):
            raise ValueError("INVALID_BUSY_TIMEOUT")
        if not callable(clock):
            raise TypeError("INVALID_CLOCK")
        self.path = Path(path)
        self._clock = clock
        self._busy_timeout_seconds = float(busy_timeout_seconds)

    def _connect(self) -> sqlite3.Connection:
        database_uri = f"{self.path.resolve().as_uri()}?mode=rw"
        connection = sqlite3.connect(
            database_uri,
            timeout=self._busy_timeout_seconds,
            isolation_level=None,
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize_schema_for_test(self) -> None:
        """Create the isolated test schema; production uses offline migrations."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(
            self.path,
            timeout=self._busy_timeout_seconds,
            isolation_level=None,
        )) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS writer_authority (
                    scope_id TEXT PRIMARY KEY,
                    active_epoch INTEGER NOT NULL CHECK (active_epoch >= 1),
                    lease_token TEXT NOT NULL CHECK (length(lease_token) > 0),
                    granted_at_us INTEGER NOT NULL,
                    expires_at_us INTEGER NOT NULL,
                    CHECK (expires_at_us > granted_at_us)
                );

                CREATE TABLE IF NOT EXISTS authority_claims (
                    claim_id TEXT PRIMARY KEY,
                    scope_id TEXT NOT NULL,
                    expected_epoch INTEGER,
                    lease_token TEXT NOT NULL,
                    granted_at_us INTEGER NOT NULL,
                    expires_at_us INTEGER NOT NULL,
                    granted_epoch INTEGER NOT NULL CHECK (granted_epoch >= 1),
                    UNIQUE (scope_id, lease_token)
                );

                CREATE TABLE IF NOT EXISTS aggregate_high_water (
                    scope_id TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence >= 1),
                    PRIMARY KEY (scope_id, aggregate_id)
                );

                CREATE TABLE IF NOT EXISTS command_journal (
                    command_id TEXT PRIMARY KEY,
                    scope_id TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    lease_token TEXT NOT NULL,
                    current_time_us INTEGER NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    expected_sequence INTEGER NOT NULL,
                    resulting_sequence INTEGER NOT NULL,
                    event_ref TEXT NOT NULL,
                    outbox_ref TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS canonical_events (
                    scope_id TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    command_id TEXT NOT NULL UNIQUE,
                    event_ref TEXT NOT NULL,
                    PRIMARY KEY (scope_id, aggregate_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS pending_outbox (
                    command_id TEXT PRIMARY KEY,
                    scope_id TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    outbox_ref TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status = 'PENDING')
                );
                """
            )

    def read_authority(self, scope_id: str) -> AuthoritySnapshot | None:
        _required_text(scope_id, "INVALID_SCOPE_ID")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT scope_id, active_epoch, lease_token, granted_at_us, expires_at_us "
                "FROM writer_authority WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
        if row is None:
            return None
        return AuthoritySnapshot(
            row["scope_id"], row["active_epoch"], row["lease_token"],
            row["granted_at_us"], row["expires_at_us"],
        )

    def aggregate_sequence(self, scope_id: str, aggregate_id: str) -> int:
        _required_text(scope_id, "INVALID_SCOPE_ID")
        _required_text(aggregate_id, "INVALID_AGGREGATE_ID")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT sequence FROM aggregate_high_water "
                "WHERE scope_id = ? AND aggregate_id = ?",
                (scope_id, aggregate_id),
            ).fetchone()
        return 0 if row is None else int(row["sequence"])

    def _begin(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    def _observed_time_microseconds(self) -> int:
        try:
            return _utc_microseconds(self._clock(), "INVALID_CLOCK_TIME")
        except Exception as error:
            raise _ClockAnomaly("INVALID_CLOCK_TIME") from error

    def _before_commit(self, operation: str, identity: str) -> None:
        """Fault-injection seam; production implementation intentionally does nothing."""

    def _commit(self, connection: sqlite3.Connection) -> None:
        connection.execute("COMMIT")

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        try:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
        except sqlite3.DatabaseError:
            # Preserve the operation's typed failure; close() remains the final
            # fail-closed boundary for a transaction that cannot be rolled back.
            pass

    @staticmethod
    def _is_busy(error: sqlite3.OperationalError) -> bool:
        code = getattr(error, "sqlite_errorcode", None)
        if isinstance(code, int):
            return (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
        message = str(error).lower()
        return "locked" in message or "busy" in message

    @staticmethod
    def _claim_matches(row: sqlite3.Row, request: AuthorityClaim) -> bool:
        return (
            row["scope_id"] == request.scope_id
            and row["expected_epoch"] == request.expected_epoch
            and row["lease_token"] == request.lease_token
            and row["granted_at_us"] == _utc_microseconds(
                request.granted_at_utc, "INVALID_GRANTED_AT")
            and row["expires_at_us"] == _utc_microseconds(
                request.expires_at_utc, "INVALID_EXPIRES_AT")
        )

    @staticmethod
    def _command_matches(row: sqlite3.Row, request: AppendCommand) -> bool:
        return (
            row["scope_id"] == request.scope_id
            and row["epoch"] == request.epoch
            and row["lease_token"] == request.lease_token
            and row["aggregate_id"] == request.aggregate_id
            and row["expected_sequence"] == request.expected_sequence
            and row["event_ref"] == request.event_ref
            and row["outbox_ref"] == request.outbox_ref
        )

    def claim_authority(self, request: AuthorityClaim) -> ClaimResult:
        if type(request) is not AuthorityClaim:
            raise TypeError("INVALID_AUTHORITY_CLAIM")
        try:
            connection = self._connect()
        except sqlite3.DatabaseError as error:
            status = (ClaimStatus.BUSY
                      if isinstance(error, sqlite3.OperationalError) and self._is_busy(error)
                      else ClaimStatus.STORAGE_FAILURE)
            return ClaimResult(status, request.scope_id)
        committed_maybe = False
        try:
            self._begin(connection)
            prior_claim = connection.execute(
                "SELECT * FROM authority_claims WHERE claim_id = ?",
                (request.claim_id,),
            ).fetchone()
            if prior_claim is not None:
                status = (ClaimStatus.IDEMPOTENT if self._claim_matches(prior_claim, request)
                          else ClaimStatus.IDENTITY_CONFLICT)
                self._rollback(connection)
                return ClaimResult(status, request.scope_id,
                                   prior_claim["granted_epoch"], prior_claim["lease_token"])

            active = connection.execute(
                "SELECT * FROM writer_authority WHERE scope_id = ?",
                (request.scope_id,),
            ).fetchone()
            granted_us = _utc_microseconds(request.granted_at_utc, "INVALID_GRANTED_AT")
            expires_us = _utc_microseconds(request.expires_at_utc, "INVALID_EXPIRES_AT")
            observed_us = self._observed_time_microseconds()
            if observed_us < granted_us or observed_us >= expires_us:
                self._rollback(connection)
                return ClaimResult(ClaimStatus.CLOCK_ANOMALY, request.scope_id)
            if active is None:
                if request.expected_epoch not in (None, 0):
                    self._rollback(connection)
                    return ClaimResult(ClaimStatus.AUTHORITY_CONFLICT, request.scope_id)
                new_epoch = 1
                success = ClaimStatus.CLAIMED
                connection.execute(
                    "INSERT INTO writer_authority "
                    "(scope_id, active_epoch, lease_token, granted_at_us, expires_at_us) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (request.scope_id, new_epoch, request.lease_token,
                     granted_us, expires_us),
                )
            else:
                if request.expected_epoch != active["active_epoch"]:
                    self._rollback(connection)
                    return ClaimResult(ClaimStatus.AUTHORITY_CONFLICT, request.scope_id,
                                       active["active_epoch"], active["lease_token"])
                if observed_us < active["granted_at_us"]:
                    self._rollback(connection)
                    return ClaimResult(ClaimStatus.CLOCK_ANOMALY, request.scope_id,
                                       active["active_epoch"], active["lease_token"])
                if observed_us < active["expires_at_us"]:
                    self._rollback(connection)
                    return ClaimResult(ClaimStatus.LEASE_ACTIVE, request.scope_id,
                                       active["active_epoch"], active["lease_token"])
                token_seen = connection.execute(
                    "SELECT 1 FROM authority_claims WHERE scope_id = ? AND lease_token = ?",
                    (request.scope_id, request.lease_token),
                ).fetchone()
                if token_seen is not None:
                    self._rollback(connection)
                    return ClaimResult(ClaimStatus.TOKEN_REUSE, request.scope_id,
                                       active["active_epoch"], active["lease_token"])
                new_epoch = active["active_epoch"] + 1
                success = ClaimStatus.TAKEN_OVER
                updated = connection.execute(
                    "UPDATE writer_authority SET active_epoch = ?, lease_token = ?, "
                    "granted_at_us = ?, expires_at_us = ? "
                    "WHERE scope_id = ? AND active_epoch = ? AND lease_token = ?",
                    (new_epoch, request.lease_token, granted_us, expires_us,
                     request.scope_id, active["active_epoch"], active["lease_token"]),
                )
                if updated.rowcount != 1:
                    self._rollback(connection)
                    return ClaimResult(ClaimStatus.AUTHORITY_CONFLICT, request.scope_id)

            connection.execute(
                "INSERT INTO authority_claims "
                "(claim_id, scope_id, expected_epoch, lease_token, granted_at_us, "
                "expires_at_us, granted_epoch) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (request.claim_id, request.scope_id, request.expected_epoch,
                 request.lease_token, granted_us, expires_us, new_epoch),
            )
            self._before_commit("claim", request.claim_id)
            committed_maybe = True
            self._commit(connection)
            return ClaimResult(success, request.scope_id, new_epoch, request.lease_token)
        except IndeterminateCommit:
            self._rollback(connection)
            return self._reconcile_claim(request)
        except _ClockAnomaly:
            self._rollback(connection)
            return ClaimResult(ClaimStatus.CLOCK_ANOMALY, request.scope_id)
        except sqlite3.OperationalError as error:
            self._rollback(connection)
            if self._is_busy(error):
                return ClaimResult(ClaimStatus.BUSY, request.scope_id)
            if committed_maybe:
                return self._reconcile_claim(request)
            return ClaimResult(ClaimStatus.STORAGE_FAILURE, request.scope_id)
        except sqlite3.DatabaseError:
            self._rollback(connection)
            if committed_maybe:
                return self._reconcile_claim(request)
            return ClaimResult(ClaimStatus.STORAGE_FAILURE, request.scope_id)
        except Exception:
            self._rollback(connection)
            raise
        finally:
            connection.close()

    def _reconcile_claim(self, request: AuthorityClaim) -> ClaimResult:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM authority_claims WHERE claim_id = ?",
                    (request.claim_id,),
                ).fetchone()
        except sqlite3.DatabaseError:
            return ClaimResult(ClaimStatus.INDETERMINATE_COMMIT, request.scope_id)
        if row is None:
            return ClaimResult(ClaimStatus.INDETERMINATE_COMMIT, request.scope_id)
        if not self._claim_matches(row, request):
            return ClaimResult(ClaimStatus.IDENTITY_CONFLICT, request.scope_id,
                               row["granted_epoch"], row["lease_token"])
        return ClaimResult(ClaimStatus.COMMITTED_AFTER_INDETERMINATE,
                           request.scope_id, row["granted_epoch"], row["lease_token"])

    def append(self, request: AppendCommand) -> AppendResult:
        if type(request) is not AppendCommand:
            raise TypeError("INVALID_APPEND_COMMAND")
        try:
            connection = self._connect()
        except sqlite3.DatabaseError as error:
            status = (AppendStatus.BUSY
                      if isinstance(error, sqlite3.OperationalError) and self._is_busy(error)
                      else AppendStatus.STORAGE_FAILURE)
            return AppendResult(status, request.command_id)
        committed_maybe = False
        try:
            self._begin(connection)
            prior = connection.execute(
                "SELECT * FROM command_journal WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()
            if prior is not None:
                status = (AppendStatus.IDEMPOTENT if self._command_matches(prior, request)
                          else AppendStatus.IDENTITY_CONFLICT)
                self._rollback(connection)
                return AppendResult(status, request.command_id,
                                    prior["resulting_sequence"])

            active = connection.execute(
                "SELECT * FROM writer_authority WHERE scope_id = ?",
                (request.scope_id,),
            ).fetchone()
            if active is None:
                self._rollback(connection)
                return AppendResult(AppendStatus.AUTHORITY_MISSING, request.command_id)
            if request.epoch != active["active_epoch"]:
                status = (AppendStatus.STALE_EPOCH
                          if request.epoch < active["active_epoch"]
                          else AppendStatus.UNCLAIMED_EPOCH)
                self._rollback(connection)
                return AppendResult(status, request.command_id)
            if request.lease_token != active["lease_token"]:
                self._rollback(connection)
                return AppendResult(AppendStatus.FENCE_LOST, request.command_id)

            observed_us = self._observed_time_microseconds()
            if observed_us < active["granted_at_us"]:
                self._rollback(connection)
                return AppendResult(AppendStatus.CLOCK_ANOMALY, request.command_id)
            if observed_us >= active["expires_at_us"]:
                self._rollback(connection)
                return AppendResult(AppendStatus.LEASE_EXPIRED, request.command_id)

            high_water = connection.execute(
                "SELECT sequence FROM aggregate_high_water "
                "WHERE scope_id = ? AND aggregate_id = ?",
                (request.scope_id, request.aggregate_id),
            ).fetchone()
            current_sequence = 0 if high_water is None else high_water["sequence"]
            if request.expected_sequence != current_sequence:
                self._rollback(connection)
                return AppendResult(AppendStatus.SEQUENCE_CONFLICT, request.command_id,
                                    current_sequence)
            resulting_sequence = current_sequence + 1

            if high_water is None:
                connection.execute(
                    "INSERT INTO aggregate_high_water (scope_id, aggregate_id, sequence) "
                    "VALUES (?, ?, ?)",
                    (request.scope_id, request.aggregate_id, resulting_sequence),
                )
            else:
                updated = connection.execute(
                    "UPDATE aggregate_high_water SET sequence = ? "
                    "WHERE scope_id = ? AND aggregate_id = ? AND sequence = ?",
                    (resulting_sequence, request.scope_id, request.aggregate_id,
                     current_sequence),
                )
                if updated.rowcount != 1:
                    self._rollback(connection)
                    return AppendResult(AppendStatus.SEQUENCE_CONFLICT,
                                        request.command_id, current_sequence)

            connection.execute(
                "INSERT INTO command_journal "
                "(command_id, scope_id, epoch, lease_token, current_time_us, "
                "aggregate_id, expected_sequence, resulting_sequence, event_ref, outbox_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request.command_id, request.scope_id, request.epoch,
                 request.lease_token, observed_us, request.aggregate_id,
                 request.expected_sequence, resulting_sequence,
                 request.event_ref, request.outbox_ref),
            )
            connection.execute(
                "INSERT INTO canonical_events "
                "(scope_id, aggregate_id, sequence, command_id, event_ref) "
                "VALUES (?, ?, ?, ?, ?)",
                (request.scope_id, request.aggregate_id, resulting_sequence,
                 request.command_id, request.event_ref),
            )
            connection.execute(
                "INSERT INTO pending_outbox "
                "(command_id, scope_id, aggregate_id, sequence, outbox_ref, status) "
                "VALUES (?, ?, ?, ?, ?, 'PENDING')",
                (request.command_id, request.scope_id, request.aggregate_id,
                 resulting_sequence, request.outbox_ref),
            )
            self._before_commit("append", request.command_id)
            committed_maybe = True
            self._commit(connection)
            return AppendResult(AppendStatus.APPENDED, request.command_id,
                                resulting_sequence)
        except IndeterminateCommit:
            self._rollback(connection)
            return self._reconcile_append(request)
        except _ClockAnomaly:
            self._rollback(connection)
            return AppendResult(AppendStatus.CLOCK_ANOMALY, request.command_id)
        except sqlite3.OperationalError as error:
            self._rollback(connection)
            if self._is_busy(error):
                return AppendResult(AppendStatus.BUSY, request.command_id)
            if committed_maybe:
                return self._reconcile_append(request)
            return AppendResult(AppendStatus.STORAGE_FAILURE, request.command_id)
        except sqlite3.DatabaseError:
            self._rollback(connection)
            if committed_maybe:
                return self._reconcile_append(request)
            return AppendResult(AppendStatus.STORAGE_FAILURE, request.command_id)
        except Exception:
            self._rollback(connection)
            raise
        finally:
            connection.close()

    def _reconcile_append(self, request: AppendCommand) -> AppendResult:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM command_journal WHERE command_id = ?",
                    (request.command_id,),
                ).fetchone()
        except sqlite3.DatabaseError:
            return AppendResult(AppendStatus.INDETERMINATE_COMMIT, request.command_id)
        if row is None:
            return AppendResult(AppendStatus.INDETERMINATE_COMMIT, request.command_id)
        if not self._command_matches(row, request):
            return AppendResult(AppendStatus.IDENTITY_CONFLICT, request.command_id,
                                row["resulting_sequence"])
        return AppendResult(AppendStatus.COMMITTED_AFTER_INDETERMINATE,
                            request.command_id, row["resulting_sequence"])


__all__ = (
    "AppendCommand",
    "AppendResult",
    "AppendStatus",
    "AuthorityClaim",
    "AuthoritySnapshot",
    "ClaimResult",
    "ClaimStatus",
    "IndeterminateCommit",
    "SQLiteFencedJournal",
)
