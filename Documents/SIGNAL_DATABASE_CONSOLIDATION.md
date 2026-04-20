# Signal Database Consolidation

## Overview
Signal database inconsistency has been fixed. Previously there were 2 signal tables:
- `trading.db.signals` - Old/deprecated table (now removed)
- `signals.db.signals` - Current/clean table (single source of truth)

## Changes Made

### 1. Removed Redundant Table from trading.db
```bash
python old_app/migrate_signals.py --execute
```
Result: Old signals table dropped from trading.db (had 0 rows)

### 2. Cleaned up core/database.py
Removed deprecated methods:
- `save_signal()` - Was commented out, now removed
- `get_latest_signals()` - Was unused, now removed

### 3. Updated old_app Scripts

| Script | Update |
|--------|--------|
| `check_model_status.py` | Signal queries now use signals.db |
| `delete_invalid_pairs.py` | Delete from signals.db (symbol column) |
| `delete_invalid_v2.py` | Delete from signals.db (symbol column) |

## Current Architecture

### Single Database Schema (signals.db)
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,           -- Was: pair
    price REAL NOT NULL,
    recommendation TEXT NOT NULL,   -- Was: signal_type
    rsi TEXT,
    macd TEXT,
    ma_trend TEXT,
    bollinger TEXT,
    volume TEXT,
    ml_confidence REAL,             -- Separate confidence field
    combined_strength REAL,
    analysis TEXT,                  -- Detailed analysis
    signal_time TEXT,
    received_at TEXT NOT NULL,      -- Was: timestamp
    received_date TEXT NOT NULL,
    source TEXT DEFAULT 'telegram',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Indexes
- `idx_signals_symbol` - Fast symbol lookups
- `idx_signals_received_date` - Date range queries
- `idx_signals_recommendation` - Filter by BUY/SELL/HOLD
- `idx_signals_received_at` - Time-based sorting

## Module Routing

### Primary Storage
```
bot.py → SignalDatabase.insert_signal() → signals.db
trading_engine.py → Returns signal to bot → signals.db
```

### Analysis/Reading
```
analysis/signal_analyzer.py → signals.db (direct SQL)
old_app/ml_trainer.py → signals.db (direct SQL)
old_app/analyze_signals.py → signals.db (pandas)
```

### Utility Scripts
```
old_app/check_signal_db.py → signals.db (read-only)
old_app/reset_dryrun.py → signals.db (reset)
```

## Data Statistics
- **signals.db**: 4,509 signals (current)
- **trading.db**: 0 signals (cleaned)

## Column Mapping (Old → New)
| Old Table | New Table | Notes |
|-----------|-----------|-------|
| `pair` | `symbol` | Uppercase stored |
| `signal_type` | `recommendation` | BUY/SELL/HOLD/STRONG_BUY/STRONG_SELL |
| `timestamp` | `received_at` | ISO format datetime |
| `confidence` | `ml_confidence` | Separate field |
| `indicators` | `rsi,macd,ma_trend,bollinger,volume` | Expanded columns |
| `ml_prediction` | - | Not stored separately |
| - | `combined_strength` | New field |
| - | `analysis` | New field (reason text) |
| - | `signal_time` | New field (HH:MM:SS) |
| - | `received_date` | New field (YYYY-MM-DD) |
| - | `source` | New field (telegram/manual) |

## Benefits of Consolidation

1. **No Data Duplication** - Single source of truth
2. **Cleaner Schema** - Expanded columns instead of JSON
3. **Better Performance** - Proper indexing
4. **Easier Queries** - No JOINs needed
5. **No Confusion** - Clear module routing

## Backward Compatibility

### For Scripts
Old scripts using `trading.db.signals` have been updated to use `signals.db`:
```python
# Old (DEPRECATED)
conn = sqlite3.connect('data/trading.db')
cursor.execute("SELECT * FROM signals WHERE pair = ?", (pair,))

# New
conn = sqlite3.connect('data/signals.db')
cursor.execute("SELECT * FROM signals WHERE symbol = ?", (pair.upper(),))
```

### For Code
Use SignalDatabase class:
```python
from signals.signal_db import SignalDatabase

db = SignalDatabase("data/signals.db")
signal_id = db.insert_signal(signal_data, datetime.now())
signals = db.get_signals(symbol="BTCIDR", limit=10)
```

## Verification

Check current state:
```bash
python old_app/migrate_signals.py  # Dry run - shows status
python old_app/check_signal_db.py   # Check signals.db
```

## Future Maintenance

1. All signal data goes to `signals.db` only
2. Never create signals table in `trading.db`
3. Use SignalDatabase class for all signal operations
4. Direct SQL queries should target `signals.db`
