# AUTO TP/SL — Scalper Fitur Baru

> **Status:** ✅ Implemented & Tested (65/65 scalper tests pass)
> **Tanggal:** 2026-05-30
> **Oleh:** BMAD Session
> **Branch:** fix/scalper-sltp-telegram-ui

---

## 1. Ringkasan

AUTO TP/SL menggantikan mode manual TP/SL sebelumnya. Sekarang setiap posisi
yang dibuka secara otomatis mendapatkan **Take Profit (TP)** dan **Stop Loss (SL)**
berdasarkan konfigurasi yang dapat diatur.

**Fitur utama:**
- ✅ Auto-apply TP/SL setiap kali buy
- ✅ Risk/Reward ratio enforcement minimum 1.5:1
- ✅ Optional trailing stop (SL naik mengikuti harga)
- ✅ Manual override — user bisa kembali ke mode manual kapan saja
- ✅ Status display di posisi — 🤖 AUTO / ✋ MANUAL
- ✅ Akses via command `/s_auto_sltp` dan tombol 🤖 di menu

---

## 2. Perubahan dari Mode Lama

| Aspek | Lama (Manual) | Baru (AUTO) |
|-------|--------------|-------------|
| TP/SL saat buy | User harus set manual via `/s_sltp` atau tombol | Otomatis dihitung dan diterapkan saat buy |
| R/R Ratio | User harus hitung sendiri | Minimum R/R ratio di-enforce otomatis |
| Trailing Stop | Tidak ada | Optional trailing stop update SL |
| Status display | Tidak ada indikator | Tampilkan 🤖 AUTO / ✋ MANUAL / — |
| Override | N/A | Manual TP/SL override auto mode |
| Menu akses | Tidak ada | Tombol 🤖 AUTO TP/SL di menu utama |

---

## 3. Akses Menu

### Via Telegram Button

Menu utama scalper (`/s_menu`) sekarang memiliki tombol:

```
⚡ SCALPER MENU

• 📊 Trading Pairs    • 📦 Posisi Aktif
• 💼 Portfolio         • 📜 Riwayat
• 📈 Analisa Pair     • ⚙️ Manajemen Pair
• 🔄 Sync Indodax     • 🤖 AUTO TP/SL     ← TOMBOL BARU
• 🚪 Tutup Semua
```

Klik tombol **🤖 AUTO TP/SL** → menampilkan konfigurasi AUTO TP/SL saat ini.

### Via Command

```
/s_auto_sltp
```

---

## 4. Konfigurasi (ScalperConfig)

```python
class ScalperConfig:
    # ── AUTO TP/SL Configuration ────────────────────────
    AUTO_TP_SL_ENABLED = True          # Master toggle
    AUTO_TP_PCT = 0.03                 # Take Profit: +3%
    AUTO_SL_PCT = 0.02                 # Stop Loss: -2%
    AUTO_RISK_REWARD_RATIO = 1.5       # Minimum R/R 1.5:1
    AUTO_TRAILING_STOP_ENABLED = False  # Trailing stop toggle
    AUTO_TRAILING_DISTANCE_PCT = 0.01  # 1% from peak
    AUTO_TRAILING_STEP_PCT = 0.005     # 0.5% min rise to update
```

| Parameter | Default | Deskripsi |
|-----------|---------|-----------|
| `AUTO_TP_SL_ENABLED` | `True` | Master toggle on/off |
| `AUTO_TP_PCT` | `0.03` | Take Profit 3% |
| `AUTO_SL_PCT` | `0.02` | Stop Loss 2% |
| `AUTO_RISK_REWARD_RATIO` | `1.5` | Min R/R ratio 1.5:1 |
| `AUTO_TRAILING_STOP_ENABLED` | `False` | Trailing stop off by default |
| `AUTO_TRAILING_DISTANCE_PCT` | `0.01` | Jarak trailing 1% dari peak |
| `AUTO_TRAILING_STEP_PCT` | `0.005` | Minimal kenaikan 0.5% untuk update |

---

## 5. Commands Lengkap

### `/s_auto_sltp` — Lihat konfigurasi

```
🤖 AUTO TP/SL Configuration

Status: ✅ ON
TP: 3.0%
SL: 2.0%
Min R/R: 1.5
Trailing Stop: ❌ OFF
Trailing Distance: 1.0%

Commands:
/s_auto_sltp on — Aktifkan AUTO TP/SL
/s_auto_sltp off — Nonaktifkan AUTO TP/SL
/s_auto_sltp tp 4 — Set auto TP 4%
/s_auto_sltp sl 2.5 — Set auto SL 2.5%
/s_auto_sltp trailing on — Aktifkan trailing stop
/s_auto_sltp apply BTCIDR — Apply ke posisi
```

### `/s_auto_sltp on` — Aktifkan

```
🤖 AUTO TP/SL: ✅ Diaktifkan
Semua buy baru akan dengan auto TP/SL.
```

### `/s_auto_sltp off` — Nonaktifkan

```
🤖 AUTO TP/SL: ❌ Dinonaktifkan
Semua buy baru akan tanpa auto TP/SL.
```

### `/s_auto_sltp tp <persen>` — Set auto TP

```
/s_auto_sltp tp 5
✅ Auto TP diatur ke 5.0%
```

### `/s_auto_sltp sl <persen>` — Set auto SL

```
/s_auto_sltp sl 1.5
✅ Auto SL diatur ke 1.5%
```

### `/s_auto_sltp trailing on|off` — Toggle trailing stop

```
/s_auto_sltp trailing on
📐 Trailing Stop: ✅ Diaktifkan
Distance: 1.0%
```

### `/s_auto_sltp apply <pair>` — Apply ke posisi existing

```
/s_auto_sltp apply BTCIDR
🤖 AUTO TP/SL Applied: BTCIDR

Entry: 1.000 IDR
🎯 TP: 1.030 (+3.0%)
🛑 SL: 980 (-2.0%)

Mode: 🤖 AUTO
```

> ⚠️ Perintah ini **menghapus manual TP/SL** yang lama.

---

## 6. Contoh Penggunaan (Step-by-Step)

### Workflow Standar

```
Step 1: Aktifkan AUTO TP/SL
/s_auto_sltp on

Step 2: Atur persentase (opsional)
/s_auto_sltp tp 4
/s_auto_sltp sl 2

Step 3: Aktifkan trailing stop (opsional)
/s_auto_sltp trailing on

Step 4: Buy seperti biasa
/s_buy BTCIDR 1000 500000
→ Posisi otomatis: TP=1040, SL=980, Mode=🤖 AUTO

Step 5: Monitor
/s_posisi
→ Tampilkan "Mode: 🤖 AUTO"

Step 6: Override manual jika perlu
/s_sltp BTCIDR 1100 970
→ Mode berubah ke "✋ MANUAL"
```

### Contoh dengan Trailing Stop

```
Entry: 1000, SL awal: 980

Harga naik 1000 → 1020:
  trailing_high = 1020
  new_sl = 1020 × 0.99 = 1009.8
  SL: 980 → 1009.8 (naik!)

Harga naik 1020 → 1050:
  trailing_high = 1050
  new_sl = 1050 × 0.99 = 1039.5
  SL: 1009.8 → 1039.5 (naik lagi!)

Harga turun 1050 → 1040:
  SL TETAP 1039.5 (tidak pernah turun)

Harga jatuh 1040 → 1039:
  SL HIT @ 1039.5 → Posisi terjual otomatis
```

---

## 7. Cara Kerja (Technical)

### Flow Auto-Apply saat Buy

```
/s_buy BTCIDR 1000 500000
         │
         ▼
  ┌─ Buat posisi {entry: 1000, amount: ..., capital: 500000}
  │
  ├─ _auto_apply_tp_sl("btcidr")
  │    ├─ Hitung: TP = 1000 × 1.03 = 1030
  │    ├─ Hitung: SL = 1000 × 0.98 = 980
  │    ├─ Set: pos['auto_sltp'] = True
  │    ├─ Set: pos['trailing_high'] = 1000
  │    └─ Simpan ke file
  │
  └─ Reply: "✅ BUY BTCIDR 🤖 ... TP: 1030 ... SL: 980"
```

### Flow Monitor Thread (every 5 sec)

```
  ┌─ _check_tp_sl_real(live_prices)
  │    │
  │    ├─ Verifikasi posisi di Indodax
  │    ├─ Cek profit alerts
  │    ├─ Cek drop alerts
  │    │
  │    ├─ _check_trailing_stop() ──────────────┐
  │    │    ├─ Update trailing_high jika naik   │
  │    │    ├─ Hitung new_sl = high × (1-dist)  │
  │    │    └─ SL hanya boleh NAIK, tidak turun │
  │    │                                        │
  │    ├─ Cek TP: price >= TP ────── _execute_real_sell("TAKE PROFIT")
  │    └─ Cek SL: price <= SL ────── _execute_real_sell("STOP LOSS")
  │
  └─ Sleep 5 detik, ulang
```

### Flow Manual Override

```
/s_sltp BTCIDR 1100 970
         │
         ▼
  ├─ pos['tp'] = 1100
  ├─ pos['sl'] = 970
  ├─ pos.pop('auto_sltp')   ← HAPUS flag auto
  ├─ pos.pop('trailing_high') ← HAPUS trailing
  └─ Mode: ✋ MANUAL
```

---

## 8. Position Data Structure

```json
{
  "entry": 1000,
  "time": 1717065600,
  "amount": 498.5,
  "capital": 500000,
  "tp": 1030,
  "sl": 980,
  "auto_sltp": true,
  "trailing_high": 1020,
  "order_id": "buy-123"
}
```

### Field Baru

| Field | Tipe | Deskripsi |
|-------|------|-----------|
| `auto_sltp` | `bool` | `true` = posisi dalam mode AUTO |
| `trailing_high` | `float` | Harga tertinggi sejak buy (untuk trailing stop) |

### Field Lama (tidak berubah)

| Field | Tipe | Deskripsi |
|-------|------|-----------|
| `entry` | `float` | Harga entry |
| `time` | `float` | Timestamp |
| `amount` | `float` | Jumlah coin |
| `capital` | `float` | Modal IDR |
| `tp` | `float` | Take profit price |
| `sl` | `float` | Stop loss price |

---

## 9. Risk/Reward Enforcement

Sistem otomatis menyesuaikan TP jika R/R ratio di bawah minimum:

```
AUTO_TP_PCT = 3%, AUTO_SL_PCT = 2%, R/R = 1.5

min_tp_pct = 2% × 1.5 = 3%
→ TP tetap 3% (sudah memenuhi minimum) ✅
```

Jika TP dikurangi:

```
AUTO_TP_PCT = 2%, AUTO_SL_PCT = 2%, R/R = 1.5

min_tp_pct = 2% × 1.5 = 3%
→ TP dinaikkan ke 3%! ⚠️ (forced minimum)
```

---

## 10. Method Reference

### ScalperConfig

| Method | Deskripsi |
|--------|-----------|
| `AUTO_TP_SL_ENABLED` | Master toggle |
| `AUTO_TP_PCT` | Default TP percentage |
| `AUTO_SL_PCT` | Default SL percentage |
| `AUTO_RISK_REWARD_RATIO` | Min R/R ratio |
| `AUTO_TRAILING_STOP_ENABLED` | Trailing stop toggle |
| `AUTO_TRAILING_DISTANCE_PCT` | Trailing distance |
| `AUTO_TRAILING_STEP_PCT` | Trailing step |

### ScalperModule (New Methods)

| Method | Deskripsi |
|--------|-----------|
| `_calculate_auto_tp_sl(entry)` | Hitung (tp, sl) dari entry price |
| `_auto_apply_tp_sl(pair)` | Apply auto TP/SL ke posisi |
| `_check_trailing_stop(pair, pos, price)` | Update trailing SL |
| `_auto_sltp_status_text(pos)` | Label: 🤖 AUTO / ✋ MANUAL / — |
| `cmd_auto_sltp(update, context)` | Handler `/s_auto_sltp` |

### ScalperModule (Modified Methods)

| Method | Perubahan |
|--------|-----------|
| `_check_tp_sl_real()` | Tambah `_check_trailing_stop()` sebelum cek TP/SL |
| `_execute_confirmed_buy()` | Tambah `_auto_apply_tp_sl()` setelah buy |
| `_execute_buy()` | Tambah `_auto_apply_tp_sl()` setelah buy |
| `cmd_buy()` | Tambah `_auto_apply_tp_sl()` di DRY RUN path |
| `cmd_sltp()` | Clear `auto_sltp` + `trailing_high` saat manual set |
| `_set_quick_sltp()` | Clear `auto_sltp` + `trailing_high` saat manual set |
| `cmd_posisi()` | Tampilkan "Mode: 🤖 AUTO" / "✋ MANUAL" |
| `refresh_posisi_callback()` | Tampilkan mode auto/manual |
| `cmd_menu()` | Tambah tombol 🤖 AUTO TP/SL + teks command |
| `_register_handlers()` | Register `s_auto_sltp` command |
| `menu_callback()` | Handle `s_auto_sltp_hint` callback |

---

## 11. Testing

### Jalankan Semua Test

```bash
# AUTO TP/SL tests (28 tests)
/home/officer/.hermes/bin/python -m pytest tests/test_scalper_auto_tpsl.py -v

# Existing scalper tests (37 tests — regression check)
/home/officer/.hermes/bin/python -m pytest tests/test_scalper_dryrun_positions.py -v

# Semua scalper tests (65 total)
/home/officer/.hermes/bin/python -m pytest tests/test_scalper_auto_tpsl.py tests/test_scalper_dryrun_positions.py tests/test_scalper_ai_analysis.py tests/test_scalper_historical_data_fetch.py tests/test_telegram_signal_scalper_buttons.py -v
```

### Coverage Summary

| Area | Tests | Detail |
|------|-------|--------|
| Kalkulasi TP/SL | 3 | Default, R/R enforcement, zero entry |
| Auto-apply | 4 | New position, disabled, skip manual, skip existing auto |
| Trailing stop | 5 | Update, no-lower, disabled, non-auto, step threshold |
| Status text | 3 | Auto, manual, none |
| Manual override | 2 | Quick sltp, cmd_sltp |
| Persistence | 1 | JSON save/load |
| Dry run buy | 2 | Applies auto, no auto when disabled |
| Command /s_auto_sltp | 6 | Show, toggle, tp, sl, apply, non-admin |

### Test File

```
tests/test_scalper_auto_tpsl.py
  class TestAutoTpSl (28 tests)
```

---

## 12. Rollback Plan

| Level | Cara | Dampak |
|-------|------|--------|
| Soft | `/s_auto_sltp off` | Buy baru tanpa auto, posisi existing tetap |
| Config | `ScalperConfig.AUTO_TP_SL_ENABLED = False` | Sama seperti above |
| Code | `git checkout HEAD~1 scalper/scalper_module.py` | Revert semua perubahan |
| Full | `git revert <commit>` | Revert + hapus tests/docs |

---

## 13. Changelog

| Tanggal | Perubahan |
|---------|-----------|
| 2026-05-30 | Initial implementation: ScalperConfig, _calculate_auto_tp_sl, _auto_apply_tp_sl, _check_trailing_stop, cmd_auto_sltp, menu button, 28 tests, docs |
