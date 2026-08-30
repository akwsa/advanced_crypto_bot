from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from autotrade_next.application.settlement import (
    PrepareExecutionCommand,
    SettleLifecycleCommand,
    prepare_before_dispatch,
    settle_lifecycle_event,
)
from autotrade_next.domain.execution import (
    AccountState,
    ExecutionError,
    ExecutionPreparation,
    ExecutionSide,
    OrderSettlementState,
    OutboxStatus,
    prepare_execution,
    settle_event,
)
from autotrade_next.domain.market import (
    InstrumentRules,
    MarketQuality,
    MarketSnapshot,
    OrderBookLevel,
    OrderBookSide,
    UniverseMembership,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.simulator import (
    CostRules,
    FeeType,
    LifecycleScenario,
    OrderSimulator,
    OrderStatus,
    ScenarioOutcome,
    SimulatedFill,
    SimulatorEvent,
)
from autotrade_next.ports.settlement import (
    PreparationCommitBundle,
    SettlementCommitBundle,
)


AT = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


def amount(units: int, scale: int) -> ScaledInteger:
    return ScaledInteger(units, scale)


def fill(
    fill_id: str,
    order_id: str,
    *,
    quantity: ScaledInteger,
    price: ScaledInteger,
    fee: ScaledInteger,
    tax: ScaledInteger,
    notional: ScaledInteger | None = None,
) -> SimulatedFill:
    return SimulatedFill(
        fill_id=fill_id,
        order_id=order_id,
        price=price,
        quantity=quantity,
        fee=fee,
        fee_type=FeeType.TAKER,
        filled_at_utc=AT,
        notional=(notional or amount(
            quantity.units * price.units, quantity.scale + price.scale
        )),
        tax=tax,
    )


def lifecycle_event(
    order_id: str,
    sequence: int,
    status: OrderStatus,
    fills: tuple[SimulatedFill, ...],
    filled: ScaledInteger,
    remaining: ScaledInteger,
    *,
    at: datetime = AT,
    schema_version: str = "simulator-event:v1",
) -> SimulatorEvent:
    return SimulatorEvent.create(
        event_id=f"venue-event-{sequence}",
        order_id=order_id,
        status=status,
        filled_quantity=filled,
        remaining_quantity=remaining,
        average_price=amount(10000, 2) if fills else amount(0, 2),
        fills=fills,
        event_at_utc=at,
        sequence=sequence,
        schema_version=schema_version,
    )


class MemoryUnitOfWork:
    """Reference fault-injected UoW; it makes no durability claim."""

    def __init__(self, account: AccountState, *, fail_commit: bool = False) -> None:
        self.account = account
        self.fail_commit = fail_commit
        self.preparations: dict[str, PreparationCommitBundle] = {}
        self.orders = {}
        self.outbox = []
        self._staged = None
        self.rollback_count = 0
        self.close_count = 0

    def get_preparation(self, intent_id: str):
        return self.preparations.get(intent_id)

    def get_order_state(self, order_id: str):
        return self.orders.get(order_id)

    def get_account(self, account_id: str, instrument_id: str):
        return (self.account if self.account.account_id == account_id
                and self.account.instrument_id == instrument_id else None)

    def is_entry_frozen(self, authority_scope_id: str, account_id: str) -> bool:
        return any(
            state.entry_frozen
            and state.order.authority_scope_id == authority_scope_id
            and state.order.account_id == account_id
            for state in self.orders.values()
        )

    def stage_preparation(self, bundle: PreparationCommitBundle) -> None:
        self._staged = bundle

    def stage_settlement(self, bundle: SettlementCommitBundle) -> None:
        self._staged = bundle

    def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("injected commit fault")
        bundle = self._staged
        if isinstance(bundle, PreparationCommitBundle):
            self.preparations[bundle.preparation.intent.intent_id.key] = bundle
            self.orders[bundle.preparation.order.order_id.key] = bundle.preparation.order_state
            self.outbox.append(bundle.preparation.outbox)
        elif isinstance(bundle, SettlementCommitBundle):
            current = self.orders[bundle.order_state.order.order_id.key]
            if (current.last_sequence != bundle.expected_sequence
                    or self.account.revision != bundle.expected_account_revision):
                raise RuntimeError("stale settlement revision")
            self.orders[bundle.order_state.order.order_id.key] = bundle.order_state
            self.account = bundle.account
            self.outbox.append(bundle.outbox)
        self._staged = None

    def rollback(self) -> None:
        self._staged = None
        self.rollback_count += 1

    def close(self) -> None:
        self.close_count += 1


class RollbackFaultUnitOfWork(MemoryUnitOfWork):
    def rollback(self) -> None:
        super().rollback()
        raise RuntimeError("injected rollback fault")


def prepare_command(side: ExecutionSide = ExecutionSide.BUY) -> PrepareExecutionCommand:
    return PrepareExecutionCommand(
        decision_id="decision:v1:" + "1" * 64,
        authority_scope_id="dryrun:primary",
        account_id="account:primary",
        instrument_id="BTCIDR",
        side=side,
        requested_quantity=amount(150, 2),
        order_ordinal=0,
        created_at_utc=AT,
    )


def account(*, cash=amount(100000, 2), quantity=amount(0, 2)) -> AccountState:
    return AccountState(
        account_id="account:primary",
        instrument_id="BTCIDR",
        cash_balance=cash,
        position_quantity=quantity,
        fees_paid=amount(0, 2),
        taxes_paid=amount(0, 2),
        processed_fill_ids=(),
    )


def advance_to_open(uow: MemoryUnitOfWork, order_id: str) -> None:
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        order_id, 1, OrderStatus.ACCEPTED, (), amount(0, 2), amount(150, 2))), uow)
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        order_id, 2, OrderStatus.OPEN, (), amount(0, 2), amount(150, 2))), uow)


def test_prepare_is_deterministic_and_dispatch_is_exposed_only_after_commit():
    command = prepare_command()
    first = prepare_execution(**command.to_domain_arguments())
    second = prepare_execution(**command.to_domain_arguments())

    assert first == second
    assert first.intent.intent_id.key.startswith("intent:v1:")
    assert first.order.order_id.key.startswith("client_order:v1:")
    assert first.outbox.status is OutboxStatus.PENDING

    uow = MemoryUnitOfWork(account())
    envelope = prepare_before_dispatch(command, uow)
    assert envelope.order_id == first.order.order_id.key
    assert uow.outbox == [first.outbox]

    retry = prepare_before_dispatch(command, uow)
    assert retry == envelope
    assert uow.outbox == [first.outbox]

    failed = MemoryUnitOfWork(account(), fail_commit=True)
    with pytest.raises(RuntimeError, match="injected commit fault"):
        prepare_before_dispatch(command, failed)
    assert failed.preparations == {}
    assert failed.orders == {}
    assert failed.outbox == []
    assert failed.rollback_count == 1


def test_ack_and_open_advance_sequence_without_changing_account():
    uow = MemoryUnitOfWork(account())
    envelope = prepare_before_dispatch(prepare_command(), uow)
    before = uow.account

    accepted = lifecycle_event(
        envelope.order_id, 1, OrderStatus.ACCEPTED, (), amount(0, 2), amount(150, 2)
    )
    opened = lifecycle_event(
        envelope.order_id, 2, OrderStatus.OPEN, (), amount(0, 2), amount(150, 2)
    )
    first = settle_lifecycle_event(SettleLifecycleCommand(accepted), uow)
    second = settle_lifecycle_event(SettleLifecycleCommand(opened), uow)

    assert first.entries == second.entries == ()
    assert uow.account == before
    assert uow.orders[envelope.order_id].last_sequence == 2


def test_cumulative_partial_then_filled_settles_only_new_fills_with_mixed_scales():
    uow = MemoryUnitOfWork(account())
    envelope = prepare_before_dispatch(prepare_command(), uow)
    order_id = envelope.order_id
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        order_id, 1, OrderStatus.ACCEPTED, (), amount(0, 2), amount(150, 2))), uow)
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        order_id, 2, OrderStatus.OPEN, (), amount(0, 2), amount(150, 2))), uow)

    first_fill = fill(
        "fill-1", order_id, quantity=amount(5, 1), price=amount(100, 0),
        fee=amount(25, 2), tax=amount(10, 2),
    )
    partial = lifecycle_event(
        order_id, 3, OrderStatus.PARTIAL, (first_fill,), amount(50, 2), amount(100, 2)
    )
    partial_result = settle_lifecycle_event(SettleLifecycleCommand(partial), uow)
    assert tuple(item.fill_id for item in partial_result.entries) == ("fill-1",)
    assert uow.account.cash_balance == amount(94965, 2)
    assert uow.account.position_quantity == amount(50, 2)

    second_fill = fill(
        "fill-2", order_id, quantity=amount(100, 2), price=amount(10000, 2),
        fee=amount(50, 2), tax=amount(20, 2),
    )
    terminal = lifecycle_event(
        order_id, 4, OrderStatus.FILLED, (first_fill, second_fill),
        amount(150, 2), amount(0, 2),
    )
    final_result = settle_lifecycle_event(SettleLifecycleCommand(terminal), uow)

    assert tuple(item.fill_id for item in final_result.entries) == ("fill-2",)
    assert uow.account.cash_balance == amount(84895, 2)
    assert uow.account.position_quantity == amount(150, 2)
    assert uow.account.fees_paid == amount(75, 2)
    assert uow.account.taxes_paid == amount(30, 2)
    assert uow.account.processed_fill_ids == ("fill-1", "fill-2")
    assert final_result.order_state.remaining_quantity == amount(0, 2)

    duplicate = settle_lifecycle_event(SettleLifecycleCommand(terminal), uow)
    assert duplicate.is_noop is True
    assert duplicate.entries == ()
    assert uow.account.cash_balance == amount(84895, 2)


def test_sell_credit_and_overdraft_oversell_are_rejected_without_partial_state():
    sell_uow = MemoryUnitOfWork(account(cash=amount(0, 2), quantity=amount(150, 2)))
    envelope = prepare_before_dispatch(prepare_command(ExecutionSide.SELL), sell_uow)
    order_id = envelope.order_id
    advance_to_open(sell_uow, order_id)
    executed = fill(
        "sell-1", order_id, quantity=amount(15, 1), price=amount(100, 0),
        fee=amount(25, 2), tax=amount(10, 2),
    )
    result = settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        order_id, 3, OrderStatus.FILLED, (executed,), amount(150, 2), amount(0, 2))), sell_uow)
    assert result.account.cash_balance == amount(14965, 2)
    assert result.account.position_quantity == amount(0, 2)

    for side, initial, code in (
        (ExecutionSide.BUY, account(cash=amount(1, 2)), "CASH_OVERDRAFT"),
        (ExecutionSide.SELL, account(quantity=amount(1, 2)), "POSITION_OVERSELL"),
    ):
        uow = MemoryUnitOfWork(initial)
        envelope = prepare_before_dispatch(prepare_command(side), uow)
        advance_to_open(uow, envelope.order_id)
        executed = fill(
            "unsafe-fill", envelope.order_id, quantity=amount(150, 2),
            price=amount(100, 0), fee=amount(0, 2), tax=amount(0, 2),
        )
        previous_account = uow.account
        with pytest.raises(ExecutionError) as caught:
            settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
                envelope.order_id, 3, OrderStatus.FILLED, (executed,),
                amount(150, 2), amount(0, 2))), uow)
        assert caught.value.code == code
        assert uow.account == previous_account
        assert uow.rollback_count == 1


def test_sequence_prefix_conflict_and_unknown_fail_closed_or_freeze():
    uow = MemoryUnitOfWork(account())
    envelope = prepare_before_dispatch(prepare_command(), uow)
    order_id = envelope.order_id
    accepted = lifecycle_event(
        order_id, 1, OrderStatus.ACCEPTED, (), amount(0, 2), amount(150, 2)
    )
    settle_lifecycle_event(SettleLifecycleCommand(accepted), uow)

    conflicting = SimulatorEvent.create(
        event_id="conflicting-id", order_id=order_id, status=OrderStatus.REJECTED,
        filled_quantity=amount(0, 2), remaining_quantity=amount(150, 2),
        average_price=amount(0, 2), fills=(), event_at_utc=AT, sequence=1,
    )
    with pytest.raises(ExecutionError) as caught:
        settle_lifecycle_event(SettleLifecycleCommand(conflicting), uow)
    assert caught.value.code == "CONFLICTING_DUPLICATE_EVENT"

    unknown = lifecycle_event(
        order_id, 2, OrderStatus.UNKNOWN, (), amount(0, 2), amount(150, 2)
    )
    frozen = settle_lifecycle_event(SettleLifecycleCommand(unknown), uow)
    assert frozen.order_state.entry_frozen is True
    assert frozen.order_state.remaining_quantity == amount(150, 2)


def test_commit_fault_during_fill_has_zero_partial_state_and_retry_is_idempotent():
    uow = MemoryUnitOfWork(account())
    envelope = prepare_before_dispatch(prepare_command(), uow)
    advance_to_open(uow, envelope.order_id)
    executed = fill(
        "fill-atomic", envelope.order_id, quantity=amount(150, 2), price=amount(100, 0),
        fee=amount(0, 2), tax=amount(0, 2),
    )
    event = lifecycle_event(
        envelope.order_id, 3, OrderStatus.FILLED, (executed,),
        amount(150, 2), amount(0, 2),
    )
    before_account = uow.account
    before_order = uow.orders[envelope.order_id]
    uow.fail_commit = True
    with pytest.raises(RuntimeError, match="injected commit fault"):
        settle_lifecycle_event(SettleLifecycleCommand(event), uow)
    assert uow.account == before_account
    assert uow.orders[envelope.order_id] == before_order
    assert uow.rollback_count == 1

    uow.fail_commit = False
    settled = settle_lifecycle_event(SettleLifecycleCommand(event), uow)
    assert settled.is_noop is False
    replay = settle_lifecycle_event(SettleLifecycleCommand(event), uow)
    assert replay.is_noop is True
    assert uow.account.processed_fill_ids == ("fill-atomic",)


def test_coarse_quote_notional_from_simulator_contract_settles_authoritatively():
    uow = MemoryUnitOfWork(account(cash=amount(10, 0), quantity=amount(0, 2)))
    command = replace(prepare_command(), requested_quantity=amount(15, 2))
    envelope = prepare_before_dispatch(command, uow)
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        envelope.order_id, 1, OrderStatus.ACCEPTED, (), amount(0, 2), amount(15, 2)
    )), uow)
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        envelope.order_id, 2, OrderStatus.OPEN, (), amount(0, 2), amount(15, 2)
    )), uow)
    executed = fill(
        "coarse-fill", envelope.order_id, quantity=amount(15, 2),
        price=amount(7, 0), fee=amount(0, 0), tax=amount(0, 0),
        notional=amount(2, 0),
    )
    settled = settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        envelope.order_id, 3, OrderStatus.FILLED, (executed,),
        amount(15, 2), amount(0, 2)
    )), uow)

    assert settled.account.cash_balance == amount(8, 0)
    assert settled.account.position_quantity == amount(15, 2)
    assert settled.account.revision == 1


def test_actual_story_23_lifecycle_stream_settles_without_evidence_rewrite():
    command = replace(prepare_command(), requested_quantity=amount(15, 2))
    uow = MemoryUnitOfWork(account(cash=amount(10, 0), quantity=amount(0, 2)))
    envelope = prepare_before_dispatch(command, uow)
    snapshot = MarketSnapshot.create(
        instrument_id="BTCIDR", event_at_utc=AT, received_at_utc=AT,
        venue_cursor="coarse:1", ingest_cursor="coarse:1",
        bids=(OrderBookLevel(amount(6, 0), amount(15, 2)),),
        asks=(OrderBookLevel(amount(7, 0), amount(15, 2)),),
        execution_side=OrderBookSide.ASK, requested_size=amount(15, 2),
        rules=InstrumentRules(
            "rules:coarse", amount(1, 2), 0, 2,
            amount(1, 0), amount(1, 2), True,
        ),
        membership=UniverseMembership("universe:coarse", AT, True, "proof:coarse"),
        quality=MarketQuality(0, 1, 1, 2, True, "coarse", "coarse:1"),
    )
    lifecycle = OrderSimulator(seed=9).simulate_lifecycle(
        order_id=envelope.order_id, side=OrderBookSide.ASK,
        requested_size=amount(15, 2), snapshot=snapshot,
        evaluated_at_utc=AT,
        scenario=LifecycleScenario(
            "scenario:coarse", "seed", 0, 0,
            ScenarioOutcome.EXECUTE, FeeType.TAKER,
        ),
        cost_rules=CostRules("cost:coarse", 0, 0, 0, 0),
    )

    for event in lifecycle.events:
        result = settle_lifecycle_event(SettleLifecycleCommand(event), uow)

    assert lifecycle.terminal_event.fills[0].notional == amount(2, 0)
    assert result.account.cash_balance == amount(8, 0)
    assert result.account.position_quantity == amount(15, 2)


def test_schema_time_quantity_scale_and_unknown_mutation_fail_closed():
    uow = MemoryUnitOfWork(account())
    envelope = prepare_before_dispatch(prepare_command(), uow)
    accepted = lifecycle_event(
        envelope.order_id, 1, OrderStatus.ACCEPTED, (), amount(0, 2), amount(150, 2),
        at=AT + timedelta(seconds=1),
    )
    settle_lifecycle_event(SettleLifecycleCommand(accepted), uow)

    invalid_events = (
        (lifecycle_event(
            envelope.order_id, 2, OrderStatus.OPEN, (), amount(0, 2), amount(150, 2),
            at=AT,
        ), "EVENT_TIME_REGRESSION"),
        (lifecycle_event(
            envelope.order_id, 2, OrderStatus.OPEN, (), amount(0, 2), amount(150, 2),
            at=AT + timedelta(seconds=1), schema_version="simulator-event:v2",
        ), "UNSUPPORTED_EVENT_SCHEMA"),
        (lifecycle_event(
            envelope.order_id, 2, OrderStatus.OPEN, (), amount(0, 1), amount(15, 1),
            at=AT + timedelta(seconds=1),
        ), "ORDER_QUANTITY_SCALE_MISMATCH"),
    )
    for event, code in invalid_events:
        with pytest.raises(ExecutionError) as caught:
            settle_lifecycle_event(SettleLifecycleCommand(event), uow)
        assert caught.value.code == code

    opened = lifecycle_event(
        envelope.order_id, 2, OrderStatus.OPEN, (), amount(0, 2), amount(150, 2),
        at=AT + timedelta(seconds=1),
    )
    settle_lifecycle_event(SettleLifecycleCommand(opened), uow)
    executed = fill(
        "unknown-fill", envelope.order_id, quantity=amount(50, 2),
        price=amount(100, 0), fee=amount(0, 2), tax=amount(0, 2),
    )
    ambiguous = lifecycle_event(
        envelope.order_id, 3, OrderStatus.UNKNOWN, (executed,),
        amount(50, 2), amount(100, 2), at=AT + timedelta(seconds=2),
    )
    with pytest.raises(ExecutionError) as caught:
        settle_lifecycle_event(SettleLifecycleCommand(ambiguous), uow)
    assert caught.value.code == "UNKNOWN_QUANTITY_CHANGE"


def test_unknown_freeze_blocks_new_entry_but_allows_exact_prepare_retry():
    uow = MemoryUnitOfWork(account())
    command = prepare_command()
    envelope = prepare_before_dispatch(command, uow)
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        envelope.order_id, 1, OrderStatus.ACCEPTED, (), amount(0, 2), amount(150, 2)
    )), uow)
    settle_lifecycle_event(SettleLifecycleCommand(lifecycle_event(
        envelope.order_id, 2, OrderStatus.UNKNOWN, (), amount(0, 2), amount(150, 2)
    )), uow)

    assert prepare_before_dispatch(command, uow) == envelope
    with pytest.raises(ExecutionError) as caught:
        prepare_before_dispatch(replace(
            command, decision_id="decision:v1:" + "2" * 64
        ), uow)
    assert caught.value.code == "ENTRY_FROZEN"


def test_duplicate_replay_rejects_split_brain_account_fill_history():
    uow = MemoryUnitOfWork(account())
    envelope = prepare_before_dispatch(prepare_command(), uow)
    advance_to_open(uow, envelope.order_id)
    executed = fill(
        "history-fill", envelope.order_id, quantity=amount(150, 2),
        price=amount(100, 0), fee=amount(0, 2), tax=amount(0, 2),
    )
    terminal = lifecycle_event(
        envelope.order_id, 3, OrderStatus.FILLED, (executed,),
        amount(150, 2), amount(0, 2),
    )
    settle_lifecycle_event(SettleLifecycleCommand(terminal), uow)
    uow.account = replace(uow.account, processed_fill_ids=())

    with pytest.raises(ExecutionError) as caught:
        settle_lifecycle_event(SettleLifecycleCommand(terminal), uow)
    assert caught.value.code == "ACCOUNT_FILL_HISTORY_MISMATCH"


def test_composite_values_and_commit_bundles_reject_cross_aggregate_links():
    first = prepare_execution(**prepare_command().to_domain_arguments())
    second = prepare_execution(**replace(
        prepare_command(), decision_id="decision:v1:" + "2" * 64
    ).to_domain_arguments())
    with pytest.raises(ExecutionError, match="EXECUTION_PREPARATION_MISMATCH"):
        ExecutionPreparation(first.intent, second.order, second.order_state, second.outbox)

    accepted = lifecycle_event(
        first.order.order_id.key, 1, OrderStatus.ACCEPTED, (),
        amount(0, 2), amount(150, 2),
    )
    result = settle_event(first.order_state, account(), accepted)
    assert result.outbox is not None
    with pytest.raises(TypeError, match="SETTLEMENT_COMMIT_MISMATCH"):
        SettlementCommitBundle(
            0, 0, result.order_state, result.account, accepted,
            result.entries, second.outbox,
        )


def test_direct_unknown_state_duplicate_fill_and_unbounded_scale_are_rejected():
    preparation = prepare_execution(**prepare_command().to_domain_arguments())
    accepted = lifecycle_event(
        preparation.order.order_id.key, 1, OrderStatus.ACCEPTED, (),
        amount(0, 2), amount(150, 2),
    )
    accepted_result = settle_event(preparation.order_state, account(), accepted)
    unknown = lifecycle_event(
        preparation.order.order_id.key, 2, OrderStatus.UNKNOWN, (),
        amount(0, 2), amount(150, 2),
    )
    frozen_result = settle_event(accepted_result.order_state, account(), unknown)
    with pytest.raises(ExecutionError, match="UNKNOWN_NOT_FROZEN"):
        replace(frozen_result.order_state, entry_frozen=False)

    repeated = fill(
        "same-fill", preparation.order.order_id.key, quantity=amount(75, 2),
        price=amount(100, 0), fee=amount(0, 2), tax=amount(0, 2),
    )
    with pytest.raises(ExecutionError, match="DUPLICATE_FILL_ID"):
        OrderSettlementState(
            preparation.order, 0, None, amount(0, 2), amount(150, 2),
            (repeated, repeated), (), False,
        )

    with pytest.raises(ExecutionError, match="INVALID_REQUESTED_QUANTITY"):
        prepare_execution(**replace(
            prepare_command(), requested_quantity=amount(1, 2_048)
        ).to_domain_arguments())


def test_read_noop_and_failure_paths_close_uow_without_masking_primary_fault():
    missing = MemoryUnitOfWork(account())
    event = lifecycle_event(
        "missing-order", 1, OrderStatus.REJECTED, (), amount(0, 2), amount(150, 2)
    )
    with pytest.raises(ExecutionError, match="ORDER_NOT_FOUND"):
        settle_lifecycle_event(SettleLifecycleCommand(event), missing)
    assert missing.rollback_count == 1
    assert missing.close_count == 1

    faulty = RollbackFaultUnitOfWork(account(), fail_commit=True)
    with pytest.raises(RuntimeError, match="injected commit fault"):
        prepare_before_dispatch(prepare_command(), faulty)
    assert faulty.rollback_count == 1
    assert faulty.close_count == 1
