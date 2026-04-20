# 🔧 Signal Generation & Decision Flow - Fix Summary

**Date**: 2026-04-14  
**Status**: ✅ CRITICAL ISSUES FIXED

---

## Issues Found & Fixed

### 1. 🐛 CRITICAL: Confluence Score Directional Bias

**Problem**:  
Fungsi `_calculate_confluence_score()` menggunakan **scoring yang sama** untuk BUY dan SELL signals, hanya menambah poin untuk kondisi bullish (RSI OVERSOLD, MACD BULLISH, dll). Ini menyebabkan:
- SELL signals mendapat confluence score rendah (salah perhitungan)
- SELL signals sering di-reject karena score tidak memenuhi threshold
- Sinyal bearish tidak terdeteksi dengan benar

**Contoh Bug**:
```python
# Setup SELL sempurna: RSI OVERBOUGHT, MACD BEARISH
# Tapi score hanya 1 (dari volume) karena logika hanya check kondisi bullish!
```

**Fix**:  
Ditambahkan parameter `signal_direction` untuk scoring yang berbeda:
```python
def _calculate_confluence_score(..., signal_direction: str = 'BUY'):
    if signal_direction == 'BUY':
        # RSI OVERSOLD (+2), MACD BULLISH (+2), MA BULLISH (+1)
        # Bollinger OVERSOLD/LOWER_BAND (+1)
    else:  # SELL
        # RSI OVERBOUGHT (+2), MACD BEARISH (+2), MA BEARISH (+1)
        # Bollinger OVERBOUGHT/UPPER_BAND (+1)
    # Volume HIGH (+1) dan ML Confidence >= 70% (+1) untuk keduanya
```

**File**: `signals/signal_quality_engine.py` (line 215-290)

---

### 2. 📝 Typo di Comment

**Problem**:  
`STRONG_BAY` (typo) seharusnya `STRONG_BUY` di comment.

**Fix**:  
```python
# STRONG_BUY validation  # Fixed from STRONG_BAY
if ml_signal_class == 'STRONG_BUY':
```

**File**: `signals/signal_quality_engine.py` (line 303)

---

### 3. 🐛 Missing HOLD Signal Handling

**Problem**:  
Signal Quality Engine tidak menangani HOLD signals dari ML model dengan baik. Ketika `ml_signal_class` adalah HOLD atau None, fungsi `_determine_final_signal()` me-return default HOLD tanpa proper handling.

**Fix**:  
Ditambahkan explicit handling untuk HOLD signals:
```python
# HOLD signal - pass through directly (no validation needed)
if ml_signal_class == 'HOLD' or ml_signal_class is None:
    return {'type': 'HOLD', 'recommendation': 'HOLD', 'confluence': confluence_score}
```

**File**: `signals/signal_quality_engine.py` (line 303-305)

---

### 4. 🔄 Signal Direction Passing

**Problem**:  
Call ke `_calculate_confluence_score()` tidak mengirim parameter `signal_direction`, sehingga selalu pakai default 'BUY'.

**Fix**:  
```python
# Determine signal direction for proper confluence calculation
signal_direction = 'BUY' if ml_signal_class in ['BUY', 'STRONG_BUY'] else 'SELL'

confluence_score = self._calculate_confluence_score(
    rsi, macd, ma_trend, bollinger, volume, ml_confidence, ta_strength,
    signal_direction=signal_direction
)
```

**File**: `signals/signal_quality_engine.py` (line 190-197)

---

## Signal Flow Architecture (Fixed)

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Data Collection                                        │
│  - Fetch OHLCV price data                                       │
│  - Technical Analysis (RSI, MACD, MA, BB, Volume)               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: ML Prediction                                          │
│  - ML Model V2 predicts signal class                            │
│  - Returns: (prediction, confidence, signal_class)              │
│  - Example: (True, 0.75, 'BUY')                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Trading Engine (Combined Strength)                     │
│  - TA Strength × 0.6 + ML Strength × 0.4                        │
│  - ML Strength = direction × confidence                         │
│    • BUY: +1.0 × confidence                                     │
│    • SELL: -1.0 × confidence                                    │
│    • HOLD: 0                                                    │
│  - Generate: STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Signal Quality Engine V3                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  4a. Cooldown Check (30 min antar signal)               │    │
│  │  4b. RSI Protection (no BUY when OVERBOUGHT)            │    │
│  │  4c. Volume Confirmation (warning if not HIGH)          │    │
│  │  4d. ML vs TA Conflict Detection                      │    │
│  │      • BUY + TA bearish = HOLD                        │    │
│  │      • SELL + TA bullish = HOLD                         │    │
│  │  4e. Confluence Scoring (DIRECTIONAL - FIXED!)          │    │
│  │      • BUY: Check bullish indicators (+ poin)         │    │
│  │      • SELL: Check bearish indicators (+ poin)        │    │
│  │  4f. Final Signal Validation                          │    │
│  │      • STRONG_BUY: score ≥6, conf ≥80%, strength ≥0.65│    │
│  │      • BUY: score ≥4, conf ≥70%, strength ≥0.30     │    │
│  │      • SELL: score ≥4, conf ≥70%, strength ≤-0.30    │    │
│  │      • STRONG_SELL: score ≥6, conf ≥80%, strength ≤-0.65│   │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: Signal Stabilization (bot.py)                         │
│  - Prevent signal jumping (HOLD → STRONG_BUY → SELL)            │
│  - Require consecutive confirmations                            │
│  - Time-based stability checks                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: Output                                                 │
│  - Save to signals.db                                           │
│  - Send Telegram notification                                   │
│  - Execute trade (if auto-trading enabled)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Thresholds Reference

### Trading Engine Thresholds (combined_strength based)
```python
STRONG_THRESHOLD = 0.45       # For STRONG_BUY/STRONG_SELL
MODERATE_THRESHOLD = 0.20     # For BUY/SELL
ML_STRONG_THRESHOLD = 0.65    # Minimum confidence for STRONG signals
```

### Signal Quality Engine Thresholds
```python
# Confluence Score Requirements
CONFLUENCE_MINIMUM_BUY = 4    # Minimum 4 points for BUY
CONFLUENCE_MINIMUM_SELL = 4   # Minimum 4 points for SELL
CONFLUENCE_STRONG_BUY = 6     # Minimum 6 points for STRONG_BUY
CONFLUENCE_STRONG_SELL = 6    # Minimum 6 points for STRONG_SELL

# Combined Strength Requirements
STRONG_BUY_COMBINED_STRENGTH = 0.65
BUY_COMBINED_STRENGTH = 0.30
STRONG_SELL_COMBINED_STRENGTH = -0.65
SELL_COMBINED_STRENGTH = -0.30

# Confidence Requirements
STRONG_BUY_ML_CONFIDENCE = 0.80
BUY_ML_CONFIDENCE = 0.70
STRONG_SELL_ML_CONFIDENCE = 0.80
SELL_ML_CONFIDENCE = 0.70
```

### Confluence Scoring (Max 8 points)
| Indicator | BUY Direction | SELL Direction | Poin |
|-----------|--------------|----------------|------|
| RSI | OVERSOLD | OVERBOUGHT | +2 |
| MACD | BULLISH | BEARISH | +2 |
| MA Trend | BULLISH | BEARISH | +1 |
| Bollinger | LOWER_BAND | UPPER_BAND | +1 |
| Volume | HIGH | HIGH | +1 |
| ML Confidence | ≥70% | ≥70% | +1 |

---

## Test Suite

File baru: `tests/test_signal_flow.py`

**Tests**:
1. ✅ Trading Engine combined strength calculation
2. ✅ Signal Quality Engine confluence scoring (BUY & SELL)
3. ✅ ML prediction to signal class mapping
4. ✅ Input validation

**Usage**:
```bash
python tests/test_signal_flow.py
```

---

## Verification

Jalankan test untuk memverifikasi fixes:

```bash
# Test signal flow
python tests/test_signal_flow.py

# Expected output:
# ✅ Trading Engine Calculations: PASSED
# ✅ Signal Quality Confluence: PASSED
# ✅ ML Signal Mapping: PASSED
# ✅ Input Validation: PASSED
# 🎉 ALL TESTS PASSED!
```

---

## Files Modified

| File | Line | Change |
|------|------|--------|
| `signals/signal_quality_engine.py` | 190-197 | Added signal_direction parameter |
| `signals/signal_quality_engine.py` | 215-290 | Fixed directional confluence scoring |
| `signals/signal_quality_engine.py` | 303 | Fixed typo STRONG_BAY → STRONG_BUY |
| `signals/signal_quality_engine.py` | 303-305 | Added HOLD signal handling |
| `tests/test_signal_flow.py` | New | Complete test suite |

---

## Notes for Production

1. **Directional Scoring**: Sekarang SELL signals mendapat confluence score yang fair
2. **Balanced Detection**: BUY dan SELL signals sama-sama bisa mencapai score maksimum (8)
3. **HOLD Handling**: HOLD signals dari ML diproses dengan baik
4. **Validation**: Semua input divalidasi sebelum diproses

---

**Last Updated**: 2026-04-14
**Fixed By**: Claude Code
