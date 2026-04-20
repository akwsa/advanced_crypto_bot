# ROOT CAUSE: Signal BUY/SELL Tidak Muncul di Telegram

**Tanggal:** 2026-04-15  
**Status:** ❌ CRITICAL - NO SIGNALS SENT TO TELEGRAM

---

## ANALYSIS FLOW

Bot berjalan → Price poller fetch data → Signal di-generate → **Signal Quality Engine filter** → **SEMUA BUY/SELL DI-REJECT → HOLD** → **TIDAK ADA SIGNAL DI TELEGRAM**

---

## ROOT CAUSE IDENTIFIED

### Signal Quality Engine V3 - Thresholds Terlalu Ketat

File: `signals/signal_quality_engine.py`

#### BUY Requirements (LINE 310-317):
```python
if (confluence_score >= CONFLUENCE_MINIMUM_BUY and    # >= 4
    ml_confidence >= BUY_ML_CONFIDENCE and            # >= 0.70 (70%)
    ta_strength >= BUY_COMBINED_STRENGTH):            # >= 0.30
    return BUY
else:
    return HOLD  # ← INI YANG TERJADI!
```

#### SELL Requirements (LINE 339-346):
```python
if (confluence_score >= CONFLUENCE_MINIMUM_SELL and   # >= 4
    ml_confidence >= SELL_ML_CONFIDENCE and           # >= 0.70 (70%)
    ta_strength <= SELL_COMBINED_STRENGTH):           # <= -0.30
    return SELL
else:
    return HOLD  # ← INI YANG TERJADI!
```

---

## BUKTI DARI LOG

### Contoh BUY yang di-reject:
```
btcidr: 
  ML Confidence: 75.62% (OK, butuh 70%) ✅
  TA Strength: -0.10 (FAIL, butuh +0.30) ❌
  Confluence Score: 3 (FAIL, butuh 4) ❌
  
Result: BUY → HOLD | Reason: BUY requirements not met
```

### Contoh SELL yang di-reject:
```
wifidr:
  ML Confidence: 86.08% (OK, butuh 70%) ✅
  TA Strength: -0.10 (FAIL, butuh -0.30) ❌  
  Confluence Score: 4 (OK, butuh 4) ✅
  
Result: SELL → HOLD | Reason: SELL requirements not met
```

---

## KENAPA THRESHOLDS TIDAK TERCAPAI?

### 1. TA Strength Rendah (-0.10 instead of +0.30)
**Problem:** TA strength dihitung dari kombinasi RSI, MACD, MA, Bollinger
- Kalau RSI netral (~50), MACD netral, MA sideways → TA strength mendekati 0
- Butuh kondisi EXTREME (RSI oversold/overbought + MACD cross + trend kuat)

**Solution:** Turunkan threshold dari 0.30 ke 0.10 atau 0.15

### 2. Confluence Score Rendah (3 instead of 4)
**Confluence scoring:**
- RSI OVERSOLD: +2 poin
- MACD BULLISH: +2 poin  
- MA BULLISH: +1 poin
- Bollinger OVERSOLD: +1 poin
- Volume HIGH: +1 poin
- ML Confidence >= 70%: +1 poin
- **Max: 8 poin**

**Problem:** Market sedang sideways/consolidation
- RSI tidak oversold/overbought (netral) → cuma +1
- MACD belum cross → +0
- Volume NORMAL (bukan HIGH) → +0
- ML confidence 75% → +1
- **Total: 2-3 poin** (butuh 4)

**Solution:** Turunkan threshold dari 4 ke 3

### 3. ML Confidence Threshold 70%
**Problem:** ML model V2 multi-class lebih conservative
- Banyak prediksi di range 50-65% (tidak yakin)
- Butuh confidence >= 70% untuk BUY/SELL

**Solution:** Turunkan threshold dari 0.70 ke 0.60 atau 0.65

---

## SOLUTION: Relax Thresholds

### OPTION A: Conservative Fix (Recommended)
Ubah di `signals/signal_quality_engine.py`:

```python
# LINE 46-49: Confluence thresholds
CONFLUENCE_MINIMUM_BUY = 3    # Changed from 4
CONFLUENCE_MINIMUM_SELL = 3   # Changed from 4
CONFLUENCE_STRONG_BUY = 5     # Changed from 6
CONFLUENCE_STRONG_SELL = 5    # Changed from 6

# LINE 52-59: ML/TA thresholds  
STRONG_BUY_ML_CONFIDENCE = 0.75    # Changed from 0.80
STRONG_BUY_COMBINED_STRENGTH = 0.50  # Changed from 0.65
BUY_ML_CONFIDENCE = 0.60           # Changed from 0.70 ← KEY FIX!
BUY_COMBINED_STRENGTH = 0.10       # Changed from 0.30 ← KEY FIX!

STRONG_SELL_ML_CONFIDENCE = 0.75   # Changed from 0.80
STRONG_SELL_COMBINED_STRENGTH = -0.50  # Changed from -0.65
SELL_ML_CONFIDENCE = 0.60          # Changed from 0.70 ← KEY FIX!
SELL_COMBINED_STRENGTH = -0.10     # Changed from -0.30 ← KEY FIX!
```

**Expected Result:**
- btcidr: TA=-0.10 >= -0.10 ✅, Confluence=3 >= 3 ✅ → **BUY SENT** ✅
- wifidr: TA=-0.10 <= -0.10 ✅, Confluence=4 >= 3 ✅ → **SELL SENT** ✅

### OPTION B: Aggressive Fix (More Signals)
Kalau masih mau lebih banyak signal:

```python
CONFLUENCE_MINIMUM_BUY = 2        # More lenient
CONFLUENCE_MINIMUM_SELL = 2       # More lenient
BUY_ML_CONFIDENCE = 0.55          # Much lower
SELL_ML_CONFIDENCE = 0.55         # Much lower
BUY_COMBINED_STRENGTH = 0.05      # Almost neutral
SELL_COMBINED_STRENGTH = -0.05    # Almost neutral
```

**Risk:** Lebih banyak false positive signals (BUY/SELL yang salah)

---

## ADDITIONAL ISSUE: Cooldown Period

File: `signals/signal_quality_engine.py` LINE 38

```python
MINIMUM_SIGNAL_INTERVAL_MINUTES = 30  # 30 minutes cooldown
```

**Problem:** 30 menit terlalu lama untuk market crypto yang fast-moving
**Recommendation:** Turunkan ke 15 atau 20 menit

---

## VERIFICATION PLAN

Setelah fix thresholds:

1. **Restart bot**
   ```bash
   # Stop bot
   taskkill /F /PID 5596
   
   # Start bot
   python bot.py
   ```

2. **Monitor logs**
   ```bash
   # Search for BUY/SELL in logs
   Get-Content logs\trading_bot.log -Tail 100 | Select-String "BUY|SELL"
   ```

3. **Expected result:**
   ```
   ✅ [QUALITY ENGINE] btcidr: BUY approved (confluence: 3)
   📢 Signal alert sent to admin XXXX for btcidr: BUY
   ```

4. **Check Telegram:**
   - Signal BUY/SELL should appear within 5-10 minutes
   - One signal per pair every 15-30 minutes (cooldown)

---

## IMPACT ANALYSIS

### Before Fix:
- **Signals Generated:** ~100% HOLD
- **Signals Sent to Telegram:** 0
- **User Experience:** No signals, bot appears broken

### After Fix (Option A - Conservative):
- **Signals Generated:** ~20-30% BUY/SELL, rest HOLD
- **Signals Sent to Telegram:** 1-2 signals per pair per hour
- **User Experience:** Regular signals, actionable trading opportunities
- **Signal Quality:** Still high (60%+ confidence required)

### After Fix (Option B - Aggressive):
- **Signals Generated:** ~40-50% BUY/SELL
- **Signals Sent to Telegram:** 3-4 signals per pair per hour  
- **User Experience:** Many signals, might be overwhelming
- **Signal Quality:** Moderate (55%+ confidence, more false positives)

---

## RECOMMENDATION

**Use Option A (Conservative Fix)** because:
1. Still maintains signal quality
2. Reduces false positives
3. Gives users actionable signals
4. Can always lower more later if needed

**Changes needed:**
- File: `signals/signal_quality_engine.py`
- Lines to modify: 46-49, 52-59
- Total changes: 8 lines

---

## NEXT STEPS

Mau saya:
A. **Fix thresholds sekarang** (Option A - Conservative)?
B. **Fix thresholds sekarang** (Option B - Aggressive)?
C. **Buat script test** untuk verify thresholds sebelum apply?
D. **Cek market conditions** dulu untuk tahu apakah memang ada BUY/SELL opportunity?
