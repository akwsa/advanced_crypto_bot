"""Qualified Runtime Artifact Contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from .content import ContentRef
from .errors import DecisionError


@dataclass(frozen=True, slots=True)
class QualifiedRuntimeManifest:
    artifact_id: str
    python_version: str
    sqlite_version: str
    lock_hash: str
    sbom_hash: str
    manifest_ref: ContentRef

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        python_version: str,
        sqlite_version: str,
        lock_hash: str,
        sbom_hash: str,
    ) -> QualifiedRuntimeManifest:
        if not python_version or not sqlite_version:
            raise DecisionError("INVALID_RUNTIME_VERSIONS")
        value = {
            "artifact_id": artifact_id,
            "python_version": python_version,
            "sqlite_version": sqlite_version,
            "lock_hash": lock_hash,
            "sbom_hash": sbom_hash,
        }
        manifest_ref = ContentRef.v2("runtime.manifest", "qualified-runtime-manifest", value)
        return cls(
            artifact_id=artifact_id,
            python_version=python_version,
            sqlite_version=sqlite_version,
            lock_hash=lock_hash,
            sbom_hash=sbom_hash,
            manifest_ref=manifest_ref,
        )


__all__ = ("QualifiedRuntimeManifest",)
