---
story_id: "3.1"
title: "Menegakkan fenced command authority"
epic: "3"
status: "done"
baseline_commit: "7da4fe9"
---

# Story 3.1: Menegakkan fenced command authority

Status: done

## Story

As a Officer,
I want hanya satu writer epoch dapat melakukan canonical mutation,
so that restart, takeover, atau network partition tidak menciptakan split brain.

## Acceptance Criteria

1. **Fenced Writer Authority**:
   - Menegakkan `FencedWriterAuthority` yang mengelola `epoch` dan `lease_token` secara monotonik.
   - Penolakan mutasi mutlak (*fail-closed*) jika epoch/token yang dibawa oleh command lebih kecil dari epoch aktif (*stale epoch*).
