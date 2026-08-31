"""Story 2.6 deterministic lifecycle recovery contracts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from autotrade_next.domain.execution import (
    AccountState, ExecutionSide, prepare_execution, settle_event,
)
from autotrade_next.domain.exit_protection import (
    ExitReason, PositionProtectionState, PositionProtectionStatus, ProtectionState,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.recovery import (
    CorrectionKind,
    CorrectionRequest,
    ProjectionHighWater,
    RecoveryAction,
    RecoveryCheckpoint,
    RecoveryError,
    VenueOrderEvidence,
    plan_recovery,
)
from autotrade_next.domain.simulator import OrderStatus, SimulatorEvent


AT = datetime(2026, 8, 30, 13, 0, tzinfo=UTC)


def amount(units, scale):
    return ScaledInteger(units, scale)


def account():
    return AccountState(
        "account:primary", "BTCIDR", amount(100000, 2), amount(10000, 4),
        amount(0, 2), amount(0, 2), (), 0,
    )


def preparation():
    return prepare_execution(
        decision_id="event:v1:" + "1" * 64,
        authority_scope_id="dryrun:primary", account_id="account:primary",
        instrument_id="BTCIDR", side=ExecutionSide.SELL,
        requested_quantity=amount(10000, 4), order_ordinal=0,
        created_at_utc=AT,
    )


def event(order_id, sequence, status):
    return SimulatorEvent.create(
        event_id=f"venue:{sequence}", order_id=order_id, status=status,
        filled_quantity=amount(0, 4), remaining_quantity=amount(10000, 4),
        average_price=amount(0, 2), fills=(), event_at_utc=AT, sequence=sequence,
    )


def position():
    return PositionProtectionState(
        position_id="position:btc:1", authority_scope_id="dryrun:primary",
        account_id="account:primary", instrument_id="BTCIDR",
        entry_price=amount(5000, 2), entered_at_utc=AT - timedelta(days=1),
        last_evaluated_at_utc=AT - timedelta(minutes=1),
        remaining_quantity=amount(10000, 4), sequence=7,
        status=PositionProtectionStatus.ACTIVE,
        protection=ProtectionState(
            amount(4500, 2), amount(5500, 2), amount(5000, 2),
            AT + timedelta(hours=2), amount(500, 2), "invalidation:v1",
        ),
        policy_state_ref="policy-state:v1:abc", partial_exit=False,
        pending_exit_key=None, pending_exit_sequence=None, pending_order_id=None,
        pending_reason=None,
        pending_target_quantity=None, processed_exit_fill_ids=(), dust_incident=None,
    )


def checkpoint(*, unknown=False, entry_frozen=False):
    prepared = preparation()
    order_state = prepared.order_state
    if unknown:
        order_state = settle_event(
            order_state, account(), event(prepared.order.order_id.key, 1,
                                          OrderStatus.ACCEPTED)
        ).order_state
        order_state = settle_event(
            order_state, account(), event(prepared.order.order_id.key, 2,
                                          OrderStatus.UNKNOWN)
        ).order_state
    return RecoveryCheckpoint.create(
        authority_scope_id="dryrun:primary", journal_high_water=22,
        account_snapshot=account(), order_states=(order_state,),
        positions=(position(),), preparations=(prepared,),
        pending_command_refs=("command:exit:1",),
        inbox_ids=("inbox:1",), outbox=(prepared.outbox,),
        projection_high_waters=(ProjectionHighWater("dashboard", 22),),
        entry_frozen=entry_frozen or unknown,
        unknown_deadline_utc=AT + timedelta(seconds=60) if unknown else None,
        captured_at_utc=AT,
    )


def test_clean_checkpoint_recovery_is_deterministic_and_never_evaluates_strategy():
    state = checkpoint()
    first = plan_recovery(state, venue_evidence=(), corrections=())
    second = plan_recovery(state, venue_evidence=(), corrections=())

    assert first == second
    assert first.checkpoint_ref == state.checkpoint_ref
    assert first.no_strategy_evaluation is True
    assert RecoveryAction.REDELIVER_OUTBOX in first.actions
    assert RecoveryAction.RESUME_PENDING_DISPATCH not in first.actions
    assert first.redeliver_message_ids == (state.outbox[0].message_id.key,)
    assert first.redispatch_order_ids == ()
    assert first.plan_ref.verify(first.binding_value())


def test_unknown_is_query_before_resubmit_and_keeps_entry_frozen():
    state = checkpoint(unknown=True)
    order_id = state.order_states[0].order.order_id.key
    result = plan_recovery(state, venue_evidence=(), corrections=())

    assert result.actions[0] is RecoveryAction.QUERY_VENUE
    assert result.query_order_ids == (order_id,)
    assert result.redispatch_order_ids == ()
    assert result.entry_frozen is True


def test_venue_mismatch_freezes_and_only_approved_correction_taxonomy_is_planned():
    state = checkpoint()
    order_id = state.order_states[0].order.order_id.key
    evidence = VenueOrderEvidence(
        order_id, OrderStatus.FILLED, "venue-evidence:fill:1", AT,
    )
    mismatch = plan_recovery(state, venue_evidence=(evidence,), corrections=())
    assert RecoveryAction.FREEZE_ENTRY in mismatch.actions
    assert mismatch.entry_frozen is True
    assert mismatch.mismatch_order_ids == (order_id,)

    correction = CorrectionRequest(
        CorrectionKind.ORDER_STATE_CORRECTION, order_id,
        "venue-evidence:fill:1", "approval:operator:1", 22,
        "correction:idempotency:1",
    )
    approved = plan_recovery(
        state, venue_evidence=(evidence,), corrections=(correction,),
    )
    assert RecoveryAction.APPLY_CORRECTION in approved.actions
    assert approved.corrections == (correction,)


@pytest.mark.parametrize("kind", tuple(CorrectionKind))
def test_all_and_only_additive_correction_kinds_require_evidence_approval_and_highwater(kind):
    request = CorrectionRequest(
        kind, "order:1", "evidence:1", "approval:1", 22, "idempotency:1",
    )
    assert request.kind is kind
    with pytest.raises(RecoveryError, match="CORRECTION_HIGH_WATER_CONFLICT"):
        plan_recovery(checkpoint(), venue_evidence=(), corrections=(
            CorrectionRequest(
                kind, "order:1", "evidence:1", "approval:1", 21, "idempotency:2",
            ),
        ))


def test_checkpoint_rejects_duplicate_or_unbound_recovery_state():
    state = checkpoint()
    with pytest.raises(RecoveryError, match="DUPLICATE_RECOVERY_ORDER"):
        RecoveryCheckpoint.create(
            authority_scope_id=state.authority_scope_id,
            journal_high_water=state.journal_high_water,
            account_snapshot=state.account_snapshot,
            order_states=(state.order_states[0], state.order_states[0]),
            positions=state.positions, preparations=state.preparations,
            pending_command_refs=state.pending_command_refs,
            inbox_ids=state.inbox_ids, outbox=state.outbox,
            projection_high_waters=state.projection_high_waters,
            entry_frozen=state.entry_frozen,
            unknown_deadline_utc=state.unknown_deadline_utc,
            captured_at_utc=state.captured_at_utc,
        )

    with pytest.raises(RecoveryError, match="UNKNOWN_NOT_FROZEN"):
        replace(checkpoint(unknown=True), entry_frozen=False)
