"""Portfolio Risk Governor and Exposure Limit Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .numeric import ScaledInteger


class RiskCheckReason(str, Enum):
    APPROVED = "APPROVED"
    MAX_POSITION_EXCEEDED = "MAX_POSITION_EXCEEDED"
    MAX_EXPOSURE_EXCEEDED = "MAX_EXPOSURE_EXCEEDED"
    DAILY_LOSS_EXCEEDED = "DAILY_LOSS_EXCEEDED"
    HARD_DRAWDOWN_BREACH = "HARD_DRAWDOWN_BREACH"


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    allowed: bool
    reason: RiskCheckReason


class RiskGovernor:
    # Baseline constraints: Position <= 10%, Portfolio Exposure <= 40%
    MAX_POSITION_RATIO_BPS = 1000  # 10%
    MAX_PORTFOLIO_EXPOSURE_BPS = 4000  # 40%

    @classmethod
    def evaluate_entry(
        self,
        *,
        proposed_notional: ScaledInteger,
        current_portfolio_exposure: ScaledInteger,
        total_equity: ScaledInteger,
    ) -> RiskEvaluationResult:
        if total_equity.units <= 0:
            return RiskEvaluationResult(allowed=False, reason=RiskCheckReason.HARD_DRAWDOWN_BREACH)

        # Position limit <= 10% of equity
        max_pos_units = (total_equity.units * self.MAX_POSITION_RATIO_BPS) // 10000
        if proposed_notional.units > max_pos_units:
            return RiskEvaluationResult(allowed=False, reason=RiskCheckReason.MAX_POSITION_EXCEEDED)

        # Portfolio exposure <= 40% of equity
        new_exposure_units = current_portfolio_exposure.units + proposed_notional.units
        max_exp_units = (total_equity.units * self.MAX_PORTFOLIO_EXPOSURE_BPS) // 10000
        if new_exposure_units > max_exp_units:
            return RiskEvaluationResult(allowed=False, reason=RiskCheckReason.MAX_EXPOSURE_EXCEEDED)

        return RiskEvaluationResult(allowed=True, reason=RiskCheckReason.APPROVED)


__all__ = (
    "RiskCheckReason",
    "RiskEvaluationResult",
    "RiskGovernor",
)
