# ML Signal Data Collection Setup

## 🎯 Purpose

Setup sistem untuk **mengumpulkan SEMUA signal** (termasuk meme coins) untuk **ML training data**.

### Why No Blacklist?

Untuk ML yang baik, model perlu belajar dari:
- ✅ **Signal bagus** yang profit
- ❌ **Signal jelek** yang loss (termasuk meme coins)
- ⏸️ **Signal HOLD** yang tidak jadi trade

**Tanpa data "bad signals", ML tidak bisa belajar membedakan!**

---

## 📊 Data Collection Architecture

```
┌────────────────────────────────────────────────────────┐
│                   BOT UTAMA (bot.py)                    │
│                                                         │
│  _generate_signal_for_pair()                           │
│  ├── Generate signal (TA + ML)                         │
│  ├── Format: HOLD, BUY, STRONG_BUY, SELL, STRONG_SELL  │
│  └── 💾 AUTO-SAVE to signals.db (ALL signals)          │
└────────────────────────────────────────────────────────┘
                      ↓ (auto-save)
┌────────────────────────────────────────────────────────┐
│              SQLite: data/signals.db                    │
│                                                         │
│  Table: signals                                        │
│  ├── symbol (BTCIDR, PEPEIDR, RFCIDR, etc)            │
│  ├── price                                            │
│  ├── recommendation (ALL types)                        │
│  ├── rsi, macd, ma_trend, bollinger, volume           │
│  ├── ml_confidence                                    │
│  ├── combined_strength                                │
│  └── received_at                                      │
│                                                         │
│  NO BLACKLIST - Semua coin disimpan!                  │
└────────────────────────────────────────────────────────┘
                      ↑
┌────────────────────────────────────────────────────────┐
│           EXTERNAL SIGNAL SOURCES                       │
│                                                         │
│  fetch_signal_history.py                               │
│  ├── Fetch dari Telegram (7 hari)                     │
│  ├── NO BLACKLIST - Semua signal diambil              │
│  └── Batch insert ke signals.db                       │
│                                                         │
│  telegram_signal_saver.py                              │
│  ├── Monitor @myownwebsocket_bot                      │
│  ├── NO BLACKLIST - Semua signal disimpan            │
│  └── Real-time insert ke signals.db                   │
└────────────────────────────────────────────────────────┘
```

---

## 🚀 How It Works

### 1. Bot Utama (bot.py) - Auto-Save

**Setiap kali bot generate signal:**

```python
# bot.py - _generate_signal_for_pair()

signal = self.trading_engine.generate_signal(...)

# 🆕 AUTO-SAVE to SQLite (ALL signals - no filter)
signal_data = {
    "symbol": pair.upper(),
    "price": str(real_time_price),
    "rec": signal['recommendation'],  # HOLD, BUY, SELL, etc
    "rsi": ta_signals.get('rsi', '—'),
    "macd": ta_signals.get('macd', '—'),
    "ma": ta_signals.get('ma_trend', '—'),
    "bollinger": ta_signals.get('bb', '—'),
    "volume": ta_signals.get('volume', '—'),
    "confidence": f"{ml_confidence:.1%}",
    "strength": f"{signal.get('combined_strength', 0):.2f}",
    "analysis": signal.get('reason', ''),
    "signal_time": datetime.now().strftime("%H:%M:%S")
}

signal_id = self._signal_db.insert_signal(signal_data, datetime.now())
# ✅ Saved to signals.db - ALL signals, including HOLD and meme coins!
```

**Log Output:**
```
📊 Signal for btcidr: BUY
📊 ML Confidence: 75.0%
📊 TA Strength: 0.45
📊 Combined Strength: 0.42
💾 Signal #1234 saved to signals.db: BTCIDR - BUY
```

---

### 2. Fetch History (fetch_signal_history.py)

**Fetch historical signals dari Telegram:**

```bash
python fetch_signal_history.py
```

**Behavior:**
- ✅ Fetch 7 hari terakhir (default)
- ✅ **NO BLACKLIST** - Semua coin diambil (BTC, PEPE, RFC, dll)
- ✅ Clear database sebelum fetch (fresh start)
- ✅ Batch insert (cepat!)

**Output:**
```
🗑️ Clearing database before fetch...
✅ Deleted 0 old signals

[INFO] Scan summary:
   • Total messages checked: 487
   • Signal messages found: 67
   • Skipped (not signal): 420

[SELESAI] 67 signal baru ditambahkan ke database

📊 Database Statistics:
   Total signals: 67
   By recommendation:
     • BUY: 25
     • STRONG_BUY: 15
     • HOLD: 20  ← TERSIMPAN JUGA!
     • SELL: 5
     • STRONG_SELL: 2
   Top symbols:
     • BTCIDR: 15
     • ETHIDR: 12
     • PEPEIDR: 8  ← MEME COIN TERSIMPAN!
     • RFCIDR: 5   ← MEME COIN TERSIMPAN!
```

---

### 3. Signal Saver (telegram_signal_saver.py)

**Monitor real-time signals:**

```bash
python telegram_signal_saver.py
```

**Behavior:**
- ✅ Monitor @myownwebsocket_bot
- ✅ **NO BLACKLIST** - Semua signal disimpan
- ✅ Real-time insert ke SQLite
- ✅ Duplicate detection (prevent re-save)

**Output:**
```
✅ Signal #628 saved to DB | PEPEIDR | STRONG_BUY | Price: 0.061179 | Conf: 80.0%
✅ Signal #629 saved to DB | BTCIDR | BUY | Price: 1237992000 | Conf: 75.0%
✅ Signal #630 saved to DB | RFCIDR | HOLD | Price: 9.3850 | Conf: 45.0%
```

---

## 📈 Data Collection Stats

### Check Collected Data:

```bash
# View statistics
python signal_history_viewer.py --stats

# View all signals (last 50)
python signal_history_viewer.py

# View specific coin
python signal_history_viewer.py --symbol PEPEIDR

# Export to Excel for analysis
python signal_history_viewer.py --export all_signals.xlsx
```

### Example Stats:

```
======================================================================
  SIGNAL DATABASE STATISTICS
======================================================================

📊 Overview:
   Total Signals:    1,234
   Date Range:       2026-04-03 to 2026-04-10
   Avg Confidence:   68.5%

📈 By Recommendation:
   BUY             456 ( 37.0%) ██████████████████
   STRONG_BUY      234 ( 19.0%) ████████
   HOLD            345 ( 28.0%) ███████████
   SELL            123 ( 10.0%) ████
   STRONG_SELL      76 (  6.0%) ███

🔝 Top 10 Symbols:
   BTCIDR          234 signals
   ETHIDR          189 signals
   PEPEIDR         145 signals  ← Meme coin data collected!
   SOLIDR          123 signals
   DOGEIDR         112 signals  ← Meme coin data collected!
   RFCIDR           98 signals  ← Meme coin data collected!
   ...
```

---

## 🗄️ Database Schema

```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,              -- BTCIDR, PEPEIDR, RFCIDR, etc
    price REAL NOT NULL,               -- 1237992000.0, 0.061179, etc
    recommendation TEXT NOT NULL,      -- HOLD, BUY, STRONG_BUY, SELL, STRONG_SELL
    rsi TEXT,                          -- OVERSOLD, OVERBOUGHT, NEUTRAL
    macd TEXT,                         -- BULLISH, BEARISH, NEUTRAL
    ma_trend TEXT,                     -- BULLISH, BEARISH, NEUTRAL
    bollinger TEXT,                    -- UPPER, LOWER, BOUNCE, NEUTRAL
    volume TEXT,                       -- HIGH, NORMAL, LOW
    ml_confidence REAL,                -- 0.0 to 1.0
    combined_strength REAL,           -- -1.0 to 1.0
    analysis TEXT,                     -- Full analysis text
    signal_time TEXT,                  -- 19:57:03
    received_at TEXT NOT NULL,         -- 2026-04-10 21:42:09
    received_date TEXT NOT NULL,       -- 2026-04-10
    source TEXT DEFAULT 'telegram',    -- telegram, bot, manual
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX idx_signals_symbol ON signals(symbol);
CREATE INDEX idx_signals_received_date ON signals(received_date);
CREATE INDEX idx_signals_recommendation ON signals(recommendation);
CREATE INDEX idx_signals_received_at ON signals(received_at);
```

---

## 🔧 Blacklist Status

### ✅ BLACKLIST **DISABLED** (for ML training)

```python
# signal_filter_v2.py
"enable_blacklist": False,  # ← DISABLED for ML data collection
"blacklisted_coins": [
    # DISABLED: Semua coin disimpan untuk ML training
    # "rfcidr",
    # "pippinidr",
    # "pepeidr",
    # ...
]
```

**Result**: SEMUA coin disimpan:
- ✅ BTCIDR, ETHIDR (legitimate)
- ✅ PEPEIDR, DOGEIDR (meme - established)
- ✅ RFCIDR, PIPPINIDR (meme - high risk)
- ✅ ALL coins with ANY recommendation (HOLD, BUY, SELL, etc)

### Why Disabled?

| Aspect | With Blacklist | Without Blacklist |
|--------|---------------|-------------------|
| **Data Variety** | Low (only legit coins) | **High (all coins)** |
| **ML Training** | ❌ Biased dataset | ✅ **Balanced dataset** |
| **Learn Bad Signals** | ❌ Cannot learn | ✅ **Can learn patterns** |
| **Model Accuracy** | Lower | **Higher** |
| **Production Use** | ✅ Safer | ⚠️ Need manual review |

**Trade-off**: 
- ✅ **Training phase**: Collect ALL data (no blacklist)
- ⏸️ **Production phase (future)**: Enable blacklist for safety

---

## 📊 Data Quality for ML

### What ML Can Learn From This Data:

**1. Pattern Recognition:**
```
Input: RSI, MACD, MA, Bollinger, Volume, ML Confidence
Output: Recommendation (HOLD/BUY/SELL)
Target: Actual outcome (profit/loss)

ML learns: "When RSI=OVERSOLD + MACD=BULLISH + Volume=HIGH → 75% profit rate"
```

**2. Meme Coin Behavior:**
```
PEPEIDR signals:
- High volatility (big price swings)
- Pump & dump patterns
- Low reliability (many false signals)

ML learns: "Meme coin signals less reliable → lower confidence"
```

**3. HOLD Signal Value:**
```
HOLD signals (28% of data):
- Market conditions unclear
- TA indicators conflicting
- ML confidence low

ML learns: "When to NOT trade = valuable signal"
```

**4. Confidence Calibration:**
```
ML Confidence 70-80%:
- Actual win rate: 65%
- Slightly overconfident

ML learns: "Adjust confidence down by 5%"
```

---

## 🎯 Next Steps for ML Development

### Phase 1: Data Collection (NOW)

```bash
# Bot auto-saves all signals
python bot.py

# Fetch history periodically
python fetch_signal_history.py --days 7

# Monitor real-time
python telegram_signal_saver.py
```

**Target**: Collect 1000+ signals with diverse coins

### Phase 2: Data Analysis (1-2 weeks)

```bash
# Export data
python signal_history_viewer.py --export ml_dataset.xlsx

# Analyze patterns
python ml_data_analysis.py  # (will create later)

# Check data quality
python signal_history_viewer.py --stats
```

### Phase 3: ML Training (future)

```python
# Train model on collected data
from ml_trainer import SignalMLTrainer

trainer = SignalMLTrainer("data/signals.db")
model = trainer.train_model()

# Evaluate
accuracy = trainer.evaluate()
print(f"Model accuracy: {accuracy:.1%}")

# Deploy
trainer.deploy_model("models/signal_model_v2.pkl")
```

### Phase 4: Production (future)

```python
# Enable blacklist for safety
"enable_blacklist": True,

# Use trained model for better signals
model.predict(signal_features)
```

---

## 📁 Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| `signal_filter_v2.py` | Blacklist disabled | Collect all data |
| `bot.py` | Auto-save to signals.db | Save ALL signals |
| `fetch_signal_history.py` | No blacklist | Fetch all signals |
| `telegram_signal_saver.py` | No blacklist | Save all signals |

---

## 📝 Summary

### ✅ What's Happening Now:

1. **Bot utama** → Auto-save SEMUA signal ke `signals.db`
2. **Fetch history** → Ambil SEMUA signal dari Telegram (7 hari)
3. **Signal saver** → Monitor dan simpan SEMUA signal real-time
4. **NO BLACKLIST** → Semua coin disimpan (BTC, PEPE, RFC, dll)
5. **ALL recommendations** → HOLD, BUY, SELL, STRONG_BUY, STRONG_SELL

### 📊 Data Collected:

- **Symbol**: BTCIDR, ETHIDR, PEPEIDR, RFCIDR, dll
- **Recommendations**: HOLD (28%), BUY (37%), STRONG_BUY (19%), SELL (10%), STRONG_SELL (6%)
- **Indicators**: RSI, MACD, MA, Bollinger, Volume
- **ML Metrics**: Confidence, Combined Strength

### 🎯 Goal:

Kumpulkan **1000+ signals** dalam 2-4 minggu untuk ML training yang robust.

---

**Setup Date**: 2026-04-10  
**Status**: ✅ **ACTIVE - Collecting Data**  
**Blacklist**: ❌ **DISABLED** (for ML training)  
**Target**: 1000+ signals for ML model
