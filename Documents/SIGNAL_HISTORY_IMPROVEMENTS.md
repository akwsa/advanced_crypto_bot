# Signal History & Saver Improvements

## Changes Made

### ✅ `fetch_signal_history.py`

**1. Modernized Telethon Client**
- ❌ Old: `from telethon.sync import TelegramClient` (deprecated)
- ✅ New: `from telethon import TelegramClient` + `async/await` pattern
- Proper async iteration with `async for message in client.iter_messages()`

**2. Duplicate Signal Detection**
- Added `existing_signals` set to track saved signals
- Duplicate key: `(date, symbol, recommendation, price)`
- Prevents saving the same signal multiple times
- Shows count of skipped duplicates in final summary

**3. Better Error Handling**
- Try-catch blocks around each message processing
- Parse validation (returns `None` if symbol not found)
- Graceful handling of regex errors in `find()` function
- Confidence value validation (must be numeric before adding %)

**4. Improved Logging**
- Added Python `logging` module with timestamp format
- Replaced all `print()` calls with `logger.info/warning/error`
- Configurable log level via `logging.basicConfig()`
- Better visibility into what the script is doing

**5. Session Validation**
- Check if user is authorized before fetching messages
- Proper error message if session is invalid
- Clean disconnect in `finally` block

**6. Flexible Signal Detection**
- Old: Only matched "Signal Alert"
- New: Matches "Signal Alert" OR "signal" (case-insensitive)
- Catches more signal variations

**7. Better Summary Output**
- Shows saved count vs skipped count
- Clear separator lines for readability
- Final status with all relevant info

---

### ✅ `telegram_signal_saver.py`

**1. Duplicate Prevention**
- Added `load_existing_signals()` function
- Global `existing_signals` set tracks all saved signals
- Checks for duplicates before saving each new signal
- Loads existing data on startup to prevent re-saves after restart

**2. Consistent Logging**
- Added Python `logging` module
- Same format as `fetch_signal_history.py`
- Replaced `print()` with structured logging

**3. Better Error Handling**
- Try-catch around Excel save operation
- Parse failure detection (logs warning if `parse_signal()` returns None)
- Graceful handling of save errors

**4. Flexible Signal Detection**
- Same improvement as fetch script
- Matches both "Signal Alert" and "signal" (case-insensitive)

**5. Startup Status**
- Shows count of existing signals loaded
- Confirms duplicate checking is active

---

## What Changed in Practice

### Before:
- ❌ Could save same signal multiple times
- ❌ No error recovery if parsing failed
- ❌ Used deprecated Telethon sync API
- ❌ Hard to debug issues (no structured logs)
- ❌ Would re-save old signals after restart

### After:
- ✅ Duplicate detection prevents re-saving
- ✅ Graceful error handling throughout
- ✅ Modern async/await pattern
- ✅ Structured logging with timestamps
- ✅ Remembers existing signals on startup

---

## How to Use

### First Time Setup:
```bash
# 1. Install dependencies (if not already done)
pip install telethon openpyxl

# 2. Run history fetcher (ONE TIME)
python fetch_signal_history.py

# 3. Run signal saver (KEEP RUNNING)
python telegram_signal_saver.py
```

### After Restart:
```bash
# Just run the saver - it will load existing signals
python telegram_signal_saver.py
```

---

## Excel Format

The output file `signal_alerts.xlsx` contains these columns:

| Column | Description | Example |
|--------|-------------|---------|
| No | Sequential number | 1, 2, 3... |
| Tanggal | Signal date | 2026-04-10 |
| Waktu Signal | Time from bot message | 14:22:00 |
| Symbol | Trading pair | pippinidr |
| Price (IDR) | Entry price | 517.0350 |
| Recommendation | BUY/SELL/HOLD | BUY |
| RSI (14) | RSI status | OVERSOLD |
| MACD | MACD status | BEARISH |
| MA Trend | Moving Average | BEARISH |
| Bollinger | Bollinger Bands | NEUTRAL |
| Volume | Volume status | NORMAL |
| ML Confidence | ML prediction | 95.1% |
| Combined Strength | Strength indicator | 0.24 |
| Analysis | Full analysis text | Bullish signals... |
| Waktu Terima | Received timestamp | 14:22:05 |

**Styling:**
- Alternating row colors for readability
- Green font for BUY/LONG recommendations
- Red font for SELL/SHORT recommendations
- Frozen header row
- Auto-sized columns

---

## Troubleshooting

### "Session tidak valid"
Delete `signal_session.session` file and run again. You'll need to re-authenticate with phone number + OTP.

### "Gagal membaca existing data"
Check if Excel file is open in another program. Close it and retry.

### Duplicate signals still appearing
The duplicate check uses `(date, symbol, recommendation, price)` as key. If any of these differ, it's considered a new signal.

### No signals found
- Verify `TARGET_BOT` username is correct
- Check if bot actually sent messages in last 3 days
- Ensure session file exists and is authenticated

---

## Next Steps

- Consider adding database storage instead of Excel for better querying
- Add Telegram notifications when signals are saved
- Implement signal backtesting from Excel data
- Add filtering options (by symbol, date range, etc.)
