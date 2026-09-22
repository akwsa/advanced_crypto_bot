# AUDIT: Autotrade Decision Path — Feature Coverage
**Date:** 2026-05-29
**Updated:** 2026-05-30
**Branch:** fix/scalper-sltp-telegram-ui

## Decision Flow (BUY path)

```
check_trading_opportunity() → runtime.py:421
  1. decision-layer execution gate
     - duplicate_filtered=True → block
     - execution_allowed=False → block
     - display_recommendation=PANTAU → block
  2. pre_sr_recommendation gate
  3. should_execute_trade
  4. analyze_market_intelligence → passes_entry_filter
     [spread guard + volume + orderbook → overall_signal]
  5. Market regime detection
  6. evaluate_autotrade_setup → should_skip
     [volume_ratio, buy_sell_ratio, rr_after_fees]
  7. Post-optimization rr_after_fees re-check
  8. V4 filter
  9. Chase prevention
  10. Correlation/heat check
```

## Feature Status

| # | Feature | Status | Hard Block Location | Gap? |
|---|---------|--------|---------------------|------|
| 1 | Orderbook pressure / bid-ask imbalance | ✅ ACTIVE | `runtime.py` market-intelligence gate, `profit_optimizer.py` | None |
| 2 | Volume ratio/spike | ✅ ACTIVE | `runtime.py` market-intelligence gate, `profit_optimizer.py` | None |
| 3 | Fee-aware R/R | ✅ ACTIVE | `profit_optimizer.py`, `runtime.py` post-optimization R/R check | None |
| 4 | Spread guard (SPREAD_TOO_WIDE) | ✅ ACTIVE | `runtime.py` market-intelligence gate | None |
| 5a | pre_sr_recommendation | ✅ ACTIVE | `runtime.py` pre-SR execution recommendation gate | None |
| 5b | signal_decision_layer outputs | ✅ ACTIVE | `runtime.py` decision-layer execution gate | Fixed 2026-05-30 |

## Fix Detail: signal_decision_layer.py → autotrade runtime

`signal_decision_layer.py` defines position-aware and duplicate-suppression outputs:
- `DecisionResult.execution_allowed: bool`
- `classify_buy_signal_label()` → labels: PANTAU, BELI_BERTAHAP, BUY, STRONG_BUY
- `should_reject_duplicate_buy_signal()` → sets `duplicate_filtered=True`

Autotrade now reads decision-layer output before `pre_sr_recommendation` can promote a signal into the execution path:
- `duplicate_filtered=True` blocks execution and records the duplicate reason.
- `execution_allowed=False` blocks execution and records the decision reason.
- `display_recommendation="PANTAU"` blocks execution even when `pre_sr_recommendation` is BUY/STRONG_BUY.

## Regression Coverage

Added regression tests in `tests/test_autotrade_dryrun_signal_cycle.py`:
- duplicate-filtered BUY/STRONG_BUY signals do not open DRY RUN trades.
- `execution_allowed=False` signals do not open DRY RUN trades.
- `display_recommendation=PANTAU` does not open DRY RUN trades even if `pre_sr_recommendation=STRONG_BUY`.

Verified with:

```bash
./scripts/test.sh tests/test_autotrade_dryrun_signal_cycle.py::TestAutoTradeDryRunSignalCycle::test_duplicate_filtered_signal_does_not_open_dryrun_trade \
  tests/test_autotrade_dryrun_signal_cycle.py::TestAutoTradeDryRunSignalCycle::test_execution_allowed_false_signal_does_not_open_dryrun_trade \
  tests/test_autotrade_dryrun_signal_cycle.py::TestAutoTradeDryRunSignalCycle::test_pantau_display_signal_does_not_open_dryrun_trade_even_when_pre_sr_buy -q

./scripts/test.sh tests/test_autotrade_dryrun_signal_cycle.py tests/test_autotrade_status_watchlist.py tests/test_scalper_dryrun_positions.py tests/test_orderbook_market_intelligence.py -q

venv/bin/python - <<'PY'
import autotrade.runtime
from autotrade.runtime import check_trading_opportunity
print('import ok', callable(check_trading_opportunity))
PY
```
