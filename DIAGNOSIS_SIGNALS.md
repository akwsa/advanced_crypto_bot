# Diagnosis: Tidak Ada Signal BUY/SELL di Telegram

**Tanggal:** 2026-04-15  
**Status:** ❌ NO SIGNALS  
**Root Cause:** Price Poller tidak berjalan / tidak menyimpan data ke DB

---

## ROOT CAUSE ANALYSIS

### Yang Ditemukan:

1. **Watchlist di Database: ✅ OK**
   - User 256024600 punya 56 pairs di watchlist
   - _monitor_strong_signal AKAN mengirim signal untuk pair ini

2. **Historical Data di Database: ❌ KRITIS**
   - btcidr: **HANYA 5 CANDLES** (butuh 60+)
   - ethidr: **HANYA 5 CANDLES**
   - solidr: **TIDAK ADA DATA**
   - xrpidr: **TIDAK ADA DATA**
   - adaidr: **TIDAK ADA DATA**

3. **ML Model: ✅ OK**
   - File ada: models/trading_model.pkl (3.1 MB)
   - CONFIDENCE_THRESHOLD: 0.55 (sudah diturunkan dari 0.65)

4. **Redis: ✅ OK**
   - Connection available
   - Tapi cache size: 0 pairs (belum ada data)

5. **Config: ✅ OK**
   - AUTO_TRADE_DRY_RUN: true (aman untuk test)
   - 8 pairs di WATCH_PAIRS config

---

## KENAPA TIDAK ADA SIGNAL?

### Flow Signal Generation:

```
Price Poller (setiap 15 detik)
  ↓
Poll harga dari Indodax API
  ↓
Simpan ke DB (save_price)
  ↓
Update historical_data (in-memory)
  ↓
IF candle_count >= 60:
  → _monitor_strong_signal()
    → Generate signal (TA + ML)
    → IF signal = BUY/SELL:
      → Kirim ke Telegram
```

### Masalah:

**Cuma ada 5 candles per pair** → **TIDAK PERNAH mencapai 60 candles** → **_monitor_strong_signal TIDAK PERNAH dipanggil** → **TIDAK ADA SIGNAL**

---

## KEMUNGKINAN PENYEBAB:

### A. Bot Belum Pernah Running
- Kalau bot belum pernah di-start, price poller belum jalan
- Data 5 candles mungkin dari test sebelumnya yang tidak selesai

### B. Price Poller Error Saat Runtime
- Poller start tapi error saat fetch data
- Atau error saat save ke DB
- Cek log file untuk error

### C. Poller Jalan Tapi Terlalu Lambat
- 8 pairs × ~0.6s delay = ~5s per cycle
- 15s interval = 4 cycles per minute
- Butuh 60 candles = **15 minutes minimum**
- Kalau bot baru running < 15 menit, belum cukup data

### D. Poller Gagal Save ke DB
- DB connection issue
- Table structure issue
- Save berhasil tapi query read gagal

---

## SOLUSI

### STEP 1: Cek Apakah Bot Sedang Running

```bash
# Cek apakah process bot.py ada
tasklist | findstr python

# Atau cek log file
type logs\*.log | findstr "Polling"
type logs\*.log | findstr "Candle saved"
```

**Jika TIDAK ADA output:** Bot tidak running → Start bot

### STEP 2: Start Bot dan Tunggu 15-20 Menit

```bash
# Cara 1: Foreground (lihat log langsung)
python bot.py

# Cara 2: Background (Windows)
start_bot_bg.bat
```

**Tunggu 15-20 menit** agar price poller mengumpulkan 60+ candles.

### STEP 3: Monitor Log

Cari message ini di log:
```
🔄 Polling X pair(s)
📊 Polled btcidr: xxxxx
🕯️ Candle saved for btcidr: xxxxx | Total candles: Y
```

**Jika "Total candles" bertambah setiap 15 detik:** Poller jalan OK ✅  
**Jika tidak ada message:** Poller error ❌

### STEP 4: Cek Data di DB Setelah 15 Menit

```bash
python -c "
from core.database import Database
db = Database()
for pair in ['btcidr', 'ethidr', 'bridr']:
    df = db.get_price_history(pair, limit=5)
    print(f'{pair}: {len(df)} candles')
"
```

**Jika sudah 60+ candles:** Signal akan muncul ✅  
**Jika masih < 60:** Tunggu lebih lama atau cek error

### STEP 5: Force Generate Signal (Test Manual)

Jika ingin test signal generation tanpa tunggu 15 menit:

```bash
python -c "
import asyncio
from core.database import Database
from analysis.technical_analysis import TechnicalAnalysis

db = Database()

# Load data untuk btcidr
df = db.get_price_history('btcidr', limit=100)
print(f'Candles available: {len(df)}')

if len(df) >= 60:
    # Test TA
    ta = TechnicalAnalysis(df)
    indicators = ta.calculate_all()
    print(f'RSI: {indicators.get(\"rsi\", 0):.2f}')
    print(f'MACD: {indicators.get(\"macd_signal\", \"NEUTRAL\")}')
    print(f'Signal: {indicators.get(\"recommendation\", \"HOLD\")}')
else:
    print(f'Not enough data: need 60+, have {len(df)}')
"
```

---

## QUICK FIX: Preload Historical Data

Jika ingin signal langsung muncul tanpa tunggu 15 menit, preload data dari Indodax:

**File:** `preload_data.py` (akan saya buat jika diperlukan)

Script ini akan:
1. Fetch 200+ candles historical data dari Indodax
2. Save ke DB
3. Bot langsung bisa generate signal saat start

---

## VERIFICATION CHECKLIST

Setelah start bot, cek ini:

- [ ] Bot start tanpa error
- [ ] Log muncul: "Price poller thread started"
- [ ] Log muncul: "Polling X pair(s)" setiap 15 detik
- [ ] Log muncul: "Candle saved for btcidr" dengan count bertambah
- [ ] Setelah 15 menit: count >= 60
- [ ] Signal muncul di Telegram (BUY/SELL)
- [ ] Signal muncul setiap 5 menit (rate limit per pair)

---

## RECOMMENDATION

**SOLUTION 1: Just Wait (Easiest)**
- Start bot
- Wait 15-20 minutes
- Signals will appear automatically

**SOLUTION 2: Preload Data (Fastest)**
- I create preload script
- Fetch historical data from Indodax API
- Bot has data immediately
- Signals appear within 1-2 minutes

**SOLUTION 3: Check for Errors (If Poller Not Running)**
- Check logs for errors
- Fix any issues
- Restart bot

---

## NEXT ACTION

Mau saya:
A. Buat script untuk preload historical data (signal muncul dalam 1-2 menit)?
B. Cek log file untuk error (kalau bot sudah running)?
C. Tunggu 15-20 menit dengan bot running (no action needed)?
