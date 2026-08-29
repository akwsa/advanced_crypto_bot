"""Policy Promotion and Authority Governance Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum

from .errors import DecisionError


class PolicyAuthorityState(str, Enum):
    SHADOW_ONLY = "SHADOW_ONLY"
    PROMOTED_LIVE = "PROMOTED_LIVE"
    DEMOTED = "DEMOTED"


@dataclass(frozen=True, slots=True)
class PolicyPromotionRecord:
    policy_id: str
    report_id: str
    state: PolicyAuthorityState
    approved_by_actor: str
    reason: str
    promoted_at_utc: datetime

    @classmethod
    def promote(
        cls,
        *,
        policy_id: str,
        report_id: str,
        approved_by_actor: str,
        reason: str,
        promoted_at_utc: datetime,
        is_conjunctive_pass: bool,
    ) -> PolicyPromotionRecord:
        if not is_conjunctive_pass:
            raise DecisionError("NON_PROMOTABLE_REPORT_DENIED")
        if not approved_by_actor:
            raise DecisionError("MISSING_HUMAN_APPROVAL_ACTOR")
        return cls(
            policy_id=policy_id,
            report_id=report_id,
            state=PolicyAuthorityState.PROMOTED_LIVE,
            approved_by_actor=approved_by_actor,
            reason=reason,
            promoted_at_utc=promoted_at_utc,
        )


__all__ = (
    "PolicyAuthorityState",
    "PolicyPromotionRecord",
)
