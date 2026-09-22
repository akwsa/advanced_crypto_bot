# OPERATIONS FLOW & ALGORITHMA

**Last Updated:** 2026-05-16  
**Purpose:** Detail flow operasi runtime, algoritma signal, trading, dan test policy.

## Perubahan Terbaru

- **2026-05-16 — Quant Trading Modules Integration:** 6 modul quantitative trading ditambahkan ke `quant/` dan diintegrasikan ke runtime:
  1. **Mean Reversion** (Z-Score) → aktif di `signal_quality_engine.py` confluence scoring (+0 to +2 bonus) dan `signal_pipeline.py` (confidence boost +2-4%)
  2. **Bayesian Kelly** → aktif di `autotrade/runtime.py` position sizing (adaptive per-pair)
  3. **Momentum Factor** → aktif di `autotrade/runtime.py` (reduce BUY size jika strong bearish momentum)
  4. **Dynamic Correlation** → aktif di `autotrade/runtime.py` `_check_correlated_exposure()` (rolling real-time correlation matrix)
  5. **Performance Analytics** → available via `/quant_perf` command (Sharpe, Sortino, Calmar)
  6. **Statistical Arbitrage** → available via `/quant_arb` command (cointegration + spread z-score)
  
  Telegram commands: `/quant`, `/quant_mr`, `/quant_kelly`, `/quant_momentum`, `/quant_perf`, `/quant_corr`, `/quant_arb`

- **2026-05-16 — Threshold Relaxation (Signal Delivery Fix):** Semua signal sebelumnya di-block oleh filter yang terlalu strict. Perubahan:
  - `SELL_MIN_CONFIDENCE`: 0.65 → 0.55 (signal_rules.py)
  - `STRONG_SELL_MIN_CONFIDENCE`: 0.80 → 0.70 (signal_rules.py)
  - `BUY_MIN_CONFIDENCE`: 0.60 → 0.55 (signal_rules.py)
  - `STRONG_BUY_MIN_CONFIDENCE`: 0.75 → 0.70 (signal_rules.py)
  - `STRONG_SELL_ML_CONFIDENCE`: 0.80 → 0.70 (signal_quality_engine.py)
  - `STRONG_BUY_ML_CONFIDENCE`: 0.75 → 0.70 (signal_quality_engine.py)
  - `SR_MIN_RR_RATIO`: 1.5 → 1.0 (config.py)
  - `SR_MIN_SL_PCT`: 0.3 → 0.1 (config.py)
  - `SR_NEAR_SUPPORT/RESISTANCE_PCT`: 2.0 → 1.0 (config.py)
  - `REGIME_VOLATILE`: 0.0 → 0.3 (config.py) — volatile market no longer blocks signals, just reduces position size
  - Enhancement max negative adjustment capped at -0.05 (signal_pipeline.py)

- **2026-05-05 — Opsi B (Asimetri threshold BUY-side):** Threshold confidence BUY diturunkan untuk mengimbangi bias bearish ML model. BUY=0.60, STRONG_BUY=0.75, SELL=0.65 (tetap), STRONG_SELL=0.80 (tetap). Terdampak: `@signals/signal_rules.py`, `@signals/signal_quality_engine.py`, `@signals/signal_filter_v2.py`, `@analysis/adaptive_learning.py` (default fallback). Regression test di `@tests/test_batch3_rule_rejections.py`.
- **2026-05-05 — Fix adaptive confidence gate (Opsi A):** `@signals/signal_pipeline.py` sebelumnya mereferensi `BUY_SELL_MIN_CONFIDENCE` / `STRONG_MIN_CONFIDENCE` tanpa import → `NameError` ditelan `try/except` → adaptive gate `ADAPTIVE_CONF` tidak pernah aktif (hanya `skip_pair` yang bekerja). Di-fix dengan import `min_confidence_for` dari `signal_rules` dan memakai fallback threshold per-arah ketika DB override tidak ada.

---

## 🔄 FLOW UTAMA

### 1. STARTUP SEQUENCE

```
┌─────────────────────────────────────────────────────────────┐
│ 1. bot.py main()                                            │
├─────────────────────────────────────────────────────────────┤
│ 2. Load Config → core/config.py                             │
│    - API keys (Telegram, Indodax, Claude)                   │
│    - Trading thresholds, risk limits                        │
├─────────────────────────────────────────────────────────────┤
│ 3. Init Database → core/database.py                         │
│    - SQLite: signals, trades, positions, performance        │
├─────────────────────────────────────────────────────────────┤
│ 4. Init API Clients                                         │
│    - IndodaxAPI (REST + WebSocket)                          │
│    - Telegram Bot API                                       │
├─────────────────────────────────────────────────────────────┤
│ 5. Load ML Models                                           │
│    - MLTradingModelV3 (backtesting)                         │
│    - MLTradingModelV4 (trade outcome)                       │
│    - SignalEnhancementEngine (Claude AI)                    │
│    - MeanReversionEngine (quant z-score, via QualityEngine) │
├─────────────────────────────────────────────────────────────┤
│ 6. Init Trading Components                                  │
│    - TradingEngine                                          │
│    - RiskManager                                            │
│    - Portfolio                                              │
│    - PriceMonitor                                           │
│    - Quant Engines (lazy-init at first use):                │
│      · BayesianKellyEngine (position sizing)                │
│      · MomentumFactorEngine (edge scoring)                  │
│      · DynamicCorrelationEngine (portfolio heat)            │
│      · PerformanceAnalytics (Sharpe/Sortino/Calmar)         │
│      · StatArbEngine (pair trading)                         │
├─────────────────────────────────────────────────────────────┤
│ 7. Init Specialized Modules                                 │
│    - ScalperModule                                          │
│    - SmartHunterBotIntegration                              │
│    - UltraHunterBotIntegration                              │
├─────────────────────────────────────────────────────────────┤
│ 8. Init Workers                                             │
│    - BackgroundWorker (async tasks)                         │
│    - PricePoller (price updates)                            │
│    - SignalQueue + Scheduler                                │
├─────────────────────────────────────────────────────────────┤
│ 9. Register Handlers → core/handler_registry.py             │
│    - Command handlers (/start, /signal, /buy, etc.)         │
│    - Callback query handlers (inline buttons)               │
│    - Message handlers                                       │
├─────────────────────────────────────────────────────────────┤
│ 10. Start Telegram Bot Polling                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📡 SIGNAL GENERATION FLOW

### Pipeline: `signals/signal_pipeline.py::generate_signal_for_pair()`

```
┌─────────────────────────────────────────────────────────────┐
│ INPUT: pair (e.g., "btcidr")                                │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Fetch Historical Data                               │
│ - Check bot.historical_data[pair]                           │
│ - If missing → return HOLD ("no data")                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Technical Analysis                                  │
│ File: analysis/technical_analysis.py                        │
│ - RSI, MACD, Bollinger Bands, ATR, ADX                      │
│ - Volume analysis, trend detection                          │
│ → Output: indicators dict                                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Support/Resistance Detection                        │
│ File: analysis/support_resistance.py                        │
│ - Detect key S/R levels                                     │
│ - Calculate distance to S/R (%)                             │
│ → Output: support_1, resistance_1                           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: ML Model Scoring                                    │
│ Files: analysis/ml_model_v3.py, ml_model_v4.py              │
│ - Feature engineering from indicators                       │
│ - ML prediction (BUY/SELL probability)                      │
│ - Base confidence score (0.0 - 1.0)                         │
│ → Output: recommendation, confidence                        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: AI Enhancement (Claude API)                         │
│ File: core/signal_enhancement_engine.py                     │
│ - Send indicators + ML result to Claude                     │
│ - Get AI-enhanced confidence adjustment                     │
│ - Apply directional adjustment (BUY→+, SELL→-)              │
│ → Output: enhanced_confidence, ai_reasoning                 │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: Signal Quality Check                                │
│ File: signals/signal_quality_engine.py                      │
│ - Quality score (0-100)                                     │
│ - Risk/reward ratio validation                              │
│ - Volatility check                                          │
│ → Output: quality_score, quality_details                    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 7: Final Rejection Gates                               │
│ File: signals/signal_rules.py                               │
│ - Stale price check (> 5 min old)                           │
│ - Low confidence threshold (< 0.55)                         │
│ - Poor risk/reward ratio (< 1.5)                            │
│ - High volatility rejection                                 │
│ → If rejected: recommendation = "HOLD"                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 8: Format & Store Signal                               │
│ - Save to DB (core/database.py)                             │
│ - Format message (signals/signal_formatter.py)              │
│ - Apply notification filter (BUY/SELL/actionable/all)       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ OUTPUT: signal dict                                         │
│ {                                                            │
│   "pair": "btcidr",                                          │
│   "recommendation": "BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL", │
│   "confidence": 0.75,                                        │
│   "quality_score": 85,                                       │
│   "support_1": 450000000,                                    │
│   "resistance_1": 480000000,                                 │
│   "reason": "AI reasoning...",                               │
│   "timestamp": "2026-04-30 10:30:00"                         │
│ }                                                            │
└─────────────────────────────────────────────────────────────┘
```

### Signal Notification Flow

```
autotrade/runtime.py::process_price_update_signal_tasks()
    │
    ├─ Check: _signal_notifications_enabled()
    │   → If disabled: skip notification
    │
    ├─ Check: _is_watched(pair)
    │   → If not watched: skip
    │
    ├─ Generate signal: _get_cached_signal(pair)
    │   → Cache 2 seconds to avoid duplicate API calls
    │
    ├─ Filter: _signal_passes_filter(recommendation)
    │   → User filter: all|buy|sell|actionable
    │
    └─ Send Telegram notification
        → format_signal_message_html()
```

---

## 💹 AUTO-TRADING FLOW

### Trading Opportunity Check: `autotrade/runtime.py::check_trading_opportunity()`

```
┌─────────────────────────────────────────────────────────────┐
│ INPUT: signal, pair                                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ GATE 1: Is Auto-Trade Enabled?                              │
│ - Check: bot.auto_trade_enabled == True                     │
│ - Check: pair in bot.auto_trade_pairs                       │
│ → If NO: return (skip trading)                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ GATE 2: Is Signal Actionable?                               │
│ - recommendation in [BUY, STRONG_BUY, SELL, STRONG_SELL]    │
│ - confidence >= Config.MIN_CONFIDENCE (0.55)                │
│ - quality_score >= Config.MIN_QUALITY (60)                  │
│ → If NO: return (signal too weak)                           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ GATE 3: Market Intelligence Check                           │
│ Function: analyze_market_intelligence()                     │
│ - Check market regime (trending/ranging/volatile)           │
│ - Validate current market conditions                        │
│ → If unfavorable: return (market not suitable)              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ GATE 4: Risk & Runtime Validation                           │
│ Files: autotrade/risk_manager.py, trading_engine.py         │
│ - Check portfolio exposure (max 30% per trade)              │
│ - Check max concurrent positions (default: 3)               │
│ - Check available balance                                   │
│ - Reject duplicate BUY when normalized pair already open    │
│ - Enforce local trading-hour window (default WIB UTC+7)     │
│ - Validate position sizing                                  │
│ → If rejected: return (risk/runtime limit exceeded)         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Calculate Order Size                                │
│ - Get available balance from Portfolio                      │
│ - Apply risk % (default: 10% of capital per trade)          │
│ - Calculate stop loss & take profit levels                  │
│ → Output: order_amount, stop_loss, take_profit              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: Execute Order                                        │
│ File: autotrade/trading_engine.py                           │
│ - If BUY: TradingEngine.execute_buy()                       │
│ - If SELL: TradingEngine.execute_sell()                     │
│ - API call to Indodax (via api/indodax_api.py)              │
│ → Output: order_id, fill_price, status                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 7: Update Portfolio & DB                               │
│ - Portfolio.add_position()                                  │
│ - Database.save_trade()                                     │
│ - Send Telegram notification (trade confirmation)           │
└─────────────────────────────────────────────────────────────┘
```

### Auto-Sell Monitoring: `autotrade/runtime.py::execute_auto_sell()`

```
Background Loop (every 30s)
    │
    ├─ Fetch all open positions from Portfolio
    │
    └─ For each position:
        │
        ├─ Get current price from PriceMonitor
        │
        ├─ Calculate current P&L
        │
        ├─ Check Exit Conditions:
        │   ├─ Take Profit Hit? (current_price >= take_profit)
        │   ├─ Stop Loss Hit? (current_price <= stop_loss)
        │   ├─ Trailing Stop? (dynamic adjustment)
        │   └─ Time-based Exit? (holding too long)
        │
        ├─ If exit triggered:
        │   ├─ Execute sell via TradingEngine
        │   ├─ Update Portfolio
        │   ├─ Save trade result to DB
        │   └─ Send Telegram notification
        │
        └─ Continue monitoring
```

---

## 🎯 SPECIALIZED MODULES FLOW

### Scalper Module: `scalper/scalper_module.py`

```
Trigger: High-frequency price movements
    │
    ├─ Detect micro-trends (< 5 min timeframe)
    ├─ Quick entry/exit (target: 0.5-2% profit)
    ├─ Tight stop loss (< 0.5%)
    └─ High volume requirement (avoid slippage)
```

### Smart Hunter: `autohunter/smart_hunter_integration.py`

```
Trigger: Strong signals on low-cap coins
    │
    ├─ Scan for momentum breakouts
    ├─ Validate volume surge (> 3x average)
    ├─ Quick profit taking (target: 3-5%)
    └─ Aggressive position sizing
```

### Ultra Hunter: `autohunter/ultra_hunter_integration.py`

```
Trigger: Extreme market conditions
    │
    ├─ Detect flash crashes / pumps
    ├─ Ultra-fast execution (< 1s)
    ├─ Maximum risk tolerance
    └─ Emergency exit if reversal
```

---

## 🧪 TEST POLICY

### Test Execution Rules

```bash
# 1. Test Modul Spesifik (Scalper)
pytest tests/test_scalper_dryrun_positions.py -v

# 2. Test Signal Pipeline
pytest tests/test_v4_integration.py -v

# 3. Test Safety (Dry-Run)
pytest tests/test_dryrun_safety.py -v

# 3b. Test TradingEngine/config regression
python -m unittest tests.test_bug_fixes_verification -v

# 4. Test Notification Controls
pytest tests/test_signal_notification_controls.py -v

# 5. Test UI Formatting
pytest tests/test_telegram_ui_formatting.py -v

# Full suite (run sparingly)
pytest tests/ -v
```

### Test Scope per Modul

| Modul Changed | Test to Run |
|---------------|-------------|
| `scalper/*` | `test_scalper_dryrun_positions.py` |
| `signals/*` | `test_v4_integration.py`, `test_signal_notification_controls.py` |
| `autotrade/*` | `test_dryrun_safety.py`, `test_bug_fixes_verification.py` |
| `core/config.py` | `test_bug_fixes_verification.py` |
| `analysis/ml_*` | `test_adaptive_learning.py`, `test_performance_backfill.py` |
| `bot_parts/formatting.py` | `test_telegram_ui_formatting.py` |

---

## 🔄 RESTART & RECOVERY FLOW

### Graceful Shutdown

```python
# Signal: SIGINT / SIGTERM
    │
    ├─ Stop PricePoller
    ├─ Stop BackgroundWorker
    ├─ Close WebSocket connections
    ├─ Save state to Redis (cache/redis_state_manager.py)
    ├─ Close database connections
    └─ Exit cleanly
```

### Recovery on Restart

```python
# bot.py startup
    │
    ├─ Load state from Redis
    ├─ Restore open positions from DB
    ├─ Re-subscribe to price feeds
    ├─ Resume signal monitoring
    └─ Continue normal operation
```

---

## 📊 MARKET REGIME DETECTION

Function: `autotrade/runtime.py::detect_market_regime()`

```
Input: OHLCV data (last 100 candles)
    │
    ├─ Calculate ATR (Average True Range)
    ├─ Calculate ADX (trend strength)
    ├─ Calculate Bollinger Band width
    │
    └─ Classification:
        ├─ TRENDING: ADX > 25, low BB width
        ├─ RANGING: ADX < 20, stable price
        ├─ VOLATILE: ATR > 2x avg, wide BB
        └─ CHOPPY: Low volume, no clear direction

Strategy Adjustment per Regime:
    │
    ├─ TRENDING → Follow trend, wider stops
    ├─ RANGING → Mean reversion, tight stops
    ├─ VOLATILE → Reduce position size, wait
    └─ CHOPPY → Avoid trading
```

---

## 📝 DOKUMENTASI UPDATE RULES

### When Code Changes → Update These Docs:

| Code Area Changed | Update Document |
|-------------------|-----------------|
| Startup sequence, core modules, DB schema | `SYSTEM_MAP.md` |
| Signal flow, trading flow, test policy | `OPERATIONS_FLOW_ALGORITHMA.md` (this file) |
| Telegram commands, callbacks | `COMMAND_REFERENCE.md` |
| Doc standards, header format | `DOCUMENTATION_RULES.md` |

### Example: Adding New Signal Filter

```python
# 1. Edit: signals/signal_rules.py
# 2. Test: pytest tests/test_v4_integration.py
# 3. Update SYSTEM_MAP.md → Add new function to signals/ table
# 4. Update OPERATIONS_FLOW_ALGORITHMA.md → Add to "STEP 7: Final Rejection Gates"
# 5. Git commit with clear message
```

---

**Navigation:**
- Prev: `SYSTEM_MAP.md` (indeks modul)
- Next: `COMMAND_REFERENCE.md` (Telegram commands)
