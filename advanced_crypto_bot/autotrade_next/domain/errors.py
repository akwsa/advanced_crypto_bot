"""Stable, typed errors shared by pure domain contracts."""

from __future__ import annotations

from typing import TypeAlias


CanonicalPathPart: TypeAlias = str | int
CanonicalPath: TypeAlias = tuple[CanonicalPathPart, ...]


class CanonicalEncodingError(ValueError):
    """Reject a value that cannot have one unambiguous canonical encoding."""

    def __init__(self, code: str, *, path: CanonicalPath = ()) -> None:
        self.code = code
        self.error_code = code
        self.path = path
        self.partial_bytes = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = None
        self.correlation_id = None
        super().__init__(code)


class IdentityError(ValueError):
    """Reject an unknown identity recipe or an invalid recipe projection."""

    def __init__(self, code: str, *, kind: str, field: str | None = None) -> None:
        self.code = code
        self.error_code = code
        self.kind = kind
        self.field = field
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = None
        self.correlation_id = None
        super().__init__(code)


class CandidateCaptureError(ValueError):
    """Reject an incomplete or ambiguous Candidate capture atomically."""

    def __init__(
        self,
        code: str,
        *,
        path: CanonicalPath = (),
        evidence_ref: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.code = code
        self.error_code = code
        self.path = path
        self.partial_snapshot = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = evidence_ref
        self.correlation_id = correlation_id
        super().__init__(code)


class DecisionError(ValueError):
    """Reject an illegal or ambiguous Canonical Decision atomically."""

    def __init__(self, code: str, *, path: CanonicalPath = (), incident=None) -> None:
        self.code = self.error_code = code
        self.path = path
        self.incident = incident
        self.partial_decision = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = None
        self.correlation_id = None
        super().__init__(code)


class PolicyEvaluationError(ValueError):
    """Reject an incomplete or ambiguous policy transition atomically."""

    def __init__(
        self,
        code: str,
        *,
        path: CanonicalPath = (),
        evidence_ref: str | None = None,
    ) -> None:
        self.code = code
        self.error_code = code
        self.path = path
        self.partial_transition = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = evidence_ref
        self.correlation_id = None
        super().__init__(code)


class ReplayError(ValueError):
    """Reject an incomplete or non-deterministic replay contract atomically."""

    def __init__(self, code: str, *, path: CanonicalPath = ()) -> None:
        self.code = code
        self.error_code = code
        self.path = path
        self.partial_result = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = None
        self.correlation_id = None
        super().__init__(code)


class CapabilityRegistryError(ValueError):
    """Reject an ambiguous or unbound market capability atomically."""

    def __init__(self, code: str, *, path: CanonicalPath = ()) -> None:
        self.code = self.error_code = code
        self.path = path
        self.partial_result = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = None
        self.correlation_id = None
        super().__init__(code)


class MarketEvidenceError(ValueError):
    """Reject malformed, foreign, or non-content-bound market evidence."""

    def __init__(
        self,
        code: str,
        *,
        path: CanonicalPath = (),
        evidence_ref: str | None = None,
    ) -> None:
        self.code = self.error_code = code
        self.path = path
        self.partial_result = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = evidence_ref
        self.correlation_id = None
        super().__init__(code)


class RecoveryEvaluationError(ValueError):
    """Reject malformed recovery inputs without changing freeze state."""

    def __init__(self, code: str, *, path: CanonicalPath = ()) -> None:
        self.code = self.error_code = code
        self.path = path
        self.partial_result = None
        self.severity = "ERROR"
        self.retryable = False
        self.evidence_ref = None
        self.correlation_id = None
        super().__init__(code)
