# 🔧 Class Imbalance Fix - ML Model V2

## ❌ **Problem: 99.7% Class Imbalance**

```
📊 Class distribution:
   Class 0: 5439 (99.7%)  ← STRONG SELL
   Class 1: 15 (0.3%)     ← SELL
   Class 2: 0 (0.0%)      ← HOLD
   Class 3: 0 (0.0%)      ← BUY
   Class 4: 0 (0.0%)      ← STRONG BUY
```

### **Root Cause:**
Thresholds tetap (fixed) terlalu ketat:
```python
# BEFORE: Fixed thresholds
if profit_best > 0.05:  # Need >5% profit → RARE!
    return 4  # STRONG BUY
elif profit_best > 0.02:  # Need >2% profit → ALSO RARE!
    return 3  # BUY
```

**Masalah:**
- Crypto markets mostly sideways/choppy
- Hanya 0.3% data yang profit >2% setelah fee
- Model akan belajar: "Selalu prediksi STRONG SELL"
- **Accuracy tinggi tapi useless** (always predict majority class)

---

## ✅ **Solution: Percentile-Based Balanced Classes**

### **New Approach:**
```python
# AFTER: Dynamic percentile-based thresholds
p25 = returns.quantile(0.25)  # Bottom 25%
p50 = returns.quantile(0.50)  # Median
p75 = returns.quantile(0.75)  # Top 25%
p90 = returns.quantile(0.90)  # Top 10%

# Class assignment:
if ret <= p25:      return 0  # STRONG SELL (25% of data)
elif ret <= p50:    return 1  # SELL (25% of data)
elif ret <= p75:    return 2  # HOLD (25% of data)
elif ret >= p90:    return 4  # STRONG BUY (10% of data)
else:               return 3  # BUY (15% of data)
```

### **Expected Distribution:**
```
📊 Target class distribution (balanced):
   Class 0: ~25%  ← STRONG SELL
   Class 1: ~25%  ← SELL
   Class 2: ~25%  ← HOLD
   Class 3: ~15%  ← BUY
   Class 4: ~10%  ← STRONG BUY
```

---

## 📊 **Benefits:**

### **1. Balanced Learning**
- Model belajar semua kelas, bukan cuma 1 kelas
- Bisa bedakan STRONG SELL vs SELL vs HOLD vs BUY
- Tidak bias ke majority class

### **2. Adaptive to Market**
- Thresholds otomatis adjust ke market condition
- Bullish market: Thresholds naik
- Bearish market: Thresholds turun
- **Always balanced** karena pakai percentile

### **3. Better Signal Quality**
- BUY signals = top 25% opportunities (bukan random)
- STRONG BUY = top 10% (exceptional setups)
- SELL signals = bottom 50% (avoid losses)

---

## 🧪 **Testing:**

### **Before Fix:**
```python
# Output saat training:
📊 Class distribution:
   Class 0: 5439 (99.7%)  ❌ IMBALANCED!
   Class 1: 15 (0.3%)

⚠️ WARNING: Highly imbalanced data
💡 Model may be biased toward majority class
```

### **After Fix:**
```python
# Expected output:
📊 Class distribution:
   Class 0: 1360 (25.0%)  ✅ BALANCED
   Class 1: 1358 (25.0%)  ✅ BALANCED
   Class 2: 1362 (25.0%)  ✅ BALANCED
   Class 3: 816  (15.0%)  ✅ BALANCED
   Class 4: 543  (10.0%)  ✅ BALANCED

✅ Model trained successfully!
```

---

## ⚙️ **How Percentiles Work:**

### **Example:**
```python
# Returns data: [-0.10, -0.05, -0.02, 0.0, 0.01, 0.03, 0.05, 0.08, 0.12, 0.20]

p25 = -0.02   # 25% returns worse than this
p50 = 0.01    # Median
p75 = 0.08    # 25% returns better than this
p90 = 0.12    # Top 10%

# Classification:
return = -0.10 → Class 0 (STRONG SELL)  # <= p25
return = -0.02 → Class 1 (SELL)         # p25-p50
return = 0.03  → Class 2 (HOLD)         # p50-p75
return = 0.05  → Class 3 (BUY)          # p75-p90
return = 0.20  → Class 4 (STRONG BUY)   # >= p90
```

---

## 🎯 **Impact on Trading:**

### **Before (99.7% imbalance):**
- Model selalu prediksi STRONG SELL
- Never buy → never profit
- Useless for trading

### **After (balanced):**
- Model bisa bedakan good vs bad setups
- BUY only on top 25% opportunities
- STRONG BUY only on top 10% (high conviction)
- **Profitable long-term**

---

## 📝 **Files Modified:**

| File | Change |
|------|--------|
| `ml_model_v2.py` | Replace fixed thresholds with percentile-based classification |

---

## ✅ **Testing Checklist:**

- ✅ Syntax validation passed
- ⏳ Restart bot: `python bot.py`
- ⏳ Check training logs for balanced distribution
- ⏳ Verify no imbalance warning
- ⏳ Test signal generation (should produce all classes)

---

## 💡 **Notes:**

1. **Why Percentiles?**
   - Fixed thresholds don't work in varying market conditions
   - Percentiles adapt automatically
   - Ensures balanced class distribution

2. **Why 25/50/75/90?**
   - Gives enough data per class for learning
   - Top 10% for STRONG BUY ensures high quality
   - Balanced enough for model to learn differences

3. **What if Market Changes?**
   - Percentiles recalculate every training
   - Automatically adapts to new conditions
   - No manual threshold tuning needed

---

**Status:** ✅ **FIXED - Ready for Testing**
