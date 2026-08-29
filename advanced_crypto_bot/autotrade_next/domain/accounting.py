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

        raw_cost_units = quantity.units * price.units
        total_cost_units = raw_cost_units // (10 ** quantity.scale)
        fee_units = fee.units

        if is_buy:
            new_cash_units = self.cash_balance.units - total_cost_units - fee_units
            new_pos_units = self.position_quantity.units + quantity.units
            mtype = MovementType.FILL_BUY
        else:
            new_cash_units = self.cash_balance.units + total_cost_units - fee_units
            new_pos_units = self.position_quantity.units - quantity.units
            mtype = MovementType.FILL_SELL

        new_cash = ScaledInteger(new_cash_units, self.cash_balance.scale)
        new_pos = ScaledInteger(new_pos_units, self.position_quantity.scale)
        updated_fills = (*self.processed_fill_ids, fill_id)

        updated_account = PositionAccount(
            instrument_id=self.instrument_id,
            cash_balance=new_cash,
            position_quantity=new_pos,
            processed_fill_ids=updated_fills,
        )

        entry = CashLedgerEntry(
            entry_id=f"entry-{fill_id}",
            fill_id=fill_id,
            movement_type=mtype,
            amount=ScaledInteger(total_cost_units, self.cash_balance.scale),
            fee=fee,
            balance_after=new_cash,
            recorded_at_utc=recorded_at_utc,
        )

        return updated_account, entry


__all__ = (
    "CashLedgerEntry",
    "MovementType",
    "PositionAccount",
)
