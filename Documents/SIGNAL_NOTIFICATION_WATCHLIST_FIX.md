# 🔧 Signal Notification Fix - Watchlist Pairs Only

## ❌ Masalah: Notifikasi Tidak Keluar

**User report:** "belum jalan" - tidak ada notifikasi BUY/SELL yang masuk

**Root Cause Analysis:**

1. **Rate limit terlalu panjang (15 menit)** - User harus tunggu terlalu lama untuk notifikasi pertama
2. **Tidak ada filter untuk watchlist pairs** - Bot seharusnya hanya kirim notifikasi untuk pair yang user tambahkan via `/watch`

---

## ✅ Solusi yang Diterapkan

### Fix 1: Filter Hanya untuk Watchlist Pairs

**Sebelum:**
```python
# Monitor SEMUA pairs (termasuk yang tidak di-watch)
async def _monitor_strong_signal(self, pair):
    # Langsung generate signal tanpa cek apakah pair di-watchlist
```

**Sesudah:**
```python
async def _monitor_strong_signal(self, pair):
    # Cek apakah pair ada di watchlist ANY user
    is_watched = False
    for user_id, pairs in self.subscribers.items():
        if pair in pairs:
            is_watched = True
            break
    
    if not is_watched:
        return  # Pair tidak di-watch, skip!
```

**Artinya:**
- ✅ Hanya pair yang ditambahkan via `/watch` yang dimonitor
- ✅ Pair di config.WATCH_PAIRS tapi tidak di `/watch` → TIDAK dapat notifikasi
- ✅ Pair di auto_trade_pairs tapi tidak di `/watch` → TIDAK dapat notifikasi

---

### Fix 2: Reduce Rate Limit (15 menit → 5 menit)

**Sebelum:**
```python
if last_check and datetime.now() - last_check < timedelta(minutes=15):
    return  # Tunggu 15 menit terlalu lama!
```

**Sesudah:**
```python
if last_check and datetime.now() - last_check < timedelta(minutes=5):
    return  # 5 menit lebih responsif
```

**Impact:**
```
Sebelum: User tambah pair → tunggu 15 menit → notifikasi pertama
Sesudah: User tambah pair → tunggu 5 menit → notifikasi pertama ✅
```

---

## 📊 Flow Notifikasi Baru

```
1. User: /watch btcidr,ethidr,solidr
   ↓
2. Bot: pair masuk ke self.subscribers[user_id]
   ↓
3. Price poller update harga setiap 15 detik
   ↓
4. _process_price_update() dipanggil
   ↓
5. asyncio.create_task(_monitor_strong_signal(pair))
   ↓
6. Cek: Apakah pair di subscribers? 
   - YA → Lanjut generate signal
   - TIDAK → Skip (tidak di-watch)
   ↓
7. Rate limit: Terakhir check < 5 menit?
   - YA → Skip (tunggu berikutnya)
   - TIDAK → Lanjut
   ↓
8. Generate signal
   ↓
9. Jika recommendation in [BUY, SELL, STRONG_BUY, STRONG_SELL]:
   → Kirim notifikasi ke Telegram ✅
   ↓
10. User dapat notifikasi!
```

---

## 📝 Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `bot.py` | +15 | Added watchlist filter + reduced rate limit |

**Total:** +15 lines changed

---

## ✅ Status

**Fix Date:** April 2026  
**Status:** ✅ COMPLETE  
**Tested:** Pending user verification

**Expected Result:**
- ✅ Hanya pair di watchlist (`/watch`) yang dapat notifikasi
- ✅ Notifikasi pertama muncul dalam 5 menit (bukan 15)
- ✅ BUY/SELL/STRONG_BUY/STRONG_SELL selalu dikirim
- ✅ HOLD tidak dikirim (tidak berguna)
- ✅ Max 1 notifikasi per 5 menit per pair (no spam)

**Test Scenario:**
```
User: /watch btcidr,ethidr
[Wait 5 minutes]
Bot: 📊 Signal Alert
     🚀 btcidr - STRONG_BUY (confidence 89%)
     
[Wait 5 minutes lagi]
Bot: 📊 Signal Alert
     📈 ethidr - BUY (confidence 75%)
```
