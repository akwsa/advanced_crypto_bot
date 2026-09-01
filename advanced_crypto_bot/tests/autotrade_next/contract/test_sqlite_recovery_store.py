"""Crash/restart contracts for Story 2.6 durable lifecycle recovery."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from autotrade_next.adapters.sqlite.fenced_journal import (
    AuthorityClaim,
    ClaimStatus,
    SQLiteFencedJournal,
)
from autotrade_next.adapters.sqlite.recovery_store import (
    RecoveryCheckpointCommand,
    RecoveryCommitStatus,
    RecoveryIndeterminateCommit,
    RecoveryPersistenceError,
    SQLiteRecoveryStore,
    decode_recovery_checkpoint,
    encode_recovery_checkpoint,
)
from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.execution import (
    AccountState,
    ExecutionSide,
    prepare_execution,
    settle_event,
)
from autotrade_next.domain.exit_protection import (
    PositionProtectionState,
    PositionProtectionStatus,
    ProtectionState,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.policy import GapBehavior, PolicyState, build_margin_ref
from autotrade_next.domain.recovery import (
    CorrectionKind,
    CorrectionRequest,
    ProjectionHighWater,
    RecoveryAction,
    RecoveryCheckpoint,
)
from autotrade_next.domain.simulator import (
    FeeType,
    OrderStatus,
    SimulatedFill,
    SimulatorEvent,
)


AT = datetime(2026, 8, 31, 5, 0, tzinfo=UTC)
SCOPE = "dryrun:primary"


def amount(units: int, scale: int) -> ScaledInteger:
    return ScaledInteger(units, scale)


def policy() -> PolicyState:
    margin = amount(50, 6)
    return PolicyState(
        policy_version="policy:v1", boundary_version="boundary:v1",
        instrument_id="BTCIDR", horizon_id="1H", required_margin=margin,
        margin_ref=build_margin_ref("policy:v1", "boundary:v1", margin),
        enter_confirmations=0, alpha_exit_confirmations=0,
        last_enter_candidate_ref=None, last_enter_input_ref=None,
        last_enter_completed=False, last_alpha_exit_candidate_ref=None,
        last_alpha_exit_input_ref=None, last_alpha_exit_completed=False,
        enter_required=2, protective_exit_required=1, alpha_exit_required=2,
        gap_behavior=GapBehavior.RESET_ENTER_ONLY,
        high_water_ref="high-water:1", protection_ref="protection:1",
    )


def checkpoint(*, high_water: int = 22, pending_outbox: bool = True,
               inbox_ids: tuple[str, ...] = ("inbox:1",),
               applied_correction_refs: tuple[str, ...] = (),
               unknown: bool = False,
               captured_at: datetime = AT) -> RecoveryCheckpoint:
    prepared = prepare_execution(
        decision_id="event:v1:" + "1" * 64,
        authority_scope_id=SCOPE, account_id="account:primary",
        instrument_id="BTCIDR", side=ExecutionSide.SELL,
        requested_quantity=amount(10000, 4), order_ordinal=0,
        created_at_utc=AT,
    )
    policy_state = policy()
    policy_ref = ContentRef.v1(
        "policy-state", policy_state.to_canonical_value(),
    ).key
    order_state = prepared.order_state
    if unknown:
        accepted = SimulatorEvent.create(
            event_id="venue:accepted", order_id=prepared.order.order_id.key,
            status=OrderStatus.ACCEPTED,
            filled_quantity=amount(0, 4), remaining_quantity=amount(10000, 4),
            average_price=amount(0, 2), fills=(), event_at_utc=AT, sequence=1,
        )
        ambiguous = SimulatorEvent.create(
            event_id="venue:unknown", order_id=prepared.order.order_id.key,
            status=OrderStatus.UNKNOWN,
            filled_quantity=amount(0, 4), remaining_quantity=amount(10000, 4),
            average_price=amount(0, 2), fills=(), event_at_utc=AT, sequence=2,
        )
        accepted_result = settle_event(
            order_state,
            AccountState(
                "account:primary", "BTCIDR", amount(100000, 2),
                amount(10000, 4), amount(0, 2), amount(0, 2), (), 0,
            ),
            accepted,
        )
        order_state = settle_event(
            accepted_result.order_state, accepted_result.account, ambiguous,
        ).order_state
    position = PositionProtectionState(
        position_id="position:btc:1", authority_scope_id=SCOPE,
        account_id="account:primary", instrument_id="BTCIDR",
        entry_price=amount(5000, 2), entered_at_utc=AT - timedelta(days=1),
        last_evaluated_at_utc=AT - timedelta(minutes=1),
        remaining_quantity=amount(10000, 4), sequence=7,
        status=PositionProtectionStatus.ACTIVE,
        protection=ProtectionState(
            amount(4500, 2), amount(5500, 2), amount(5000, 2),
            AT + timedelta(hours=2), amount(500, 2), "invalidation:v1",
        ),
        policy_state_ref=policy_ref, partial_exit=False,
        pending_exit_key=None, pending_exit_sequence=None, pending_order_id=None,
        pending_reason=None, pending_target_quantity=None,
        processed_exit_fill_ids=(), dust_incident=None,
    )
    return RecoveryCheckpoint.create(
        authority_scope_id=SCOPE, journal_high_water=high_water,
        account_snapshot=AccountState(
            "account:primary", "BTCIDR", amount(100000, 2),
            amount(10000, 4), amount(0, 2), amount(0, 2), (), 0,
        ),
        settlement_entries=(), order_states=(order_state,),
        positions=(position,), policy_states=(policy_state,),
        preparations=(prepared,), pending_command_refs=("command:exit:1",),
        inbox_ids=inbox_ids,
        applied_correction_refs=applied_correction_refs,
        outbox=(prepared.outbox,) if pending_outbox else (),
        projection_high_waters=(ProjectionHighWater("dashboard", high_water),),
        entry_frozen=unknown,
        unknown_deadline_utc=AT + timedelta(seconds=60) if unknown else None,
        captured_at_utc=captured_at,
    )


def command(state: RecoveryCheckpoint, *, operation_id: str,
            expected: str | None) -> RecoveryCheckpointCommand:
    return RecoveryCheckpointCommand(
        operation_id, SCOPE, 1, "lease:1", AT + timedelta(seconds=10),
        expected, state,
    )


def rebuild(state: RecoveryCheckpoint, **changes) -> RecoveryCheckpoint:
    values = {
        "authority_scope_id": state.authority_scope_id,
        "journal_high_water": state.journal_high_water,
        "account_snapshot": state.account_snapshot,
        "settlement_entries": state.settlement_entries,
        "order_states": state.order_states,
        "positions": state.positions,
        "policy_states": state.policy_states,
        "preparations": state.preparations,
        "pending_command_refs": state.pending_command_refs,
        "inbox_ids": state.inbox_ids,
        "applied_correction_refs": state.applied_correction_refs,
        "outbox": state.outbox,
        "projection_high_waters": state.projection_high_waters,
        "entry_frozen": state.entry_frozen,
        "unknown_deadline_utc": state.unknown_deadline_utc,
        "captured_at_utc": state.captured_at_utc,
    }
    values.update(changes)
    return RecoveryCheckpoint.create(**values)


def stores(tmp_path: Path) -> tuple[SQLiteFencedJournal, SQLiteRecoveryStore]:
    path = tmp_path / "canonical.sqlite3"
    journal = SQLiteFencedJournal(path, clock=lambda: AT)
    journal.initialize_schema_for_test()
    recovery = SQLiteRecoveryStore(path)
    recovery.initialize()
    claim = AuthorityClaim(
        "claim:1", SCOPE, None, "lease:1", AT,
        AT + timedelta(minutes=5),
    )
    assert journal.claim_authority(claim).status is ClaimStatus.CLAIMED
    return journal, recovery


class ApprovalVerifier:
    def __init__(self, allowed_ref: str | None) -> None:
        self.allowed_ref = allowed_ref

    def verify_correction(self, request: CorrectionRequest) -> bool:
        return request.approval_ref == self.allowed_ref


def test_codec_and_process_restart_restore_exact_complete_checkpoint(tmp_path: Path) -> None:
    original = checkpoint()
    assert decode_recovery_checkpoint(encode_recovery_checkpoint(original)) == original
    _, recovery = stores(tmp_path)

    result = recovery.commit_checkpoint(command(
        original, operation_id="recovery:init", expected=None,
    ))
    restarted = SQLiteRecoveryStore(recovery.path)
    restored, plan = restarted.load_recovery_plan(SCOPE)

    assert result.status is RecoveryCommitStatus.COMMITTED
    assert restored == original
    assert restored.account_snapshot == original.account_snapshot
    assert restored.settlement_entries == original.settlement_entries
    assert restored.order_states == original.order_states
    assert restored.positions == original.positions
    assert restored.policy_states == original.policy_states
    assert restored.pending_command_refs == original.pending_command_refs
    assert restored.inbox_ids == original.inbox_ids
    assert restored.outbox == original.outbox
    assert restored.projection_high_waters == original.projection_high_waters
    assert plan.no_strategy_evaluation is True
    assert plan.redeliver_message_ids == (original.outbox[0].message_id.key,)


def test_delivery_ack_checkpoint_survives_restart_without_duplicate_redelivery(
    tmp_path: Path,
) -> None:
    _, recovery = stores(tmp_path)
    first = checkpoint()
    assert recovery.commit_checkpoint(command(
        first, operation_id="recovery:init", expected=None,
    )).status is RecoveryCommitStatus.COMMITTED
    acknowledged = checkpoint(
        high_water=23, pending_outbox=False,
        inbox_ids=("inbox:1", "inbox:delivery-ack"),
        captured_at=AT + timedelta(seconds=1),
    )
    result = recovery.commit_checkpoint(command(
        acknowledged, operation_id="recovery:delivery-ack",
        expected=first.checkpoint_ref.key,
    ))

    restarted = SQLiteRecoveryStore(recovery.path)
    restored, plan = restarted.load_recovery_plan(SCOPE)
    assert result.status is RecoveryCommitStatus.COMMITTED
    assert restored.outbox == ()
    assert restored.preparations == acknowledged.preparations
    assert restored.inbox_ids[-1] == "inbox:delivery-ack"
    assert restored.projection_high_waters[0].sequence == 23
    assert plan.actions == (RecoveryAction.NO_ACTION,)
    assert plan.redeliver_message_ids == ()


def test_unknown_restart_is_query_before_resubmit_and_never_redelivers_submit(
    tmp_path: Path,
) -> None:
    _, recovery = stores(tmp_path)
    ambiguous = checkpoint(unknown=True)
    recovery.commit_checkpoint(command(
        ambiguous, operation_id="recovery:unknown", expected=None,
    ))

    _, plan = SQLiteRecoveryStore(recovery.path).load_recovery_plan(SCOPE)
    assert plan.actions[0] is RecoveryAction.QUERY_VENUE
    assert plan.query_order_ids == (ambiguous.order_states[0].order.order_id.key,)
    assert plan.redeliver_message_ids == ()
    assert plan.redispatch_order_ids == ()
    assert plan.entry_frozen is True
    assert plan.no_strategy_evaluation is True


def test_successor_cannot_rewrite_cash_without_append_only_ledger_evidence(
    tmp_path: Path,
) -> None:
    _, recovery = stores(tmp_path)
    first = checkpoint()
    recovery.commit_checkpoint(command(
        first, operation_id="recovery:init", expected=None,
    ))
    forged = rebuild(
        first,
        journal_high_water=23,
        account_snapshot=replace(
            first.account_snapshot, cash_balance=amount(99999, 2),
        ),
        projection_high_waters=(ProjectionHighWater("dashboard", 23),),
        captured_at_utc=AT + timedelta(seconds=1),
    )

    result = recovery.commit_checkpoint(command(
        forged, operation_id="recovery:forged-cash",
        expected=first.checkpoint_ref.key,
    ))
    assert result.status is RecoveryCommitStatus.HISTORY_CONFLICT
    assert recovery.load_latest(SCOPE) == first


def test_fill_ledger_order_position_and_cash_rehydrate_as_one_consistent_cut(
    tmp_path: Path,
) -> None:
    _, recovery = stores(tmp_path)
    first = checkpoint()
    recovery.commit_checkpoint(command(
        first, operation_id="recovery:init", expected=None,
    ))
    order_id = first.order_states[0].order.order_id.key
    fill = SimulatedFill(
        "fill:venue:1", order_id, amount(5000, 2), amount(1000, 4),
        amount(1, 2), FeeType.TAKER, AT,
        notional=amount(500, 2), tax=amount(0, 2),
    )
    accepted = SimulatorEvent.create(
        event_id="venue:accepted:1", order_id=order_id,
        status=OrderStatus.ACCEPTED,
        filled_quantity=amount(0, 4), remaining_quantity=amount(10000, 4),
        average_price=amount(0, 2), fills=(), event_at_utc=AT, sequence=1,
    )
    opened = SimulatorEvent.create(
        event_id="venue:open:1", order_id=order_id,
        status=OrderStatus.OPEN,
        filled_quantity=amount(0, 4), remaining_quantity=amount(10000, 4),
        average_price=amount(0, 2), fills=(), event_at_utc=AT, sequence=2,
    )
    partial = SimulatorEvent.create(
        event_id="venue:partial:1", order_id=order_id,
        status=OrderStatus.PARTIAL,
        filled_quantity=amount(1000, 4), remaining_quantity=amount(9000, 4),
        average_price=amount(5000, 2), fills=(fill,),
        event_at_utc=AT, sequence=3,
    )
    accepted_result = settle_event(
        first.order_states[0], first.account_snapshot, accepted,
    )
    opened_result = settle_event(
        accepted_result.order_state, accepted_result.account, opened,
    )
    settled = settle_event(
        opened_result.order_state, opened_result.account, partial,
    )
    assert settled.outbox is not None
    filled_state = rebuild(
        first,
        journal_high_water=23,
        account_snapshot=settled.account,
        settlement_entries=settled.entries,
        order_states=(settled.order_state,),
        positions=(replace(
            first.positions[0], remaining_quantity=amount(9000, 4),
        ),),
        outbox=(settled.outbox,),
        projection_high_waters=(ProjectionHighWater("dashboard", 23),),
        captured_at_utc=AT + timedelta(seconds=1),
    )

    result = recovery.commit_checkpoint(command(
        filled_state, operation_id="recovery:fill:1",
        expected=first.checkpoint_ref.key,
    ))
    restored = SQLiteRecoveryStore(recovery.path).load_latest(SCOPE)
    assert result.status is RecoveryCommitStatus.COMMITTED
    assert restored == filled_state
    assert restored.settlement_entries == settled.entries
    assert restored.account_snapshot.cash_balance == amount(100499, 2)
    assert restored.account_snapshot.position_quantity == amount(9000, 4)


def test_correction_requires_external_approval_and_commits_atomically(
    tmp_path: Path,
) -> None:
    _, recovery = stores(tmp_path)
    first = checkpoint()
    recovery.commit_checkpoint(command(
        first, operation_id="recovery:init", expected=None,
    ))
    next_state = checkpoint(
        high_water=23, captured_at=AT + timedelta(seconds=1),
        applied_correction_refs=("correction:idempotency:1",),
    )
    request = CorrectionRequest(
        CorrectionKind.ADJUSTMENT_QUARANTINE, first.account_snapshot.account_id,
        "evidence:reconciliation:1", "approval:operator:1", 22,
        "correction:idempotency:1",
    )
    correction_command = command(
        next_state, operation_id="recovery:correction:1",
        expected=first.checkpoint_ref.key,
    )

    rejected = recovery.commit_correction(
        correction_command, request, venue_evidence=(),
        approval_verifier=ApprovalVerifier(None),
    )
    assert rejected.status is RecoveryCommitStatus.AUTHORIZATION_REJECTED
    assert recovery.load_latest(SCOPE) == first
    bypass = recovery.commit_checkpoint(correction_command)
    assert bypass.status is RecoveryCommitStatus.HISTORY_CONFLICT
    assert recovery.load_latest(SCOPE) == first

    committed = recovery.commit_correction(
        correction_command, request, venue_evidence=(),
        approval_verifier=ApprovalVerifier("approval:operator:1"),
    )
    retry = recovery.commit_correction(
        correction_command, request, venue_evidence=(),
        approval_verifier=ApprovalVerifier(None),
    )
    assert committed.status is RecoveryCommitStatus.COMMITTED
    assert retry.status is RecoveryCommitStatus.IDEMPOTENT
    assert recovery.load_latest(SCOPE) == next_state
    with sqlite3.connect(recovery.path) as connection:
        assert connection.execute(
            "SELECT kind, evidence_ref, approval_ref FROM recovery_corrections"
        ).fetchone() == (
            "ADJUSTMENT_QUARANTINE", "evidence:reconciliation:1",
            "approval:operator:1",
        )


class CrashBeforeCommitStore(SQLiteRecoveryStore):
    def _before_commit(self, operation_id: str) -> None:
        raise RuntimeError(f"crash before commit: {operation_id}")


class CommitThenRaiseStore(SQLiteRecoveryStore):
    def _commit(self, connection: sqlite3.Connection) -> None:
        super()._commit(connection)
        raise RecoveryIndeterminateCommit("commit result lost")


def test_crash_before_delivery_ack_redelivers_same_deterministic_identity(
    tmp_path: Path,
) -> None:
    _, healthy = stores(tmp_path)
    initial = checkpoint()
    healthy.commit_checkpoint(command(
        initial, operation_id="recovery:init", expected=None,
    ))
    acknowledged = checkpoint(
        high_water=23, pending_outbox=False,
        captured_at=AT + timedelta(seconds=1),
    )
    crashing = CrashBeforeCommitStore(healthy.path)
    with pytest.raises(RuntimeError, match="crash before commit"):
        crashing.commit_checkpoint(command(
            acknowledged, operation_id="recovery:ack-crash",
            expected=initial.checkpoint_ref.key,
        ))

    restored, plan = SQLiteRecoveryStore(healthy.path).load_recovery_plan(SCOPE)
    assert restored == initial
    assert plan.redeliver_message_ids == (initial.outbox[0].message_id.key,)
    assert restored.order_states[0].order.order_id == initial.order_states[0].order.order_id


def test_crash_boundaries_are_atomic_and_indeterminate_commit_reconciles(
    tmp_path: Path,
) -> None:
    _, healthy = stores(tmp_path)
    state = checkpoint()
    crashing = CrashBeforeCommitStore(healthy.path)
    with pytest.raises(RuntimeError, match="crash before commit"):
        crashing.commit_checkpoint(command(
            state, operation_id="recovery:crash", expected=None,
        ))
    assert healthy.load_latest(SCOPE) is None

    uncertain = CommitThenRaiseStore(healthy.path)
    result = uncertain.commit_checkpoint(command(
        state, operation_id="recovery:uncertain", expected=None,
    ))
    assert result.status is RecoveryCommitStatus.COMMITTED_AFTER_INDETERMINATE
    assert healthy.load_latest(SCOPE) == state


def test_corrupt_snapshot_fails_closed_instead_of_loading_partial_state(
    tmp_path: Path,
) -> None:
    _, recovery = stores(tmp_path)
    state = checkpoint()
    recovery.commit_checkpoint(command(
        state, operation_id="recovery:init", expected=None,
    ))
    with sqlite3.connect(recovery.path) as connection:
        connection.execute(
            "UPDATE recovery_snapshots SET payload = ?",
            (b'{"schema_version":"recovery-snapshot:v1"}',),
        )
    with pytest.raises(RecoveryPersistenceError, match="RECOVERY_SNAPSHOT_CORRUPT"):
        recovery.load_latest(SCOPE)


def test_checkpoint_identity_binds_policy_state_cash_ledger_and_delivery_state() -> None:
    state = checkpoint()
    changed_policy = replace(
        state.policy_states[0], high_water_ref="high-water:changed",
    )
    with pytest.raises(ValueError, match="RECOVERY_POLICY_STATE_MISMATCH"):
        RecoveryCheckpoint.create(
            authority_scope_id=state.authority_scope_id,
            journal_high_water=state.journal_high_water,
            account_snapshot=state.account_snapshot,
            settlement_entries=state.settlement_entries,
            order_states=state.order_states, positions=state.positions,
            policy_states=(changed_policy,), preparations=state.preparations,
            pending_command_refs=state.pending_command_refs,
            inbox_ids=state.inbox_ids,
            applied_correction_refs=state.applied_correction_refs,
            outbox=state.outbox,
            projection_high_waters=state.projection_high_waters,
            entry_frozen=state.entry_frozen,
            unknown_deadline_utc=state.unknown_deadline_utc,
            captured_at_utc=state.captured_at_utc,
        )

    invalid_account = replace(
        state.account_snapshot, processed_fill_ids=("fill:missing-ledger",),
    )
    with pytest.raises(ValueError, match="RECOVERY_CASH_LEDGER_MISMATCH"):
        RecoveryCheckpoint.create(
            authority_scope_id=state.authority_scope_id,
            journal_high_water=state.journal_high_water,
            account_snapshot=invalid_account,
            settlement_entries=(), order_states=state.order_states,
            positions=state.positions, policy_states=state.policy_states,
            preparations=state.preparations,
            pending_command_refs=state.pending_command_refs,
            inbox_ids=state.inbox_ids,
            applied_correction_refs=state.applied_correction_refs,
            outbox=state.outbox,
            projection_high_waters=state.projection_high_waters,
            entry_frozen=state.entry_frozen,
            unknown_deadline_utc=state.unknown_deadline_utc,
            captured_at_utc=state.captured_at_utc,
        )
