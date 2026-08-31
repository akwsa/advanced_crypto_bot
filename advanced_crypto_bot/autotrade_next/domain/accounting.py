"""Fill-Authoritative Accounting and Position Ledger Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum

from .content import ContentRef
from .errors import MarketEvidenceError
from .numeric import ScaledInteger


class MovementType(str, Enum):
    CASH_DEPOSIT = "CASH_DEPOSIT"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"
    FILL_BUY = "FILL_BUY"
    FILL_SELL = "FILL_SELL"
    FEE_PAYMENT = "FEE_PAYMENT"


@dataclass(frozen=True, slots=True)
class CashLedgerEntry:
    entry_id: str
    fill_id: str | None
    movement_type: MovementType
    amount: ScaledInteger
    fee: ScaledInteger
    balance_after: ScaledInteger
    recorded_at_utc: datetime

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "fill_id": self.fill_id,
            "movement_type": self.movement_type.value,
            "amount": {"units": self.amount.units, "scale": self.amount.scale},
            "fee": {"units": self.fee.units, "scale": self.fee.scale},
            "balance_after": {"units": self.balance_after.units, "scale": self.balance_after.scale},
            "recorded_at_utc": self.recorded_at_utc,
        }


@dataclass(frozen=True, slots=True)
class PositionAccount:
    instrument_id: str
    cash_balance: ScaledInteger
    position_quantity: ScaledInteger
    processed_fill_ids: tuple[str, ...]

    def apply_fill(
        self,
        *,
        fill_id: str,
        is_buy: bool,
        quantity: ScaledInteger,
        price: ScaledInteger,
        fee: ScaledInteger,
        recorded_at_utc: datetime,
    ) -> tuple[PositionAccount, CashLedgerEntry]:
        if fill_id in self.processed_fill_ids:
            # Idempotent duplicate fill ignore
            entry = CashLedgerEntry(
                entry_id=f"dup-{fill_id}",
                fill_id=fill_id,
                movement_type=MovementType.FILL_BUY if is_buy else MovementType.FILL_SELL,
                amount=ScaledInteger(0, cash_balance.scale if (cash_balance := self.cash_balance) else 2),
                fee=ScaledInteger(0, fee.scale),
                balance_after=self.cash_balance,
                recorded_at_utc=recorded_at_utc,
            )
            return self, entry

        cost = quantity.multiply(price, target_scale=self.cash_balance.scale)
        fee_scaled = fee.rescale(self.cash_balance.scale)

        if is_buy:
            new_cash = self.cash_balance.subtract(cost).subtract(fee_scaled)
            new_pos = self.position_quantity.add(quantity)
            mtype = MovementType.FILL_BUY
        else:
            new_cash = self.cash_balance.add(cost).subtract(fee_scaled)
            new_pos = self.position_quantity.subtract(quantity)
            mtype = MovementType.FILL_SELL

        updated_account = PositionAccount(
            instrument_id=self.instrument_id,
            cash_balance=new_cash,
            position_quantity=new_pos,
            processed_fill_ids=(*self.processed_fill_ids, fill_id),
        )

        entry = CashLedgerEntry(
            entry_id=f"entry-{fill_id}",
            fill_id=fill_id,
            movement_type=mtype,
            amount=cost,
            fee=fee_scaled,
            balance_after=new_cash,
            recorded_at_utc=recorded_at_utc,
        )

        return updated_account, entry


__all__ = (
    "CashLedgerEntry",
    "MovementType",
    "PositionAccount",
)
