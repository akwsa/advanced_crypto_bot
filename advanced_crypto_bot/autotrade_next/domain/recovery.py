"""Lifecycle Recovery and Reconciliation Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum

from .accounting import PositionAccount
from .errors import RecoveryEvaluationError
from .numeric import ScaledInteger
from .simulator import OrderStatus


class RecoveryAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    QUERY_VENUE = "QUERY_VENUE"
    REAPPLY_FILL = "REAPPLY_FILL"
    FREEZE_ENTRY = "FREEZE_ENTRY"


@dataclass(frozen=True, slots=True)
class RecoveryState:
    last_processed_sequence: int
    account_snapshot: PositionAccount
    pending_order_ids: tuple[str, ...]
    unreconciled_unknown_orders: tuple[str, ...]


class LifecycleRecoveryManager:
    @staticmethod
    def evaluate_recovery(
        *,
        state: RecoveryState,
        order_statuses: dict[str, OrderStatus],
    ) -> tuple[RecoveryAction, tuple[str, ...]]:
        if state.unreconciled_unknown_orders:
            # Query venue before any resubmit
            return RecoveryAction.QUERY_VENUE, state.unreconciled_unknown_orders

        for order_id, status in order_statuses.items():
            if status is OrderStatus.UNKNOWN:
                return RecoveryAction.QUERY_VENUE, (order_id,)

        return RecoveryAction.NO_ACTION, ()


__all__ = (
    "LifecycleRecoveryManager",
    "RecoveryAction",
    "RecoveryState",
)
