"""Contract tests for Story 4.1: Experiment Specification and Universe Freezing."""

import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.experiment import EvidenceSpecification


def test_evidence_specification_freeze():
    spec = EvidenceSpecification.freeze(
        experiment_id="exp-001",
        version=1,
        opportunity_universe=("BTC-IDR", "ETH-IDR"),
        horizon_minutes=60,
        seed=42,
    )

    assert spec.experiment_id == "exp-001"
    assert spec.opportunity_universe == ("BTC-IDR", "ETH-IDR")
    assert spec.spec_ref.domain == "experiment.spec"


def test_evidence_specification_empty_universe_rejected():
    with pytest.raises(DecisionError) as exc_info:
        EvidenceSpecification.freeze(
            experiment_id="exp-002",
            version=1,
            opportunity_universe=(),
            horizon_minutes=60,
            seed=42,
        )
    assert exc_info.value.code == "EMPTY_OPPORTUNITY_UNIVERSE"
