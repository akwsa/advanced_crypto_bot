"""Contract tests for Story 3.3: Portfolio Risk Governor."""

import pytest

from autotrade_next.domain.numeric import ScaledInteger
from autotrade_next.domain.risk_governor import RiskCheckReason, RiskGovernor


def test_risk_governor_approved():
    res = RiskGovernor.evaluate_entry(
        proposed_notional=ScaledInteger(50000, 2),        # 500.00 (5% of equity)
        current_portfolio_exposure=ScaledInteger(100000, 2), # 1000.00 (10% of equity)
        total_equity=ScaledInteger(1000000, 2),             # 10,000.00
    )
    assert res.allowed is True
    assert res.reason is RiskCheckReason.APPROVED


def test_risk_governor_exceeds_max_position():
    res = RiskGovernor.evaluate_entry(
        proposed_notional=ScaledInteger(150000, 2),       # 1500.00 (15% of equity > 10%)
        current_portfolio_exposure=ScaledInteger(0, 2),
        total_equity=ScaledInteger(1000000, 2),
    )
    assert res.allowed is False
    assert res.reason is RiskCheckReason.MAX_POSITION_EXCEEDED
