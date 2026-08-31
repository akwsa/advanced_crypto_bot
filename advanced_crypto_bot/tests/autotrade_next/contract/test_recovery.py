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
from autotrade_next.domain.content import ContentRef
from autotrade_next.domain.identity import build_identity
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.policy import GapBehavior, PolicyState, build_margin_ref
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


def policy_state():
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


def position():
    state_ref = ContentRef.v1(
        "policy-state", policy_state().to_canonical_value(),
    ).key
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
        policy_state_ref=state_ref, partial_exit=False,
        pending_exit_key=None, pending_exit_sequence=None, pending_order_id=None,
        pending_reason=None,
        pending_target_quantity=None, processed_exit_fill_ids=(), dust_incident=None,
    )


def pending_position(*, reason=ExitReason.STOP_LOSS,
                     target=amount(1000, 4)):
    state = position()
    sequence = state.sequence + 1
    exit_key = build_identity("event", {
        "authority_scope_id": state.authority_scope_id,
        "aggregate_id": state.position_id,
        "aggregate_seq": sequence,
        "event_type": "ExitRequested",
        "schema_version": 1,
    }).key
    intent_id = build_identity("intent", {"decision_id": exit_key})
    order_id = build_identity("client_order", {
        "authority_scope_id": state.authority_scope_id,
        "intent_id": intent_id.key,
        "order_ordinal": 0,
    }).key
    return replace(
        state,
        sequence=sequence,
        status=PositionProtectionStatus.EXIT_PENDING,
        pending_exit_key=exit_key,
        pending_exit_sequence=sequence,
        pending_order_id=order_id,
        pending_reason=reason,
        pending_target_quantity=target,
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
        account_snapshot=account(), settlement_entries=(),
        order_states=(order_state,), positions=(position(),),
        policy_states=(policy_state(),), preparations=(prepared,),
        pending_command_refs=("command:exit:1",),
        inbox_ids=("inbox:1",), applied_correction_refs=(),
        outbox=(prepared.outbox,),
        projection_high_waters=(ProjectionHighWater("dashboard", 22),),
        entry_frozen=entry_frozen or unknown,
        unknown_deadline_utc=AT + timedelta(seconds=60) if unknown else None,
        captured_at_utc=AT,
    )


def rebuild_checkpoint(state, **changes):
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
    assert result.redeliver_message_ids == ()
    assert result.entry_frozen is True


def test_authoritative_query_result_resolves_unknown_without_redispatch():
    state = checkpoint(unknown=True)
    order_id = state.order_states[0].order.order_id.key
    evidence = VenueOrderEvidence(
        order_id, OrderStatus.FILLED, "venue-evidence:fill:resolved", AT,
    )
    correction = CorrectionRequest(
        CorrectionKind.ORDER_STATE_CORRECTION,
        order_id,
        evidence.evidence_ref,
        "approval:operator:resolved",
        state.journal_high_water,
        "correction:idempotency:resolved",
    )

    result = plan_recovery(
        state, venue_evidence=(evidence,), corrections=(correction,),
    )

    assert result.query_order_ids == ()
    assert result.mismatch_order_ids == (order_id,)
    assert RecoveryAction.QUERY_VENUE not in result.actions
    assert RecoveryAction.APPLY_CORRECTION in result.actions
    assert result.redeliver_message_ids == result.redispatch_order_ids == ()


def test_already_acknowledged_order_never_redelivers_initial_submit():
    state = checkpoint()
    prepared = state.preparations[0]
    acknowledged = settle_event(
        state.order_states[0],
        state.account_snapshot,
        event(prepared.order.order_id.key, 1, OrderStatus.ACCEPTED),
    ).order_state
    recovered = rebuild_checkpoint(state, order_states=(acknowledged,))

    result = plan_recovery(recovered, venue_evidence=(), corrections=())

    assert result.actions == (RecoveryAction.NO_ACTION,)
    assert result.redeliver_message_ids == ()


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


def test_plan_identity_binds_and_canonicalizes_venue_evidence():
    state = checkpoint()
    order_id = state.order_states[0].order.order_id.key
    filled = VenueOrderEvidence(
        order_id, OrderStatus.FILLED, "venue-evidence:filled", AT,
    )
    rejected = VenueOrderEvidence(
        order_id, OrderStatus.REJECTED, "venue-evidence:rejected", AT,
    )

    filled_plan = plan_recovery(
        state, venue_evidence=(filled,), corrections=(),
    )
    rejected_plan = plan_recovery(
        state, venue_evidence=(rejected,), corrections=(),
    )

    assert filled_plan.plan_ref != rejected_plan.plan_ref
    assert filled_plan.venue_evidence == (filled,)


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
            settlement_entries=state.settlement_entries,
            order_states=(state.order_states[0], state.order_states[0]),
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

    with pytest.raises(RecoveryError, match="UNKNOWN_NOT_FROZEN"):
        replace(checkpoint(unknown=True), entry_frozen=False)


def test_checkpoint_binds_complete_pending_position_state():
    state = checkpoint()
    first = rebuild_checkpoint(state, positions=(pending_position(),))
    second = rebuild_checkpoint(
        state,
        positions=(pending_position(
            reason=ExitReason.TAKE_PROFIT,
            target=amount(500, 4),
        ),),
    )

    assert first.checkpoint_ref != second.checkpoint_ref
    value = first.binding_value()["positions"][0]
    assert value["pending_reason"] == ExitReason.STOP_LOSS.value
    assert value["pending_target_quantity"] == {"units": 1000, "scale": 4}


def test_checkpoint_rejects_cross_account_state_and_ahead_of_journal_state():
    state = checkpoint()
    with pytest.raises(RecoveryError, match="RECOVERY_ACCOUNT_MISMATCH"):
        rebuild_checkpoint(
            state,
            account_snapshot=replace(
                state.account_snapshot,
                account_id="account:foreign",
            ),
        )
    with pytest.raises(RecoveryError, match="STATE_AHEAD_OF_JOURNAL"):
        rebuild_checkpoint(
            state,
            journal_high_water=0,
            projection_high_waters=(),
        )


def test_recovery_rejects_foreign_correction_targets():
    request = CorrectionRequest(
        CorrectionKind.FORCED_CLOSE_REQUEST,
        "position:foreign",
        "evidence:1",
        "approval:1",
        22,
        "idempotency:foreign",
    )
    with pytest.raises(RecoveryError, match="FOREIGN_CORRECTION_TARGET"):
        plan_recovery(checkpoint(), venue_evidence=(), corrections=(request,))


def test_public_plan_constructor_rejects_semantically_inconsistent_actions():
    state = checkpoint()
    values = {
        "schema_version": "recovery-plan:v2",
        "checkpoint_ref": state.checkpoint_ref.key,
        "actions": (RecoveryAction.NO_ACTION.value,),
        "query_order_ids": (state.order_states[0].order.order_id.key,),
        "mismatch_order_ids": (),
        "redispatch_order_ids": (),
        "redeliver_message_ids": (),
        "venue_evidence": (),
        "corrections": (),
        "entry_frozen": False,
        "no_strategy_evaluation": True,
    }
    with pytest.raises(RecoveryError, match="INVALID_RECOVERY_PLAN"):
        from autotrade_next.domain.recovery import RecoveryPlan
        RecoveryPlan(
            state.checkpoint_ref,
            (RecoveryAction.NO_ACTION,),
            (state.order_states[0].order.order_id.key,),
            (),
            (),
            (),
            (),
            (),
            False,
            True,
            ContentRef.v2("recovery.plan", "recovery-plan", values),
        )
