# Verification Results — AutoTrade Replacement PRD

Date: 2026-08-25
Scope: PRD finalization and current brownfield regression baseline

## Focused AutoTrade Regression

Command:

```bash
advanced_crypto_bot/scripts/test.sh -q \
  tests/test_autotrade_dispatch_lifecycle.py \
  tests/test_autotrade_dryrun_signal_cycle.py \
  tests/test_autotrade_funnel.py \
  tests/test_autotrade_ledger.py \
  tests/test_open_position_sweep.py \
  tests/test_price_poller_canonical_positions.py \
  tests/test_runtime_price_guard.py \
  tests/test_signal_queue_recovery.py \
  tests/test_canonical_equity.py \
  tests/test_strategy2_contracts.py \
  tests/test_strategy2_isolation.py \
  tests/test_strategy2_repository.py \
  tests/test_strategy2_state_machine.py
```

Result: **132 passed**, 1 warning, 22 subtests passed in 6.63 seconds.

The warning is the Redis `retry_on_timeout` deprecation at `cache/redis_price_cache.py:70`.

## Full Repository Regression

Command:

```bash
advanced_crypto_bot/scripts/test.sh -q --tb=short
```

Result: **696 passed**, 14 failed, 5 errors, 25 warnings, 22 subtests passed in 38.00 seconds.

Failure groups:

| Group | Count | Observed cause |
|---|---:|---|
| Removed configuration helpers | 5 failures | `is_production_user_id` and `_filter_admin_ids` no longer importable |
| Removed quant-cache helper | 5 errors | `_quant_cache_clear` no longer importable |
| Adaptive-learning/trade-review fixtures | 3 failures | Foreign-key setup and performance-backfill expectation mismatch |
| AutoTrade notification mocks | 2 failures | Test bot lacks the now-required `db` dependency |
| VaR integration gates | 2 failures | Expected rejection but current gate allowed the trade |
| Signal decision label | 1 failure | Expected `BELI_BERTAHAP`, received `BUY` |
| Telegram sanitization | 1 failure | Raw `<` was not escaped to `&lt;` |

These failures are documented as the pre-implementation brownfield baseline. Finalizing this PRD changes documentation only and does not claim that the repository-wide runtime baseline is green.
