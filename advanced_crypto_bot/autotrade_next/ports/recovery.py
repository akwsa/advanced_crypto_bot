"""External authorization boundary for sensitive recovery corrections."""

from __future__ import annotations

from typing import Protocol

from autotrade_next.domain.recovery import CorrectionRequest


class CorrectionApprovalVerifier(Protocol):
    """Resolve an approval reference through an authenticated authority."""

    def verify_correction(self, request: CorrectionRequest) -> bool:
        """Return true only when evidence, target, and approval are authorized."""
        ...


__all__ = ("CorrectionApprovalVerifier",)
