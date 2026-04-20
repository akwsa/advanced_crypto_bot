# 🔧 Signal Notification Not Firing Fix

## ❌ Masalah: Notifikasi BUY/SELL Tidak Keluar Setelah Pertama Kali

**User report:** "Notifikasi masuk untuk BUY/SELL/STRONG_BUY/STRONG_SELL belum juga keluar, padahal sudah ada notif BUY juga"

**Root Cause:**

```python
# HANYA firing SEKALI saat mencapai 60 candles!
if candle_count >= 60 and not getattr(self.bot, f'_signal_sent_{pair}', False):
    setattr(self.bot, f'_signal_sent_{pair}', True)  # ← Mark as sent (PERMANENT!)
    # Fire signal...
    
# Setelah ini: TIDAK PERNAH fire lagi karena flag sudah True!
```

**Akibat:**
- Notifikasi BUY pertama keluar (saat pair pertama kali mencapai 60 candles)
- Setelah itu: **TIDAK ADA notifikasi lagi** karena `_signal_sent_{pair} = True`
- User tidak dapat update sinyal berikutnya

---

## ✅ Solusi: Hapus Flag, Call `_monitor_strong_signal` Setiap Poll

**Sebelum:**
```python
# Fire SEKALI saja
if candle_count >= 60 and not getattr(self.bot, f'_signal_sent_{pair}', False):
    setattr(self.bot, f'_signal_sent_{pair}', True)  # Permanent flag
    signal = await _generate_signal_for_pair(pair)
    # ... send notification
```

**Sesudah:**
```python
# Fire SETIAP poll (tapi _monitor_strong_signal ada rate limit 5 menit)
if candle_count >= 60:
    await self.bot._monitor_strong_signal(pair)  # Rate limit: 5 min/pair
    
    if self.bot.is_trading:
        asyncio.create_task(self.bot._check_trading_opportunity(pair))
```

**Cara Kerja `_monitor_strong_signal`:**
```python
async def _monitor_strong_signal(self, pair):
    # Rate limit: check every 5 minutes per pair
    last_check = self._last_signal_checks.get(pair)
    if last_check and datetime.now() - last_check < timedelta(minutes=5):
        return  # Too soon, skip
    
    self._last_signal_checks[pair] = datetime.now()
    
    # Generate signal
    signal = await self._generate_signal_for_pair(pair)
    
    # Only notify for BUY/SELL/STRONG_BUY/STRONG_SELL
    if recommendation in ['STRONG_BUY', 'STRONG_SELL', 'BUY', 'SELL']:
        send_notification()
```

---

## 📊 Flow Baru

```
1. Poller update harga setiap 15 detik
   ↓
2. Candle count >= 60? 
   - YA → Call _monitor_strong_signal(pair)
   - TIDAK → Skip (data belum cukup)
   ↓
3. _monitor_strong_signal:
   - Last check < 5 menit? → Skip (rate limit)
   - Last check >= 5 menit? → Generate signal
   ↓
4. Signal = BUY/SELL/STRONG_BUY/STRONG_SELL?
   - YA → Kirim notifikasi ke Telegram ✅
   - TIDAK (HOLD) → Skip
   ↓
5. User dapat notifikasi setiap ada sinyal kuat!
```

---

## 📝 Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `price_poller.py` | -15 / +6 (×2) | Removed _signal_sent flag, added _monitor_strong_signal call |

**Total:** ~18 lines changed

---

## ✅ Status

**Fix Date:** April 2026  
**Status:** ✅ COMPLETE  
**Tested:** Pending user verification

**Expected Result:**
- ✅ Notifikasi BUY/SELL keluar SETIAP ada sinyal kuat (bukan cuma sekali)
- ✅ Rate limit: max 1 notifikasi per 5 menit per pair (no spam)
- ✅ Hanya pair di watchlist (`/watch`) yang dapat notifikasi
- ✅ Hanya BUY/SELL/STRONG_BUY/STRONG_SELL yang dikirim (HOLD di-skip)

**Test Scenario:**
```
User: /watch btcidr,ethidr

[Wait for 60+ candles ~15 menit]

Bot: 📊 Signal Alert
     🚀 btcidr - STRONG_BUY (confidence 89%)

[Wait 5 menit]

Bot: 📊 Signal Alert
     📈 ethidr - BUY (confidence 75%)

[Wait 5 menit lagi]

Bot: 📊 Signal Alert
     🚀 btcidr - STRONG_SELL (confidence 92%)
     
... dan seterusnya setiap ada sinyal kuat!
```
