# PHASE 1 - Baseline Metrik + Daftar Rule Wajib Reject

Tanggal baseline: 2026-04-21  
Window utama: 7 hari terakhir (2026-04-14 15:46:31 s/d 2026-04-21 15:46:31)  
Sumber data:
- `advanced_crypto_bot/data/signals.db` (tabel `signals`)
- `advanced_crypto_bot/data/trading.db` (tabel `trades`, `performance`)

## 1) Baseline Metrik (7 Hari)

### 1.1 Distribusi Signal
Total signal 7 hari: `10,966`

- `HOLD`: `7,492` (`68.32%`)
- `SELL`: `1,792` (`16.34%`)
- `STRONG_SELL`: `1,392` (`12.69%`)
- `BUY`: `204` (`1.86%`)
- `STRONG_BUY`: `86` (`0.78%`)

Ringkasan:
- Bias signal masih dominan ke `HOLD` + sisi `SELL`.
- Actionable signal (`BUY/STRONG_BUY/SELL/STRONG_SELL`) = `3,474` dengan:
  - avg `ml_confidence`: `75.30%`
  - avg `combined_strength`: `-0.2766` (condong bearish)

### 1.2 Distribusi Multi-Window (stabilitas bias)

- 1 hari (`1,067` signal): BUY-like `5.16%`, SELL-like `23.89%`, HOLD `70.95%`
- 3 hari (`6,214` signal): BUY-like `4.37%`, SELL-like `33.54%`, HOLD `62.09%`
- 7 hari (`10,969` signal): BUY-like `2.65%`, SELL-like `29.04%`, HOLD `68.31%`
- 14 hari (`15,451` signal): BUY-like `7.40%`, SELL-like `31.08%`, HOLD `61.54%`

Keterangan:
- BUY-like = `BUY + STRONG_BUY`
- SELL-like = `SELL + STRONG_SELL`

### 1.3 Top Pair Actionable (indikasi konsentrasi)

Top pair dengan actionable signal tertinggi 7 hari:
- `MYXIDR`: 134 (buy_like 12, sell_like 122)
- `PIPPINIDR`: 110 (buy_like 8, sell_like 102)
- `TROLLSOLIDR`: 109 (buy_like 11, sell_like 98)
- `DRXIDR`: 107 (buy_like 15, sell_like 92)
- `NXAIDR`: 105 (buy_like 6, sell_like 99)

Interpretasi singkat:
- Pair-pair teratas juga condong SELL-like, konsisten dengan bias global.

### 1.4 Win-rate / PnL / False-positive 7 Hari

Status data eksekusi (trading):
- Closed trades 7 hari: `0`
- Closed trades 30 hari: `0`
- Closed trades 90 hari: `0`
- Tabel `performance`: belum terisi data ringkasan harian.

Implikasi:
- Win-rate realized, average PnL realized, dan false-positive berbasis hasil close trade **belum bisa dihitung valid** pada baseline ini.
- `FALSE_POSITIVE_PROXY` berbasis closed-losing-trades juga belum representatif karena denominator `0`.

Konteks eksposur saat ini:
- Open trades: `153`
- Gross open notional: `158,207,714.9991 IDR`

## 2) Daftar Rule Wajib Reject (Fondasi Fase Lanjut)

Catatan: daftar ini disusun sebagai policy target final untuk menyaring signal berisiko tinggi. Ini belum mengubah kode; ini acuan keputusan implementasi.

### Rule Set A - Price Context (Support/Resistance)

1. Reject BUY saat harga terlalu dekat resistance
- Kondisi: `distance_to_resistance_pct < 2.0%`
- Alasan: entry mepet target, upside kecil, risk skew buruk.

2. Reject SELL saat harga terlalu dekat support
- Kondisi: `distance_to_support_pct < 2.0%`
- Alasan: rawan jual di bottom.

3. Reject BUY jika risk/reward tidak layak
- Kondisi: `risk_reward_ratio < 1.5`
- Alasan: expected reward tidak sebanding risiko.

4. Reject signal dengan stop-loss distance terlalu sempit
- Kondisi: `sr_stop_distance_pct < 0.3%`
- Alasan: noise market kecil saja bisa memicu stop.

### Rule Set B - Consistency & Confidence

5. Reject BUY/STRONG_BUY jika `combined_strength` negatif
- Kondisi: rec BUY-like dan `combined_strength < 0`
- Alasan: arah rekomendasi kontra skor gabungan.

6. Reject SELL/STRONG_SELL jika `combined_strength` terlalu positif
- Kondisi: rec SELL-like dan `combined_strength > 0.3`
- Alasan: arah rekomendasi kontra kondisi teknikal gabungan.

7. Reject actionable signal bila `ML Confidence (final)` di bawah minimum
- Kondisi target:
  - BUY/SELL: `< 0.65`
  - STRONG_BUY/STRONG_SELL: `< 0.80`
- Alasan: confidence rendah meningkatkan noise.

### Rule Set C - Data Integrity & Market Regime

8. Reject signal jika data harga real-time stale/tidak valid
- Kondisi: harga terakhir stale melampaui SLA feed internal atau fallback invalid.
- Alasan: keputusan berbasis harga usang.

9. Reject signal jika candle historis belum cukup
- Kondisi: data candle `< 60`
- Alasan: indikator TA tidak stabil.

10. Reject signal pada rezim market terlarang/volatilitas ekstrem
- Kondisi: regime filter = no-trade atau volatility safety check gagal.
- Alasan: probabilitas false signal meningkat tajam.

## 3) Gap Data yang Harus Ditutup (agar baseline berikutnya lengkap)

1. Pastikan closed-trade logging aktif dan konsisten (`profit_loss`, `closed_at`).
2. Tambah metrik harian ke tabel `performance` (minimal total trade, win rate, total PnL).
3. Definisikan false-positive resmi:
- opsi A: closed trade loss ratio
- opsi B: signal outcome horizon (mis. +N candle return sesuai arah signal)
4. Simpan `signal_id`/trace-id ke trade agar mapping signal -> outcome presisi.

## 4) Keputusan Fase 1 (Siap Dipakai)

1. Baseline signal bias sudah terukur (7d/14d) dan terdokumentasi.
2. Baseline performa realized belum tersedia karena closed trade = 0.
3. Rule wajib reject sudah siap jadi spesifikasi implementasi fase stabilisasi.
