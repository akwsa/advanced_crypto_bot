# 📋 Panduan Lengkap Command Bot

## 🚀 Command Utama - `/cmd`

Gunakan `/cmd` sebagai **pintu utama** untuk mengakses semua panduan:

```bash
/cmd            - Lihat ringkasan
/cmd bot        - Command Bot Utama
/cmd scalp      - Command Scalper Module
/cmd pair       - Manajemen Pair
/cmd trade      - Command Trading
/cmd status     - Status & Monitoring
```

---

## 🤖 BOT UTAMA

### 👀 Watchlist & Monitoring

|Command|Fungsi|
|---|---|
|`/watch <pair>`|Tambah pair ke watchlist|
|`/unwatch <pair>`|Hapus dari watchlist|
|`/list`|Lihat semua pair di watchlist|
|`/price <pair>`|Cek harga cepat|
|`/monitor <pair>`|Set price monitoring|

**Contoh:**

```bash
/watch btcidr
/watch ethidr
/list
/price btcidr
```

### 📊 Analisa & Sinyal

|Command|Fungsi|
|---|---|
|`/signal <pair>`|Analisa teknikal 1 pair|
|`/signals`|Analisa semua pair di watchlist|
|`/signal_quality <pair> [type]`|**Analisis kualitas signal historis**|
|`/signal_report [BUY/SELL] [n]`|**Ranking pair paling profitable**|
|`/scan`|Scan market untuk peluang|
|`/position <pair>`|Analisa posisi mendalam|
|`/topvolume`|**Top 50 pair by Volume 24h (descending)**|

**Command Baru — Signal Quality Analysis:**

```bash
/signal_quality btcidr BUY    # Cek kualitas BUY signal BTCIDR
/signal_quality zenidr SELL   # Cek kualitas SELL signal ZENIDR
/signal_report BUY 10         # Top 10 pair BUY paling profit
/signal_report SELL 5         # Top 5 pair SELL paling profit
```

**Contoh Output `/signal_quality`:**
```
🔍 SIGNAL QUALITY REPORT
📊 Pair: BTCIDR | Signal: BUY
🏆 Quality Grade: A (✅ EXCELLENT) | Score: 8/10
• Win Rate: 89.3% | Avg Profit: +4.1%
• Optimal Hold Time: 5.7 hours
✅ RECOMMENDATION: TAKE THIS SIGNAL
```

**Contoh Output `/signal_report`:**
```
🏆 TOP 10 PAIRS — BUY SIGNALS
1. ✅ ZENIDR — 97,202 IDR
   Win Rate: 85.7% | Score: 10/10
   Signals: 14 | Avg Profit: +7.4%
   💰 Buy: /trade BUY zenidr 97202 100000
```

**Contoh Output `/signal`:**

```text
⏸️ BR/IDR - Trading Signal

💰 Price: 2,448 IDR
🎯 Recommendation: HOLD

📈 Technical Indicators:
• RSI (14): NEUTRAL
• MACD: BULLISH
• MA Trend: BEARISH
• Bollinger: NEUTRAL
• Volume: NORMAL

🤖 ML Prediction:
• Confidence: 56.0%
• Combined Strength: -0.15

💡 Analysis: ML confidence too low
```

### 💼 Portfolio & Trading

|Command|Fungsi|
|---|---|
|`/balance`|Cek saldo & posisi|
|`/trades`|Riwayat trade|
|`/performance`|Statistik win rate & P&L|
|`/sync`|Sync trade dari Indodax|

### ⚙️ Auto Trading

|Command|Fungsi|
|---|---|
|`/autotrade`|Toggle auto-trade|
|`/autotrade dryrun`|Mode simulasi (AMAN!)|
|`/autotrade real`|Trading sungguhan|
|`/autotrade off`|Matikan auto-trade|
|`/autotrade_status`|Cek status auto-trade|
|`/set_interval <menit>`|**Ubah interval cek sinyal** (1-30 menit)|

### 🔧 Admin & ML

|Command|Fungsi|
|---|---|
|`/status`|Status bot|
|`/retrain`|Retrain model ML|
|`/hunter_status`|Status profit hunter|
|`/ultrahunter`|Ultra hunter commands|

### 🛠️ Manual Trading

|Command|Fungsi|
|---|---|
|`/trade BUY <pair> <price> <idr>`|Buy manual → **posisi masuk `/s_posisi`**|
|`/trade SELL <pair> <price> <coin>`|Sell manual → **posisi keluar dari `/s_posisi`**|
|`/cancel <order_id>`|Cancel order|
|`/set_sl <pair> <price>`|Set stop loss|
|`/set_tp <pair> <price>`|Set take profit|

**PENTING:** `/trade BUY/SELL` sekarang **terintegrasi dengan scalper module**.
Posisi dari `/trade` otomatis muncul di `/s_posisi` dengan button SELL.
Format pair otomatis convert: `zenidr` → `zen_idr` (Indodax format)

---

## ⚡ SCALPER MODULE

### 📊 Pair Management

|Command|Fungsi|
|---|---|
|`/s_pair list`|Lihat pair aktif|
|`/s_pair add <pair>`|Tambah pair baru|
|`/s_pair remove <pair>`|Hapus pair|
|`/s_pair reset`|Reset ke default|

**Default Pairs:** `pippinidr`, `bridr`, `stoidr`, `drxidr`

### 🔍 Analisa

|Command|Fungsi|
|---|---|
|`/s_analisa <pair>`|Analisa teknikal lengkap|

**Contoh:**

```bash
/s_analisa bridr
```

**Output:**

```text
⏸️ BR/IDR - Trading Signal

💰 Price: 2,448 IDR
🎯 Recommendation: HOLD

📈 Technical Indicators:
• RSI (14): NEUTRAL (52.3)
• MACD: BULLISH
• MA Trend: BEARISH
• Bollinger: NEUTRAL
• Volume: NORMAL

🤖 ML Prediction:
• Confidence: 56.0%
• Combined Strength: -0.15

💡 Analysis: ML confidence too low

⏰ 14:32:15
```

### 💰 Trading Manual

|Command|Fungsi|
|---|---|
|`/s_buy <pair>`|Buy manual|
|`/s_sell <pair>`|Sell manual|
|`/s_sltp <pair> <tp> <sl>`|Set TP/SL|
|`/s_cancel <pair>`|Cancel TP/SL|
|`/s_info <pair>`|Info posisi|

### 📋 Monitoring

|Command|Fungsi|
|---|---|
|`/s_menu`|Menu utama scalper|
|`/s_posisi`|Lihat posisi aktif (dengan tombol SELL)|
|`/s_portfolio`|**Lihat SEMUA pair (posisi + monitor)**|
|`/s_riwayat`|**Lihat RIWAYAT semua pair yang pernah di-trade**|
|`/s_reset`|Reset semua posisi|
|`/s_sync`|**Sync posisi dari Indodax**|

**Perbedaan `/s_posisi` vs `/s_portfolio` vs `/s_riwayat`:**

- `/s_posisi` → Hanya tampilkan pair yang ADA POSISI aktif
- `/s_portfolio` → Tampilkan SEMUA pair (yang ada posisi + yang hanya di-monitor)
- `/s_riwayat` → **Lihat SEMUA pair yang PERNAH di-trade** (dari Indodax history)

**PENTING untuk Live Trading:**

- `/s_sync` → Sync posisi ACTUAL dari akun Indodax
- Auto-sync saat bot startup (real trading mode)
- Safety check di `/s_reset` untuk hindari loss data

---

## 📖 CONTOH WORKFLOW

### 1️⃣ Setup Awal

```bash
# Bot Utama
/watch btcidr
/watch bridr
/list

# Scalper
/s_pair list
/s_pair add btcidr
```

### 2️⃣ Analisa Sebelum Entry

```bash
# Bot Utama
/signal btcidr

# Scalper
/s_analisa btcidr
```

### 3️⃣ Trading (Simulasi Dulu!)

```bash
# Aktifkan mode simulasi
/autotrade dryrun

# Atau manual via scalper
/s_buy bridr
/s_sltp bridr 2600 2300
```

### 4️⃣ Monitoring

```bash
# Bot Utama
/status
/balance
/signals

# Scalper
/s_posisi
/s_menu
```

---

## 🎯 RISK MANAGEMENT

### Parameter Default

|Setting|Nilai|
|---|---|
|Max position size|25% balance|
|Stop loss|2%|
|Take profit|5%|
|**Trailing stop**|**1.5% (aktif setelah +2% profit)**|
|Max trades/hari|10|
|Daily loss limit|5%|
|Min risk-reward|2:1|

### Fitur Auto-Trading Baru

#### Core Trading Engine

- ✔️ Multi pair scanning
- ✔️ Auto entry dengan market intelligence filter
- ✔️ Auto exit (SL/TP/Trailing Stop)
- ✔️ **Auto SELL** saat sinyal SELL/STRONG_SELL (baru!)
- ✔️ **Trailing stop dinamis**

#### Risk Management

- ✔️ Position size otomatis (25% balance)
- ✔️ **Position size adaptif** berdasarkan regime (baru!)
- ✔️ Risk % balance
- ✔️ Stop loss dinamis dengan S/R adjustment

#### Market Intelligence

- ✔️ **Support/resistance detection**
- ✔️ **Volume spike detection**
- ✔️ **Orderbook pressure analysis**
- ✔️ **Entry filter** (volume + orderbook harus PASS) (baru!)

#### Market Regime Detection (baru!)

- ✔️ **TREND** - Market sedang trending (naik/turun)
- ✔️ **RANGE** - Market sideways/choppy
- ✔️ **HIGH_VOLATILITY** - Market tidak stabil
- ✔️ Auto-adjust position size berdasarkan regime

#### 🧠 Advanced Features (baru!)

- ✔️ **Portfolio allocation dinamis** - Alokasi modal berdasarkan skor risk-adjusted
- ✔️ **Reinforcement Learning** - Q-learning agent adaptif (belajar dari hasil trade)
- ✔️ **Spoofing detection** - Filter fake wall di orderbook
- ✔️ **Smart order routing** - Split order jadi 3 chunks + adaptive pricing
- ✔️ **Heatmap liquidity** - Tracking zona likuiditas time-series
- ✔️ **Elite signal** - Konfirmasi sinyal via MA probability + orderbook imbalance + zone bounce
- ✔️ **Fee-aware execution** - Kalkulasi entry/exit termasuk fee 0.3% (real profit)

### ⚙️ Command Interval (baru!)

**`/set_interval <menit>`** - Ubah kecepatan auto-trade scan tanpa restart bot

```bash
/set_interval 1      → Fast (scalping, cek setiap 1 menit)
/set_interval 2      → Medium-fast
/set_interval 3      → Balanced (recommended)
/set_interval 5      → Conservative (default)
```

**Kenapa bukan 10 detik?**
- Cek terlalu cepat = signal noise tinggi, ML confidence rendah
- 5 menit = balance antara responsif dan akurasi
- Bisa diubah kapan saja via `/set_interval` tanpa upload ulang ke VPS

---

## 💡 TIPS & TRIK

### ⚡ Shortcut

- Gunakan `/cmd` sebagai referensi cepat
- `/cmd scalp` untuk scalper commands
- `/cmd trade` untuk trading commands

### 🔍 Tips Analisa

- Selalu gunakan `/signal` atau `/s_analisa` sebelum entry
- Perhatikan confidence level (>60% = cukup kuat)
- Cek RSI: <30 = oversold (potensial buy), >70 = overbought

### 💰 Trading Aman

1. Mulai dengan `/autotrade dryrun` (simulasi)
2. Pelajari pola dari hasil simulasi
3. Baru switch ke `/autotrade real` setelah yakin

### 📊 Monitoring

- `/s_posisi` untuk cek profit/loss scalper
- `/balance` untuk cek saldo
- `/performance` untuk statistik keseluruhan

---

## 🆘 TROUBLESHOOTING

### Problem: "Pair not found"

**Solusi:** Pastikan pair ditambahkan dulu

```bash
/watch btcidr          # Bot utama
/s_pair add btcidr     # Scalper
```

### Problem: "Not enough data"

**Solusi:** Tunggu sampai bot mengumpulkan cukup data (minimal 60 candle)

### Problem: "Auto-trade not working"

**Solusi:** Cek status

```bash
/autotrade_status
```

Pastikan mode sudah diatur (dryrun atau real)

---

## 📞 Quick Reference Card

**Simpan ini untuk akses cepat:**

```text
┌─────────────────────────────────────┐
│  📋 QUICK COMMAND REFERENCE         │
├─────────────────────────────────────┤
│  /cmd              - Panduan lengkap│
│  /cmd bot          - Bot commands   │
│  /cmd scalp        - Scalper cmds   │
│  /cmd trade        - Trading cmds   │
│                                     │
│  /watch <pair>     - Add pair       │
│  /signal <pair>    - Analisa        │
│  /s_analisa <pair> - Scalper anal.  │
│  /s_posisi         - Cek posisi     │
│  /balance          - Cek saldo      │
│  /autotrade dryrun - Mode simulasi  │
└─────────────────────────────────────┘
```
