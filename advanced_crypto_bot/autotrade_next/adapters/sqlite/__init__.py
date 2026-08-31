"""SQLite persistence adapters for the isolated AutoTrade Next runtime."""

from .fenced_journal import (
    AppendCommand,
    AppendResult,
    AppendStatus,
    AuthorityClaim,
    AuthoritySnapshot,
    ClaimResult,
    ClaimStatus,
    IndeterminateCommit,
    SQLiteFencedJournal,
)
from .recovery_store import (
    RecoveryCheckpointCommand,
    RecoveryCommitResult,
    RecoveryCommitStatus,
    RecoveryIndeterminateCommit,
    RecoveryPersistenceError,
    SQLiteRecoveryStore,
    decode_recovery_checkpoint,
    encode_recovery_checkpoint,
)

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
    "RecoveryCheckpointCommand",
    "RecoveryCommitResult",
    "RecoveryCommitStatus",
    "RecoveryIndeterminateCommit",
    "RecoveryPersistenceError",
    "SQLiteRecoveryStore",
    "decode_recovery_checkpoint",
    "encode_recovery_checkpoint",
)
