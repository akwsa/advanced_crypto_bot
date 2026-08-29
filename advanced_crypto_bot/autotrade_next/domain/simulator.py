"""Deterministic Order Execution Simulator for DRY RUN and Replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
import random

from .content import ContentRecipe, ContentRef
from .encoding import canonical_bytes
from .errors import MarketEvidenceError
from .market import MarketSnapshot, OrderBookSide
from .numeric import ScaledInteger


class OrderStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class FeeType(str, Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"


@dataclass(frozen=True, slots=True)
class SimulatedFill:
    fill_id: str
    order_id: str
    price: ScaledInteger
    quantity: ScaledInteger
    fee: ScaledInteger
    fee_type: FeeType
    filled_at_utc: datetime

    def to_canonical_value(self) -> dict[str, object]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "price": {"units": self.price.units, "scale": self.price.scale},
            "quantity": {"units": self.quantity.units, "scale": self.quantity.scale},
            "fee": {"units": self.fee.units, "scale": self.fee.scale},
            "fee_type": self.fee_type.value,
            "filled_at_utc": self.filled_at_utc,
        }


@dataclass(frozen=True, slots=True)
class SimulatorEvent:
    event_id: str
    order_id: str
    status: OrderStatus
    filled_quantity: ScaledInteger
    remaining_quantity: ScaledInteger
    average_price: ScaledInteger
    fills: tuple[SimulatedFill, ...]
    event_at_utc: datetime
    event_ref: ContentRef

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        order_id: str,
        status: OrderStatus,
        filled_quantity: ScaledInteger,
        remaining_quantity: ScaledInteger,
        average_price: ScaledInteger,
        fills: tuple[SimulatedFill, ...] | list[SimulatedFill],
        event_at_utc: datetime,
    ) -> SimulatorEvent:
        frozen_fills = tuple(fills)
        value = {
            "event_id": event_id,
            "order_id": order_id,
            "status": status.value,
            "filled_quantity": {"units": filled_quantity.units, "scale": filled_quantity.scale},
            "remaining_quantity": {"units": remaining_quantity.units, "scale": remaining_quantity.scale},
            "average_price": {"units": average_price.units, "scale": average_price.scale},
            "fills": tuple(fill.to_canonical_value() for fill in frozen_fills),
            "event_at_utc": event_at_utc,
        }
        event_ref = ContentRef.v2("simulator.event", "simulator-event", value)
        return cls(
            event_id=event_id,
            order_id=order_id,
            status=status,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            average_price=average_price,
            fills=frozen_fills,
            event_at_utc=event_at_utc,
            event_ref=event_ref,
        )


@dataclass(frozen=True, slots=True)
class OrderSimulator:
    seed: int
    maker_fee_bps: int = 10
    taker_fee_bps: int = 20

    def simulate_execution(
        self,
        *,
        order_id: str,
        side: OrderBookSide,
        requested_size: ScaledInteger,
        snapshot: MarketSnapshot,
        evaluated_at_utc: datetime,
    ) -> SimulatorEvent:
        rng = random.Random(self.seed + hash(order_id))
        
        # Check if depth exists
        levels = snapshot.asks if side is OrderBookSide.ASK else snapshot.bids
        if not levels:
            return SimulatorEvent.create(
                event_id=f"sim-evt-{order_id}-reject",
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_quantity=ScaledInteger(0, requested_size.scale),
                remaining_quantity=requested_size,
                average_price=ScaledInteger(0, 2),
                fills=(),
                event_at_utc=evaluated_at_utc,
            )

        capacity, avg_price = snapshot.calculate_executable_price(side, requested_size)
        if capacity.units == 0:
            return SimulatorEvent.create(
                event_id=f"sim-evt-{order_id}-reject",
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_quantity=ScaledInteger(0, requested_size.scale),
                remaining_quantity=requested_size,
                average_price=ScaledInteger(0, 2),
                fills=(),
                event_at_utc=evaluated_at_utc,
            )

        filled_units = min(capacity.units, requested_size.units)
        remaining_units = requested_size.units - filled_units

        fee_units = (filled_units * avg_price.units * self.taker_fee_bps) // 10000
        fill = SimulatedFill(
            fill_id=f"fill-{order_id}-1",
            order_id=order_id,
            price=avg_price,
            quantity=ScaledInteger(filled_units, requested_size.scale),
            fee=ScaledInteger(fee_units, 2),
            fee_type=FeeType.TAKER,
            filled_at_utc=evaluated_at_utc,
        )

        status = OrderStatus.FILLED if remaining_units == 0 else OrderStatus.PARTIAL
        return SimulatorEvent.create(
            event_id=f"sim-evt-{order_id}-exec",
            order_id=order_id,
            status=status,
            filled_quantity=ScaledInteger(filled_units, requested_size.scale),
            remaining_quantity=ScaledInteger(remaining_units, requested_size.scale),
            average_price=avg_price,
            fills=(fill,),
            event_at_utc=evaluated_at_utc,
        )


__all__ = (
    "FeeType",
    "OrderSimulator",
    "OrderStatus",
    "SimulatedFill",
    "SimulatorEvent",
)
