"""Shared venue lifecycle boundary; implementations remain outside the domain."""

from typing import Protocol

from autotrade_next.domain.simulator import SimulatorEvent


class VenuePort(Protocol):
    def publish_event(self, event: SimulatorEvent) -> None:
        ...


__all__ = ("VenuePort",)
