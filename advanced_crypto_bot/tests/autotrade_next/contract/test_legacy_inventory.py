"""Contract tests for Story 5.1: Legacy Inventory Classification."""

import pytest

from autotrade_next.domain.legacy_inventory import (
    LegacyEntityDisposition,
    LegacyInventoryClassifier,
    LegacyInventoryRecord,
)


def test_legacy_inventory_readiness_pass():
    r1 = LegacyInventoryRecord("ord-10", "order", LegacyEntityDisposition.PROVEN_CLOSED, "ev-10")
    r2 = LegacyInventoryRecord("pos-20", "position", LegacyEntityDisposition.PROVEN_OPEN, "ev-20")

    assert LegacyInventoryClassifier.audit_readiness((r1, r2)) is True


def test_legacy_inventory_ambiguous_fails_readiness():
    r1 = LegacyInventoryRecord("ord-10", "order", LegacyEntityDisposition.PROVEN_CLOSED, "ev-10")
    r2 = LegacyInventoryRecord("pos-99", "position", LegacyEntityDisposition.AMBIGUOUS, "ev-99")

    assert LegacyInventoryClassifier.audit_readiness((r1, r2)) is False
