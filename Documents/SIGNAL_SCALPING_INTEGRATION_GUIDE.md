# 📊 Signal Analysis & Scalping Integration Guide

## 🎯 Overview

Modul ini menghubungkan **Signal Quality Analysis** dengan **Scalper Module** agar setiap keputusan buy/sell didukung data historis yang akurat.

**Prinsip Utama:**
- Semua berjalan di **DRY RUN** dulu (simulasi, tidak pakai uang real)
- Saat switch ke **REAL TRADE**, semua perintah tetap sama — hanya eksekusi yang beda
- Tidak ada perubahan code yang dibutuhkan saat switch mode

---

## 📋 Daftar Command Baru

### 1. `/signal_quality <pair> [type]`
**Fungsi:** Analisis kualitas signal historis untuk 1 pair
**Dipakai oleh:** Scalper sebelum entry posisi
**Mode:** DRY RUN & REAL TRADE (sama)

**Contoh:**
```
/signal_quality btcidr BUY
/signal_quality zenidr SELL
/signal_quality drxidr
```

**Output:**
```
🔍 SIGNAL QUALITY REPORT
========================================
📊 Pair: BTCIDR
📈 Signal Type: BUY
🏆 Quality Grade: A (✅ EXCELLENT)
⭐ Score: 8/10

📊 Performance (Last 30 Days):
• Total Signals: 28
• Analyzed: 28
• ✅ Winning: 25
• ❌ Losing: 0
• ➖ Neutral: 3

💰 Profitability:
• Win Rate: 89.3%
• Avg Profit (when right): +4.1%
• Avg Loss (when wrong): -2.5%

⏱️ Optimal Hold Time: 5.7 hours

✅ RECOMMENDATION: TAKE THIS SIGNAL
Historical accuracy sangat bagus!
========================================
```

**Cara Baca:**
- Grade A/B = aman untuk entry
- Grade C = hati-hati, pertimbangkan skip
- Grade D = hindari, false positive rate tinggi
- Optimal Hold Time = berapa jam idealnya hold sebelum sell

---

### 2. `/signal_report [BUY|SELL] [limit]`
**Fungsi:** Ranking pair dengan signal paling profitable
**Dipakai oleh:** Scalper untuk pilih pair terbaik saat mau entry
**Mode:** DRY RUN & REAL TRADE (sama)

**Contoh:**
```
/signal_report BUY 10
/signal_report SELL 5
```

**Output:**
```
🏆 TOP 10 PAIRS — BUY SIGNALS
========================================
1. ✅ ZENIDR — 97,202 IDR
   Win Rate: 85.7% | Score: 10/10
   Signals: 14 | Avg Profit: +7.4%
   💰 Buy: /trade BUY zenidr 97202 100000

2. ✅ DRXIDR — 186 IDR
   Win Rate: 89.3% | Score: 10/10
   Signals: 28 | Avg Profit: +4.1%
   💰 Buy: /trade BUY drxidr 186 100000
========================================
```

**Fitur:**
- Urut by **Avg Profit tertinggi** (bukan win rate)
- Tampilkan **harga real-time** tiap pair
- Ada **quick buy command** — tinggal copy-paste

---

### 3. `/trade BUY/SELL <pair> <price> <amount>`
**Fungsi:** Entry posisi manual (sekarang **terintegrasi dengan scalper**)
**Dipakai oleh:** User untuk buy/sell langsung dari signal report
**Mode:** DRY RUN = simulasi | REAL TRADE = eksekusi real di Indodax

**Contoh:**
```
/trade BUY zenidr 97000 1000000
/trade SELL zenidr 99000 10.28
```

**Yang Berubah (FIX):**
- Sebelumnya: `/trade` dan `/s_buy` sistem terpisah
- Sekarang: `/trade BUY` → **delegate ke scalper** → posisi muncul di `/s_posisi`
- Format pair otomatis convert: `zenidr` → `zen_idr` (Indodax format)

**Confirmation:**
```
⚠️ CONFIRM TRADE?
• Pair: ZENIDR → zen_idr (Indodax format)
• Reply YES to confirm, NO to cancel
```

**DRY RUN Output:**
```
✅ DRY RUN ORDER EXECUTED!
• Pair: ZENIDR → zen_idr
• Type: BUY
• Price: 97,000 IDR
• Amount: 10.30927835 ZEN
• Total: 1,000,000 IDR
• Fee (0.3%): 3,000 IDR
• Trade ID: 286
⚠️ Note: Ini DRY RUN — tidak ada real trade di Indodax!
💡 Posisi sekarang muncul di /s_posisi
```

---

### 4. `/s_posisi`
**Fungsi:** Lihat semua posisi aktif (dari scalper + manual trade)
**Dipakai oleh:** Scalper untuk monitor P/L dan quick sell
**Mode:** DRY RUN & REAL TRADE (sama)

**Output:**
```
📦 POSISI AKTIF
💰 Saldo: 9,000,000
📈 P/L: -1,000,000
📊 Open: 1

🟢 ZENIDR 97,000 → 99,500 | +1.89% (+18,500)
[🟢 ZENIDR (INFO)] [💰 SELL ZENIDR (PROFIT)]
```

**Button:**
- `INFO` → detail posisi lengkap
- `SELL` → jual cepat (hijau kalau profit, merah kalau loss)
- `Refresh` → update harga + rebuild keyboard
- `Menu` → kembali ke `/s_menu`

**FIX:** Setelah refresh, button SELL tetap muncul (sebelumnya hilang)

---

### 5. `/s_buy <pair> <price> <idr>`
**Fungsi:** Buy via scalper module (sama dengan `/trade BUY`)
**Dipakai oleh:** Scalper yang prefer command `/s_` prefix

**Contoh:**
```
/s_buy zenidr 97000 1000000
/s_buy zenidr 97000 1000000 100000 90000  # dengan TP/SL
```

---

### 6. `/s_menu`
**Fungsi:** Menu utama scalper — lihat semua pair + harga + posisi
**Dipakai oleh:** Scalper untuk overview market

**FIX:** Sekarang tampilkan button BUY/SELL untuk semua pair (termasuk yang dari `/trade`)

---

## 🔄 Alur Kerja Lengkap

```
1. User cek market:
   /signal_report BUY 10
   → Muncul top 10 pair paling profitable

2. User cek kualitas signal:
   /signal_quality zenidr BUY
   → Grade A, Win Rate 85%, Avg Profit +7.4%

3. User entry posisi:
   /trade BUY zenidr 97000 1000000
   → YES
   → Posisi masuk ke scalper

4. User monitor posisi:
   /s_posisi
   → Muncul ZENIDR dengan button SELL

5. User jual saat profit:
   Klik button 💰 SELL ZENIDR (PROFIT)
   → Konfirmasi → Sell executed

6. Posisi hilang dari /s_posisi
```

---

## ⚙️ Konfigurasi Mode

### File: `.env`

```bash
# DRY RUN MODE (default — aman untuk testing)
AUTO_TRADE_DRY_RUN=true
MANUAL_TRADING_ENABLED=true

# REAL TRADE MODE (hati-hati — uang real!)
AUTO_TRADE_DRY_RUN=false
MANUAL_TRADING_ENABLED=true
INDODAX_API_KEY=your_key
INDODAX_SECRET_KEY=your_secret
```

### Yang Berubah Saat Switch Mode:

| Fitur | DRY RUN | REAL TRADE |
|-------|---------|------------|
| `/trade BUY` | Simulasi, simpan ke DB | Eksekusi real di Indodax |
| `/s_buy` | Simulasi, kurangi balance virtual | Order real di Indodax |
| `/s_posisi` | Tampilkan posisi virtual | Tampilkan posisi real |
| `/signal_report` | Query DB (sama) | Query DB (sama) |
| `/signal_quality` | Query DB (sama) | Query DB (sama) |

**Penting:** Signal analysis (`/signal_report`, `/signal_quality`) **tidak terpengaruh mode** — selalu query database, tidak peduli DRY RUN atau REAL.

---

## 📁 File yang Terkait

| File | Fungsi |
|------|--------|
| `signal_analyzer.py` | Core analysis engine |
| `bot.py` | Main bot — command handlers |
| `scalper_module.py` | Scalper module — position tracking |
| `indodax_api.py` | API wrapper untuk Indodax |
| `data/signals.db` | Database signal historis |
| `data/trading.db` | Database trades + price history |
| `scalper_positions.json` | Posisi aktif scalper (persistent) |

---

## 🛡️ Risk Settings

Default risk settings (bisa diubah di `config.py`):

```python
STOP_LOSS_PCT = 2.0       # Cut loss 2%
TAKE_PROFIT_PCT = 5.0     # Take profit 5%
TRADING_FEE_RATE = 0.003  # Indodax fee 0.3%
MIN_TRADE_AMOUNT = 100000 # Minimum trade 100k IDR
```

---

## 💡 Tips & Best Practices

### Sebelum Entry (DRY RUN):
1. Cek `/signal_report BUY 10` → pilih pair dengan profit tertinggi
2. Cek `/signal_quality <pair> BUY` → pastikan Grade A atau B
3. Entry dengan `/trade BUY <pair> <price> <amount>`
4. Monitor dengan `/s_posisi`

### Sebelum Entry (REAL TRADE):
1. Sama seperti DRY RUN — pastikan dulu strategi profit di simulasi
2. Double check saldo Indodax sebelum entry
3. Mulai dengan amount kecil dulu
4. Selalu set TP/SL untuk proteksi

### Setelah Entry:
1. `/s_posisi` → cek P/L real-time
2. Klik `SELL` button → jual cepat
3. Kalau profit → 💰 hijau, kalau loss → 📉 merah

---

## 🐛 Troubleshooting

### Masalah: `/s_posisi` tidak muncul posisi setelah `/trade BUY`
**Solusi:** Restart bot — fix sudah diterapkan, posisi sekarang tersinkron

### Masalah: Button SELL hilang setelah refresh
**Solusi:** Restart bot — keyboard sekarang build dari `active_positions + pairs`

### Masalah: Error `Invalid pair` saat trade
**Solusi:** Sudah fixed — auto-convert `zenidr` → `zen_idr`

### Masalah: Error `Insufficient balance` di DRY RUN
**Solusi:** Sudah fixed — DRY RUN tidak cek saldo real, langsung simulasi

### Masalah: Error `Event loop conflict`
**Solusi:** Sudah fixed — trade execution jalan di background thread
