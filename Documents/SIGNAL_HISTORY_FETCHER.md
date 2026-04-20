# 📡 Signal History Fetcher - Usage Guide

## What It Does

`signal_history_viewer.py` sekarang bisa **mengambil pesan Telegram lama** (hingga 7 hari ke belakang) dan menyimpannya ke database `data/signals.db`.

Ini berguna untuk **backfill** sinyal yang terlewat atau tidak tersimpan dengan benar.

---

## Usage

### **Fetch 7 Days of History:**
```bash
python signal_history_viewer.py --fetch-history
```

### **Fetch Specific Range:**
```bash
# Last 14 days
python signal_history_viewer.py --fetch-history --days 14

# Fetch up to 1000 messages
python signal_history_viewer.py --fetch-history --msg-limit 1000
```

### **View Existing Signals:**
```bash
# View recent 50 signals
python signal_history_viewer.py

# View with filters
python signal_history_viewer.py --symbol BTCIDR --rec BUY

# Show statistics
python signal_history_viewer.py --stats

# Export to Excel
python signal_history_viewer.py --export report.xlsx
```

### **Cleanup:**
```bash
# Remove incomplete signals (rsi='—', etc.)
python signal_history_viewer.py --cleanup 90
```

---

## How It Works

1. **Connects to Telegram** using your user account (via Telethon)
2. **Reads past messages** from the target bot chat
3. **Parses each message** looking for signal format
4. **Saves valid signals** to `data/signals.db`
5. **Skips duplicates** (same symbol + price + date + recommendation)

---

## Expected Output

```
🔄 Starting Telegram history fetch...
✅ Connected to Telegram as YourName
📡 Fetching messages from: myownwebsocket_bot
📅 Fetching messages from last 7 days (since 2026-04-05)

💾 Saved #2986: BTCIDR BUY @ 08:30
💾 Saved #2987: ETHIDR STRONG_BUY @ 09:15
⏭️ Duplicate signal skipped: BTCIDR @ 10:00
💾 Saved #2988: SOLIDR SELL @ 11:45

==================================================
📊 FETCH SUMMARY:
   Messages parsed: 150
   Signals saved:   45
   Skipped (dup/invalid): 105
==================================================
```

---

## Requirements

```bash
pip install telethon
```

First run will ask for your phone number and OTP code (one-time login).

---

## ⚠️ Important Notes

1. **Only fetches messages that contain "Trading Signal" or "Signal"**
2. **Duplicate detection prevents re-saving the same signal**
3. **Bot does NOT need to be stopped** - this runs separately
4. **Messages older than Telegram's history limit may not be available**

---

## Complete Workflow

```bash
# Step 1: Cleanup existing incomplete data
python signal_history_viewer.py --cleanup 90

# Step 2: Fetch past 7 days of messages
python signal_history_viewer.py --fetch-history --days 7

# Step 3: Verify data
python signal_history_viewer.py --stats

# Step 4: Export if needed
python signal_history_viewer.py --export signals_backup.xlsx
```

---

**Status:** ✅ **READY TO USE**
