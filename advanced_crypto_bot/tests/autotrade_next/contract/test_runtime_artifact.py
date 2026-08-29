"""Contract tests for Story 5.2: Qualified Runtime Artifact."""

import pytest

from autotrade_next.domain.errors import DecisionError
from autotrade_next.domain.runtime_artifact import QualifiedRuntimeManifest


def test_qualified_runtime_manifest_creation():
    manifest = QualifiedRuntimeManifest.create(
        artifact_id="art-001",
        python_version="3.12.14",
        sqlite_version="3.53.4",
        lock_hash="hash-lock-123",
        sbom_hash="hash-sbom-456",
    )

    assert manifest.artifact_id == "art-001"
    assert manifest.python_version == "3.12.14"
    assert manifest.manifest_ref.domain == "runtime.manifest"


def test_qualified_runtime_manifest_empty_version_rejected():
    with pytest.raises(DecisionError) as exc_info:
        QualifiedRuntimeManifest.create(
            artifact_id="art-002",
            python_version="",
            sqlite_version="3.53.4",
            lock_hash="hash-lock-123",
            sbom_hash="hash-sbom-456",
        )
    assert exc_info.value.code == "INVALID_RUNTIME_VERSIONS"
