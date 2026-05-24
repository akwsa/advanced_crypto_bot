# REKOMENDASI TEAM — 2026-05-20

**Untuk:** Koordinasi team development  
**Dari:** AI Assistant (Kiro)  
**Tanggal:** 20 Mei 2026, 07:55 WIB

---

## 📌 Status Ringkas

| Area | Status |
|------|--------|
| Bug CRITICAL (C1-C8) | ✅ Semua fixed |
| Bug HIGH (H1-H12) | ✅ Semua fixed/guarded |
| Test suite | ✅ 121/121 pass (test inti) |
| Bot runtime | ⚠️ Perlu restart untuk aktivasi fix terbaru |
| ML model | ⚠️ Threshold sudah dituning, tapi perlu retrain |
| Database | ✅ WAL aktif, VACUUM deadlock fixed |

---

## 🎯 Prioritas Kerja (Urut)

### Prioritas 1 — Harus Segera (Minggu Ini)

| # | Task | PIC | Effort | Alasan |
|---|------|-----|--------|--------|
| 1 | Install dependency venv: `pip install python-telegram-bot matplotlib` | DevOps | 5 menit | Full test suite tidak bisa jalan tanpa ini |
| 2 | Retrain ML model V2 dengan data seimbang | ML Engineer | 2 jam | Sinyal masih bias SELL 3:1 vs BUY. Fix threshold hanya mengurangi gejala. |
| 3 | Restart bot setelah fix terbaru | Ops | 1 menit | Fix VACUUM deadlock + ML threshold belum aktif |

### Prioritas 2 — Minggu Depan

| # | Task | PIC | Effort | Alasan |
|---|------|-----|--------|--------|
| 4 | Tambah database indexes | Backend | 1 jam | Query lambat saat data besar |
| 5 | Fix duplicate notification (threading lock) | Backend | 2-4 jam | User terima 2-3 notif identik |
| 6 | Monitor distribusi sinyal 3-5 hari pasca-fix | Trader/QA | Ongoing | Validasi efektivitas fix ML bias |

### Prioritas 3 — Bulan Depan

| # | Task | PIC | Effort | Alasan |
|---|------|-----|--------|--------|
| 7 | Rate limiting Telegram commands | Backend | 3-5 jam | Security, bukan urgent |
| 8 | WebSocket reconnection logic | Backend | 6-8 jam | Harga real-time lebih cepat dari REST |
| 9 | Refactor bot.py (9.700 baris) | Full team | 2-3 minggu | Risiko operasional, tapi jangan sekarang |

---

## 🔴 JANGAN Dilakukan Sekarang

1. **Jangan refactor bot.py** — risiko introduce bug baru lebih besar dari manfaat. Fokus stabilitas dulu.
2. **Jangan aktifkan REAL trading** sebelum ML retrain selesai dan distribusi sinyal terbukti seimbang (minimal 3-5 hari observasi).
3. **Jangan ubah `MAX_DRAWDOWN_PCT`** — nilai 0.10 sudah benar (fraksi = 10%). Bug report lama salah interpretasi.

---

## 📊 Data Pendukung Keputusan

### Distribusi Sinyal Saat Ini (7 hari terakhir, 5.578 sinyal)

```
HOLD        : 68.8%  ← mayoritas (normal)
STRONG_SELL : 13.0%  ← terlalu banyak
SELL        : 10.0%  ← terlalu banyak
BUY         :  6.9%  ← terlalu sedikit
STRONG_BUY  :  1.4%  ← terlalu sedikit
```

**Target setelah retrain:** SELL+STRONG_SELL ≈ 10-15%, BUY+STRONG_BUY ≈ 10-15%

### Fix ML yang Sudah Diterapkan (belum retrain)

| Layer | Mekanisme | Status |
|-------|-----------|--------|
| Model level | `class_weight='balanced'` di RandomForest | ✅ Sudah ada |
| Model level | Undersampling majority class | ✅ Sudah ada (binary mode) |
| Predict level | SELL threshold diturunkan (prob < 0.25) | ✅ Baru diterapkan |
| Pipeline level | `SELL_MIN_CONFIDENCE = 0.58` (lebih ketat dari BUY 0.50) | ✅ Sudah ada |
| Pipeline level | ARIMA filter blokir BUY jika prediksi DOWN > -1% | ✅ Baru diterapkan |

**Yang belum:** GradientBoosting tidak punya `class_weight`. Perlu tambah `sample_weight` saat retrain.

---

## 🧪 Cara Verifikasi Setelah Restart

```bash
# 1. Masuk WSL
wsl -d Ubuntu

# 2. Aktifkan environment
source ~/hermes-pi.sh
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
source venv/bin/activate

# 3. Install dependency (jika belum)
pip install python-telegram-bot matplotlib

# 4. Jalankan test suite
python3 -m unittest tests.test_quant_integration tests.test_quant_new_features tests.test_batch3_rule_rejections tests.test_support_resistance_ordering -v

# 5. Restart bot
python3 bot.py

# 6. Setelah 3-5 hari, cek distribusi sinyal baru
python3 tmp/check_signals.py
```

---

## 📁 Referensi Dokumen

| Dokumen | Isi |
|---------|-----|
| `BUG_REPORT_CRITICAL.md` | Status semua bug C1-C8, H1-H12 (verified 2026-05-20) |
| `CATATAN_CHAT_2026-05-20.md` | Detail teknis semua fix hari ini |
| `CATATAN_CHAT_2026-05-19_SESI2.md` | Detail implementasi quant modules + integrasi |
| `QUANT_MODULES.md` | Dokumentasi 10 modul quant (termasuk 4 baru) |
| `CHANGELOG.md` | Riwayat perubahan + planned v1.1.0 |

---

## ✅ Checklist Koordinasi

- [ ] Restart bot
- [ ] Install `python-telegram-bot` + `matplotlib` di venv
- [ ] Assign PIC retrain ML model
- [ ] Jadwalkan review distribusi sinyal (3-5 hari dari sekarang)
- [ ] Diskusikan timeline database indexes + duplicate notification fix

---

**Pertanyaan?** Baca `BUG_REPORT_CRITICAL.md` untuk detail teknis atau `CATATAN_CHAT_2026-05-20.md` untuk kronologi fix.
