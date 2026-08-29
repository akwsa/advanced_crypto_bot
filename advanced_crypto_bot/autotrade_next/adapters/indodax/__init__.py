"""Offline, fail-closed Indodax market-evidence adapter."""

from .capability_registry import INDODAX_CAPABILITY_REGISTRY, build_indodax_capability_registry
from .market_evidence import qualify_recorded_input

__all__ = (
    "INDODAX_CAPABILITY_REGISTRY",
    "build_indodax_capability_registry",
    "qualify_recorded_input",
)
