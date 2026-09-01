"""Atomic application/persistence contracts for Story 3.2."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from autotrade_next.adapters.sqlite.fenced_journal import (
    AuthorityClaim,
    ClaimStatus,
    IndeterminateCommit,
    SQLiteFencedJournal,
)
from autotrade_next.application.portfolio_allocation import (
    AllocatePortfolioCommand,
    allocate_portfolio,
)
from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.portfolio_allocation import (
    AllocationProposal,
    ConstituentCheckpoint,
    PortfolioConsistencyCut,
    ReservationBucket,
    ReservationVector,
    RiskReservation,
)
from autotrade_next.ports.portfolio_allocation import (
    AllocationCommitStatus,
    AllocationContentRecord,
)


NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


class ManualClock:
    def __init__(self, current: datetime = NOW) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def ref(kind: str, value: str) -> ContentRef:
    return ContentRef.v2("autotrade-next", kind, {"value": value})


def bucket(initial: int) -> ReservationBucket:
    return ReservationBucket(
        ScaledInteger(initial, 2), ScaledInteger(0, 2),
        ScaledInteger(initial, 2), ScaledInteger(0, 2),
    )


def proposal(pair: str, horizon: str, reservation_id: str) -> AllocationProposal:
    return AllocationProposal(
        decision_ref=ref("Decision", reservation_id),
        pair_id=pair,
        instrument_id=pair,
        horizon=horizon,
        risk_increasing=True,
        reservation=RiskReservation(
            reservation_id, pair, pair, horizon,
            ReservationVector(
                bucket(4_000), bucket(200), bucket(40), bucket(60), bucket(4_000),
            ),
        ),
    )


def checkpoints() -> tuple[ConstituentCheckpoint, ...]:
    return (
        ConstituentCheckpoint(
            "opportunity-set", "portfolio", 1, ref("OpportunitySet", "frozen"),
        ),
        ConstituentCheckpoint(
            "market-cutoff", "portfolio", 1, ref("MarketCutoff", "t0"),
        ),
        ConstituentCheckpoint(
            "journal-high-water", "portfolio", 91,
            ContentRef.v2("autotrade-next", "JournalHighWater", {"sequence": 91}),
        ),
        ConstituentCheckpoint("positions", "portfolio", 7, ref("Positions", "7")),
        ConstituentCheckpoint("working-orders", "portfolio", 3, ref("Orders", "3")),
        ConstituentCheckpoint("risk-state", "portfolio", 11, ref("RiskState", "11")),
    )


def cut() -> PortfolioConsistencyCut:
    return PortfolioConsistencyCut(
        NOW,
        ScaledInteger(10_000, 2),
        ref("OpportunitySet", "frozen"),
        ref("MarketCutoff", "t0"),
        91,
        ref("Positions", "7"),
        ref("Orders", "3"),
        ref("RiskState", "11"),
        checkpoints(),
    )


def command(
    *,
    epoch: int = 1,
    token: str = "token-1",
    observed: tuple[ConstituentCheckpoint, ...] | None = None,
) -> AllocatePortfolioCommand:
    btc = proposal("BTC-IDR", "H1", "res-btc")
    eth = proposal("ETH-IDR", "H4", "res-eth")
    risk_value = {"value": "12"}
    return AllocatePortfolioCommand(
        authority_scope_id="global-writer",
        writer_epoch=epoch,
        lease_token=token,
        aggregate_id="portfolio-1",
        consistency_cut=cut(),
        proposals=(eth, btc),
        observed_constituents=checkpoints() if observed is None else observed,
        expected_sequence=0,
        decisions=(
            AllocationContentRecord(btc.decision_ref, {"value": "res-btc"}),
            AllocationContentRecord(eth.decision_ref, {"value": "res-eth"}),
        ),
        next_risk_state=AllocationContentRecord(ref("RiskState", "12"), risk_value),
    )


def store(tmp_path: Path, cls: type[SQLiteFencedJournal] = SQLiteFencedJournal):
    journal = cls(tmp_path / "journal.sqlite3", clock=ManualClock())
    journal.initialize_schema_for_test()
    claim = AuthorityClaim(
        "claim-1", "global-writer", None, "token-1", NOW,
        NOW + timedelta(minutes=5),
    )
    assert journal.claim_authority(claim).status is ClaimStatus.CLAIMED
    return journal


def effect_counts(path: Path) -> tuple[int, ...]:
    tables = (
        "command_journal",
        "canonical_events",
        "pending_outbox",
        "aggregate_high_water",
        "portfolio_allocation_batches",
        "portfolio_allocation_decisions",
        "portfolio_risk_reservations",
        "portfolio_pair_ownership",
        "portfolio_risk_states",
    )
    with sqlite3.connect(path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        )


def test_handler_commits_decisions_reservations_risk_event_and_outbox_in_one_cas(
    tmp_path: Path,
) -> None:
    journal = store(tmp_path)

    result = allocate_portfolio(command(), journal)

    assert result.committed
    assert result.commit is not None
    assert result.commit.status is AllocationCommitStatus.COMMITTED
    assert result.commit.sequence == 1
    assert effect_counts(journal.path) == (1, 1, 1, 1, 1, 2, 2, 2, 1)
    with sqlite3.connect(journal.path) as connection:
        row = connection.execute(
            "SELECT batch_payload, event_payload, outbox_payload "
            "FROM command_journal JOIN portfolio_allocation_batches USING (command_id)"
        ).fetchone()
        assert row is not None
        assert all(type(value) is bytes and value for value in row)


def test_stale_cut_rejects_batch_without_any_persistent_effect(tmp_path: Path) -> None:
    journal = store(tmp_path)
    stale = list(checkpoints())
    stale[2] = ConstituentCheckpoint(
        "journal-high-water", "portfolio", 92,
        ContentRef.v2("autotrade-next", "JournalHighWater", {"sequence": 92}),
    )

    result = allocate_portfolio(command(observed=tuple(stale)), journal)

    assert not result.allocation.executable
    assert result.commit is None
    assert effect_counts(journal.path) == (0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_invalid_fence_writes_no_allocation_effect(tmp_path: Path) -> None:
    journal = store(tmp_path)

    result = allocate_portfolio(command(epoch=2, token="forged"), journal)

    assert not result.committed
    assert result.commit is not None
    assert result.commit.status is AllocationCommitStatus.UNCLAIMED_EPOCH
    assert effect_counts(journal.path) == (0, 0, 0, 0, 0, 0, 0, 0, 0)


class CrashBeforeCommitJournal(SQLiteFencedJournal):
    def _before_commit(self, operation: str, identity: str) -> None:
        if operation == "append":
            raise RuntimeError(f"simulated allocation crash for {identity}")


def test_crash_rolls_back_every_allocation_table(tmp_path: Path) -> None:
    journal = store(tmp_path, CrashBeforeCommitJournal)

    with pytest.raises(RuntimeError, match="simulated allocation crash"):
        allocate_portfolio(command(), journal)

    assert effect_counts(journal.path) == (0, 0, 0, 0, 0, 0, 0, 0, 0)


class CommitThenRaiseJournal(SQLiteFencedJournal):
    def _commit(self, connection: sqlite3.Connection) -> None:
        super()._commit(connection)
        raise IndeterminateCommit("commit return lost")


def test_indeterminate_commit_reconciles_and_retry_is_idempotent(tmp_path: Path) -> None:
    healthy = store(tmp_path)
    uncertain = CommitThenRaiseJournal(healthy.path, clock=ManualClock())

    first = allocate_portfolio(command(), uncertain)
    retry = allocate_portfolio(command(), healthy)

    assert first.commit is not None
    assert first.commit.status is AllocationCommitStatus.COMMITTED_AFTER_INDETERMINATE
    assert retry.commit is not None
    assert retry.commit.status is AllocationCommitStatus.IDEMPOTENT
    assert effect_counts(uncertain.path) == (1, 1, 1, 1, 1, 2, 2, 2, 1)


def test_content_records_reject_self_attested_payloads() -> None:
    decision_ref = ref("Decision", "res-btc")
    with pytest.raises(TypeError, match="ALLOCATION_CONTENT_REFERENCE_MISMATCH"):
        AllocationContentRecord(decision_ref, {"value": "forged"})
