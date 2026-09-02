---
title: 'Stabilize Canonical Equity Time Fixture'
type: 'bugfix'
created: '2026-09-02'
status: 'done'
route: 'one-shot'
---

# Stabilize Canonical Equity Time Fixture

## Intent

**Problem:** Canonical-equity timestamp cases were created during pytest collection, so the one-minute `future_mark` aged into a valid past mark before its test ran late in the full suite.

**Approach:** Freeze the production clock per invocation, pin the configured mark-age policy, and construct deterministic numeric marks just outside the stale and future-skew boundaries while preserving fail-closed assertions.

## Suggested Review Order

- Review the frozen clock, pinned policy, and explicit case boundaries.
  [`test_canonical_equity.py:42`](../../advanced_crypto_bot/tests/test_canonical_equity.py#L42)

- Confirm pair-qualified fail-closed behavior remains asserted.
  [`test_canonical_equity.py:68`](../../advanced_crypto_bot/tests/test_canonical_equity.py#L68)
