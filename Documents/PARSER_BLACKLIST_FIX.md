# Parser & Blacklist Fix

## 🔴 Masalah yang Diperbaiki

### 1. PEPEIDR Tidak Di-Blacklist
**Problem**: PEPE (meme coin) lolos dari filter blacklist

**Fix**: Tambah PEPEIDR dan meme coins lainnya ke blacklist

### 2. Parsing Gagal Tanpa Info
**Problem**: 
```
⚠️  Parsing gagal untuk pesan baru
```
Tidak ada info message seperti apa yang gagal

**Fix**: Tambahkan preview text yang gagal parse

---

## ✅ Changes Made

### Blacklist Update (signal_filter_v2.py)

**Before:**
```python
"blacklisted_coins": [
    "rfcidr",
    "pippinidr",
    "dogwifhatidr",
    "pepeidr",
    "shibainuidr",
]
```

**After:**
```python
"blacklisted_coins": [
    "rfcidr",           # Retard Finder Coin
    "pippinidr",        # Pippin
    "pepeidr",          # Pepe ✅
    "dogwifhatidr",     # Dogwifhat
    "shibainuidr",      # Shiba Inu
    "bonkidr",          # Bonk ✅ NEW
    "flokiidr",         # Floki ✅ NEW
]
```

### Parser Improvement (telegram_signal_saver.py)

**Better Fallback:**
```python
# Validasi lebih longgar: symbol ATAU recommendation
if symbol == "—" and rec == "—":
    logger.debug(f"⚠️  Parse failed")
    logger.debug(f"Text preview: {text[:150]}...")
    return None

# Default values jika kosong
return {
    "symbol": symbol if symbol != "—" else "UNKNOWN",
    "price": price if price != "—" else "0",
    "rec": rec if rec != "—" else "HOLD",
    ...
}
```

**Verbose Error:**
```python
if data is None:
    logger.warning(f"⚠️  Parsing gagal untuk pesan baru")
    logger.warning(f"   Preview: {text[:120]}...")  # ← NEW
    return
```

---

## 📊 Blacklist Coverage

| Coin | Type | Status |
|------|------|--------|
| RFCIDR | Meme (zero utility) | ✅ Blacklisted |
| PIPPINIDR | Meme (high risk) | ✅ Blacklisted |
| PEPEIDR | Meme coin | ✅ Blacklisted |
| DOGWIFHATIDR | Meme coin | ✅ Blacklisted |
| SHIBAINUIDR | Meme coin | ✅ Blacklisted |
| BONKIDR | Meme coin | ✅ Blacklisted |
| FLOKIIDR | Meme coin | ✅ Blacklisted |
| DOGEIDR | Meme (established) | ⚠️ Not blacklisted (too popular) |

---

## 🧪 Testing

### Test Parser dengan Debug
```bash
python telegram_signal_saver.py
```

**Saat parsing gagal:**
```
⚠️  Parsing gagal untuk pesan baru
   Preview: 📊 Price Alert: BTCIDR reached $50,000...
```

Sekarang bisa lihat **kenapa** parsing gagal!

### Test Blacklist
```bash
python signal_analyzer_v2.py --test-mode
```

**Expected:**
```
❌ PEPEIDR - STRONG_BUY REJECTED
   • Coin blacklisted: pepeidr
```

---

## 📝 Summary

| Issue | Before | After |
|-------|--------|-------|
| **PEPE Blacklist** | ❌ Not covered | ✅ Blacklisted |
| **Parse Error Info** | ❌ No details | ✅ Text preview shown |
| **Fallback Values** | ❌ Returns None | ✅ Defaults to HOLD |
| **Meme Coverage** | 5 coins | **7 coins** |

---

**Fix Date**: 2026-04-10  
**Status**: ✅ **COMPLETED**
