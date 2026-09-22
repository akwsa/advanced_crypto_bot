# Catatan Chat 2026-05-26 — AutoTrade DRY RUN Auto-Promote, Signal Queue Integration, dan /s_analisa Timeframe

## Scope — AutoTrade DRY RUN Auto-Promote & Signal Queue Path

Melanjutkan perbaikan AutoTrade DRY RUN agar:

1. Sinyal BUY / STRONG_BUY yang dikirim ke Telegram (via pipeline dan signal queue, bukan hanya WebSocket price handler) bisa memicu AutoTrade DRY RUN.
2. Pair yang sudah di-watch (`/watch`) otomatis masuk daftar `auto_trade_pairs` saat ada sinyal BUY/STRONG_BUY (auto-promote), tanpa perlu `/add_autotrade` manual.
3. Trade DRY RUN hasil eksekusi AutoTrade disimpan ke DB sebagai referensi tuning parameter.

## Root Cause — AutoTrade DRY RUN tidak jalan saat ada sinyal BUY/STRONG_BUY

Dari pembacaan kode (`autotrade/runtime.py`, `bot.py`, `core/database.py`) dan test (`tests/test_autotrade_dryrun_signal_cycle.py`, `tests/test_dryrun_safety.py`, `tests/test_signal_notification_controls.py`, `tests/test_near_miss_signals.py`) ditemukan beberapa akar masalah:

1. **Signal queue path tidak memanggil auto-promote logic**
   - `process_price_update_signal_tasks()` berisi logic auto-promote DRY RUN (watched pair + BUY/STRONG_BUY → `auto_trade_pairs` + `check_trading_opportunity()`), tetapi fungsi ini hanya dipanggil dari WebSocket price handler.
   - Market scan thread + signal queue worker yang sebenarnya mengirim sinyal ke Telegram, memanggil langsung `check_trading_opportunity()` **tanpa** auto-promote, dan `check_trading_opportunity()` menolak pair yang belum ada di `auto_trade_pairs`.

2. **SR_VALIDATION menurunkan semua BUY menjadi HOLD untuk eksekusi**
   - Pipeline sinyal menerapkan SR_VALIDATION sehingga `recommendation` akhir sering menjadi `HOLD` meskipun ML+TA awal memberikan `BUY`/`STRONG_BUY`.
   - Autotrade runtime sebelumnya hanya melihat field `recommendation` akhir, sehingga tidak pernah melihat BUY/STRONG_BUY untuk trigger trade.

3. **State is_trading dan penyimpanan mode belum konsisten**
   - Di konstruktor `AdvancedCryptoBot`, `self.is_trading` di-set ke `False` setelah `_enable_startup_dryrun_autotrade()` mengaktifkan DRY RUN. Akibatnya setiap restart bot kembali ke OFF meskipun mode startup DRY RUN seharusnya ON.
   - `core/database.Database` belum punya `set_auto_trade_mode()`, sehingga penyimpanan mode ke tabel `app_settings` gagal.

## Files Changed — AutoTrade DRY RUN

### `autotrade/runtime.py`

- Menambahkan helper `_auto_promote_pair(bot, pair)` untuk memasukkan pair yang di-watch ke `auto_trade_pairs` admin secara otomatis (DRY RUN only):
  - Normalisasi pair (`btcidr` vs `BTC/IDR` vs `btc_idr`) sebelum deduplikasi.
  - Menentukan `user_id` dari `bot.subscribers.keys()`.

- Memperkuat `check_trading_opportunity(bot, pair, signal=None)`:
  - Jika `Config.AUTO_TRADE_DRY_RUN` dan pair **belum** ada di `auto_trade_pairs` tetapi **ada di watchlist**, fungsi akan **auto-promote** pair tersebut sebelum melanjutkan.
  - Untuk eksekusi trade, `signal['recommendation']` di-override dengan `signal['pre_sr_recommendation']` (jika tersedia) agar SR_VALIDATION tidak memblokir semua BUY.
  - Tetap menghormati semua 17 gate risk/VAR/correlation/optimizer; perubahan hanya pada sumber sinyal eksekusi, bukan pada threshold risiko.

- Memperbarui `process_price_update_signal_tasks()`:
  - Saat DRY RUN aktif dan `bot.is_trading=True`, watched pair dengan `pre_sr_recommendation` BUY/STRONG_BUY memicu `_auto_promote_pair()` + `check_trading_opportunity()`.
  - Menambahkan log debug `[AUTO-PROMOTE]` untuk memudahkan tracing.

### `signals/signal_pipeline.py`

- Menyimpan field baru `signal['pre_sr_recommendation']` sebelum SR_VALIDATION mengubah `recommendation`.
- Konsumen lain (notifikasi Telegram) tetap memakai `recommendation` final; autotrade runtime khusus memakai `pre_sr_recommendation` untuk keputusan eksekusi.

### `bot.py`

- Startup trading state:
  - Setelah `_enable_startup_dryrun_autotrade()`, penetapan `self.is_trading = False` diganti dengan guard `if not hasattr(self, 'is_trading'):` sehingga state yang di-set startup tidak di-overwrite.

- Handler `/autotrade`:
  - Dokumentasi di docstring diperjelas: `/autotrade dryrun` mengaktifkan DRY RUN dan sinkronisasi dengan watchlist admin.
  - Menambahkan help text yang lebih eksplisit saat mode tidak dikenal (`/autotrade`, `/autotrade help`).
  - Mengunci mode REAL untuk safety: `/autotrade real` tetap diarahkan ke DRY RUN dan memanggil `_lock_no_money_automation()` jika API key belum dikonfigurasi.

- Handler `/autotrade_status`:
  - Saat `self.is_trading=True` tapi belum ada trade hari ini, output sekarang menampilkan ringkasan pair aktif dari watchlist/auto-trade list dan checklist langkah uji DRY RUN.

### `core/database.py`

- Menambahkan method `set_auto_trade_mode(self, is_enabled: bool)`:
  - Menyimpan mode ke tabel `app_settings` dengan kunci `autotrade_mode` (`DRY_RUN`/`OFF`).
  - Tetap kompatibel dengan `get_auto_trade_mode()` yang sudah ada.

- Dipastikan bahwa trade DRY RUN tetap disimpan lewat jalur `add_trade()` dan `get_open_trades()` (tidak diubah dalam patch ini).

### `autotrade/price_monitor.py`

- Menambahkan `rebuild_from_open_trades(db, trading_engine)`:
  - Pada startup, membaca semua open trades dari DB.
  - Menghitung ulang SL/TP via `trading_engine.calculate_stop_loss_take_profit()`.
  - Menggunakan `set_price_level()` untuk setiap posisi sehingga monitoring SL/TP aktif kembali setelah restart.

- `bot.py` memanggil `self.price_monitor.rebuild_from_open_trades(self.db, self.trading_engine)` setelah `_enable_startup_dryrun_autotrade()`.

## Tests — AutoTrade DRY RUN

### Test Baru / Diperluas

- `tests/test_autotrade_dryrun_signal_cycle.py`
  - Menambahkan skenario:
    - Watched pair (`/watch btcidr`) dengan sinyal BUY/STRONG_BUY di DRY RUN:
      - Pair otomatis masuk `auto_trade_pairs` (auto-promote).
      - `check_trading_opportunity()` membuka trade DRY RUN dan menyimpan ke DB.
    - Sinyal SELL/STRONG_SELL berikutnya untuk pair yang sama:
      - Diperbolehkan melewati cooldown scan `last_ml_update` jika posisi pair sudah terbuka.
      - Menutup posisi DRY RUN di DB.

- `tests/test_autotrade_status_watchlist.py` (baru)
  - Memastikan `/autotrade_status` saat `is_trading=True` dan tidak ada trade hari ini:
    - Menampilkan pair aktif dari watchlist/auto-trade list.
    - Menggunakan `parse_mode='Markdown'` tanpa HTML tags (`<i>`, `<b>`) atau newline ganda `"\\n"`.

### Test Fokus yang Dijalankan

Perintah yang sudah dijalankan dan PASS:

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_autotrade_dryrun_signal_cycle.py tests/test_autotrade_status_watchlist.py
# 4 passed
```

Selain itu, sebagian besar suite lain juga sempat dijalankan, namun saat full test (`scripts/test.sh -q`) muncul error dependency FastAPI yang tidak tersedia di environment lokal (`ModuleNotFoundError: No module named 'fastapi'` untuk dashboard API tests). Ini dependency baru dashboard dan **tidak terkait** jalur AutoTrade.

## Safety Impact — AutoTrade DRY RUN

- AutoTrade tetap **DRY RUN only**:
  - `Config.AUTO_TRADE_DRY_RUN` digunakan sebagai gate; tidak ada kode yang mengaktifkan real trading baru.
  - `/autotrade real` tetap dilock dan mengarah ke pesan safety, seperti yang sudah didokumentasikan di `COMMANDS.md`.

- Perubahan hanya menyentuh:
  - Integrasi watchlist → auto_trade_pairs (auto-promote DRY RUN).
  - Pengambilan sinyal eksekusi dari `pre_sr_recommendation` alih-alih `recommendation` akhir.
  - Konsistensi state `is_trading` dan persistence mode ke DB.
  - Rebuild monitoring SL/TP dari open trades DRY RUN saat restart.

- Tidak mengubah:
  - `MAX_DRAWDOWN_PCT` di `core/config.py` (tetap `0.10` = 10%).
  - Sizing real money, path Scalper real trading, atau API key gate.
  - Struktur tabel DB trade; hanya cara runtime memakainya di DRY RUN.

- Rollback: cukup revert perubahan di `autotrade/runtime.py`, `signals/signal_pipeline.py`, `bot.py`, `core/database.py`, `autotrade/price_monitor.py`, dan test terkait.

---

## Scope — Scalper /s_analisa Timeframe & OHLC Fix

Menambahkan kemampuan memilih timeframe untuk `/s_analisa` dan memperbaiki resample OHLC yang sebelumnya menghasilkan nilai high/low/open palsu.

### Files Changed

- `scalper/scalper_module.py`
  - `/s_analisa <PAIR> [timeframe]` sekarang mendukung timeframe: `15m`, `1h`, `1d`, `1W` (default `15m`).
  - `_fetch_historical_data()` diperbaiki:
    - Normalisasi pair ke compact lowercase untuk endpoint Indodax (`edenidr`, `btcidr`).
    - Resample candle menggunakan `1min` dan menghitung OHLC asli (`open`=first, `high`=max, `low`=min, `close`=last).
    - Menyesuaikan jumlah minimal candles: 20 untuk 1d/1W, 60 untuk timeframe lebih pendek.

- `bot_parts/scalper_ai_analysis.py`
  - Helper pure untuk analisa teknikal dan narasi bergaya Gemini tetap memakai data OHLC baru.

### Tests

- `tests/test_scalper_historical_data_fetch.py`
  - Regression untuk bentuk data historis (OHLC, volume, timestamp) dan normalisasi pair.

- `tests/test_scalper_ai_analysis.py`
  - Regression untuk narasi teknikal yang konsisten per timeframe.

### Dokumentasi

- `ARCHITECTURE.md`
  - Menambahkan penjelasan singkat untuk modul AutoTrade dan scalper analysis.

- `COMMANDS.md`
  - Menjelaskan opsi timeframe baru untuk `/s_analisa`.

- `CHANGELOG.md`
  - Menambahkan entri `[Unreleased]` yang merangkum perbaikan AutoTrade DRY RUN, signal queue integration, dan `/s_analisa` timeframe/OHLC.

---

## GOALS2 — Tambahan Tujuan Setelah Perbaikan

> Catatan: GOALS2.md belum dibuat sebelumnya; sementara ini, GOALS tambahan dicatat di sini sebagai referensi implementasi selanjutnya.

1. **AutoTrade DRY RUN Responsif dan Transparan**
   - Setiap sinyal BUY/STRONG_BUY dari pair yang ada di watchlist harus:
     - Memicu auto-promote ke `auto_trade_pairs` (DRY RUN), dan
     - Menyimpan trade DRY RUN ke DB bila semua gate risiko lolos.
   - `/autotrade_status` dan `/trades` harus bisa dipakai untuk memverifikasi siklus ini tanpa perlu membuka log.

2. **Integrasi Signal Queue yang Independen dari WebSocket**
   - AutoTrade DRY RUN tidak lagi bergantung pada WebSocket price handler saja; signal queue worker dari market scan cukup untuk memicu trade.
   - Jika WebSocket mati sementara, signal queue + DRY RUN harus tetap berjalan.

3. **Analisa Scalper yang Lebih Fleksibel**
   - `/s_analisa` menyediakan analisa teknikal yang konsisten untuk timeframe 15m, 1h, 1d, dan 1W dengan OHLC yang benar.
   - Digunakan sebagai referensi manual saat mengevaluasi trade DRY RUN hasil AutoTrade.

4. **Kebersihan Test & Dependency Dashboard**
   - Error `ModuleNotFoundError: fastapi` pada full test menjadi indikator bahwa dependency dashboard belum diinstall, bukan kegagalan fitur trading.
   - Ke depan, dependency dashboard bisa dipisahkan (extra) agar full test environment jelas statusnya.
