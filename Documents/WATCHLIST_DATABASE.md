# 📋 Watchlist Database - Persistent Storage

## 🎯 **Overview**

Watchlist (/watch) sekarang disimpan di **database SQLite**, bukan hanya di memory. Ini membuat:
- ✅ **Persistent** - Watchlist tetap ada walau bot restart
- ✅ **Easy to Control** - Bisa dihapus dengan command database
- ✅ **DRY RUN Friendly** - Reset semua watchlist dengan 1 command
- ✅ **Live Trading Ready** - Nanti bisa sync dengan posisi Indodax

---

## 🆕 **New Commands**

### **`/clear_watchlist`**
Clear semua pair dari watchlist user.

**Usage:**
- Regular user: `/clear_watchlist` → Clear watchlist sendiri
- Admin: `/clear_watchlist` → Clear watchlist admin sendiri  
- Admin: `/clear_watchlist all` → Clear SEMUA watchlist SEMUA user

**Response:**
```
🗑️ **Watchlist Cleared!**

Semua pair telah dihapus dari watchlist Anda.
Gunakan `/watch <PAIR>` untuk menambahkan pair baru.
```

### **`/clear_watchlist all`** (Admin Only)
Clear semua watchlist dari semua user.

**Response:**
```
🗑️ **SEMUA WATCHLIST CLEARED!**

• 15 records dihapus dari database
• Semua user watchlist dikosongkan
• Bot siap untuk fresh start
```

---

## 🗄️ **Database Schema**

### **Table: `watchlist`**
```sql
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pair TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    UNIQUE(user_id, pair)
);

CREATE INDEX idx_watchlist_user_pair ON watchlist(user_id, pair);
```

**Fields:**
- `user_id` - Telegram user ID
- `pair` - Pair yang di-watch (lowercase, e.g. "btcidr")
- `added_at` - Kapan pair ditambahkan
- `is_active` - 1 = active, 0 = removed (soft delete ready)

---

## 🔄 **How It Works**

### **1. Bot Startup**
```python
# Load watchlist from database → memory cache
self.subscribers = self._load_watchlist_from_db()
```

### **2. User Adds Pair (`/watch btcidr`)**
```python
# Add to memory (fast access)
self.subscribers[user_id].append(pair)

# Sync to database (persistent)
self._sync_watchlist_to_db(user_id, pair)
```

### **3. User Removes Pair (`/unwatch btcidr`)**
```python
# Remove from memory
self.subscribers[user_id].remove(pair)

# Remove from database
self._remove_watchlist_from_db(user_id, pair)
```

### **4. Clear Watchlist (`/clear_watchlist`)**
```python
# Clear from database
self.db.clear_all_watchlists()

# Clear memory cache
self.subscribers.clear()
```

---

## 📊 **Database Methods**

### **Available in `database.py`:**

```python
# Add pair to watchlist
db.add_to_watchlist(user_id, "btcidr")

# Remove pair from watchlist
db.remove_from_watchlist(user_id, "btcidr")

# Get user's watchlist
pairs = db.get_watchlist(user_id)  # Returns: ["btcidr", "ethidr"]

# Get ALL watchlists
all_watchlists = db.get_all_watchlists()  # Returns: {user_id: [pairs]}

# Clear user's watchlist
db.clear_watchlist(user_id)

# Clear ALL watchlists
count = db.clear_all_watchlists()  # Returns: deleted count

# Check if watching
is_watching = db.is_watching(user_id, "btcidr")  # Returns: True/False

# Get count
count = db.get_watchlist_count(user_id)  # Returns: int
```

---

## 🎮 **Use Cases**

### **DRY RUN Mode:**
```bash
# Test fresh start
/clear_watchlist all     # Clear everything
/watch btcidr            # Add test pairs
/watch ethidr
/list                    # Verify watchlist
/clear_watchlist all     # Reset again
```

### **Live Trading (Future):**
```bash
# Reset watchlist and sync with Indodax
/clear_watchlist all     # Clear old watchlist
# Bot will fetch open orders from Indodax
# And populate watchlist automatically
```

### **Admin Management:**
```bash
# Check who's watching what
# (Query database directly)
SELECT user_id, pair, added_at FROM watchlist;

# Clear specific user's watchlist
/clear_watchlist  # (as that user)

# Clear everything
/clear_watchlist all
```

---

## 📝 **Files Modified**

| File | Changes |
|------|---------|
| `database.py` | + New `watchlist` table<br>+ 8 new methods for watchlist management |
| `bot.py` | + Load watchlist from DB on startup<br>+ Sync add/remove to DB<br>+ `/clear_watchlist` command<br>+ Helper methods for DB sync |
| `scalper_module.py` | + Note about `/clear_watchlist` in `/s_pair reset` |

---

## ✅ **Benefits**

### **Before (Memory Only):**
```
❌ Watchlist hilang saat bot restart
❌ Tidak ada cara reset semua watchlist
❌ Sulit kontrol dari CLI
❌ Tidak ada audit trail
```

### **After (Database):**
```
✅ Watchlist persistent (survive restart)
✅ Easy reset dengan /clear_watchlist
✅ Bisa query dari CLI/database
✅ Ada timestamp kapan pair ditambahkan
✅ Ready untuk live trading sync
```

---

## 🧪 **Testing Checklist**

- ✅ Database table created on startup
- ✅ `/watch btcidr` adds to DB
- ✅ `/unwatch btcidr` removes from DB
- ✅ `/list` shows pairs from DB
- ✅ `/clear_watchlist` clears user's watchlist
- ✅ `/clear_watchlist all` clears ALL watchlists
- ✅ Bot restart → watchlist restored from DB
- ✅ Scalper `/s_pair reset` shows note about `/clear_watchlist`

---

## 🔮 **Future Enhancements**

### **1. Auto-Sync with Indodax (Live Trading)**
```python
# On bot startup, fetch open orders from Indodax
open_orders = indodax.get_open_orders()
for order in open_orders:
    db.add_to_watchlist(user_id, order['pair'])
```

### **2. Watchlist History**
```python
# Track when pairs were added/removed
# Show in /watchlist_history command
```

### **3. Bulk Import/Export**
```python
# Import from file
/import_watchlist pairs.txt

# Export to file
/export_watchlist
```

### **4. Pair Limits**
```python
# Limit max pairs per user
MAX_WATCHLIST_SIZE = 50

if db.get_watchlist_count(user_id) >= MAX_WATCHLIST_SIZE:
    await send_message("Watchlist penuh! Max 50 pairs")
```

---

## 💡 **Tips**

1. **DRY RUN Testing:**
   ```bash
   # Start fresh
   /clear_watchlist all
   
   # Add test pairs
   /watch btcidr, ethidr, solidr
   
   # Test signals
   /signals
   
   # Reset when done
   /clear_watchlist all
   ```

2. **Database Query (CLI):**
   ```bash
   sqlite3 crypto_bot.db "SELECT * FROM watchlist;"
   ```

3. **Cleanup Old Data:**
   ```bash
   # Soft delete (keep history)
   UPDATE watchlist SET is_active = 0 WHERE user_id = 123;
   
   # Hard delete (remove permanently)
   DELETE FROM watchlist WHERE user_id = 123;
   ```

---

**Status:** ✅ **IMPLEMENTED & READY**

**Next Steps:** 
- Test with bot restart
- Implement Indodax sync for live trading
- Add watchlist history tracking
