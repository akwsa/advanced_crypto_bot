"""Atomic application handlers for prepare-before-dispatch and fill settlement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from autotrade_next.domain.execution import (
    DispatchEnvelope,
    ExecutionError,
    ExecutionSide,
    SettlementResult,
    prepare_execution,
    settle_event,
)
from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.simulator import SimulatorEvent
from autotrade_next.ports.settlement import (
    PreparationCommitBundle,
    SettlementCommitBundle,
    SettlementUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class PrepareExecutionCommand:
    decision_id: str
    authority_scope_id: str
    account_id: str
    instrument_id: str
    side: ExecutionSide
    requested_quantity: ScaledInteger
    order_ordinal: int
    created_at_utc: datetime

    def to_domain_arguments(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "authority_scope_id": self.authority_scope_id,
            "account_id": self.account_id,
            "instrument_id": self.instrument_id,
            "side": self.side,
            "requested_quantity": self.requested_quantity,
            "order_ordinal": self.order_ordinal,
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True, slots=True)
class SettleLifecycleCommand:
    event: SimulatorEvent

    def __post_init__(self) -> None:
        if type(self.event) is not SimulatorEvent:
            raise ExecutionError("INVALID_LIFECYCLE_EVENT")


def _dispatch(bundle: PreparationCommitBundle) -> DispatchEnvelope:
    preparation = bundle.preparation
    return DispatchEnvelope(
        preparation.intent.intent_id.key,
        preparation.order.order_id.key,
        preparation.order.order_ref,
    )


def _rollback_without_masking(uow: SettlementUnitOfWork) -> None:
    try:
        uow.rollback()
    except BaseException:
        pass


def _close_without_masking(uow: SettlementUnitOfWork) -> None:
    try:
        uow.close()
    except BaseException:
        pass


def prepare_before_dispatch(command: PrepareExecutionCommand,
                            uow: SettlementUnitOfWork) -> DispatchEnvelope:
    """Return a dispatch envelope only after its pending outbox commit succeeds."""
    if type(command) is not PrepareExecutionCommand:
        raise ExecutionError("INVALID_PREPARE_COMMAND")
    preparation = prepare_execution(**command.to_domain_arguments())
    try:
        existing = uow.get_preparation(preparation.intent.intent_id.key)
        if existing is not None:
            if (type(existing) is not PreparationCommitBundle
                    or existing.preparation != preparation):
                raise ExecutionError("INTENT_CONFLICT")
            return _dispatch(existing)
        if uow.is_entry_frozen(command.authority_scope_id, command.account_id):
            raise ExecutionError("ENTRY_FROZEN")
        bundle = PreparationCommitBundle(preparation)
        uow.stage_preparation(bundle)
        uow.commit()
        return _dispatch(bundle)
    except BaseException:
        _rollback_without_masking(uow)
        raise
    finally:
        _close_without_masking(uow)


def settle_lifecycle_event(command: SettleLifecycleCommand,
                           uow: SettlementUnitOfWork) -> SettlementResult:
    """Commit event, fill effects and PENDING outbox as one UoW bundle."""
    if type(command) is not SettleLifecycleCommand:
        raise ExecutionError("INVALID_SETTLEMENT_COMMAND")
    event = command.event
    try:
        order_state = uow.get_order_state(event.order_id)
        if order_state is None:
            raise ExecutionError("ORDER_NOT_FOUND")
        account = uow.get_account(
            order_state.order.account_id, order_state.order.instrument_id
        )
        if account is None:
            raise ExecutionError("ACCOUNT_NOT_FOUND")
        result = settle_event(order_state, account, event)
        if result.is_noop:
            return result
        if result.outbox is None:
            raise ExecutionError("MISSING_SETTLEMENT_OUTBOX")
        bundle = SettlementCommitBundle(
            order_state.last_sequence,
            account.revision,
            result.order_state,
            result.account,
            event,
            result.entries,
            result.outbox,
        )
        uow.stage_settlement(bundle)
        uow.commit()
        return result
    except BaseException:
        _rollback_without_masking(uow)
        raise
    finally:
        _close_without_masking(uow)


__all__ = (
    "PrepareExecutionCommand",
    "SettleLifecycleCommand",
    "prepare_before_dispatch",
    "settle_lifecycle_event",
)
