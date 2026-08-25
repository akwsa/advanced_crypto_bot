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
