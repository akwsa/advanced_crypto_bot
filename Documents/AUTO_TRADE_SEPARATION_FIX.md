# 🔧 Auto-Trade Pairs Separation & Smart Hunter Integration Fix

## 📋 Ringkasan Perubahan

Dua masalah utama telah diperbaiki:

1. **Auto-Trade Pairs Terpisah** - Auto-trade sekarang hanya trade pair yang secara eksplisit ditambahkan ke daftar auto-trade (BUKAN semua pair di watchlist)
2. **Smart Hunter Terintegrasi** - `/hunter_status` sekarang menggunakan `self.smart_hunter` yang terintegrasi, bukan menyuruh user jalankan file terpisah

---

## 🔍 Masalah Sebelumnya

### Masalah 1: Auto-Trade Campur dengan Watchlist/Scalping

**Sebelumnya:**
```
/watch btcidr,ethidr,solidr  ← Watchlist untuk monitoring
/autotrade on                ← Auto-trade SEMUA pair di watchlist!
```

**Akibat:**
- ❌ Semua pair di watchlist di-auto-trade (tidak diinginkan)
- ❌ Pair scalping juga ikut di-auto-trade (berbahaya!)
- ❌ Tidak ada cara untuk memisahkan auto-trade dari scalping
- ❌ User tidak bisa kontrol pair mana yang di-auto-trade

### Masalah 2: Smart Hunter Tidak Terintegrasi

**Sebelumnya:**
```
/hunter_status

Output:
📊 Hunter Status: ⚪️ NOT RUNNING
💡 To Start Hunter:
python smart_hunter_v3.py   ←←← INI MASALAHNYA!
```

**Akibat:**
- ❌ User disuruh jalankan file terpisah (`python smart_hunter_v3.py`)
- ❌ Padahal `smart_hunter_integration.py` sudah ada dan terintegrasi
- ❌ Membingungkan user (kenapa harus jalankan 2 bot?)
- ❌ Status tidak akurat (cek log file, bukan actual state)

---

## ✅ Solusi yang Diterapkan

### Solusi 1: Auto-Trade Pairs List (TERPISAH)

#### A. Data Structure Baru
```python
# bot.py line ~135
self.auto_trade_pairs: Dict[int, List[str]] = {}  # {user_id: [pair1, pair2, ...]}
```

**Karakteristik:**
- ✅ Terpisah dari `self.subscribers` (watchlist)
- ✅ Per-user (multi-user support)
- ✅ Pair harus ditambahkan eksplisit untuk auto-trade
- ✅ Watchlist (`/watch`) TIDAK otomatis di-auto-trade

#### B. Command Baru

| Command | Fungsi |
|---------|--------|
| `/add_autotrade <pair>` | Tambah pair ke daftar auto-trade |
| `/remove_autotrade <pair>` | Hapus pair dari daftar auto-trade |
| `/list_autotrade` | Lihat pair yang sedang di-auto-trade |

**Contoh Penggunaan:**
```bash
# Tambah pair untuk auto-trade
/add_autotrade btcidr
/add_autotrade btcidr,ethidr,solidr

# Lihat daftar auto-trade
/list_autotrade

# Hapus pair dari auto-trade
/remove_autotrade btcidr
```

#### C. Tombol /start Diperbarui

**Sebelumnya:**
```
[📝 Add First Pair]  ← callback_data="help" (membingungkan)
```

**Sesudah:**
```
[🤖 Setup Auto-Trade Pairs]  ← callback_data="autotrade_add_pair"
[🤖 Auto-Trade: 3 pair(s)]   ← callback_data="autotrade_add_pair" (jika ada pair)
```

#### D. _check_trading_opportunity Diperbarui

**Sebelumnya:**
```python
async def _check_trading_opportunity(self, pair):
    if not self.is_trading:
        return
    # ← Auto-trade SEMUA pair (termasuk watchlist/scalper!)
```

**Sesudah:**
```python
async def _check_trading_opportunity(self, pair):
    if not self.is_trading:
        return
    
    # IMPORTANT: Only trade pairs in auto_trade_pairs list
    is_auto_trade_pair = False
    for user_id, pairs in self.auto_trade_pairs.items():
        if pair in pairs:
            is_auto_trade_pair = True
            break
    
    if not is_auto_trade_pair:
        logger.debug(f"⏭️ Skipping {pair}: Not in auto-trade list")
        return  # ← SKIP jika tidak ada di daftar auto-trade
```

---

### Solusi 2: Smart Hunter Integration Fixed

#### A. hunter_status() Diperbarui

**Sebelumnya:**
```python
# Cek log file (cara lama - tidak akurat)
import os
hunter_running = os.path.exists('logs/smart_hunter.log')
status_text = "RUNNING" if hunter_running else "NOT RUNNING"

# Salah! Suruh user jalankan file terpisah
text += "💡 To Start Hunter:\n"
text += "```\npython smart_hunter_v3.py\n```\n"
```

**Sesudah:**
```python
# Gunakan integrated smart_hunter (cara baru - akurat)
hunter_status_data = self.smart_hunter.get_status()
is_running = hunter_status_data.get('is_running', False)

status_text = "RUNNING (Integrated)" if is_running else "STOPPED"
text += f"🔗 Mode: Terintegrasi dengan bot utama\n"

# Tampilkan stats internal smart_hunter
active_positions = hunter_status_data.get('active_trades', 0)
daily_trades = hunter_status_data.get('daily_trades', 0)
daily_pnl = hunter_status_data.get('daily_pnl', 0)
hunter_balance = hunter_status_data.get('balance', 0)

text += f"📊 Smart Hunter Internal Stats:\n"
text += f"• Active Positions: {active_positions}\n"
text += f"• Daily Trades: {daily_trades}\n"
text += f"• Daily P&L: {daily_pnl:,.0f} IDR\n"
text += f"• Hunter Balance: {hunter_balance:,.0f} IDR\n"

# Commands - FIXED: No more external file reference
text += "💡 Kontrol Smart Hunter:\n"
text += "• /smarthunter on - Start Smart Hunter (integrated)\n"
text += "• /smarthunter off - Stop Smart Hunter\n"
text += "• /smarthunter_status - Detail status & posisi\n"
```

#### B. Smart Hunter Stats Ditampilkan

Output `/hunter_status` sekarang menampilkan:
```
🤖 SMART HUNTER STATUS

📊 Hunter Status: 🟢 RUNNING (Integrated)
🔗 Mode: Terintegrasi dengan bot utama

📈 Today's Performance (2026-04-09):
• Hunter Trades: 5
• Wins: 4 | Losses: 1
• Win Rate: 80.0%
• P&L: +250,000 IDR

📊 Smart Hunter Internal Stats:
• Active Positions: 2
• Daily Trades: 5
• Daily P&L: 250,000 IDR
• Hunter Balance: 1,250,000 IDR

📊 Open Positions (2):
📈 BUY btcidr
   Entry: 1,450,000,000 | Current: 1,470,000,000 IDR
   P&L: +1.4% | Amount: 0.001

💵 Indodax Balance: 1,000,000 IDR

💡 Kontrol Smart Hunter:
• /smarthunter on - Start Smart Hunter (integrated)
• /smarthunter off - Stop Smart Hunter
• /smarthunter_status - Detail status & posisi
```

---

## 📊 Arsitektur Baru

### Sistem Pair Management

```
┌─────────────────────────────────────────────┐
│              PAIR DI BOT                    │
├─────────────────────────────────────────────┤
│                                             │
│  1. WATCHLIST (/watch)                      │
│     - Untuk monitoring harga                │
│     - Untuk scalping manual                 │
│     - TIDAK auto-trade otomatis             │
│     - self.subscribers[user_id]             │
│                                             │
│  2. AUTO-TRADE PAIRS (/add_autotrade)       │
│     - KHUSUS untuk auto-trade               │
│     - Terpisah dari watchlist               │
│     - Hanya pair ini yang di-auto-trade     │
│     - self.auto_trade_pairs[user_id]        │
│                                             │
│  3. SCALPER PAIRS (/s_pair add)             │
│     - Untuk scalper module                  │
│     - Juga terpisah                         │
│     - self.scalper.pairs                    │
│                                             │
└─────────────────────────────────────────────┘
```

### Flow Auto-Trade Baru

```
1. User tambah pair ke watchlist:
   /watch btcidr,ethidr,solidr  ← Hanya untuk monitoring

2. User tambah pair ke auto-trade:
   /add_autotrade btcidr,ethidr  ← Hanya ini yang di-auto-trade

3. User enable auto-trade:
   /autotrade dryrun

4. Bot polling harga SEMUA pair di watchlist (setiap 10s)

5. Bot CEK: Apakah pair ini di auto_trade_pairs?
   - BTCIDR → YES → Check opportunity → Trade jika signal kuat
   - ETHIDR → YES → Check opportunity → Trade jika signal kuat  
   - SOLIDR → NO → Skip auto-trade (hanya monitoring)

6. Scalping TIDAK terpengaruh (terpisah sama sekali)
```

---

## 📝 Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `bot.py` | +15 | Added `auto_trade_pairs` dict |
| `bot.py` | +180 | Added `add_autotrade()`, `remove_autotrade()`, `list_autotrade()` |
| `bot.py` | +15 | Updated `/start` menu button |
| `bot.py` | +25 | Updated `callback_handler` for `autotrade_add_pair` |
| `bot.py` | +10 | Registered new command handlers |
| `bot.py` | +12 | Updated `_check_trading_opportunity()` filter |
| `bot.py` | +80 | Fixed `hunter_status()` to use integrated smart_hunter |

**Total:** ~337 lines changed

---

## 🧪 Testing Checklist

### Test 1: Auto-Trade Pairs Separation
```bash
# 1. Tambah pair ke watchlist (BUKAN auto-trade)
/watch btcidr,ethidr,solidr

# 2. Cek daftar auto-trade (harus kosong)
/list_autotrade
# Expected: "Belum ada pair di daftar auto-trade!"

# 3. Tambah pair ke auto-trade
/add_autotrade btcidr,ethidr

# 4. Cek lagi (harus ada 2 pair)
/list_autotrade
# Expected: BTCIDR, ETHIDR (SOLIDR tidak ada)

# 5. Enable auto-trade
/autotrade dryrun

# 6. Tunggu dan cek log
# Expected: Hanya BTCIDR dan ETHIDR yang di-auto-trade
# Expected: SOLIDR di-skip (ada di watchlist tapi tidak di auto-trade)
```

### Test 2: Scalping Tidak Terpengaruh
```bash
# 1. Tambah pair ke scalper
/s_pair add solidr

# 2. Tambah pair berbeda ke auto-trade
/add_autotrade btcidr

# 3. Scalping solidr manual
/s_menu → BUY SOLIDR

# Expected: 
# - Scalping SOLIDR bekerja normal
# - Auto-trade hanya untuk BTCIDR
# - Tidak ada konflik
```

### Test 3: Smart Hunter Integration
```bash
# 1. Cek hunter status
/hunter_status

# Expected:
# - Status: "RUNNING (Integrated)" atau "STOPPED"
# - Mode: "Terintegrasi dengan bot utama"
# - TIDAK ADA pesan "python smart_hunter_v3.py"
# - Tampil stats internal smart_hunter

# 2. Start smart hunter
/smarthunter on

# 3. Cek lagi
/hunter_status
# Expected: Status jadi "RUNNING (Integrated)"
```

---

## 🎯 Expected User Experience

### Scenario: User ingin scalping + auto-trade terpisah

```
User ingin:
- Scalping: BTCIDR, ETHIDR, SOLIDR (manual via /s_menu)
- Auto-trade: Hanya BTCIDR (otomatis)
- Monitoring: BTCIDR, ETHIDR, SOLIDR, DOGEIDR

Cara setup:
1. /watch btcidr,ethidr,solidr,dogeidr     ← Monitoring
2. /s_pair add btcidr,ethidr,solidr        ← Scalping
3. /add_autotrade btcidr                   ← Auto-trade HANYA btcidr
4. /autotrade dryrun                       ← Enable auto-trade

Hasil:
✅ Monitoring: 4 pairs (semua di watchlist)
✅ Scalping: 3 pairs (btcidr, ethidr, solidr)
✅ Auto-trade: 1 pair (btcidr saja!)
✅ Tidak ada konflik!
```

---

## ✅ Status

**Fix Date:** April 2026  
**Status:** ✅ COMPLETE  
**Tested:** Pending user verification

**Kesimpulan:**
1. ✅ Auto-trade sekarang TERPISAH dari watchlist/scalping
2. ✅ Smart Hunter sudah terintegrasi (tidak perlu jalankan file terpisah)
3. ✅ User punya kontrol penuh atas pair mana yang di-auto-trade
4. ✅ Scalping tidak terpengaruh auto-trade (dan sebaliknya)
