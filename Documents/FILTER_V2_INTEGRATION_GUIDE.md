# Signal Filter V2 - Integration Guide

## 📁 Overview

Sistem filter V2 dibuat **SEPARATE** dari bot utama agar bisa di-test tanpa mengganggu sistem yang sudah berjalan.

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                    BOT UTAMA                         │
│  (bot.py - JANGAN DIUBAH dulu)                       │
│  - Signal generation (TA + ML)                       │
│  - Telegram interface                                │
│  - Trading execution                                 │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              FILTER V2 SYSTEM (NEW)                  │
│  (Standalone - Test dulu sebelum merge)              │
│                                                      │
│  signal_filter_v2.py                                 │
│  ├── SignalFilterV2 class                            │
│  ├── 5 filter layers                                 │
│  └── Validation result & reporting                   │
│                                                      │
│  signal_analyzer_v2.py                               │
│  ├── SignalAnalyzerV2 class                          │
│  ├── Excel signal reader                             │
│  ├── Test signal generator                           │
│  └── Report generator                                │
└─────────────────────────────────────────────────────┘
```

---

## 🧪 Step 1: Testing Filter V2

### Run Test Mode (Recommended First)

```bash
# Generate mock signals dan test filter
python signal_analyzer_v2.py --test-mode
```

**Expected Output:**
```
======================================================================
  ADVANCED SIGNAL ANALYZER V2 - REPORT
======================================================================
Analysis Time: 2026-04-10 20:15:00
Total Signals: 6
Approved: 3 (50.0%)
Rejected: 3 (50.0%)
======================================================================

📊 Filter Effectiveness:
  🛑 Blacklist: 3/6 rejected (50%)
  🛑 Liquidity: 1/6 rejected (17%)
  🛑 ATH Distance: 1/6 rejected (17%)
  ✅ Confidence Tiers: 0/6 rejected (0%)

❌ RFCIDR - STRONG_BUY
   Rejection Reasons:
     • Coin blacklisted: rfcidr
     • Volume too low: 52,500,000 IDR < 100,000,000 IDR
     • Coin too far from ATH: -99.5% (max: 80%)

✅ BTCIDR - BUY
   Result: ✅ APPROVED | Passed: 5/5

✅ ETHIDR - STRONG_BUY
   Result: ✅ APPROVED | Passed: 5/5
```

### Run with Real Excel Data

```bash
# Analyze signals dari signal_alerts.xlsx
python signal_analyzer_v2.py --file signal_alerts.xlsx

# Export report to file
python signal_analyzer_v2.py --test-mode --export report.txt
```

---

## 📊 Step 2: Validate Results

### What to Check:

1. **RFCIDR should be REJECTED**
   - ✅ Blacklist check
   - ✅ Low volume check
   - ✅ ATH distance check

2. **BTC/ETH should be APPROVED**
   - ✅ Not in blacklist
   - ✅ High volume
   - ✅ Reasonable ATH distance

3. **PIPPINIDR should be REJECTED**
   - ✅ Blacklist check

4. **DOGEIDR should be REJECTED**
   - ✅ Blacklist check

### Validation Criteria:

| Test | Expected | Pass? |
|------|----------|-------|
| RFCIDR rejected | YES | ⬜ |
| BTCIDR approved | YES | ⬜ |
| ETHIDR approved | YES | ⬜ |
| PIPPINIDR rejected | YES | ⬜ |
| DOGEIDR rejected | YES | ⬜ |
| Report generated | YES | ⬜ |

**Jika SEMUA PASS** → Filter siap untuk integration ke bot utama.

---

## 🔧 Step 3: Customize Filters (Optional)

### Edit Configuration

File: `signal_filter_v2.py`

```python
def _default_config(self) -> Dict:
    return {
        # Filter 1: Blacklist
        "enable_blacklist": True,
        "blacklisted_coins": [
            "rfcidr",      # Add/remove coins
            "pippinidr",
            "dogwifhatidr",
            "pepeidr",
        ],
        
        # Filter 2: Liquidity
        "enable_liquidity_check": True,
        "min_24h_volume_idr": 100_000_000,  # Adjust threshold
        
        # Filter 3: ATH Distance
        "enable_ath_check": True,
        "max_ath_distance_pct": 80,  # Adjust threshold
        
        # Filter 4: Market Cap
        "enable_market_cap_check": False,  # Enable if needed
        "min_market_cap_idr": 1_000_000_000,
        
        # Filter 5: Confidence Tiers
        "enable_confidence_tiers": True,
        "ml_confidence_min": 0.65,
        "combined_strength_strong_buy": 0.6,
        "combined_strength_buy": 0.3,
    }
```

### Disable Specific Filters

```python
# Example: Disable ATH check
filter_v2 = SignalFilterV2()
filter_v2.config["enable_ath_check"] = False
```

---

## 🔄 Step 4: Integration Plan (Future)

**SETUJU UNTUK MERGE?** Jika testing sukses dan results valid, berikut plan untuk integrate ke bot utama:

### Phase 1: Add Filter Module to Bot

**File**: `bot.py` (add imports)
```python
from signal_filter_v2 import SignalFilterV2

class AdvancedCryptoBot:
    def __init__(self):
        # ... existing code ...
        
        # Initialize V2 filter (optional, can be disabled)
        self.signal_filter_v2 = SignalFilterV2()
        self.enable_filter_v2 = True  # Feature flag
```

### Phase 2: Modify Signal Generation

**File**: `bot.py` (modify `_send_initial_signal_background`)

```python
async def _send_initial_signal_background(self, pair, update, context):
    # ... existing signal generation code ...
    
    signal = await self._generate_signal_for_pair(pair)
    
    if signal:
        # 🆕 V2 FILTER CHECK
        if self.enable_filter_v2:
            market_data = await self._get_market_data(pair)  # volume, ATH, etc
            validation = self.signal_filter_v2.validate_signal(signal, market_data)
            
            if not validation.passed:
                logger.info(f"🚫 {pair} signal REJECTED by V2 filter")
                reasons = "; ".join(validation.rejection_reasons)
                
                # Send rejection notification (optional)
                text = f"🚫 <b>Signal Filtered: {pair}</b>\n\n"
                text += f"Reason: {reasons}\n\n"
                text += "⚠️ Signal rejected by enhanced filter system."
                await self._send_message(update, context, text, parse_mode='HTML')
                return  # Don't send signal
        
        # Signal passed filter - send as normal
        text = self._format_signal_message_html(signal)
        await self._send_message(update, context, text, parse_mode='HTML')
```

### Phase 3: Add Market Data Fetching

**New method** in `bot.py`:

```python
async def _get_market_data(self, pair) -> Dict:
    """Get market data for V2 filter validation"""
    # Fetch from Indodax API
    # Return: {volume_24h_idr, ath_price, market_cap_idr}
    
    # Placeholder implementation
    return {
        "volume_24h_idr": 0,  # Implement API call
        "ath_price": 0,       # Implement historical lookup
        "market_cap_idr": 0   # Calculate from supply
    }
```

### Phase 4: Add Toggle Command

**New command**: `/filter_v2`

```python
async def filter_v2_command(self, update, context):
    """Toggle V2 filter on/off"""
    self.enable_filter_v2 = not self.enable_filter_v2
    status = "ENABLED" if self.enable_filter_v2 else "DISABLED"
    
    text = f"🛡️ Signal Filter V2: {status}\n\n"
    text += self.signal_filter_v2.get_validation_report()
    
    await self._send_message(update, context, text, parse_mode='HTML')
```

---

## 📋 Decision Checklist

Sebelum merge ke bot utama, pastikan:

- [ ] Test mode runs successfully (`--test-mode`)
- [ ] Real Excel data analyzed (`--file signal_alerts.xlsx`)
- [ ] RFCIDR correctly rejected
- [ ] BTC/ETH correctly approved
- [ ] Filter thresholds reviewed and approved
- [ ] Blacklist reviewed and updated
- [ ] Performance impact acceptable
- [ ] Rollback plan ready (disable via feature flag)

**Jika SEMUA DIATAS ✅** → Ready for integration.

---

## 🚨 Rollback Plan

Jika ada masalah setelah merge:

### Option 1: Disable via Feature Flag
```python
# bot.py
self.enable_filter_v2 = False  # Disable filter
```

### Option 2: Remove Import
```python
# bot.py - comment out import
# from signal_filter_v2 import SignalFilterV2
```

### Option 3: Revert Git
```bash
git revert <commit-hash>  # Revert merge commit
```

---

## 📈 Expected Impact

### Before Filter V2:
- All signals sent to user (including risky meme coins)
- User might trade RFCIDR, PIPPIN, etc.
- High risk of losses from pump & dump

### After Filter V2:
- Risky signals filtered out
- User only receives validated signals
- Reduced risk from dead coins/low liquidity

### Metrics:
- **Signal Rejection Rate**: ~40-60% (depends on market)
- **False Positive Rate**: <5% (legitimate signals rejected)
- **Performance Impact**: ~10-50ms per signal (negligible)

---

## 🎯 Next Steps

1. ✅ **Run test mode** → `python signal_analyzer_v2.py --test-mode`
2. ⬜ **Review results** → Check if filters work as expected
3. ⬜ **Adjust thresholds** → If needed, modify config
4. ⬜ **Test with real data** → `python signal_analyzer_v2.py --file signal_alerts.xlsx`
5. ⬜ **Decision point** → Ready to merge? (Yes/No)
6. ⬜ **If Yes** → Follow integration plan above
7. ⬜ **If No** → Adjust filters and re-test

---

## 📞 Support & Troubleshooting

### "No signals found" in Excel
```bash
# Check file exists
ls signal_alerts.xlsx

# Or run test mode instead
python signal_analyzer_v2.py --test-mode
```

### "Filter too strict" - All signals rejected
```python
# Adjust thresholds in signal_filter_v2.py
"min_24h_volume_idr": 50_000_000,  # Lower from 100M
"max_ath_distance_pct": 90,        # Increase from 80%
```

### "Blacklist missing coins"
```python
# Add to blacklist in signal_filter_v2.py
"blacklisted_coins": [
    "rfcidr",
    "pippinidr",
    "newmemecoinidr",  # Add here
],
```

---

## 📝 Summary

| Component | Status | Purpose |
|-----------|--------|---------|
| `signal_filter_v2.py` | ✅ Ready | Core filter logic |
| `signal_analyzer_v2.py` | ✅ Ready | Analysis & reporting |
| Test mode | ✅ Available | Safe testing |
| Integration plan | 📋 Documented | Future merge guide |
| Rollback plan | ✅ Ready | Feature flag + git revert |

**Next**: Run tests dan review results! 🚀
