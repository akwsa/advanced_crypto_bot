# 🔧 Change Percent Fix & Signal Notification Trigger

## ❌ Masalah 1: Change Percent Selalu +0.00%

**Log:**
```
📊 Polled ADAIDR: 4,253 IDR (+0.00%)
📊 Polled BTCIDR: 1,210,762,000 IDR (+0.00%)
📊 Polled DOGEIDR: 1,563 IDR (+0.00%)
```

**Root Cause:**
```python
change_pct = ticker.get('change_percent', 0)  # Indodax TIDAK selalu provide ini!
```

**Akibat:**
- Semua change percent tampil 0.00%
- User tidak tahu apakah harga naik/turun
- Tidak ada perubahan harga yang terdeteksi

---

## ✅ Fix 1: Hitung Change Percent Manual

**Sebelum:**
```python
change_pct = ticker.get('change_percent', 0)  # Selalu 0!
```

**Sesudah:**
```python
# Hitung dari harga sebelumnya
old_price = self.bot.price_data.get(pair, {}).get('last', last_price)
if old_price > 0:
    change_pct = ((last_price - old_price) / old_price) * 100
else:
    change_pct = 0.0
```

**Expected Log:**
```
📊 Polled ADAIDR: 4,253 IDR (+0.00%)  ← First poll (no previous)
📊 Polled BTCIDR: 1,210,762,000 IDR (+0.00%)  ← First poll
...
📊 Polled ADAIDR: 4,254 IDR (+0.02%)  ← Next poll (ada perubahan!)
📊 Polled BTCIDR: 1,211,000,000 IDR (+0.02%)  ← Next poll
```

---

## ❌ Masalah 2: Notifikasi BUY/SELL/HOLD Belum Keluar

**Root Cause:**
```python
# Signal hanya dikirim jika:
# 1. Pair ada di auto_trade_pairs DAN
# 2. is_trading == True DAN
# 3. Sudah 60+ candles

# Jika pair cuma di watchlist (bukan auto_trade):
# → TIDAK ada monitoring signal!
```

**Akibat:**
- User tidak dapat notifikasi sinyal kuat
- Hanya auto-trade pairs yang dimonitor
- Watchlist pairs diabaikan

---

## ✅ Fix 2: Monitor Strong Signal untuk SEMUA Watched Pairs

**Sebelum:**
```python
# Hanya di _check_trading_opportunity (auto-trade only)
if self.is_trading:
    asyncio.create_task(self._check_trading_opportunity(pair))
```

**Sesudah:**
```python
# Auto-trade pairs
if self.is_trading:
    asyncio.create_task(self._check_trading_opportunity(pair))

# SEMUA watched pairs (termasuk watchlist)
asyncio.create_task(self._monitor_strong_signal(pair))  # ← BARU!
```

**Artinya:**
- ✅ SEMUA pair di watchlist dimonitor untuk sinyal kuat
- ✅ Notifikasi dikirim jika ada STRONG_BUY/STRONG_SELL/BUY/SELL
- ✅ Rate limit: max 1 notifikasi per 15 menit per pair
- ✅ Tidak perlu auto-trade enabled

---

## 📊 Flow Notifikasi Baru

```
1. Price poller update harga setiap 15 detik
   ↓
2. _process_price_update() dipanggil
   ↓
3. asyncio.create_task(_monitor_strong_signal(pair))
   ↓
4. Generate signal untuk pair
   ↓
5. Jika recommendation in [STRONG_BUY, STRONG_SELL, BUY, SELL]:
   → Kirim notifikasi ke Telegram
   → Catat waktu terakhir check (rate limit 15 menit)
   ↓
6. User dapat notifikasi! ✅
```

---

## 📝 Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `price_poller.py` | +8 (×2) | Manual change percent calculation |
| `bot.py` | +2 | Added _monitor_strong_signal call |

**Total:** +18 lines changed

---

## ✅ Status

**Fix Date:** April 2026  
**Status:** ✅ COMPLETE  
**Tested:** Pending user verification

**Expected Result:**
- ✅ Change percent tampil benar (bukan selalu 0.00%)
- ✅ Notifikasi BUY/SELL/HOLD keluar untuk SEMUA watched pairs
- ✅ Max 1 notifikasi per 15 menit per pair (no spam)
- ✅ Tidak perlu auto-trade enabled untuk dapat notifikasi
