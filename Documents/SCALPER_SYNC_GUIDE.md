# 🔄 Scalper Sync dengan Indodax - PANDUAN LIVE TRADING

## ⚠️ **MASALAH YANG DIPERBAIKI**

Sebelum update ini, `/s_reset` memiliki **BAHAYA** untuk live trading:

### **Sebelum Fix:**
```
/s_reset → Hapus semua posisi lokal
         → Balance reset ke 10.000.000
         → ❌ TAPI coin di Indodax MASIH ADA!
         → Bot "lupa" posisi yang harus dimonitor
```

### **Setelah Fix:**
```
/s_reset → ⚠️ CEK dulu posisi di Indodax
         → ❌ Jika ada open order, warning & block
         → ✅ Rekomendasi: /s_sync dulu
         → Hanya reset dengan konfirmasi: /s_reset confirm
```

---

## ✅ **FITUR BARU**

### **1️⃣ Command `/s_sync` - Sync Posisi dari Indodax**

**Fungsi:** Mengambil semua posisi ACTUAL dari akun Indodax Anda

**Cara Pakai:**
```bash
/s_sync
```

**Output:**
```
✅ SYNC SELESAI!

📊 Ditemukan 3 posisi di Indodax:

✅ BR/IDR - Added from Indodax
Entry: ~2,448

🔄 PIPPIN/IDR - Updated order ID

✅ STO/IDR - Added from Indodax
Entry: ~1,250

💰 Balance Indodax: 12,345,678 IDR

💡 Tips:
• Gunakan /s_posisi untuk lihat detail
• Gunakan /s_sltp untuk set TP/SL
• Pair monitoring aktif: 5
```

**Kapan Pakai `/s_sync`:**
- ✅ Setelah restart bot di VPS
- ✅ Sebelum `/s_reset` (untuk backup posisi)
- ✅ Jika bot "lupa" posisi
- ✅ Setelah trading manual di website Indodax
- ✅ Saat pertama kali switch ke live trading

---

### **2️⃣ Auto-Sync Saat Startup**

Bot akan **otomatis sync** dengan Indodax saat dinyalakan:

**Log:**
```
🔄 Auto-syncing positions with Indodax at startup...
✅ Auto-synced BR/IDR: 100.00 @ 2,448
✅ Auto-synced PIPPIN/IDR: 50.00 @ 5,120
✅ Auto-synced 2 positions from Indodax
```

**Telegram Notification:**
```
🔄 AUTO-SYNC SELESAI

Ditemukan 2 posisi dari Indodax:
• BR/IDR: 100.00 @ 2,448
• PIPPIN/IDR: 50.00 @ 5,120

💡 Gunakan /s_posisi untuk detail
```

**Catatan:**
- Hanya di **real trading mode** (`AUTO_TRADE_DRY_RUN=false`)
- Tidak jalan di dry run/simulasi
- Background thread, tidak blocking startup

---

### **3️⃣ Safety Check di `/s_reset`**

**Sekarang `/s_reset` lebih aman:**

**Step 1 - Cek Open Orders di Indodax:**
```
/s_reset

⚠️ PERINGATAN: ADA POSISI DI INDODAX!

Ditemukan 3 open order di akun Indodax Anda.

Jika Anda reset:
• ✅ Bot akan lupa semua posisi lokal
• ❌ Order di Indodax TETAP ADA
• ⚠️ Bot tidak akan monitor TP/SL lagi

Rekomendasi:
• Gunakan /s_sync dulu untuk sync posisi
• Atau cancel manual order di Indodax

Ketik /s_reset confirm untuk lanjutkan reset.
```

**Step 2 - Konfirmasi (jika ada posisi lokal):**
```
/s_reset

⚠️ KONFIRMASI RESET

Ada 5 posisi aktif yang akan dihapus:
BR/IDR | PIPPIN/IDR | STO/IDR | DRX/IDR | SOL/IDR

Reset akan:
• 🗑️ Hapus semua posisi
• 💰 Reset balance ke 10,000,000
• 📊 Clear alert history

Ketik /s_reset confirm untuk lanjutkan.
```

**Step 3 - Execute:**
```
/s_reset confirm

⚠️ RESET SELESAI

🗑️ 5 posisi dihapus
💰 Saldo: 10,000,000

⚠️ PERHATIAN: 3 order masih ada di Indodax!
Gunakan /s_sync untuk sync ulang.
```

---

## 🚀 **WORKFLOW LIVE TRADING DI VPS**

### **Scenario 1: Deploy Baru ke VPS**

```bash
# 1. Setup bot di VPS
ssh user@vps
cd /path/to/bot
pip install -r requirements.txt

# 2. Upload .env (dengan API keys)
# 3. Upload model (jika ada)
scp models/trading_model.pkl user@vps:/path/bot/models/

# 4. Jalankan bot
python bot.py
```

**Di Telegram:**
```bash
# 5. Bot auto-sync saat startup
# (Akan notifikasi jika ada posisi di Indodax)

# 6. Cek posisi
/s_posisi

# 7. Mulai trading
/s_menu
```

---

### **Scenario 2: Restart Bot (Ada Posisi Aktif)**

```bash
# Di VPS
# Ctrl+C untuk stop bot

# Jalankan ulang
python bot.py
```

**Di Telegram:**
```bash
# 1. Bot auto-sync otomatis
# Tunggu notifikasi:
# "🔄 AUTO-SYNC SELESAI - Ditemukan X posisi"

# 2. Jika tidak ada notifikasi, sync manual
/s_sync

# 3. Cek posisi
/s_posisi

# 4. Lanjutkan monitoring
```

---

### **Scenario 3: Reset Total (Mulai Ulang)**

```bash
# 1. Sync dulu (backup posisi)
/s_sync

# 2. Cek posisi aktif
/s_posisi

# 3. Close semua posisi di Indodax (jika mau clean)
# Via website Indodax atau:
/s_sell bridr
/s_sell pippinidr

# 4. Reset bot
/s_reset confirm

# 5. Bot sudah clean, siap trading baru
/s_menu
```

---

## 📊 **PERBEDAAN DATA STORAGE**

### **Data Lokal (Bot):**
```
scalper_positions.json  → Posisi yang bot ingat
scalper_pairs.txt       → List pair yang dimonitor
```

### **Data di Indodax (Actual):**
```
Open Orders             → Order yang belum filled/trade
Trade History           → Riwayat semua trade
Balance                 → Saldo ACTUAL di akun
```

### **Kapan Data Hilang:**

| Aksi | Local Positions | Indodax Positions | Pairs List |
|------|----------------|-------------------|------------|
| `/s_reset` | ❌ HILANG | ✅ TETAP ADA | ✅ AMAN |
| Restart Bot | ✅ AMAN* | ✅ TETAP ADA | ✅ AMAN |
| `/s_sync` | ✅ MERGE | ✅ TETAP ADA | ✅ AMAN |
| Delete `scalper_positions.json` | ❌ HILANG | ✅ TETAP ADA | ✅ AMAN |

\* = Akan auto-sync saat startup (real trading mode)

---

## 💡 **TIPS & BEST PRACTICES**

### ✅ **DO:**
1. Selalu `/s_sync` setelah restart bot
2. Gunakan `/s_posisi` untuk cek status sebelum trading
3. Set TP/SL dengan `/s_sltp` untuk manage risk
4. Monitor balance Indodax vs bot balance
5. Backup `scalper_positions.json` secara berkala

### ❌ **DON'T:**
1. Jangan `/s_reset` tanpa cek posisi dulu
2. Jangan hapus `scalper_positions.json` manual
3. Jangan trading manual di Indodax tanpa `/s_sync` setelahnya
4. Jangan jalankan bot tanpa TP/SL

---

## 🆘 **TROUBLESHOOTING**

### **Problem: Bot tidak auto-sync saat startup**

**Solusi:**
```bash
# Cek mode trading
# Di .env: AUTO_TRADE_DRY_RUN=false

# Jika dry run, auto-sync tidak jalan (normal)
# Untuk sync, harus di real mode
```

---

### **Problem: `/s_sync` error "API Key not found"**

**Solusi:**
```bash
# Cek .env
INDODAX_API_KEY=your_key_here
INDODAX_SECRET_KEY=your_secret_here

# Pastikan tidak ada spasi/typo
```

---

### **Problem: Posisi di bot ≠ Posisi di Indodax**

**Solusi:**
```bash
# Sync ulang
/s_sync

# Jika masih beda, reset dan sync lagi
/s_reset confirm
/s_sync
```

---

### **Problem: Balance bot ≠ Balance Indodax**

**Penjelasan:**
- Balance bot = virtual balance (dari `scalper_positions.json`)
- Balance Indodax = actual balance

**Fix:**
```bash
# /s_sync akan update balance dari Indodax
/s_sync

# Setelah sync, balance bot = balance Indodax
```

---

## 📋 **CHECKLIST LIVE TRADING**

Sebelum mulai live trading di VPS:

```
✅ API Key & Secret sudah di .env
✅ AUTO_TRADE_DRY_RUN=false (untuk real trading)
✅ Bot sudah diupload ke VPS
✅ Dependencies terinstall (pip install -r requirements.txt)
✅ Model ML sudah diupload (opsional, bisa auto-train)
✅ Sudah test dengan dry run minimal 1 minggu
✅ Paham cara pakai /s_sync dan /s_reset

LIVE TRADING CHECKLIST:
✅ /s_sync → Cek ada posisi di Indodax
✅ /s_posisi → Monitor posisi aktif
✅ /s_pair list → Cek pair yang dimonitor
✅ TP/SL sudah di-set untuk setiap posisi
✅ Balance Indodax cukup untuk trading
```

---

## 🎯 **KESIMPULAN**

### **Jawaban Pertanyaan Anda:**

> "Apakah `/s_reset` akan menghapus seluruh pair yang pernah saya buat?"

**JAWAB:**
- ✅ **Pair list TETAP AMAN** (di `scalper_pairs.txt`)
- ⚠️ **Posisi aktif HILANG** (di `scalper_positions.json`)
- ✅ **Posisi di Indodax TETAP ADA** (tidak terpengaruh)
- ✅ **Balance di Indodax TETAP AMAN**

> "Atau scalper akan tetap mengingat berapa pair yang saya lakukan scalping di Indodax?"

**JAWAB:**
- **SEBELUM update ini:** ❌ Bot TIDAK INGAT setelah restart
- **SETELAH update ini:** ✅ Bot AUTO-SYNC posisi dari Indodax saat startup

**Jadi AMAN sekarang!** 🎉

---

## 📞 **Quick Commands Reference**

```
/s_sync           → Sync posisi dari Indodax
/s_reset          → Reset (dengan safety check)
/s_reset confirm  → Reset paksa
/s_posisi         → Lihat posisi aktif
/s_pair list      → Lihat pair yang dimonitor
```
