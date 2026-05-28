# CATATAN_CHAT_2026-05-27

## Ringkasan Perubahan

Sesi ini menambahkan decision layer konkret untuk sinyal BUY agar label user-facing tidak langsung meloncat ke `BELI KUAT` saat setup masih reversal awal atau sinyal kedua sebenarnya hanya duplikat lemah.

Perubahan utama:

1. Tambah helper baru `signals/signal_decision_layer.py`.
2. Klasifikasi BUY/STRONG_BUY menjadi 4 label tampilan:
   - `PANTAU`
   - `BELI_BERTAHAP`
   - `BUY`
   - `STRONG_BUY`
3. Tambah duplicate suppression buy-side berbasis kualitas sinyal, bukan hanya `(tanggal, pair, rec, price)` di DB.
4. Formatter Telegram sekarang memprioritaskan `display_recommendation` bila tersedia.
5. Pipeline DB save memakai `display_recommendation` agar histori notifikasi mengikuti decision layer baru.

## Rule Decision Layer

### 1. Kapan `PANTAU`

`classify_buy_signal_label()` mengembalikan `PANTAU` bila salah satu kondisi inti gagal:

- kandidat BUY berada di luar zona support (`price_zone` bukan `IN_SUPPORT`/`NEAR_SUPPORT`), atau
- momentum rebound belum terkonfirmasi:
  - MACD belum bullish,
  - `combined_strength < 0.32`, dan
  - ARIMA tidak mengarah `UP`.

Makna operasional: sinyal ini masih informatif, belum layak dianggap entry aktif.

### 2. Kapan `BELI_BERTAHAP`

Dipakai saat support valid dan ada tanda rebound, tetapi kualitas entry belum cukup agresif. Kondisi umum:

- masih di area support,
- sudah ada tanda momentum membaik,
- namun salah satu kualitas dasar masih lemah:
  - `ml_confidence < 0.60`, atau
  - `combined_strength < 0.18`, atau
  - `risk_reward_ratio < 1.30`.

Juga dipakai pada kasus “rebound awal” yang belum punya konfirmasi penuh trend/ruang profit.

### 3. Kapan `BUY`

Dipakai jika setup buy sudah cukup bersih:

- `ml_confidence >= 0.68`
- `combined_strength >= 0.25`
- `risk_reward_ratio >= 1.50`
- trend cukup suportif (`ma_trend == BULLISH` atau dekat support)
- tidak sedang mengejar harga (`distance_to_resistance_pct >= 2.0`)

### 4. Kapan `STRONG_BUY` / BELI KUAT

Hanya untuk setup yang benar-benar terkonfirmasi:

- semua syarat `BUY` lolos, dan
- `ml_confidence >= 0.78`
- `combined_strength >= 0.40`
- `risk_reward_ratio >= 1.80`
- MACD bullish
- volume mendukung (`HIGH` / `RISING` / `STRONG`)
- ruang ke resistance masih lega (`distance_to_resistance_pct >= 3.0`)

Tujuan rule ini: `BELI KUAT` menjadi label langka dan berkualitas, bukan default saat RR besar tetapi momentum/trend masih melawan.

### 5. Kapan sinyal kedua ditolak sebagai duplikat

`should_reject_duplicate_buy_signal()` menolak sinyal buy kedua bila:

- pair sebelumnya juga buy-flavoured (`PANTAU`, `BELI_BERTAHAP`, `BUY`, `STRONG_BUY`),
- muncul dalam <= 30 menit,
- dan tidak ada peningkatan material, yaitu sinyal baru **tidak** menunjukkan salah satu dari:
  - upgrade level label,
  - `ml_confidence` naik minimal `+0.05`,
  - `combined_strength` naik minimal `+0.10`,
  - `risk_reward_ratio` naik minimal `+0.40`.

Jika tidak ada peningkatan berarti, pipeline memberi `DECISION_DUPLICATE` lalu menurunkan tampilan ke `HOLD` agar tidak dikirim sebagai sinyal buy baru.

## Aggressive Profit Tuning Update

Atas permintaan user, threshold BUY kemudian dituning lebih agresif untuk menangkap setup profit lebih cepat, dengan pagar berikut tetap dipertahankan:

- reversal yang masih lemah/bearish tetap `PANTAU`
- duplicate suppression buy-side tetap aktif
- sinyal di luar support tetap bukan entry aktif

Perubahan threshold agresif:

- momentum valid lebih cepat:
  - `BULLISH_CROSS` sekarang dihitung sebagai momentum membaik
  - `combined_strength >= 0.26` bisa dianggap momentum membaik walau belum full bullish
- trend support lebih longgar:
  - `ma_trend == NEUTRAL` sekarang masih boleh dianggap suportif
  - toleransi jarak ke support dilonggarkan ke `<= 1.9%`
- entry tidak dianggap chasing selama `distance_to_resistance_pct >= 1.6%`
- volume `NORMAL` tetap boleh lolos untuk setup agresif; tidak harus `HIGH`

Threshold baru:

- `BELI_BERTAHAP` bila masih di bawah salah satu:
  - `ml_confidence < 0.56`
  - `combined_strength < 0.15`
  - `risk_reward_ratio < 1.15`
- `BUY` bila minimal:
  - `ml_confidence >= 0.64`
  - `combined_strength >= 0.22`
  - `risk_reward_ratio >= 1.35`
  - trend suportif
  - tidak chasing
- `BELI KUAT` bila minimal:
  - `ml_confidence >= 0.74`
  - `combined_strength >= 0.34`
  - `risk_reward_ratio >= 1.65`
  - MACD `BULLISH` atau `BULLISH_CROSS`
  - volume minimal `NORMAL`
  - `distance_to_resistance_pct >= 2.4%`

Tambahan guard setelah tuning agresif:

- jika MACD masih bearish,
- MA belum bullish,
- ARIMA belum UP,
- dan `combined_strength < 0.34`,

maka sinyal tetap dipaksa menjadi `PANTAU` agar reversal mentah tidak salah naik menjadi `BUY`.


- `signals/signal_decision_layer.py` — helper rule baru
- `signals/signal_pipeline.py` — integrasi decision layer + duplicate suppression
- `signals/signal_formatter.py` — pakai `display_recommendation`
- `tests/test_signal_decision_layer.py`
- `tests/test_signal_pipeline_decision_layer.py`
- `tests/test_signal_formatter_telegram_display.py`

## Integration Scenarios Added

Untuk mengunci behavior end-to-end di level pipeline nyata (`generate_signal_for_pair()`), ditambahkan test integrasi baru di `tests/test_signal_pipeline_integration_decision_layer.py` dengan harness bot minimal dan dependency utama dimock secukupnya.

Skenario yang ditambahkan:

1. **Kasus 389 → 388 tanpa peningkatan material**
   - Sinyal pertama lolos sebagai `STRONG_BUY` / `BELI KUAT`.
   - Sinyal kedua 8 menit kemudian dengan harga turun tipis (`389 -> 388`) tetapi confidence/strength tidak membaik berarti.
   - Expected: `DECISION_DUPLICATE`, `recommendation == HOLD`, `display_recommendation == HOLD`.

2. **Candle turun tipis tapi reversal masih lemah**
   - Raw pipeline masih menghasilkan `BUY`.
   - Namun indikator masih bearish-lemah (`macd=BEARISH`, `ma_trend=NEUTRAL`, belum ada ARIMA up kuat).
   - Expected: `recommendation` inti tetap `BUY`, tetapi `display_recommendation == PANTAU`.

3. **Candle turun tipis dengan momentum membaik**
   - `macd=BULLISH_CROSS`, trend netral, support masih valid, RR cukup.
   - Expected: `display_recommendation == BUY`, bukan `PANTAU`.

Catatan penting dari test integrasi ini:

- Fixture support/resistance dibuat realistis agar tidak mentok lebih dulu oleh `SR_VALIDATION`.
- Jadi test ini memang menguji decision layer + duplicate suppression, bukan sekadar gagal di gate resistance.


Command yang dijalankan:

```bash
scripts/test.sh -q tests/test_signal_decision_layer.py
scripts/test.sh -q tests/test_signal_decision_layer.py tests/test_signal_formatter_telegram_display.py tests/test_signal_pipeline_decision_layer.py
```

Hasil:

- `6 passed in 0.45s`
- `14 passed in 4.43s`

## Catatan Safety

- Rule baru ini fokus pada **label tampilan dan suppression notifikasi buy duplikat**.
- Jalur filter existing seperti S/R validation, V4 validation, ARIMA filter, dan final policy tetap aktif.
- Perubahan ini belum mengubah sizing/eksekusi order secara langsung; yang berubah utama adalah klasifikasi output dan penolakan sinyal buy berulang berkualitas sama.
