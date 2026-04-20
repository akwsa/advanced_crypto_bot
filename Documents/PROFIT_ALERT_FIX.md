# Fix: Profit Alert untuk Posisi yang Tidak Ada

## Masalah
Bot mengirimkan notifikasi profit untuk pair yang tidak memiliki posisi aktif di Indodax.
Contoh notifikasi yang salah:
```
💵 SCALPER PROFIT ALERT PROFIT +5%
🟢 Pair: ARCIDR
💰 Entry: 1,267 IDR
📈 Current: 1,344 IDR
```
Padahal tidak ada posisi ARCIDR yang dibuka.

## Penyebab
- Scalper module menyimpan posisi di file `scalper_positions.json`
- Bot mengirim notifikasi profit berdasarkan file ini tanpa verifikasi ke Indodax
- Posisi yang sudah dijual atau tidak ada lagi masih bisa memicu notifikasi

## Solusi

### 1. Fungsi `_verify_position_exists()`
Menambahkan verifikasi posisi sebelum mengirim notifikasi:

**Untuk Real Trading:**
- Cek saldo koin di Indodax melalui API
- Jika saldo koin = 0, posisi tidak valid → skip notifikasi
- Jika saldo koin > 0, posisi valid → lanjutkan notifikasi

**Untuk DRY RUN Mode:**
- Cek usia posisi (jika > 7 hari dan sudah ada profit alert)
- Posisi lama yang sudah ada profit alert kemungkinan stale → skip notifikasi

### 2. Modifikasi `_check_tp_sl_real()`
- **Pass 1:** Verifikasi semua posisi di `active_positions`
- **Pass 2:** Hanya kirim notifikasi untuk posisi yang sudah diverifikasi
- Posisi yang tidak valid dihapus dari `active_positions` dan file JSON

## File yang Diubah
- `scalper_module.py` - Tambahan fungsi `_verify_position_exists()`
- `scalper_module.py` - Modifikasi fungsi `_check_tp_sl_real()`
- `scalper_module.py` - Modifikasi command `/s_pair reset` untuk hapus semua posisi

---

# Fix: Command `/s_pair reset` Hapus Semua Posisi

## Masalah
Command `/s_pair reset` hanya mereset daftar pair ke default, tapi **tidak menghapus posisi aktif** yang tersimpan di `scalper_positions.json`. Ini menyebabkan:
- Posisi lama tetap ada meskipun pair sudah direset
- Notifikasi profit masih muncul untuk pair yang seharusnya sudah dihapus
- Terutama bermasalah di DRY RUN mode

## Solusi

### Modifikasi `/s_pair reset`
Sekarang command ini akan:
1. ✅ Reset daftar pair ke default
2. ✅ **Hapus SEMUA posisi aktif** dari `active_positions`
3. ✅ **Hapus semua alert tracking** (`alerted_positions`, `notified_drops`)
4. ✅ **Reset last alert time**
5. ✅ **Reset saldo ke 10,000,000 IDR** (terutama untuk DRY RUN)
6. ✅ **Simpan perubahan ke file JSON**

### Yang Dihapus
- `self.active_positions.clear()` - Semua posisi trading
- `self.alerted_positions.clear()` - Tracking posisi yang sudah di-alert
- `self.notified_drops.clear()` - Tracking threshold yang sudah di-notify
- `self.last_alert_time = None` - Waktu alert terakhir
- `self.balance = ScalperConfig.INITIAL_BALANCE` - Reset saldo ke 10,000,000 IDR
- `self._save_positions()` - Simpan perubahan ke file

### Response ke User
Bot akan menampilkan:
```
✅ Pair direset ke default (0):

🗑️ Dihapus 5 posisi aktif
• Semua posisi, alert & notifikasi direset

💰 Saldo direset: 12,345,678 → 10,000,000 IDR
```

Atau jika tidak ada posisi:
```
✅ Pair direset ke default (0):

✅ Tidak ada posisi aktif untuk dihapus

💰 Saldo direset: 8,765,432 → 10,000,000 IDR
```

## Cara Kerja
```
Sebelum Fix:
/s_pair reset → Reset pairs list → Posisi & saldo MASIH ADA ❌

Setelah Fix:
/s_pair reset → Reset pairs list + Hapus semua posisi + Clear alerts + Reset saldo ✅
```

## Testing
- ✅ Syntax check: `python -m py_compile scalper_module.py` - PASSED
- ⏳ Runtime test: Menunggu bot dijalankan

## Cara Test Manual
1. Jalankan bot: `python bot.py`
2. Buka posisi dummy di DRY RUN: `/s_buy arcidr`
3. Verifikasi posisi ada & saldo berubah: `/s_posisi`
4. Reset pair: `/s_pair reset`
5. Verifikasi hasil reset:
   - Posisi hilang: `/s_posisi` → Harusnya kosong
   - Saldo reset: Harusnya kembali ke 10,000,000 IDR
6. Cek file `scalper_positions.json`:
   - `"positions": {}` → Kosong
   - `"balance": 10000000` → Saldo awal

## Expected Behavior
✅ **Setelah `/s_pair reset`:**
- Semua posisi aktif dihapus
- Semua alert tracking direset
- **Saldo dikembalikan ke 10,000,000 IDR** (INITIAL_BALANCE)
- File JSON dibersihkan
- Tidak ada notifikasi profit untuk pair yang sudah direset

## Cara Kerja
```
1. Bot mengambil snapshot semua posisi dari active_positions
2. Untuk setiap posisi:
   - Real Trading: Cek saldo koin di Indodax
   - DRY RUN: Cek apakah posisi terlalu tua (>7 hari)
3. Jika posisi TIDAK valid:
   - Hapus dari active_positions
   - Simpan perubahan ke file JSON
   - Skip notifikasi
4. Jika posisi VALID:
   - Lanjutkan cek profit/drop alerts
   - Kirim notifikasi jika perlu
```

## Testing
- ✅ Syntax check: `python -m py_compile scalper_module.py` - PASSED
- ⏳ Runtime test: Menunggu bot dijalankan

## Cara Test Manual
1. Jalankan bot: `python bot.py`
2. Tunggu notifikasi profit muncul
3. Cek apakah notifikasi hanya untuk pair yang benar-benar ada posisinya
4. Cek log untuk pesan verifikasi:
   - `✅ Position verified: ARCIDR - Balance: 123.456`
   - `❌ Position verification failed: ARCIDR - No ARC balance (0 coins)`
   - `🗑️ Removing stale position: ARCIDR (not found in Indodax)`

## Expected Behavior
✅ Notifikasi profit HANYA dikirim jika:
- Posisi benar-benar ada di Indodax (Real Trading)
- Posisi belum terlalu tua dan masih valid (DRY RUN)

❌ Notifikasi profit TIDAK dikirim jika:
- Saldo koin = 0 di Indodax
- Posisi sudah dijual
- Posisi terlalu tua dan sudah ada profit alert sebelumnya
