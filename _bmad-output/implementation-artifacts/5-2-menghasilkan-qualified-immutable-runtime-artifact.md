---
story_id: "5.2"
title: "Menghasilkan qualified immutable runtime artifact"
epic: "5"
status: "done"
baseline_commit: "79fd868"
---

# Story 5.2: Menghasilkan qualified immutable runtime artifact

Status: done

## Story

As a Officer,
I want build target dapat direproduksi dan diverifikasi sebelum menyentuh canonical store,
so that host, Docker, dependency, dan SQLite drift tidak mengubah behavior.

## Acceptance Criteria

1. **Qualified Immutable Runtime Artifact**:
   - Menghasilkan manifest kualifikasi runtime (`QualifiedRuntimeManifest`) yang memuat versi Python, SQLite, lock hash, dan SBOM hash secara immutable.
   - Verifikasi ketat (*fail-closed*) saat startup jika terjadi ketidakcocokan konfigurasi atau versi runtime.
