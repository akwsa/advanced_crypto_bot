# 📊 Signal Commands Documentation

Dokumentasi lengkap command sinyal yang tersedia di Advanced Crypto Trading Bot.

---

## 📋 Daftar Command Sinyal

| Command | Deskripsi |
|---------|-----------|
| `/signal <PAIR>` | Signal lengkap (semua tipe: BUY, SELL, HOLD, STRONG_BUY, STRONG_SELL) |
| `/signal_buy <PAIR>` | Hanya menampilkan BUY atau STRONG_BUY |
| `/signal_sell <PAIR>` | Hanya menampilkan SELL atau STRONG_SELL |
| `/signal_hold <PAIR>` | Hanya menampilkan HOLD |
| `/signal_buysell <PAIR>` | Hanya BUY atau SELL (tidak tampil HOLD) |

---

## 📝 Penggunaan

### 1. `/signal <PAIR>`
Mendapatkan analisis trading lengkap yang mencakup:
- Harga saat ini dan perubahan 24 jam
- Indikator teknis (RSI, MACD, MA, Bollinger)
- Prediksi ML dengan confidence score
- Rekomendasi kombinasi (BUY/SELL/HOLD)
- Level Support & Resistance

**Contoh:**
```
/signal BTCIDR
/signal ETHIDR
```

---

### 2. `/signal_buy <PAIR>`
Menampilkan signal BUY atau STRONG_BUY saja. Jika signal saat ini bukan BUY/STRONG_BUY, akan muncul pesan bahwa tidak ada signal BUY.

**Contoh:**
```
/signal_buy BTCIDR
```

**Output:**
- ✅ Jika BUY: Menampilkan signal lengkap dengan label "🟢 BUY SIGNAL"
- ❌ Jika SELL/HOLD: Menampilkan pesan "Tidak ada BUY signal untuk..."

---

### 3. `/signal_sell <PAIR>`
Menampilkan signal SELL atau STRONG_SELL saja. Jika signal saat ini bukan SELL/STRONG_SELL, akan muncul pesan bahwa tidak ada signal SELL.

**Contoh:**
```
/signal_sell BTCIDR
```

**Output:**
- ✅ Jika SELL: Menampilkan signal lengkap dengan label "🔴 SELL SIGNAL"
- ❌ Jika BUY/HOLD: Menampilkan pesan "Tidak ada SELL signal untuk..."

---

### 4. `/signal_hold <PAIR>`
Menampilkan signal HOLD saja. Jika signal saat ini bukan HOLD, akan muncul pesan bahwa tidak ada signal HOLD.

**Contoh:**
```
/signal_hold BTCIDR
```

**Output:**
- ✅ Jika HOLD: Menampilkan signal lengkap dengan label "⏸️ HOLD SIGNAL"
- ❌ Jika BUY/SELL: Menampilkan pesan "Tidak ada HOLD signal untuk..."

---

### 5. `/signal_buysell <PAIR>`
Menampilkan signal BUY atau SELL (tidak termasuk HOLD). Jika signal saat ini HOLD, akan muncul pesan bahwa tidak ada BUY/SELL.

**Contoh:**
```
/signal_buysell BTCIDR
```

**Output:**
- ✅ Jika BUY/STRONG_BUY: Menampilkan signal dengan label "🟢 BUY SIGNAL"
- ✅ Jika SELL/STRONG_SELL: Menampilkan signal dengan label "🔴 SELL SIGNAL"
- ❌ Jika HOLD: Menampilkan pesan "Signal untuk ... adalah HOLD" dengan saran menggunakan `/signal_hold`

---

## 🎯 Tips Penggunaan

1. **Gunakan `/signal_buy`** untuk cari peluang BUY
2. **Gunakan `/signal_sell`** untuk cari peluang SELL
3. **Gunakan `/signal_hold`** untuk verifikasi posisi HOLD
4. **Gunakan `/signal_buysell`** untuk dapat signal aktif (tidak HOLD)

## 🔧 Command ML

- `/retrain` - Melatih ulang model ML (admin only)
  - Setelah selesai, akan muncul notifikasi "🔔 **RETRAIN SELESAI**"

---

## 📅 Last Updated

April 2026