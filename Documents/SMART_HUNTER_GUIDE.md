# 🤖 Smart Hunter - Panduan Lengkap

## 📋 Apa itu Smart Hunter?

Smart Hunter adalah **auto-trading bot canggih** yang menggunakan strategi **multi-indicator** untuk menemukan peluang trading terbaik dan **menjual secara bertahap** untuk memaksimalkan profit.

### ✨ Fitur Utama

| Fitur | Deskripsi |
|-------|-----------|
| **Partial Sell** | Jual bertahap: 50% di +3%, 30% di +5%, 20% di +8% |
| **Trailing Stop** | Auto-protect profit dengan trailing stop 1.5% |
| **Hard Stop Loss** | Cut loss otomatis di -2% |
| **Multi-Indicator** | RSI, MACD, Volume, MA, Bollinger Bands |
| **Smart Scoring** | Setiap pair dinilai 0-100, hanya yang terbaik yang ditrade |
| **Daily Limits** | Max 5 trades/hari, max loss 200k/hari |
| **Cooldown** | Wait 5 menit setelah loss sebelum trade lagi |

---

## 🚀 Cara Menjalankan

### 1️⃣ Smart Hunter Sudah Terintegrasi dengan Bot Utama

Tidak perlu menjalankan script terpisah! Smart Hunter sudah ada di dalam `bot.py` dan dikontrol via Telegram.

### 2️⃣ Aktifkan Smart Hunter

Kirim command di Telegram:

```
/smarthunter on
```

Bot akan merespon:
```
🚀 Smart Hunter STARTED

✅ Background monitoring active
📊 Partial sell: +3%, +5%, +8%
🛑 Stop loss: -2%

Use /smarthunter_status to check progress
```

### 3️⃣ Cek Status

```
/smarthunter_status
```

Bot akan menampilkan:
```
🤖 SMART HUNTER STATUS

📊 Status: 🟢 RUNNING
💰 Balance: 1,000,000 IDR
📈 Active Positions: 1
📅 Today's Trades: 2
💵 Daily P&L: +45,000 IDR

📊 Open Positions:
🔹 `PIPPIN/IDR`: Entry `700` IDR, Amount `1142.86`

💡 Commands:
• /smarthunter on - Start Smart Hunter
• /smarthunter off - Stop Smart Hunter
• /smarthunter_status - This message
```

### 4️⃣ Matikan Smart Hunter

```
/smarthunter off
```

Bot akan merespon:
```
🛑 Smart Hunter STOPPED

✅ Background monitoring disabled
📊 Open positions remain active

Use /smarthunter on to restart
```

---

## 📊 Strategi Trading

### 🔍 Entry Criteria (SEMUA harus terpenuhi)

| Indikator | Syarat |
|-----------|--------|
| **RSI** | 30-60 (oversold, belum overbought) |
| **Volume** | Minimal 1.5x rata-rata |
| **MACD** | Bullish (MACD > Signal line) |
| **MA Trend** | Short MA > Long MA (bullish) |
| **Bollinger** | Price di bawah 80% upper band |
| **Min Score** | 60/100 |
| **Risk/Reward** | Minimal 3:1 |

### 💰 Exit Strategy

| Level | Aksi | Persentase |
|-------|------|------------|
| **+3%** | Partial Sell | 50% dari posisi |
| **+5%** | Partial Sell | 30% dari posisi |
| **+8%** | Partial Sell | 20% dari posisi (sisa) |
| **Trailing** | Stop jika turun 1.5% dari highest | Protect profit |
| **-2%** | Hard Stop Loss | Cut loss otomatis |

### 🎯 Contoh Trade

```
Entry: PIPPIN/IDR @ 700 IDR (100,000 IDR = 142.86 coins)

Skenario 1: Profit Naik Bertahap
├─ Harga naik ke 721 (+3%) → Jual 71.43 coins (50%)
├─ Harga naik ke 735 (+5%) → Jual 42.86 coins (30%)
├─ Harga naik ke 756 (+8%) → Jual 28.57 coins (20%)
└─ Notification: "Highest Profit Reached: +8.0%"

Skenario 2: Trailing Stop
├─ Harga naik ke 750 (+7.1%)
├─ Trailing stop aktif di 738.75 (750 - 1.5%)
├─ Harga turun ke 738 → Sell all @ 738
└─ Notification: "Trailing Stop (+5.4%)"

Skenario 3: Stop Loss
├─ Harga turun ke 686 (-2%)
└─ Notification: "Stop Loss (-2%)"
```

---

## 🔔 Notifikasi

### ✅ BUY Notification (Saat Entry)

```
🟢 SMART BUY EXECUTED

📊 Pair: PIPPIN/IDR
💰 Entry: 700 IDR
💵 Amount: 100,000 IDR
📦 Coins: 142.86

📈 Analysis:
• RSI: 35 (Oversold)
• Volume: 2.1x average
• Trend: BULLISH
• Score: 78/100

🎯 Exit Plan:
• Target Profit: 756 IDR (+8% max target)
• Stop Loss: 686 IDR (-2%)

💡 Bot will auto-sell at highest profit reached

⏰ 19:30:45
```

### ✅ SELL Notification (Saat Exit)

**HANYA 1 NOTIFIKASI** dengan profit tertinggi:

```
🎯 POSITION CLOSED - Trailing Stop (+5.4%)

📊 Pair: PIPPIN/IDR
💰 Entry: 700 IDR
💰 Exit: 738 IDR
📈 Highest Profit Reached: +7.1% (✅ 5,432 IDR)
⏰ Duration: 0:15:30

💰 Daily P&L: +45,000 IDR
```

---

## ⚙️ Konfigurasi Advanced

File: `smart_profit_hunter.py` (line 27-40)

```python
# Entry Criteria
MIN_VOLUME_IDR = 1_000_000_000  # Min 1B IDR volume
MAX_POSITION_SIZE = 100_000     # Max 100k per trade
MAX_DAILY_LOSS = 200_000        # Max loss 200k/hari
MAX_TRADES_PER_DAY = 5          # Max 5 trades/hari

# Exit Strategy
TAKE_PROFIT_LEVELS = [
    (3.0, 0.5),   # Sell 50% at +3%
    (5.0, 0.3),   # Sell 30% at +5%
    (8.0, 0.2),   # Sell 20% at +8%
]
STOP_LOSS = -2.0                  # Hard stop di -2%
TRAILING_STOP = True              # Enable trailing
TRAILING_PERCENT = 1.5            # Trail by 1.5%

# Risk Management
MIN_RISK_REWARD = 3.0             # Min risk/reward 3:1
COOLDOWN_AFTER_LOSS = 300         # Wait 5 min setelah loss
```

---

## 🆚 Perbandingan dengan Hunter Lain

| Fitur | Profit Hunter | Smart Hunter V3 | Smart Hunter (Ini) |
|-------|---------------|-----------------|-------------------|
| **Partial Sell** | ❌ Tidak | ❌ Tidak | ✅ Ya (3%, 5%, 8%) |
| **Trailing Stop** | ❌ Tidak | ✅ Ya | ✅ Ya |
| **Multi-Indicator** | ❌ Basic | ✅ Ya | ✅ Ya (Lengkap) |
| **Smart Scoring** | ❌ Tidak | ❌ Tidak | ✅ Ya (0-100) |
| **Notifikasi** | Banyak | 1x | **1x (Highest only)** |
| **Integrasi Bot** | ❌ Standalone | ❌ Standalone | ✅ Terintegrasi |

---

## 📝 Command Reference

| Command | Fungsi |
|---------|--------|
| `/smarthunter` | Show help & cara pakai |
| `/smarthunter on` | Start Smart Hunter |
| `/smarthunter off` | Stop Smart Hunter |
| `/smarthunter_status` | Cek status & posisi aktif |
| `/balance` | Cek saldo Indodax |
| `/scan` | Scan market opportunities |
| `/hunter_status` | Status semua hunter (termasuk smart) |

---

## ⚠️ Penting!

### ✅ Do's
- ✅ Pastikan saldo IDR cukup di Indodax (min 100k)
- ✅ Gunakan di market dengan volume tinggi (>1B/hari)
- ✅ Monitor status dengan `/smarthunter_status`
- ✅ Biarkan berjalan 24/7 untuk hasil optimal

### ❌ Don'ts
- ❌ Jangan jalankan di market illiquid (volume rendah)
- ❌ Jangan set MAX_POSITION_SIZE terlalu tinggi
- ❌ Jangan disable saat ada posisi aktif (posisi tetap jalan)
- ❌ Jangan trade manual di pair yang sedang di-monitor Smart Hunter

---

## 🐛 Troubleshooting

### Smart Hunter tidak start
```
❌ Failed to start Smart Hunter
```

**Solusi:**
1. Cek log: `logs/smart_profit_hunter.log`
2. Pastikan API key Indodax sudah dikonfigurasi
3. Restart bot: `python bot.py`

### Tidak ada trade yang dieksekusi
```
⚠️ Daily trade limit reached
```

**Normal!** Smart Hunter sangat selective. Bisa jadi tidak ada pair yang memenuhi kriteria hari ini.

**Cek:**
1. `/smarthunter_status` - Lihat apakah ada opportunity
2. Market conditions - Mungkin sedang tidak ada setup yang bagus
3. Volume market - Mungkin sedang rendah

### Notifikasi tidak muncul
**Solusi:**
1. Pastikan bot Telegram running
2. Cek token di `.env`
3. Smart Hunter menggunakan **main bot's Telegram app** untuk notifikasi

---

## 📊 Log Files

| File | Isi |
|------|-----|
| `logs/smart_profit_hunter.log` | Semua aktivitas Smart Hunter |
| `logs/crypto_bot.log` | Log bot utama (termasuk start/stop Smart Hunter) |

---

## 🎯 Tips & Trik

### 1. Pair yang Cocok untuk Smart Hunter
- **High Volume**: BTC/IDR, ETH/IDR, SOL/IDR
- **Volatile**: PIPPIN/IDR, STOI/IDR, BDC/IDR
- **Min Volume**: 1B IDR/hari

### 2. Waktu Terbaik
- **Pagi (06:00-09:00)**: Volume tinggi, banyak opportunity
- **Siang (12:00-14:00)**: Volume menurun, selective trade
- **Malam (20:00-23:00)**: Volume tinggi lagi

### 3. Risk Management
- Start dengan `MAX_POSITION_SIZE = 50_000` (50k) dulu
- Naikkan perlahan jika sudah profit konsisten
- Selalu pantau `/smarthunter_status` minimal 2x sehari

---

## 📞 Support

Jika ada masalah atau pertanyaan:
1. Cek log file terlebih dahulu
2. Screenshot error message
3. Contact admin dengan detail masalah

---

**Happy Trading! 🚀📈**
