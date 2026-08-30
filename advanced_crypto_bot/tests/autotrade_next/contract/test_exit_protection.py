"""Story 2.5 unified protective EXIT contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from autotrade_next.application.exit import EvaluateExitCommand, prepare_protective_exit
from autotrade_next.domain.execution import ExecutionSide, SettlementEntry
from autotrade_next.domain.exit_protection import (
    ExitError,
    ExitReason,
    ExitSignals,
    PositionProtectionState,
    PositionProtectionStatus,
    ProtectionState,
    apply_exit_fill,
    build_exit_execution,
    evaluate_exit,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.ports.exit import ExitCommitBundle


AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def amount(units: int, scale: int) -> ScaledInteger:
    return ScaledInteger(units, scale)


def protection() -> ProtectionState:
    return ProtectionState(
        stop_loss_price=amount(450, 1),
        take_profit_price=amount(5500, 2),
        trailing_high_water=amount(5000, 2),
        expiration_at_utc=AT + timedelta(hours=2),
        trailing_distance=amount(500, 2),
        invalidation_ref="invalidation-rule:v1",
    )


def position(*, quantity=amount(10000, 4), sequence=4,
             status=None, pending_target=None) -> PositionProtectionState:
    return PositionProtectionState(
        position_id="position:btc:1",
        authority_scope_id="dryrun:primary",
        account_id="account:primary",
        instrument_id="BTCIDR",
        entry_price=amount(5000, 2),
        entered_at_utc=AT - timedelta(days=1),
        last_evaluated_at_utc=AT - timedelta(minutes=1),
        remaining_quantity=quantity,
        sequence=sequence,
        status=status or PositionProtectionStatus.ACTIVE,
        protection=protection(),
        policy_state_ref="policy-state:v1:abc",
        partial_exit=False,
        pending_exit_key=("event:v1:" + "a" * 64) if pending_target else None,
        pending_order_id="client_order:v1:" + "b" * 64 if pending_target else None,
        pending_reason=ExitReason.STOP_LOSS if pending_target else None,
        pending_target_quantity=pending_target,
        processed_exit_fill_ids=(),
        dust_incident=None,
    )


def signals(**changes) -> ExitSignals:
    values = {
        "operator_evidence_ref": None,
        "hard_drawdown_evidence_ref": None,
        "invalidation_evidence_ref": None,
        "reconciliation_evidence_ref": None,
        "alpha_exit_evidence_ref": None,
        "profit_target_quantity": None,
        "minimum_venue_quantity": amount(100, 4),
        "position_valuation": amount(5000, 2),
        "valuation_evidence_ref": "valuation:l2:1",
    }
    values.update(changes)
    return ExitSignals(**values)


def entry(fill_id: str, quantity: ScaledInteger, order_id: str) -> SettlementEntry:
    return SettlementEntry(
        "dryrun:primary", "account:primary", "BTCIDR", order_id,
        "event:fill:1", ExecutionSide.SELL, fill_id, quantity,
        amount(10000, 2), amount(10, 2), amount(5, 2),
        amount(9985, 2), ScaledInteger(-quantity.units, quantity.scale), AT,
    )


def test_mixed_scale_stop_and_fixed_precedence_are_deterministic():
    state = position()
    result = evaluate_exit(
        state, current_price=amount(4400, 2), evaluated_at_utc=AT,
        signals=signals(alpha_exit_evidence_ref="alpha:1"),
    )
    assert result.should_exit is True
    assert result.reason is ExitReason.STOP_LOSS
    assert result.target_quantity == state.remaining_quantity
    assert result.expected_sequence == 4
    assert result.next_state.sequence == 5
    assert result.event_id.key.startswith("event:v1:")
    assert result.event_ref.verify(result.binding_value())

    highest = evaluate_exit(
        state, current_price=amount(6000, 2), evaluated_at_utc=AT + timedelta(hours=3),
        signals=signals(
            operator_evidence_ref="approval:operator:1",
            hard_drawdown_evidence_ref="risk:drawdown:1",
            invalidation_evidence_ref="invalid:1",
            reconciliation_evidence_ref="reconcile:1",
            alpha_exit_evidence_ref="alpha:1",
        ),
    )
    assert highest.reason is ExitReason.OPERATOR_EXIT


@pytest.mark.parametrize(
    ("changes", "price", "at", "reason"),
    [
        ({"hard_drawdown_evidence_ref": "risk:drawdown:1"}, amount(5000, 2), AT,
         ExitReason.HARD_DRAWDOWN),
        ({"invalidation_evidence_ref": "invalid:1"}, amount(5000, 2), AT,
         ExitReason.INVALIDATION),
        ({"reconciliation_evidence_ref": "reconcile:1"}, amount(5000, 2), AT,
         ExitReason.RECONCILIATION),
        ({}, amount(5600, 2), AT, ExitReason.TAKE_PROFIT),
        ({}, amount(4499, 2), AT, ExitReason.STOP_LOSS),
        ({"alpha_exit_evidence_ref": "alpha:1"}, amount(5000, 2), AT,
         ExitReason.ALPHA_EXIT),
        ({}, amount(5000, 2), AT + timedelta(hours=3), ExitReason.TIME_EXPIRY),
    ],
)
def test_every_exit_family_uses_one_evaluator(changes, price, at, reason):
    assert evaluate_exit(position(), current_price=price, evaluated_at_utc=at,
                         signals=signals(**changes)).reason is reason


def test_high_water_advances_without_exit_and_partial_profit_has_explicit_target():
    observed = evaluate_exit(
        position(), current_price=amount(5300, 2), evaluated_at_utc=AT,
        signals=signals(),
    )
    assert observed.should_exit is False
    assert observed.reason is ExitReason.NO_EXIT
    assert observed.next_state.protection.trailing_high_water == amount(5300, 2)
    assert observed.next_state.sequence == 5

    partial = evaluate_exit(
        position(), current_price=amount(5600, 2), evaluated_at_utc=AT,
        signals=signals(profit_target_quantity=amount(2500, 4)),
    )
    assert partial.reason is ExitReason.TAKE_PROFIT
    assert partial.target_quantity == amount(2500, 4)
    assert partial.next_state.pending_target_quantity == amount(2500, 4)


def test_trailing_transition_time_monotonicity_and_protection_ranges_fail_closed():
    trailing = replace(
        position(),
        protection=ProtectionState(
            stop_loss_price=amount(4000, 2),
            take_profit_price=amount(6000, 2),
            trailing_high_water=amount(5000, 2),
            expiration_at_utc=AT + timedelta(hours=2),
            trailing_distance=amount(500, 2),
            invalidation_ref="invalidation-rule:v1",
        ),
    )
    assert evaluate_exit(
        trailing, current_price=amount(4400, 2), evaluated_at_utc=AT,
        signals=signals(),
    ).reason is ExitReason.TRAILING_STOP

    with pytest.raises(ExitError, match="EXIT_TIME_REGRESSION"):
        evaluate_exit(
            position(), current_price=amount(5000, 2),
            evaluated_at_utc=AT - timedelta(minutes=2), signals=signals(),
        )
    with pytest.raises(ExitError, match="INVALID_PROTECTION_RANGE"):
        ProtectionState(
            amount(6000, 2), amount(5500, 2), None, None,
        )


def test_exit_builds_story_24_sell_execution_from_deterministic_event():
    evaluated = evaluate_exit(
        position(), current_price=amount(4400, 2), evaluated_at_utc=AT,
        signals=signals(),
    )
    prepared = build_exit_execution(evaluated, created_at_utc=AT)
    assert prepared.intent.decision_id == evaluated.event_id.key
    assert prepared.order.side is ExecutionSide.SELL
    assert prepared.order.requested_quantity == evaluated.target_quantity
    assert prepared.intent.account_id == evaluated.next_state.account_id


class MemoryExitUnitOfWork:
    def __init__(self, state: PositionProtectionState, *, fail_commit=False):
        self.state = state
        self.fail_commit = fail_commit
        self.commits = {}
        self.outbox = []
        self._staged = None
        self.rollback_count = 0
        self.close_count = 0

    def get_position(self, position_id):
        return self.state if self.state.position_id == position_id else None

    def get_exit_commit(self, command_ref):
        return self.commits.get(command_ref.key)

    def stage_exit(self, bundle):
        self._staged = bundle

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("injected exit commit fault")
        bundle = self._staged
        if self.state.sequence != bundle.expected_sequence:
            raise RuntimeError("stale position sequence")
        self.state = bundle.evaluation.next_state
        self.commits[bundle.command_ref.key] = bundle
        self.outbox.append(bundle.evaluation.outbox)
        if bundle.execution is not None:
            self.outbox.append(bundle.execution.outbox)
        self._staged = None

    def rollback(self):
        self._staged = None
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def command(**changes) -> EvaluateExitCommand:
    values = {
        "position_id": "position:btc:1",
        "expected_sequence": 4,
        "current_price": amount(4400, 2),
        "evaluated_at_utc": AT,
        "signals": signals(),
    }
    values.update(changes)
    return EvaluateExitCommand(**values)


def test_atomic_commit_precedes_dispatch_and_exact_retry_is_idempotent():
    uow = MemoryExitUnitOfWork(position())
    first = prepare_protective_exit(command(), uow)
    assert first.dispatch is not None
    assert first.dispatch.order_id.startswith("client_order:v1:")
    assert len(uow.outbox) == 2

    retry = prepare_protective_exit(command(), uow)
    assert retry == first
    assert len(uow.outbox) == 2

    failed = MemoryExitUnitOfWork(position(), fail_commit=True)
    with pytest.raises(RuntimeError, match="injected exit commit fault"):
        prepare_protective_exit(command(), failed)
    assert failed.state == position()
    assert failed.outbox == []
    assert failed.rollback_count == 1
    assert failed.close_count == 1


def test_partial_exit_fill_preserves_protection_then_full_fill_closes_exactly_once():
    evaluated = evaluate_exit(
        position(), current_price=amount(4400, 2), evaluated_at_utc=AT,
        signals=signals(),
    )
    first = apply_exit_fill(
        evaluated.next_state, entry(
            "exit-fill-1", amount(4000, 4), evaluated.next_state.pending_order_id
        ),
        minimum_venue_quantity=amount(100, 4), valuation=amount(2640, 2),
        valuation_evidence_ref="valuation:l2:fill-1",
        recorded_at_utc=AT,
    )
    assert first.next_state.remaining_quantity == amount(6000, 4)
    assert first.next_state.status is PositionProtectionStatus.EXIT_PENDING
    assert first.next_state.protection == evaluated.next_state.protection
    assert first.next_state.partial_exit is True

    second = apply_exit_fill(
        first.next_state, entry(
            "exit-fill-2", amount(6000, 4), first.next_state.pending_order_id
        ),
        minimum_venue_quantity=amount(100, 4), valuation=amount(0, 2),
        valuation_evidence_ref="valuation:l2:fill-2",
        recorded_at_utc=AT,
    )
    assert second.next_state.remaining_quantity == amount(0, 4)
    assert second.next_state.status is PositionProtectionStatus.CLOSED
    with pytest.raises(ExitError, match="POSITION_NOT_EXITABLE"):
        apply_exit_fill(
            second.next_state, entry("exit-fill-3", amount(1, 4), "order:closed"),
            minimum_venue_quantity=amount(100, 4), valuation=amount(0, 2),
            valuation_evidence_ref="valuation:l2:fill-3",
            recorded_at_utc=AT,
        )


def test_subminimum_remainder_is_quarantined_with_incident_and_valuation():
    evaluated = evaluate_exit(
        position(quantity=amount(1050, 4)), current_price=amount(4400, 2),
        evaluated_at_utc=AT, signals=signals(),
    )
    result = apply_exit_fill(
        evaluated.next_state, entry(
            "dust-fill", amount(1000, 4), evaluated.next_state.pending_order_id
        ),
        minimum_venue_quantity=amount(100, 4), valuation=amount(22, 2),
        valuation_evidence_ref="valuation:l2:dust",
        recorded_at_utc=AT,
    )
    assert result.next_state.remaining_quantity == amount(50, 4)
    assert result.next_state.status is PositionProtectionStatus.QUARANTINED_DUST
    assert result.next_state.status is not PositionProtectionStatus.CLOSED
    assert result.incident is not None
    assert result.incident.valuation == amount(22, 2)
    assert result.incident.incident_ref.verify(result.incident.binding_value())


def test_preexisting_subminimum_position_is_quarantined_before_order_dispatch():
    tiny = position(quantity=amount(50, 4))
    evaluated = evaluate_exit(
        tiny, current_price=amount(4400, 2), evaluated_at_utc=AT,
        signals=signals(position_valuation=amount(22, 2)),
    )
    assert evaluated.reason is ExitReason.STOP_LOSS
    assert evaluated.next_state.status is PositionProtectionStatus.QUARANTINED_DUST
    assert evaluated.next_state.dust_incident is not None
    with pytest.raises(ExitError, match="EXIT_EXECUTION_NOT_REQUIRED"):
        build_exit_execution(evaluated, created_at_utc=AT)

    uow = MemoryExitUnitOfWork(tiny)
    result = prepare_protective_exit(command(
        current_price=amount(4400, 2), signals=signals(position_valuation=amount(22, 2))
    ), uow)
    assert result.dispatch is None
    assert uow.state.status is PositionProtectionStatus.QUARANTINED_DUST
    assert len(uow.outbox) == 1


def test_sequence_scale_overfill_and_cross_aggregate_bundle_fail_closed():
    with pytest.raises(ExitError, match="POSITION_SEQUENCE_CONFLICT"):
        prepare_protective_exit(command(expected_sequence=3), MemoryExitUnitOfWork(position()))

    with pytest.raises(ExitError, match="INVALID_EXIT_SCALE"):
        evaluate_exit(
            position(), current_price=amount(1, 2_048), evaluated_at_utc=AT,
            signals=signals(),
        )

    evaluated = evaluate_exit(
        position(), current_price=amount(4400, 2), evaluated_at_utc=AT,
        signals=signals(),
    )
    with pytest.raises(ExitError, match="EXIT_FILL_OVERFLOW"):
        apply_exit_fill(
            evaluated.next_state, entry(
                "too-much", amount(10001, 4), evaluated.next_state.pending_order_id
            ),
            minimum_venue_quantity=amount(100, 4), valuation=amount(0, 2),
            valuation_evidence_ref="valuation:l2:overflow",
            recorded_at_utc=AT,
        )

    execution = build_exit_execution(evaluated, created_at_utc=AT)
    good = ExitCommitBundle.create(command(), evaluated, execution)
    with pytest.raises(TypeError, match="EXIT_COMMIT_MISMATCH"):
        replace(good, expected_sequence=99)
    with pytest.raises(ExitError, match="EXIT_STATE_TRANSITION_MISMATCH"):
        replace(
            evaluated,
            next_state=replace(evaluated.next_state, account_id="account:foreign"),
        )
