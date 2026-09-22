# PHASE 2 - Rule Implementation Spec (No Code Change)

Tanggal: 2026-04-21  
Tujuan: menerjemahkan rule wajib reject menjadi peta implementasi teknis yang jelas.  
Status dokumen: spesifikasi + progress eksekusi batch.

## Scope

Dokumen ini memetakan:
1. Rule policy -> file/fungsi implementasi
2. Coverage saat ini (sudah ada vs belum ada)
3. Gap dan prioritas implementasi

## Mapping Rule ke Kode

### R1 - Reject BUY dekat resistance (<2%)
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_pipeline.py` (SR validation inline)
  - `signals/signal_filter_v2.py::_check_price_zone`
- Coverage status: `DONE` (Batch 1)
- Catatan:
  - Sudah ada logika reject.
  - Bypass confidence tinggi pada gate final pipeline sudah dihapus.

### R2 - Reject SELL dekat support (<2%)
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_pipeline.py` (SR validation inline)
  - `signals/signal_filter_v2.py::_check_price_zone`
- Coverage status: `DONE` (Batch 1)
- Catatan:
  - Bypass confidence tinggi pada gate final pipeline sudah dihapus.

### R3 - Reject BUY jika R/R < 1.5
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_filter_v2.py::_check_price_zone` (threshold 1.5)
  - `signals/signal_pipeline.py` (threshold default env `SR_MIN_RR_RATIO=0.8`)
- Coverage status: `DONE` (Batch 2)
- Catatan:
  - Default gate final pipeline diselaraskan ke `1.5`.

### R4 - Reject jika stop-loss distance terlalu sempit (<0.3%)
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_pipeline.py` (`SR_MIN_SL_PCT`, default 0.3)
- Coverage status: `DONE`
- Catatan:
  - Sudah aktif pada jalur pipeline utama.

### R5 - Reject BUY-like jika combined_strength negatif
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_filter_v2.py::_check_confidence_tiers`
- Coverage status: `PARTIAL`
- Catatan:
  - Ada di filter v2, tapi belum dipastikan menjadi gate final runtime utama.

### R6 - Reject SELL-like jika combined_strength terlalu positif (>0.3)
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_filter_v2.py::_check_confidence_tiers`
- Coverage status: `PARTIAL`
- Catatan:
  - Sama: ada di filter v2, belum jadi gate final tunggal.

### R7 - Reject actionable jika ML Confidence (final) di bawah minimum
- Policy:
  - BUY/SELL < 65% reject
  - STRONG_BUY/STRONG_SELL < 80% reject
- Titik implementasi saat ini:
  - `signals/signal_quality_engine.py` memakai threshold jauh lebih rendah
  - `signals/signal_filter_v2.py` memiliki tier threshold target
- Coverage status: `DONE` (Batch 2)
- Catatan:
  - Threshold confidence di quality engine diselaraskan:
    - BUY/SELL `0.65`
    - STRONG_BUY/STRONG_SELL `0.80`
  - Filter v2 juga diselaraskan untuk BUY/SELL/STRONG tiers.

### R8 - Reject jika data harga stale/invalid
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_pipeline.py` menandai source harga (`API`/`WEBSOCKET_FRESH`/`HISTORICAL_FALLBACK`)
  - actionable signal di-block ke HOLD jika source jatuh ke stale historical fallback
- Coverage status: `DONE` (Batch 3)
- Catatan:
  - Reason reject distandarkan dengan source tag `[PRICE_VALIDATION]`.

### R9 - Reject jika candle historis <60
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_pipeline.py` sudah return `None` jika data < 60
- Coverage status: `DONE`

### R10 - Reject saat regime terlarang / volatilitas ekstrem
- Policy: wajib reject
- Titik implementasi saat ini:
  - `signals/signal_pipeline.py` (volatility/regime -> HOLD)
- Coverage status: `DONE`

## Prioritas Implementasi (Saat Mulai Coding)

1. Satukan gate final ke satu jalur runtime yang aktif (pipeline utama).
2. Hilangkan bypass confidence tinggi untuk R1/R2 agar benar-benar “wajib reject”.
3. Samakan threshold R/R (R3) agar satu angka final.
4. Kunci threshold confidence final (R7) agar konsisten lintas modul.
5. Tambah stale-price hard reject (R8) dengan reason yang eksplisit.

## Tracker Eksekusi

- Spec mapping rule -> fungsi: `DONE`
- Definisi prioritas coding: `DONE`
- Batch 1:
  - Gate final runtime di `signal_pipeline.py` dipertegas: `DONE`
  - Bypass confidence tinggi untuk near S/R dihapus: `DONE`
  - Format reason reject SR distandarkan (`[SR_VALIDATION] ...`): `DONE`
- Batch 2:
  - R/R gate default di pipeline (`1.5`): `DONE`
  - Confidence threshold harmonization lintas quality engine + filter v2: `DONE`
- Batch 3:
  - Hard reject stale price fallback di pipeline: `DONE`
  - Tambahan helper rule ringan di `signals/signal_rules.py`: `DONE`
  - Regression tests rule wajib reject:
    - `tests/test_batch3_rule_rejections.py`: `DONE`
    - hasil: `5 tests OK` via `python -m unittest tests.test_batch3_rule_rejections -v`
