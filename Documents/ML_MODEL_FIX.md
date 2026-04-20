# 🐛 ML Model Fix: 'NoneType' object has no attribute 'tree_'

## Error
```
2026-04-11 19:34:54 - crypto_bot - WARNING - ⚠️ ML prediction failed for hifiidr: 'NoneType' object has no attribute 'tree_'
```

## Root Cause

**The bug:** `self.model` is a **dict** containing `{'rf': RandomForestClassifier, 'gb': GradientBoostingClassifier}` — but these classifiers were created via `create_model()` **without being `.fit()` first**.

In `predict()`:
```python
# OLD CODE
def predict(self, df):
    if self.model is None:  # ← Returns False (dict is not None!)
        return None, 0

    pred_rf = self.model['rf'].predict_proba(...)  # ← CRASH! 'tree_' attribute doesn't exist
    pred_gb = self.model['gb'].predict_proba(...)  # ← CRASH!
```

**When this happens:**
- `models/trading_model.pkl` doesn't exist (fresh deploy)
- Model load fails → `load_model()` calls `create_model()`
- `create_model()` creates **unfitted** classifiers
- `predict()` is called → `tree_` attribute doesn't exist → crash

## Fix

### 1. Added `_is_fitted` flag
```python
self._is_fitted = False  # Track whether model has been trained
```

### 2. Check `_is_fitted` in `predict()`
```python
def predict(self, df):
    if self.model is None or not self._is_fitted:
        return None, 0.5  # Return neutral, no crash

    # ... proceed with prediction
```

### 3. Set `_is_fitted = True` after training
```python
def train(self, df):
    # ... training code ...
    self._is_fitted = True
    return True
```

### 4. Set `_is_fitted` based on loaded model state
```python
def load_model(self):
    data = joblib.load(self.model_path)
    # ...
    self._is_fitted = self.last_trained is not None
    return True
```

### 5. Fixed `should_retrain()` and `get_feature_importance()`
```python
def should_retrain(self):
    if not self._is_fitted or self.last_trained is None:
        return True

def get_feature_importance(self):
    if self.model is None or self.feature_names is None or not self._is_fitted:
        return None
```

## Impact

| Scenario | Before | After |
|----------|--------|-------|
| Fresh deploy (no model file) | WARNING + crash | ⏳ "ML model not trained yet" — TA-only signal |
| Model load fails | WARNING + crash | ⏳ "ML model not trained yet" — TA-only signal |
| Model loaded successfully | ✅ Works | ✅ Works |
| Model trained successfully | ✅ Works | ✅ Works |

## Behavior

**Before fix:**
```
⚠️ ML prediction failed for hifiidr: 'NoneType' object has no attribute 'tree_'
```

**After fix:**
```
⏳ ML model not trained yet for hifiidr — using TA-only signal
```

Signals still work (TA only) until ML model is trained via `/retrain` command or auto-retrain (24h when trading enabled).
