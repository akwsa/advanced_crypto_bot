"""Contract tests for Story 4.4: Leakage-Safe Comparison."""

import pytest

from autotrade_next.domain.comparison import CommonComparisonResult


def test_comparison_promotable():
    res = CommonComparisonResult.evaluate(
        experiment_id="exp-001",
        total_samples=1000,
        unscorable_samples=30,  # 3% <= 5%
    )
    assert res.is_promotable is True


def test_comparison_unscorable_breach_non_promotable():
    res = CommonComparisonResult.evaluate(
        experiment_id="exp-001",
        total_samples=1000,
        unscorable_samples=60,  # 6% > 5%
    )
    assert res.is_promotable is False
