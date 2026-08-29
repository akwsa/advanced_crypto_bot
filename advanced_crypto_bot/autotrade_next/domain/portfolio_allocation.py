"""Atomic Portfolio Allocation and Risk Reservation Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .errors import DecisionError
from .numeric import ScaledInteger


@dataclass(frozen=True, slots=True)
class RiskReservation:
    reservation_id: str
    instrument_id: str
    initial_notional: ScaledInteger
    consumed_notional: ScaledInteger
    active_remainder_notional: ScaledInteger
    released_notional: ScaledInteger

    def __post_init__(self) -> None:
        # Conservation equation check: initial == consumed + active_remainder + released
        total_units = (
            self.consumed_notional.units
            + self.active_remainder_notional.units
            + self.released_notional.units
        )
        if total_units != self.initial_notional.units:
            raise DecisionError("RESERVATION_CONSERVATION_BREACH")


@dataclass(frozen=True, slots=True)
class PortfolioAllocation:
    cutoff_at_utc: datetime
    total_equity: ScaledInteger
    reservations: tuple[RiskReservation, ...]

    def allocate_reservation(
        self,
        *,
        reservation_id: str,
        instrument_id: str,
        initial_notional: ScaledInteger,
    ) -> PortfolioAllocation:
        new_reservation = RiskReservation(
            reservation_id=reservation_id,
            instrument_id=instrument_id,
            initial_notional=initial_notional,
            consumed_notional=ScaledInteger(0, initial_notional.scale),
            active_remainder_notional=initial_notional,
            released_notional=ScaledInteger(0, initial_notional.scale),
        )
        return PortfolioAllocation(
            cutoff_at_utc=self.cutoff_at_utc,
            total_equity=self.total_equity,
            reservations=(*self.reservations, new_reservation),
        )


__all__ = (
    "PortfolioAllocation",
    "RiskReservation",
)
