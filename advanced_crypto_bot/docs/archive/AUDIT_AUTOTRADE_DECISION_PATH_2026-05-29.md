# AUDIT: Autotrade Decision Path — Feature Coverage
**Date:** 2026-05-29
**Branch:** fix/scalper-sltp-telegram-ui

## Decision Flow (BUY path)

```
check_trading_opportunity() → runtime.py:421
  1. pre_sr_recommendation gate (line 474-477)
  2. should_execute_trade (line 573)
  3. analyze_market_intelligence → passes_entry_filter (line 579-595)
     [spread guard + volume + orderbook → overall_signal]
  4. Market regime detection (line 580)
  5. evaluate_autotrade_setup → should_skip (line 854-865)
     [volume_ratio, buy_sell_ratio, rr_after_fees]
  6. Post-optimization rr_after_fees re-check (line 891-898)
  7. V4 filter (line 755-785)
  8. Chase prevention (line 730-739)
  9. Correlation/heat check (line 741-753)
```

## Feature Status

| # | Feature | Status | Hard Block Location | Gap? |
|---|---------|--------|---------------------|------|
| 1 | Orderbook pressure / bid-ask imbalance | ✅ ACTIVE | `runtime.py:581-595`, `profit_optimizer.py:145-155` | None |
| 2 | Volume ratio/spike | ✅ ACTIVE | `runtime.py:581-595`, `profit_optimizer.py:145-155` | None |
| 3 | Fee-aware R/R | ✅ ACTIVE | `profit_optimizer.py:133-143`, `runtime.py:891-898` | None |
| 4 | Spread guard (SPREAD_TOO_WIDE) | ✅ ACTIVE | `runtime.py:581-595` (via override at `:1188-1189`) | None |
| 5a | pre_sr_recommendation | ✅ ACTIVE | `runtime.py:475-477` | None |
| 5b | signal_decision_layer (classify/context/result) | ⚠️ **GAP** | N/A — not wired | See below |

## GAP Detail: signal_decision_layer.py

`signal_decision_layer.py` defines rich position-aware types:
- `DecisionContext` with `position_state` (NO_POSITION/HAS_POSITION/UNKNOWN_POSITION), `pnl_pct`
- `DecisionResult` with `execution_allowed: bool`
- `classify_buy_signal_label()` → labels: PANTAU, BELI_BERTAHAP, BUY, STRONG_BUY
- `should_reject_duplicate_buy_signal()` → sets `duplicate_filtered=True`

**Problem:** These are NOT wired into autotrade execution:
- `classify_buy_signal_label()` sets `signal["display_recommendation"]` at `signal_pipeline.py:876`
- Autotrade NEVER reads `display_recommendation` or `duplicate_filtered`
- `DecisionResult.execution_allowed` is defined but never checked
- A signal labeled `PANTAU` or `duplicate_filtered=True` will still execute if `pre_sr_recommendation` says BUY/STRONG_BUY

## Recommendation

Wire `duplicate_filtered` and `execution_allowed` into `check_trading_opportunity()` as an additional gate, BEFORE the `pre_sr_recommendation` check. This prevents duplicate and non-actionable signals from reaching the autotrade execution path.
