# 🔍 SIGNAL DATABASE AUDIT & FIX

**Date**: 2026-04-14  
**Issue**: DUA database berbeda menyimpan signals (signals.db & trading.db)  
**Status**: ✅ ROOT CAUSE FOUND - FIX PLAN READY

---

## 📊 AUDIT FINDINGS

### Database #1: `data/signals.db`

**Purpose**: Signal history untuk **signal_analyzer.py** (analisis akurasi historis)

**Table Schema**:
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    symbol TEXT,              -- BTCIDR, ETHIDR
    price REAL,
    recommendation TEXT,      -- BUY, SELL, HOLD
    rsi TEXT,
    macd TEXT,
    ma_trend TEXT,
    bollinger TEXT,
    volume TEXT,
    ml_confidence REAL,
    combined_strength REAL,
    analysis TEXT,
    signal_time TEXT,
    received_at TEXT,
    received_date TEXT,
    source TEXT,
    created_at TIMESTAMP
);
```

**Total Rows**: 4,199 signals  
**Used By**: 
- ✅ `signal_analyzer.py` (untuk analisis win rate)
- ✅ `signal_db.py` (SignalDatabase class)
- ✅ `bot.py` line 219 (save signals dari bot utama)
- ✅ `fetch_signal_history.py`
- ✅ `check_signal_db.py`

---

### Database #2: `data/trading.db`

**Purpose**: Main trading database dengan **redundant signals table**

**Table Schema**:
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    pair TEXT,
    timestamp TIMESTAMP,
    signal_type TEXT,
    price REAL,
    confidence REAL,
    indicators TEXT,          -- JSON
    ml_prediction TEXT,       -- JSON
    recommendation TEXT
);
```

**Total Rows**: 21,243 signals (5x lebih banyak!)  
**Used By**:
- ✅ `database.py` (Database class - save_signal method)
- ✅ `trading_engine.py` (line 92 - calls db.save_signal)
- ✅ `bot.py` (implicit melalui trading_engine)

---

## 🐛 ROOT CAUSE ANALYSIS

### Kenapa Ada 2 Table Signals?

**Jawaban**: Ini adalah **DUPLICATE/REDUNDANCY** yang tidak disengaja!

**Timeline kemungkinan**:
1. **Awalnya**: Hanya `trading.db` dengan table `signals` (untuk save signals)
2. **Kemudian**: Developer buat `signals.db` terpisah untuk **signal analyzer** feature
3. **Masalah**: Keduanya tetap diisi data yang SAMA → **double storage, double maintenance**

### Bukti dari Code:

**di `bot.py`**:
```python
# Line 6989-7070: Signal generation flow
signal = self.trading_engine.generate_signal(...)  # ← Save ke trading.db

# Line 7047: Juga save ke signals.db!
signal_id = self._signal_db.insert_signal(signal_data, datetime.now())
```

**di `trading_engine.py`**:
```python
# Line 92-102
self.db.save_signal(  # ← Save ke trading.db
    pair=pair,
    signal_type=recommendation,
    ...
)
```

**Result**: **Setiap signal disimpan 2x** ke database berbeda!

---

## ✅ RECOMMENDED FIX

### Opsi 1: **SINGLE DATABASE** (Recommended) ⭐

**Keep**: `signals.db`  
**Remove**: Table `signals` dari `trading.db`

**Alasan**:
1. ✅ `signals.db` schema lebih lengkap (RSI, MACD, Bollinger terpisah)
2. ✅ `signals.db` sudah punya indexes dan optimization
3. ✅ `signal_analyzer.py` sudah pakai `signals.db`
4. ✅ Separation of concerns: signals vs trading data

**Migration Plan**:
```sql
-- 1. Export data dari trading.db
ATTACH 'data/signals.db' AS signals_db;

-- 2. Migrate jika ada data yang belum ada di signals.db
INSERT OR IGNORE INTO signals_db.signals (...)
SELECT ... FROM trading.db.signals;

-- 3. Drop table dari trading.db
DROP TABLE IF EXISTS trading.db.signals;
```

**Code Changes**:
```python
# trading_engine.py - Hapus save_signal call
def generate_signal(self, pair, ta_signals, ml_prediction, ml_confidence, ml_signal_class=None):
    # ... generate signal logic ...
    
    signal = {...}
    
    # ❌ HAPUS INI:
    # self.db.save_signal(...)
    
    # ✅ RETURN saja, biarkan bot.py yang save ke signals.db
    return signal
```

```python
# bot.py - Tetap save ke signals.db
signal = self.trading_engine.generate_signal(...)

# ✅ Keep ini:
signal_id = self._signal_db.insert_signal(signal_data, datetime.now())
```

---

### Opsi 2: **MERGE SCHEMA** (Alternative)

Kalau memang perlu 2 database berbeda dengan tujuan berbeda:

**signals.db**: Untuk signal history & analysis
- Keep schema yang ada sekarang
- Used by: signal_analyzer.py, signal_db.py

**trading.db**: HAPUS table signals
- Hanya untuk: users, trades, price_history, portfolio
- Used by: database.py, trading_engine.py

**Benefit**:
- ✅ Clear separation
- ✅ No redundancy
- ✅ Easier maintenance

---

## 🔍 MODULES THAT NEED FIXING

### 1. `trading_engine.py`
**Current**:
```python
def generate_signal(...):
    # ...
    self.db.save_signal(...)  # ❌ Save ke trading.db
    return signal
```

**Fix**:
```python
def generate_signal(...):
    # ...
    # ❌ HAPUS: self.db.save_signal(...)
    return signal  # ✅ Return only, let bot.py save to signals.db
```

### 2. `database.py`
**Current**:
```python
def save_signal(self, pair, signal_type, price, ...):
    # Save ke trading.db ❌
```

**Fix**:
```python
# ❌ HAPUS method ini ATAU
# ✅ DEPRECATE dengan warning
def save_signal(self, ...):
    import warnings
    warnings.warn("save_signal is deprecated. Use signal_db.py instead.")
    # Keep for backward compatibility, but log warning
```

### 3. `bot.py`
**Current**: Sudah save ke signals.db ✅  
**Action**: No change needed

---

## 📊 DATA COMPARISON

| Aspect | signals.db | trading.db (signals) |
|--------|------------|---------------------|
| **Rows** | 4,199 | 21,243 |
| **Schema** | Detailed (17 columns) | Simplified (9 columns) |
| **Indexes** | Yes (optimized) | No |
| **Used By** | signal_analyzer, signal_db | trading_engine, database |
| **Data Quality** | High (structured) | Medium (JSON blobs) |
| **Recommendation** | ✅ KEEP | ❌ REMOVE |

---

## 🎯 ACTION PLAN

### Phase 1: Audit & Backup (Hari 1)
- [x] ✅ Audit kedua database
- [ ] Backup kedua database
- [ ] Compare data untuk overlap

### Phase 2: Migration (Hari 2)
- [ ] Migrate unique signals dari trading.db → signals.db
- [ ] Verify data integrity
- [ ] Drop table signals dari trading.db

### Phase 3: Code Fix (Hari 2-3)
- [ ] Update `trading_engine.py` - hapus save_signal
- [ ] Update `database.py` - deprecate save_signal
- [ ] Test semua modul
- [ ] Verify bot.py still works

### Phase 4: Testing (Hari 3-4)
- [ ] Test signal generation
- [ ] Test signal saving
- [ ] Test signal_analyzer.py
- [ ] Verify no errors

---

## ✅ RECOMMENDATION

**Use Opsi 1: SINGLE DATABASE (signals.db)**

**Alasan**:
1. ✅ Separation of concerns
2. ✅ Better schema (more detailed)
3. ✅ Already optimized with indexes
4. ✅ Used by signal_analyzer (fitur penting)
5. ✅ Cleaner architecture

**Implementation Priority**: **HIGH**
- Menghemat storage (21K redundant rows)
- Mengurangi complexity
- Memperjelas data flow
- Mencegah inconsistency

---

**Status**: ✅ AUDIT COMPLETE - FIX PLAN READY  
**Next Step**: Approve fix plan → implement changes
