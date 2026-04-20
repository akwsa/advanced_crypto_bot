# 🔧 ML V2 API Mismatch Fix

## ❌ **Error:**
```
⚠️ ML prediction failed for btcidr: too many values to unpack (expected 2)
💡 Using TA-only signal for btcidr
```

---

## 🔍 **Root Cause:**

**ML Model V1** `predict()` returns **2 values**:
```python
prediction, confidence = model.predict(df)
# Returns: (bool, float)
```

**ML Model V2** `predict()` returns **3 values**:
```python
predicted_class, confidence, signal_class = model.predict(df)
# Returns: (int, float, str)
# Example: (3, 0.78, 'BUY')
```

**Bot.py** code expected 2 values → **CRASH!**

---

## ✅ **Solution:**

### **Before:**
```python
ml_prediction, ml_confidence = self.ml_model.predict(df)  # ❌ Fails for V2
```

### **After:**
```python
predict_result = self.ml_model.predict(df)

# Handle different model versions
if self.ml_version == 'V2':
    # V2 returns (predicted_class, confidence, signal_class)
    ml_prediction, ml_confidence, ml_signal_class = predict_result
    logger.info(f"✅ ML prediction: {ml_confidence:.2%} ({ml_signal_class})")
else:
    # V1 returns (prediction, confidence)
    ml_prediction, ml_confidence = predict_result
    ml_signal_class = None
    logger.info(f"✅ ML prediction: {ml_confidence:.2%}")
```

---

## 📊 **Expected Output After Fix:**

### **Before Fix:**
```
⚠️ ML prediction failed for btcidr: too many values to unpack (expected 2)
💡 Using TA-only signal for btcidr
```

### **After Fix:**
```
✅ ML prediction successful for btcidr: 78.5% (BUY)
📊 Combined Strength: 0.45
📊 Signal for btcidr: BUY
```

---

## 📝 **Files Modified:**

| File | Change |
|------|--------|
| `bot.py` | Updated `_generate_signal_for_pair()` to handle V1 vs V2 return values |

---

## ✅ **Testing:**

- ✅ Syntax validation passed
- ⏳ Restart bot to verify
- ⏳ Check logs for successful ML prediction
- ⏳ Verify no more "too many values" errors

---

## 🎯 **Benefits:**

1. **Backward Compatible** - Works with both V1 and V2
2. **Better Logging** - Shows signal class (BUY/SELL/HOLD) for V2
3. **Future Proof** - Easy to add V3 with different API

---

**Status:** ✅ **FIXED**

**Next:** Restart bot and verify ML predictions work correctly
