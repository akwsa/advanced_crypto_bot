"""Transaction-scoped persistence boundary for settlement application handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from autotrade_next.domain.execution import (
    AccountState,
    ExecutionError,
    ExecutionPreparation,
    OrderSettlementState,
    OutboxMessage,
    SettlementEntry,
    settle_event,
)
from autotrade_next.domain.simulator import SimulatorEvent


@dataclass(frozen=True, slots=True)
class PreparationCommitBundle:
    preparation: ExecutionPreparation

    def __post_init__(self) -> None:
        if type(self.preparation) is not ExecutionPreparation:
            raise TypeError("INVALID_PREPARATION_COMMIT")


@dataclass(frozen=True, slots=True)
class SettlementCommitBundle:
    expected_sequence: int
    expected_account_revision: int
    expected_order_state: OrderSettlementState
    expected_account: AccountState
    order_state: OrderSettlementState
    account: AccountState
    lifecycle_event: SimulatorEvent
    entries: tuple[SettlementEntry, ...]
    outbox: OutboxMessage

    def __post_init__(self) -> None:
        if type(self.expected_sequence) is not int or self.expected_sequence < 0:
            raise TypeError("INVALID_EXPECTED_SEQUENCE")
        if (type(self.expected_account_revision) is not int
                or self.expected_account_revision < 0):
            raise TypeError("INVALID_EXPECTED_ACCOUNT_REVISION")
        if type(self.expected_order_state) is not OrderSettlementState:
            raise TypeError("INVALID_EXPECTED_ORDER_STATE")
        if type(self.expected_account) is not AccountState:
            raise TypeError("INVALID_EXPECTED_ACCOUNT_STATE")
        if type(self.order_state) is not OrderSettlementState:
            raise TypeError("INVALID_ORDER_STATE")
        if type(self.account) is not AccountState:
            raise TypeError("INVALID_ACCOUNT_STATE")
        if type(self.lifecycle_event) is not SimulatorEvent:
            raise TypeError("INVALID_LIFECYCLE_EVENT")
        if type(self.entries) is not tuple or any(
                type(entry) is not SettlementEntry for entry in self.entries):
            raise TypeError("INVALID_SETTLEMENT_ENTRIES")
        if type(self.outbox) is not OutboxMessage:
            raise TypeError("INVALID_SETTLEMENT_OUTBOX")
        if (self.expected_order_state.last_sequence != self.expected_sequence
                or self.expected_account.revision != self.expected_account_revision
                or self.order_state.last_sequence != self.expected_sequence + 1):
            raise TypeError("INVALID_SETTLEMENT_SEQUENCE")
        order = self.order_state.order
        if (not self.order_state.receipts
                or self.order_state.receipts[-1] != self.lifecycle_event
                or self.lifecycle_event.order_id != order.order_id.key
                or self.account.account_id != order.account_id
                or self.account.instrument_id != order.instrument_id
                or self.account.revision != self.expected_account_revision + bool(self.entries)
                or self.outbox.authority_scope_id != order.authority_scope_id
                or self.outbox.aggregate_id != order.order_id.key
                or self.outbox.aggregate_sequence != self.lifecycle_event.sequence
                or self.outbox.payload_ref != self.lifecycle_event.event_ref):
            raise TypeError("SETTLEMENT_COMMIT_MISMATCH")
        previous_fills = (self.order_state.receipts[-2].fills
                          if len(self.order_state.receipts) > 1 else ())
        expected_fill_ids = tuple(
            fill.fill_id
            for fill in self.lifecycle_event.fills[len(previous_fills):]
        )
        if (tuple(entry.fill_id for entry in self.entries) != expected_fill_ids
                or any(
                    entry.authority_scope_id != order.authority_scope_id
                    or entry.account_id != order.account_id
                    or entry.instrument_id != order.instrument_id
                    or entry.order_id != order.order_id.key
                    or entry.event_id != self.lifecycle_event.event_id
                    or entry.side is not order.side
                    for entry in self.entries
                )):
            raise TypeError("SETTLEMENT_COMMIT_MISMATCH")
        try:
            expected_result = settle_event(
                self.expected_order_state,
                self.expected_account,
                self.lifecycle_event,
            )
        except ExecutionError as error:
            raise TypeError("SETTLEMENT_COMMIT_MISMATCH") from error
        if (expected_result.is_noop
                or expected_result.order_state != self.order_state
                or expected_result.account != self.account
                or expected_result.entries != self.entries
                or expected_result.outbox != self.outbox):
            raise TypeError("SETTLEMENT_COMMIT_MISMATCH")


class SettlementUnitOfWork(Protocol):
    """One atomic boundary; implementations own rollback and durability."""

    def get_preparation(self, intent_id: str) -> PreparationCommitBundle | None: ...

    def get_order_state(self, order_id: str) -> OrderSettlementState | None: ...

    def get_account(self, account_id: str, instrument_id: str) -> AccountState | None: ...

    def is_entry_frozen(self, authority_scope_id: str, account_id: str) -> bool: ...

    def stage_preparation(self, bundle: PreparationCommitBundle) -> None: ...

    def stage_settlement(self, bundle: SettlementCommitBundle) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


__all__ = (
    "PreparationCommitBundle",
    "SettlementCommitBundle",
    "SettlementUnitOfWork",
)
