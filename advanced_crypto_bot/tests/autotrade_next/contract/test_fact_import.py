"""Contract tests for Story 5.4: Proven Fact Import."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.fact_import import ApprovedExternalFact


def test_approved_external_fact_import_proven():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    fact = ApprovedExternalFact.import_proven(
        fact_id="fact-001",
        legacy_reference_id="leg-trade-123",
        instrument_id="BTC-IDR",
        fact_type="EXECUTION_FILL",
        imported_at_utc=now,
        is_proven=True,
    )

    assert fact.fact_id == "fact-001"
    assert fact.legacy_reference_id == "leg-trade-123"
    assert fact.fact_ref.domain == "fact.import"


def test_unproven_legacy_fact_import_rejected():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    with pytest.raises(DecisionError) as exc_info:
        ApprovedExternalFact.import_proven(
            fact_id="fact-002",
            legacy_reference_id="leg-trade-999",
            instrument_id="BTC-IDR",
            fact_type="EXECUTION_FILL",
            imported_at_utc=now,
            is_proven=False,
        )
    assert exc_info.value.code == "UNPROVEN_LEGACY_FACT_DENIED"
