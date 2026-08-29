"""Unified Exit Evaluation and Position Protection Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum

from .errors import MarketEvidenceError
from .numeric import ScaledInteger


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    INVALIDATION = "INVALIDATION"
    TIME_EXPIRY = "TIME_EXPIRY"
    ALPHA_EXIT = "ALPHA_EXIT"
    OPERATOR_EXIT = "OPERATOR_EXIT"
    NO_EXIT = "NO_EXIT"


@dataclass(frozen=True, slots=True)
class ProtectionState:
    stop_loss_price: ScaledInteger | None
    take_profit_price: ScaledInteger | None
    trailing_high_water: ScaledInteger | None
    expiration_at_utc: datetime | None


@dataclass(frozen=True, slots=True)
class ExitDecision:
    should_exit: bool
    reason: ExitReason
    target_quantity: ScaledInteger

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "should_exit": self.should_exit,
            "reason": self.reason.value,
            "target_quantity": {"units": self.target_quantity.units, "scale": self.target_quantity.scale},
        }


class ExitEvaluator:
    @staticmethod
    def evaluate(
        *,
        current_position_quantity: ScaledInteger,
        current_price: ScaledInteger,
        protection: ProtectionState,
        evaluated_at_utc: datetime,
        force_operator_exit: bool = False,
    ) -> ExitDecision:
        if current_position_quantity.units == 0:
            return ExitDecision(
                should_exit=False,
                reason=ExitReason.NO_EXIT,
                target_quantity=ScaledInteger(0, current_position_quantity.scale),
            )

        if force_operator_exit:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.OPERATOR_EXIT,
                target_quantity=current_position_quantity,
            )

        if protection.expiration_at_utc is not None and evaluated_at_utc >= protection.expiration_at_utc:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.TIME_EXPIRY,
                target_quantity=current_position_quantity,
            )

        if protection.stop_loss_price is not None and current_price.units <= protection.stop_loss_price.units:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.STOP_LOSS,
                target_quantity=current_position_quantity,
            )

        if protection.take_profit_price is not None and current_price.units >= protection.take_profit_price.units:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.TAKE_PROFIT,
                target_quantity=current_position_quantity,
            )

        return ExitDecision(
            should_exit=False,
            reason=ExitReason.NO_EXIT,
            target_quantity=ScaledInteger(0, current_position_quantity.scale),
        )


__all__ = (
    "ExitDecision",
    "ExitEvaluator",
    "ExitReason",
    "ProtectionState",
)
