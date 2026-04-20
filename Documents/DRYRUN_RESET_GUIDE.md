# 🔄 CARA RESET DRY RUN MODE

**Date**: 2026-04-14  
**Purpose**: Panduan lengkap reset pair, modal, dan trades untuk DRY RUN

---

## 📋 QUICK REFERENCE

### Reset Semua (Recommended)
```bash
python reset_dryrun.py
```
Ini akan reset:
- ✅ Balance semua users ke initial (10,000,000 IDR)
- ✅ Semua watchlist dihapus
- ✅ Semua trades dihapus
- ✅ Semua signals dihapus
- ✅ Price history dihapus

---

## 🎯 RESET SPESIFIK

### 1️⃣ Reset Balance Saja
```bash
# Reset semua users ke initial balance
python reset_dryrun.py --balance

# Reset user tertentu ke initial balance
python reset_dryrun.py --user 256024600 --balance

# Reset user tertentu ke custom balance
python reset_dryrun.py --user 256024600 --balance --new-balance 50000000
```

### 2️⃣ Reset Watchlist Saja
```bash
# Reset semua watchlist
python reset_dryrun.py --watchlist

# Reset watchlist user tertentu
python reset_dryrun.py --user 256024600 --watchlist
```

### 3️⃣ Reset Trades Saja
```bash
# Reset semua trades (open + closed)
python reset_dryrun.py --trades

# Reset trades user tertentu
python reset_dryrun.py --user 256024600 --trades
```

### 4️⃣ Reset Signals Saja
```bash
python reset_dryrun.py --signals
```

### 5️⃣ Reset Price History Saja
```bash
python reset_dryrun.py --price-history
```

---

## 🔍 CHECK STATUS

### Lihat Status Sebelum/Sesudah Reset
```bash
python reset_dryrun.py --status
```

Output contoh:
```
============================================================
  CURRENT STATUS (SEBELUM RESET)
============================================================

👥 Total Users: 2

👤 Boom (ID: 256024600)
   Balance: 10,000,000 IDR

👤 Вадим (ID: 1355992996)
   Balance: 10,000,000 IDR

📊 Total Watchlist: 55 pair(s)
📊 Total Trades: 289 trade(s)
📊 Total Signals: 3287
============================================================
```

---

## 💡 COMMON SCENARIOS

### Scenario 1: Mulai Testing Baru dari Awal
```bash
# Reset SEMUA untuk clean slate
python reset_dryrun.py --all
```

### Scenario 2: Test dengan Modal Lebih Besar
```bash
# Reset balance ke 50 juta IDR
python reset_dryrun.py --balance --new-balance 50000000

# Atau 100 juta IDR
python reset_dryrun.py --balance --new-balance 100000000
```

### Scenario 3: Hapus Semua Pair, Tapi Keep Balance
```bash
python reset_dryrun.py --watchlist
```

### Scenario 4: Hapus History Trades, Keep Balance & Watchlist
```bash
python reset_dryrun.py --trades
```

### Scenario 5: Reset User Tertentu Saja
```bash
# Reset user 256024600
python reset_dryrun.py --user 256024600 --all

# Reset balance user 1355992996 ke 20 juta
python reset_dryrun.py --user 1355992996 --balance --new-balance 20000000
```

---

## 🎮 VIA TELEGRAM COMMANDS

### Reset Watchlist via Telegram
```
/clear_watchlist
```
Ini akan menghapus semua pair dari watchlist user yang mengirim command.

### Add Pairs Baru via Telegram
```
/watch BTCIDR
/watch ETHIDR,SOLIDR,DOGEIDR
```

### Cek Balance via Telegram
```
/balance
```

### Cek Trades via Telegram
```
/trades
```

---

## 🗄️ MANUAL DATABASE RESET (Advanced)

### Via SQLite Command Line
```bash
# Buka trading database
sqlite3 data/trading.db

# Reset balance semua users
UPDATE users SET balance = 10000000;

# Hapus semua watchlist
DELETE FROM watchlist;

# Hapus semua trades
DELETE FROM trades;

# Hapus price history (opsional)
DELETE FROM price_history;

# Verify
SELECT user_id, balance, first_name FROM users;
SELECT COUNT(*) FROM watchlist;
SELECT COUNT(*) FROM trades;

# Exit
.exit
```

### Via SQLite di Python
```python
import sqlite3

# Connect to database
conn = sqlite3.connect('data/trading.db')
cursor = conn.cursor()

# Reset balance
cursor.execute('UPDATE users SET balance = 10000000')
print(f"✅ Balance reset: {cursor.rowcount} users")

# Reset watchlist
cursor.execute('DELETE FROM watchlist')
print(f"✅ Watchlist cleared: {cursor.rowcount} pairs deleted")

# Reset trades
cursor.execute('DELETE FROM trades')
print(f"✅ Trades reset: {cursor.rowcount} trades deleted")

# Commit dan close
conn.commit()
conn.close()
```

---

## 📊 WHAT GETS RESET?

### ✅ Reset Items
| Item | Description | Default Value |
|------|-------------|---------------|
| **Balance** | User balance | 10,000,000 IDR (atau custom) |
| **Watchlist** | Pairs yang dimonitor | Empty (0 pairs) |
| **Trades** | Open & closed trades | Empty (0 trades) |
| **Signals** | Historical signals | Empty (0 signals) |
| **Price History** | Historical price data | Empty (0 records) |

### ❌ NOT Reset (Kept)
| Item | Description | Reason |
|------|-------------|--------|
| **Users** | User accounts | Need user data for bot |
| **ML Model** | Trained model | Reuse untuk predictions |
| **Config** | Bot settings | Keep as-is |
| **Logs** | Bot logs | For debugging |

---

## ⚠️ IMPORTANT NOTES

### DRY RUN Mode Only
- ✅ Script ini AMAN untuk DRY RUN mode
- ✅ Tidak affect real trading di Indodax
- ✅ Balance adalah virtual balance

### Real Trading Mode
- ❌ JANGAN reset jika sedang REAL TRADING
- ❌ Bisa kehilangan data trades yang sebenarnya
- ⚠️ Backup database dulu jika ragu

### Backup Sebelum Reset
```bash
# Backup database dulu (recommended)
copy data\trading.db data\trading.db.backup_2026-04-14

copy data\signals.db data\signals.db.backup_2026-04-14
```

### After Reset
Setelah reset, bot akan:
1. ✅ Reload watchlist (empty)
2. ✅ Users need to `/watch` pairs again
3. ✅ Balance kembali ke initial
4. ✅ No trades history
5. ✅ Clean slate untuk testing baru

---

## 🧪 TESTING WORKFLOW

### Langkah Testing DRY RUN dari Awal

1. **Reset Semua**
   ```bash
   python reset_dryrun.py --all
   ```

2. **Start Bot**
   ```bash
   python bot.py
   ```

3. **Add Pairs via Telegram**
   ```
   /watch BTCIDR,ETHIDR,SOLIDR
   ```

4. **Enable DRY RUN**
   ```
   /autotrade dryrun
   ```

5. **Monitor Signals**
   ```
   /signal BTCIDR
   /signals
   ```

6. **Check Balance**
   ```
   /balance
   ```

7. **Watch Auto-Trading**
   ```
   /autotrade_status
   /trades
   ```

---

## 🔧 TROUBLESHOOTING

### Problem: Script error "Database not found"
**Solution**:
```bash
# Check if database exists
dir data\trading.db

# If missing, bot akan create new one on next start
python bot.py
```

### Problem: Balance tidak reset
**Solution**:
```bash
# Check user ID yang benar
python reset_dryrun.py --status

# Reset dengan user ID yang benar
python reset_dryrun.py --user <YOUR_USER_ID> --balance
```

### Problem: Watchlist masih ada setelah reset
**Solution**:
```bash
# Force reset via SQLite
sqlite3 data/trading.db "DELETE FROM watchlist;"
sqlite3 data/trading.db "SELECT COUNT(*) FROM watchlist;"
```

---

## 📝 SCRIPT LOCATION

**Script**: `reset_dryrun.py`  
**Database**: `data/trading.db`  
**Signals DB**: `data/signals.db`

---

## ✅ SUMMARY

### Quick Commands
```bash
# Reset semua (recommended untuk testing baru)
python reset_dryrun.py

# Lihat status
python reset_dryrun.py --status

# Reset balance ke custom amount
python reset_dryrun.py --balance --new-balance 50000000

# Reset user tertentu
python reset_dryrun.py --user 256024600 --all

# Reset watchlist saja
python reset_dryrun.py --watchlist
```

### Via Telegram
```
/clear_watchlist     - Hapus semua pair
/watch BTCIDR        - Add pair baru
/balance             - Cek balance
/autotrade dryrun    - Enable DRY RUN
/autotrade_status    - Cek status
```

---

**Last Updated**: 2026-04-14  
**Status**: ✅ Tested & Working
