---
title: 'Stabilize Historical Performance Backfill Fixture'
type: 'bugfix'
created: '2026-09-01'
status: 'done'
route: 'one-shot'
---

# Stabilize Historical Performance Backfill Fixture

## Intent

**Problem:** The FIFO performance-backfill regression test used a fixed historical SELL timestamp but retrieved results through a rolling 30-day query, causing the test to fail as the fixture aged even though backfill succeeded.

**Approach:** Keep deterministic, chronologically valid historical BUY and SELL fixtures, then verify the rebuilt aggregate for the exact SELL date and assert its complete core metrics.

## Suggested Review Order

- Review the deterministic FIFO chronology and exact-date aggregate contract.
  [`test_performance_backfill.py:80`](../../advanced_crypto_bot/tests/test_performance_backfill.py#L80)

- Confirm the rebuilt daily metrics are validated without a wall-clock-dependent rolling filter.
  [`test_performance_backfill.py:110`](../../advanced_crypto_bot/tests/test_performance_backfill.py#L110)
