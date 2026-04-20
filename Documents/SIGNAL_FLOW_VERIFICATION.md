# 🔍 Signal Generation & ML Training Flow - Verification Report

**Date**: 2026-04-14  
**Status**: ✅ VERIFIED & WORKING

---

## 📊 Signal Generation Flow (End-to-End)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: Main Bot (bot.py)                                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Function: _generate_signal_for_pair() (line 6950)                          │
│                                                                              │
│  1. Fetch OHLCV price data (CoinGecko/Indodax)                              │
│  2. Get real-time price (API → WebSocket → fallback)                        │
│  3. Technical Analysis (RSI, MACD, MA, BB, Volume)                          │
│  4. ML Prediction (ML Model V2)                                             │
│     • Returns: (prediction, confidence, signal_class)                      │
│  5. Trading Engine generates combined signal                               │
│     • Calculates combined_strength = (TA × 0.6) + (ML × 0.4)                │
│     • Returns: BUY/HOLD/SELL/STRONG_BUY/STRONG_SELL                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: Signal Quality Engine V3 (signals/signal_quality_engine.py)        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Function: generate_signal() (line 78)                                      │
│                                                                              │
│  VALIDATION CHECKS:                                                          │
│  ✅ Cooldown period (30 menit antar signal)                                  │
│  ✅ RSI Protection (no BUY saat OVERBOUGHT)                                  │
│  ✅ Volume Confirmation (warning jika tidak HIGH)                           │
│  ✅ ML vs TA Conflict Detection                                              │
│     • BUY + TA bearish (< -0.20) = HOLD                                     │
│     • SELL + TA bullish (> 0.20) = HOLD                                      │
│  ✅ Confluence Scoring (DIRECTIONAL - FIXED!)                               │
│     • BUY: Check RSI OVERSOLD, MACD BULLISH, dll (+ poin)                  │
│     • SELL: Check RSI OVERBOUGHT, MACD BEARISH, dll (+ poin)               │
│  ✅ Final Threshold Validation                                              │
│     • STRONG_BUY: score ≥6, conf ≥80%, strength ≥0.65                     │
│     • BUY: score ≥4, conf ≥70%, strength ≥0.30                            │
│     • SELL: score ≥4, conf ≥70%, strength ≤-0.30                          │
│     • STRONG_SELL: score ≥6, conf ≥80%, strength ≤-0.65                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: Signal Stabilization (bot.py line 7050)                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│  • Prevent signal jumping (HOLD → STRONG_BUY → SELL)                         │
│  • Increase jump threshold (5 → 7)                                         │
│  • "2 consecutive cycles" concept (tidak langsung downgrade)                 │
│  • Allow HOLD → STRONG_BUY jika confidence > 70%                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 4: Support & Resistance Detection (bot.py line 7230)                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Function: sr_detector.detect_levels()                                      │
│                                                                              │
│  • Auto-detect S/R levels dari historical data                              │
│  • Adds: support_1, support_2, resistance_1, resistance_2                    │
│  • Adds: price_zone, risk_reward_ratio                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 5: Signal Saving for ML Training (bot.py line 7261)                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Database: SignalDatabase (signals/signal_db.py)                            │
│  Table: signals                                                              │
│                                                                              │
│  SAVED DATA:                                                                 │
│  ├── symbol (pair name)                                                      │
│  ├── price (signal price)                                                   │
│  ├── recommendation (BUY/HOLD/SELL/STRONG_BUY/STRONG_SELL)                  │
│  ├── rsi (RSI status)                                                         │
│  ├── macd (MACD status)                                                      │
│  ├── ma_trend (MA trend direction)                                           │
│  ├── bollinger (Bollinger Bands status)                                      │
│  ├── volume (volume status)                                                  │
│  ├── ml_confidence (ML prediction confidence)                                │
│  ├── combined_strength (TA+ML combined)                                      │
│  ├── analysis (signal reason)                                                │
│  ├── signal_time, received_at, received_date (timestamps)                    │
│  └── source (telegram/auto)                                                  │
│                                                                              │
│  DUPLICATE DETECTION:                                                        │
│  • Key: (date, symbol, recommendation, price)                                │
│  • Same day + same symbol + same rec + same price = duplicate               │
│  • Duplicates skipped (return -1)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 6: Signal Queue (Optional) (signals/signal_queue.py)                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Function: push_signal()                                                      │
│                                                                              │
│  • Strong signals (STRONG_BUY/STRONG_SELL) → masuk Redis queue              │
│  • Workers process queue untuk execute trade                                 │
│  • Priority: STRONG=10, BUY/SELL=5                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 7: Telegram Notification (bot.py _format_signal_message)             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│  • Signal dikirim ke Telegram dengan format yang readable                   │
│  • Includes: Price, Indicators, ML Confidence, S/R Levels                 │
│  • Includes: Quality Engine status (approved/filtered)                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 ML Training Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ML TRAINING DATA SOURCES                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SOURCE 1: Price History (OHLCV)                                              │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Location: data/trading.db → price_history table                             │
│  Used by: ml_model_v2.py, ml_model.py                                        │
│  Purpose: Technical feature calculation (RSI, MACD, MA, BB, Volume)         │
│                                                                              │
│  Training:                                                                    │
│  • Fetch price data: db.get_price_history(pair, limit=5000)                 │
│  • Prepare features: prepare_features()                                      │
│  • Train model: model.train(df)                                              │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SOURCE 2: Signal History (for Signal Analyzer)                              │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Location: data/signals.db → signals table                                   │
│  Used by: signal_analyzer.py, tools/analyze_signals.py                      │
│  Purpose: Analyze historical signal accuracy                                  │
│                                                                              │
│  Analysis:                                                                    │
│  • Win rate per pair                                                         │
│  • Average profit/loss                                                       │
│  • Optimal hold time                                                         │
│  • Signal quality score                                                      │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SOURCE 3: Signal Training (ML Trainer - Alternative)                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Location: data/signals.db → signals table                                   │
│  Used by: tools/ml_trainer.py (STANDALONE)                                   │
│  Purpose: Train model dari TA signals (experimental)                         │
│                                                                              │
│  ⚠️  Note: ml_trainer.py menggunakan approach berbeda!                         │
│     • ml_model_v2.py: Features dari OHLCV (PRODUCTION)                        │
│     • ml_trainer.py: Features dari TA signals (EXPERIMENTAL)                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ✅ Verification Checklist

### Signal Generation
- [x] Bot fetches fresh price data (CoinGecko/Indodax)
- [x] Technical Analysis produces correct indicators
- [x] ML Model produces prediction with confidence
- [x] Trading Engine combines TA + ML correctly
- [x] Combined strength calculation: (TA × 0.6) + (ML × 0.4)
- [x] Signal classification: STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL

### Signal Quality Engine
- [x] Cooldown period enforced (30 min)
- [x] RSI protection working (no BUY when OVERBOUGHT)
- [x] Confluence scoring directional (BUY vs SELL different logic) ✅ FIXED
- [x] ML vs TA conflict detection active
- [x] Threshold validation enforced

### Signal Saving
- [x] All signals saved to signals.db
- [x] Duplicate detection active (same day/symbol/rec/price)
- [x] Complete data saved (TA indicators + ML confidence)
- [x] Timestamps recorded (signal_time, received_at, received_date)
- [x] S/R levels saved (support_1, resistance_1, etc.)

### ML Training Data
- [x] Price history saved to trading.db
- [x] Signals saved to signals.db
- [x] Data available for model retraining (24h interval)
- [x] Auto-retrain triggered periodically
- [x] Signal quality analyzer can access data

---

## 📁 Module Responsibilities

| Module | Responsibility | Status |
|--------|----------------|--------|
| `bot.py` | Main signal generation flow, orchestration | ✅ Working |
| `trading/trading_engine.py` | Combine TA + ML, calculate combined_strength | ✅ Working |
| `signals/signal_quality_engine.py` | Quality filters, confluence scoring | ✅ Fixed |
| `signals/signal_db.py` | Save signals to SQLite database | ✅ Working |
| `signals/signal_queue.py` | Queue strong signals for processing | ✅ Working |
| `analysis/ml_model_v2.py` | ML prediction from price data | ✅ Fixed |
| `analysis/signal_analyzer.py` | Analyze historical signal accuracy | ✅ Fixed |
| `analysis/technical_analysis.py` | Calculate TA indicators | ✅ Working |

---

## 🎓 Key Design Decisions

### 1. Two Databases
- **trading.db**: Price history, trades, portfolio (operational data)
- **signals.db**: Signal history (ML training data + analysis)

### 2. ML Training Approach
- **Primary**: OHLCV price data → Technical features → ML prediction
- **Secondary**: Signal history → Quality analysis (win rate, etc.)

### 3. Signal Storage Strategy
- **All signals saved**: HOLD, BUY, SELL, STRONG_BUY, STRONG_SELL
- **Purpose**: Historical analysis + ML model evaluation
- **Dedup**: Same day + same recommendation + same price = duplicate

### 4. Quality Control Layers
- **Layer 1**: Trading Engine (basic threshold)
- **Layer 2**: Signal Quality Engine V3 (advanced filters)
- **Layer 3**: Signal Stabilization (anti-jumping)

---

## 🔍 Testing Commands

```bash
# Check signal database
sqlite3 data/signals.db "SELECT COUNT(*) FROM signals;"
sqlite3 data/signals.db "SELECT * FROM signals ORDER BY id DESC LIMIT 5;"

# Check price history database
sqlite3 data/trading.db "SELECT COUNT(*) FROM price_history;"
sqlite3 data/trading.db "SELECT * FROM price_history ORDER BY timestamp DESC LIMIT 5;"

# Analyze signal quality
python tools/analyze_signals.py

# Run signal flow tests
python tests/test_signal_flow.py
```

---

## 📊 Sample Signal Data Structure

```json
{
  "id": 1234,
  "symbol": "BTCIDR",
  "price": 950000000,
  "recommendation": "STRONG_BUY",
  "rsi": "OVERSOLD",
  "macd": "BULLISH",
  "ma_trend": "BULLISH",
  "bollinger": "LOWER_BAND",
  "volume": "HIGH",
  "ml_confidence": 0.82,
  "combined_strength": 0.71,
  "analysis": "Strong bullish signals (TA: +0.85, ML: 82%)",
  "signal_time": "14:32:15",
  "received_at": "2026-04-14 14:32:15",
  "received_date": "2026-04-14",
  "source": "telegram"
}
```

---

## 🐛 Known Issues (Fixed)

### Issue #1: Confluence Scoring Directional Bias
**Status**: ✅ FIXED  
**Date**: 2026-04-14  
**Problem**: Confluence scoring hanya untuk BUY signals  
**Fix**: Ditambahkan parameter `signal_direction` untuk SELL logic

### Issue #2: SELL Signal Analysis
**Status**: ✅ FIXED  
**Date**: 2026-04-14  
**Problem**: Signal Analyzer menggunakan logika BUY untuk SELL  
**Fix**: Short selling logic untuk SELL signals

### Issue #3: ML Model V2 Predict Method
**Status**: ✅ FIXED  
**Date**: 2026-04-14  
**Problem**: predict() method salah untuk binary classification  
**Fix**: Ditambahkan `use_multi_class` parameter

---

## ✅ Final Verification Status

**Signal Generation**: ✅ WORKING  
**Signal Quality Engine**: ✅ WORKING  
**Signal Saving**: ✅ WORKING  
**ML Training Data**: ✅ AVAILABLE  
**Signal Analysis**: ✅ WORKING  

**All modules verified and functioning correctly!**

---

**Last Updated**: 2026-04-14
**Verified By**: Claude Code
