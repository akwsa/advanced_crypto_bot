# 🔧 WebSocket Reconnect Fix

## ❌ Masalah Sebelum Fix

**Symptom:**
- WebSocket connect → subscribe → disconnect → reconnect (loop setiap 30 detik)
- **Tidak ada trade data yang masuk**
- Log spam dengan: `✅ WebSocket connected to Indodax`
- Bot tidak pernah scanning untuk auto-trade

**Root Cause:**
- Tidak ada **heartbeat/ping mechanism**
- Indodax server memutuskan connection jika idle
- Bot langsung reconnect tanpa delay (spam reconnect)

---

## ✅ Fix yang Diterapkan

### 1. **WebSocket Ping/Heartbeat**
```python
# Kirim ping setiap 20 detik untuk keep connection alive
def ping_loop():
    while self.is_connected:
        self.ws.ping()
        time.sleep(20)
```

### 2. **Server Ping Configuration**
```python
self.ws.run_forever(
    ping_interval=30,  # Server akan ping setiap 30s
    ping_timeout=10    # Timeout jika 10s tidak ada response
)
```

### 3. **Exponential Backoff untuk Reconnect**
```python
# Delay: 5s → 10s → 20s → 40s → 80s
delay = 5 * (2 ** (attempt - 1))
```

**Sebelum:** Reconnect setiap 5s (spam)  
**Sesudah:** Reconnect dengan delay yang meningkat

### 4. **Auto Reset Reconnect Counter**
```python
# Jika max attempts reached, reset setelah 60s
# Agar bot bisa coba lagi nanti
```

---

## 🧪 Cara Test Fix

### Step 1: Restart Bot
```bash
# Stop bot yang sedang running (Ctrl+C)

# Start ulang
python bot.py
```

### Step 2: Check Log (Harus Berbeda Sekarang)

**❌ SEBELUM Fix (Log Lama):**
```
13:56:31 ✅ WebSocket connected
13:56:31 📡 Subscribed to trades_drxidr
13:57:02 ✅ WebSocket connected     ← RECONNECT LAGI!
13:57:02 📡 Subscribed to trades_drxidr
13:57:15 ✅ WebSocket connected     ← RECONNECT LAGI!
13:57:15 📡 Subscribed to trades_drxidr
... (setiap 30 detik)
```

**✅ SESUDAH Fix (Log yang Diharapkan):**
```
14:10:00 🔌 Connecting to wss://ws3.indodax.com/ws/...
14:10:01 ✅ WebSocket Connected!
14:10:01 📡 Subscribed to trades_drxidr (Public)
14:10:01 📡 Subscribed to trades_pippinidr (Public)
14:10:05 ✅ Updated DRX/IDR price: 150          ← DATA MASUK!
14:10:15 ✅ Updated PIPPIN/IDR price: 603        ← DATA MASUK!
14:10:30 💓 WebSocket ping sent                  ← HEARTBEAT!
14:11:00 💓 WebSocket ping sent                  ← HEARTBEAT!
14:11:30 💓 WebSocket ping sent                  ← HEARTBEAT!
```

**Perbedaan Utama:**
- ✅ Connect **SEKALI** saja (tidak loop)
- ✅ Price data **MASUK** setiap ada trade
- ✅ Ping/heartbeat **TERKIRIM** setiap 20-30s
- ✅ **TIDAK ADA** reconnect berulang

---

### Step 3: Verify di Telegram

```
/autotrade_status
```

**Expected:**
```
📊 Status: 🟢 ACTIVE
🧪 Mode: DRY RUN (Simulation)

⏱️ Last Scan: 2026-04-04 14:15:00  ← HARUS ADA TIMESTAMP!
```

**Last Scan** sekarang harus update setiap 5 menit per pair.

---

### Step 4: Check Dry Run Trades

Tunggu 10-15 menit, lalu check:

**Option 1: Status**
```
/autotrade_status
```

**Option 2: Log**
```bash
Get-Content logs\trading_bot.log -Tail 50 | Select-String "DRY RUN"
```

**Expected:**
```
🧪 DRY RUN Scanning DRX/IDR for auto-trade opportunity...
🧪 DRY RUN Scanning PIPPIN/IDR for auto-trade opportunity...
```

Atau jika ada trade:
```
🧪 [DRY RUN] Simulated BUY for DRX/IDR: 100 @ 150
```

---

## 📊 Expected Timeline Setelah Fix

```
T+0:00  - Bot started
T+0:05  - ✅ WebSocket connected (ONCE)
T+0:10  - 📡 Subscribed to channels
T+0:15  - 💓 First ping sent
T+0:20  - ✅ Price data masuk (jika ada trade di market)
T+2:00  - ~10-20 candles collected
T+10:00 - 60+ candles ready
T+10:05 - 🧪 First DRY RUN scan
T+15:00 - First DRY RUN trade (jika signal kuat)
```

---

## 🔍 Troubleshooting

### Problem 1: Masih Reconnect Berulang

**Check:**
```bash
Get-Content logs\trading_bot.log -Tail 100 | Select-String "WebSocket"
```

**If still reconnecting:**
- Indodax WebSocket server mungkin down
- Network connection issue
- Coba restart bot

---

### Problem 2: Connect Tapi Data Tidak Masuk

**Possible causes:**
1. **Pair tidak likuid** (jarang ada trade)
   - Solution: Tambah pair yang lebih likuid (BTC/IDR, ETH/IDR)

2. **WebSocket channel salah**
   - Check log: harus `trades_btcidr`, `trades_ethidr`, dll
   - Format: `trades_<coin>idr` (lowercase, tanpa slash)

3. **Data format berubah**
   - Check log: `📩 WS Message: {...}`
   - Harus ada field `data` dengan array trades

---

### Problem 3: Last Scan Masih N/A

**Check:**
```bash
Get-Content logs\trading_bot.log -Tail 50 | Select-String "Scanning"
```

**If no "Scanning" log:**
- Data belum 60 candles → tunggu lebih lama
- Auto-trade belum enabled → `/autotrade dryrun`
- Tidak ada pair di watchlist → `/watch BTC/IDR`

**If "Scanning" ada tapi "Last Scan: N/A":**
- Bug di code → check `bot.py` line ~3100

---

## 📝 Files Modified

| File | Changes |
|------|---------|
| `websocket_handler.py` | ✅ Added ping/heartbeat mechanism |
| `websocket_handler.py` | ✅ Added exponential backoff reconnect |
| `websocket_handler.py` | ✅ Added auto-reset reconnect counter |
| `bot.py` | ✅ No changes (sudah benar) |

---

## ✅ Checklist Setelah Restart

- [ ] Bot started tanpa error
- [ ] WebSocket connect **SEKALI** (tidak loop)
- [ ] Subscribed ke channels (DRX, PIPPIN, dll)
- [ ] 💓 Ping sent setiap 20-30 detik
- [ ] ✅ Price data masuk (check log)
- [ ] `/autotrade dryrun` shows enabled
- [ ] `/autotrade_status` shows Last Scan timestamp
- [ ] Setelah 10 menit: dry run scanning aktif
- [ ] Setelah 15 menit: mungkin ada dry run trade

---

**Restart bot sekarang dan monitor log!** 🚀

Expected log pattern:
```
✅ WebSocket connected (hanya SEKALI)
📡 Subscribed to channels
✅ Price data masuk
💓 Ping sent
🧪 DRY RUN Scanning
```

Bukan loop reconnect seperti sebelumnya! 🎯
