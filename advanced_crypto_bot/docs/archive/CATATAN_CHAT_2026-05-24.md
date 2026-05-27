# Catatan Chat 2026-05-24 — AutoTrade DRY RUN BUY→SELL Cycle, Scalper REAL Position Entry Fix, Runtime History Reset, Kiro Claude Balance/Signal UI

## Scope — Kiro Claude Scalper Balance Verification & Compact Signal UI

Mencatat perubahan dari Kiro Claude: verifier posisi REAL Scalper memakai key saldo Indodax yang benar (`balance`), dan format indikator utama signal Telegram dibuat lebih compact agar mudah dibaca di mobile.

## Files Changed — Kiro Claude Scalper Balance Verification & Compact Signal UI

- `scalper/scalper_module.py`
  - `_verify_position_exists()` sekarang menerima format `IndodaxAPI.get_balance()` yang berisi `balance` dan bukan `funds`.
  - Dampak: response valid dari Indodax tidak lagi menghasilkan warning `Could not fetch balance to verify position ...`; posisi tetap fail-safe bila API gagal.
- `signals/signal_formatter.py`
  - Bagian `Indikator utama` diringkas menjadi baris `RSI/MACD`, `MA/BB`, dan `Vol`.
- `GOALS.md` / `README.md`
  - Menambahkan roadmap target metrik/timeline menuju real trading bertahap dan menautkannya dari README.
  - Catatan safety: `MAX_DRAWDOWN_PCT = 0.10` berarti 10% karena config memakai fraction.
- `tests/test_scalper_dryrun_positions.py`
  - Regression untuk memastikan verifikasi posisi REAL membaca saldo coin dari key `balance`.
- `tests/test_signal_formatter_telegram_display.py`
  - Regression untuk layout indikator compact.

## Verification — Kiro Claude Scalper Balance Verification & Compact Signal UI

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_scalper_dryrun_positions.py::TestScalperDryRunPositions::test_real_position_verification_uses_indodax_balance_key tests/test_signal_formatter_telegram_display.py::test_signal_message_uses_compact_indicator_layout
# PASS

scripts/test.sh -q tests/test_scalper_dryrun_positions.py tests/test_signal_formatter_telegram_display.py tests/test_telegram_signal_scalper_buttons.py
# PASS

python -m py_compile scalper/scalper_module.py signals/signal_formatter.py
# OK
```

## Safety Impact — Kiro Claude Scalper Balance Verification & Compact Signal UI

- Tidak mengubah order execution path Indodax, `_execute_real_sell()`, `create_order()`, sizing, TP/SL trigger, atau API key gate.
- Perubahan Scalper hanya pada verifikasi saldo posisi REAL; saat balance API gagal, logic tetap fail-safe dan tidak menghapus posisi.
- Perubahan signal hanya formatting Telegram; keputusan internal (`BUY`, `SELL`, `HOLD`) tidak berubah.

## Rollback Plan — Kiro Claude Scalper Balance Verification & Compact Signal UI

Revert commit perubahan ini untuk mengembalikan verifier ke behavior sebelumnya dan format indikator lama. Tidak ada migrasi DB atau data runtime baru.

---

## Scope — Runtime History Reset & Retention

Menambahkan mekanisme cleanup/reset history AutoTrade, SmartHunter, dan AutoHunter agar data runtime bisa mulai baru dari sekarang, dengan backup aman sebelum reset dan retention otomatis 30 hari / guard 10GB.

## Files Changed — Runtime History Reset & Retention

- `bot.py`
  - `_scheduled_db_cleanup()` sekarang memanggil `cleanup_old_price_data(days=30, max_db_size_gb=10)`, `cleanup_old_runtime_history(days=30, max_db_size_gb=10)`, dan `delete_old_signals(days=30, max_db_size_gb=10)`.
- `core/database.py`
  - Menambah helper `_db_size_gb()`, `_table_count()`, dan `_delete_from_table()`.
  - Menambah `cleanup_old_runtime_history()` untuk membersihkan closed runtime history lama sambil mempertahankan posisi `OPEN` pada cleanup berkala.
  - Menambah `reset_runtime_history(include_open=False)` untuk reset eksplisit tabel runtime bot.
- `signals/signal_db.py`
  - Menambah `_db_size_gb()` dan `reset_history()`.
  - `delete_old_signals()` menerima `max_db_size_gb`.
- `tests/test_history_cleanup_retention.py`
  - Regression untuk cleanup history lama, reset runtime history, dan reset/retention signal DB.
- `.gitignore`
  - Menambahkan `backups/` agar backup operasional lokal tidak ikut ter-push.

## Backup & Live Reset Evidence — Runtime History Reset & Retention

Backup dibuat sebelum penghapusan:

```text
/home/officer/advanced_crypto_bot/backups/history_reset_20260524_045529/
├── trading.db
├── signals.db
└── pre_reset_counts.json
```

Pre-reset counts utama:

```text
trading.db: trades=289, trade_reviews=93, trade_outcomes=93, performance=28, pair_performance=5, signals=0
signals.db: signals=31795, signal_metadata=0
```

Reset live yang dijalankan:

```text
Database.reset_runtime_history(include_open=True)
SignalDatabase.reset_history()
```

Post-reset verification:

```text
trading.db: trades=0, trade_reviews=0, trade_outcomes=0, performance=0, pair_performance=0, old_*_older_than_30d=0
signals.db: old_signals=0; signal baru setelah reset boleh masuk lagi dari pipeline live
```

## Verification — Runtime History Reset & Retention

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_history_cleanup_retention.py
# 3 passed

scripts/test.sh -q tests/test_history_cleanup_retention.py tests/test_performance_backfill.py tests/test_dashboard_api_phase1.py tests/test_dashboard_api_readonly_phase1_endpoints.py
# 23 passed

python -m py_compile bot.py core/database.py signals/signal_db.py
# OK
```

## Safety Impact — Runtime History Reset & Retention

- Tidak mengubah default `AUTO_TRADE_DRY_RUN`.
- Tidak mengubah path real order Indodax, sizing, TP/SL, manual trading gate, API key gate, atau `MAX_DRAWDOWN_PCT`.
- Cleanup berkala mempertahankan posisi `OPEN`; penghapusan open trade hanya terjadi saat reset eksplisit `include_open=True` seperti operasi hari ini.
- User/watchlist/app settings/telegram users tetap dipertahankan.

## Rollback Plan — Runtime History Reset & Retention

Jika perlu mengembalikan history lama, hentikan bot terlebih dahulu lalu restore SQLite dari backup:

```bash
cp /home/officer/advanced_crypto_bot/backups/history_reset_20260524_045529/trading.db /home/officer/advanced_crypto_bot/advanced_crypto_bot/data/trading.db
cp /home/officer/advanced_crypto_bot/backups/history_reset_20260524_045529/signals.db /home/officer/advanced_crypto_bot/advanced_crypto_bot/data/signals.db
```

Untuk rollback kode, revert commit perubahan runtime history cleanup/reset.

---

# Catatan Chat 2026-05-24 — AutoTrade DRY RUN BUY→SELL Cycle

## Scope — AutoTrade DRY RUN BUY→SELL Cycle

Memperbaiki AutoTrade DRY RUN agar signal BUY/STRONG_BUY membuka posisi dan signal SELL/STRONG_SELL berikutnya untuk pair yang sama bisa menutup posisi tanpa tertahan cooldown scan `last_ml_update`.

## Files Changed — AutoTrade DRY RUN BUY→SELL Cycle

- `autotrade/runtime.py`
  - `check_trading_opportunity()` sekarang mengecek posisi terbuka per-pair sebelum cooldown scan.
  - Jika posisi pair sudah terbuka, cooldown boleh dilewati supaya SELL monitoring tetap berjalan.
  - Jika tidak ada posisi terbuka, cooldown tetap menahan scan seperti sebelumnya.
- `tests/test_autotrade_dryrun_signal_cycle.py`
  - Regression in-memory untuk BUY membuka posisi DRY RUN dan SELL menutup pair yang sama.

## RED/GREEN Evidence — AutoTrade DRY RUN BUY→SELL Cycle

- RED: test baru gagal sebelum patch karena SELL kedua tertahan cooldown dan posisi tetap `OPEN`.
- GREEN: focused regression pass setelah patch cooldown hanya bypass saat ada posisi terbuka.

## Verification — AutoTrade DRY RUN BUY→SELL Cycle

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_autotrade_dryrun_signal_cycle.py tests/test_signal_notification_controls.py tests/test_signal_formatter_telegram_display.py
# 31 passed

PYTHONPATH=. python - <<'PY'
import bot
print('bot import ok')
PY
# bot import ok

scripts/test.sh -q tests/
# 344 passed, 10 warnings (pre-existing quant/v4 warnings)
```

## Safety Impact — AutoTrade DRY RUN BUY→SELL Cycle

- Default AutoTrade tetap DRY RUN.
- Tidak mengubah `MAX_DRAWDOWN_PCT`, real API-key gate, position sizing, atau order execution real-money.
- Perubahan hanya membuat SELL monitoring tidak tertahan scan interval saat pair sudah punya posisi terbuka.

## Rollback Plan — AutoTrade DRY RUN BUY→SELL Cycle

Revert perubahan `autotrade/runtime.py` dan hapus `tests/test_autotrade_dryrun_signal_cycle.py` untuk kembali ke cooldown scan sebelumnya. Jika runtime anomali, matikan AutoTrade dan gunakan Scalper/manual confirmation sampai state open trade diverifikasi.

---

# Catatan Chat 2026-05-24 — Scalper REAL Position Entry Fix

## Scope

Memperbaiki logic Telegram Scalper REAL mode agar `/s_posisi`, refresh posisi, dan SELL flow tidak lagi memakai entry/amount stale dari local `active_positions` saat akun Indodax sudah punya eksekusi BUY/SELL terbaru.

## Files Changed

- `api/indodax_api.py`
  - `get_trade_history()` sekarang memakai Trade API v2 `/api/v2/myTrades` terlebih dahulu, lalu fallback legacy `orderHistory` dengan format pair private Indodax (`edenidr` → `eden_idr`).
- `scalper/scalper_module.py`
  - REAL position sync membaca holding aktual dari Indodax `get_balance()`.
  - Entry REAL direkonstruksi dari Indodax order/trade history dengan lot accounting, bukan cache Telegram/local.
  - `/s_posisi`, refresh posisi, SELL callback, confirmed SELL, dan `/s_sell` melakukan sync holdings REAL sebelum menampilkan/menjual posisi.
- `tests/test_scalper_dryrun_positions.py`
  - Regression untuk kasus EDENIDR: local entry stale `1,648`, trade history terbaru `1,704`, tampilan harus `Entry 1,704`.
  - Regression SELL callback/confirmed SELL agar memakai entry dan amount hasil sync Indodax.
- `tests/test_indodax_api_order_params.py`
  - Regression format private pair untuk `orderHistory`.
  - Regression agar `get_trade_history()` memakai Trade API v2 `/api/v2/myTrades` saat tersedia.

## RED/GREEN Evidence

- RED: `test_posisi_real_mode_uses_indodax_trade_history_entry_not_stale_local_cache` gagal sebelum patch karena `/s_posisi` masih menampilkan `Entry 1,648`.
- RED kedua: `test_posisi_real_mode_uses_indodax_order_history_amount_fields_not_stale_cache` gagal karena parser legacy `orderHistory` belum membaca amount dari `order_idr`/`remain_idr`.
- GREEN: focused regression dan related tests sudah pass.

## Verification

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_scalper_dryrun_positions.py tests/test_indodax_api_order_params.py
# 37 passed, 2 warnings

PYTHONPATH=. python - <<'PY'
import bot
print('bot import ok')
PY
# bot import ok
```

## Safety Impact

- Tidak mengubah default global DRY RUN bot.
- Perubahan hanya memperbaiki sumber data REAL Telegram Scalper supaya tampilan dan tombol SELL memakai holdings/trade history Indodax aktual.
- Jika Indodax API belum siap, real-order fail-closed behavior tetap dipertahankan.
- Local active positions tetap hanya dipakai sebagai metadata fallback (TP/SL/order_id) setelah posisi aktual disync dari Indodax.

## Rollback Plan

Revert commit perubahan ini untuk kembali ke logic sebelumnya. Jika ada anomali runtime, jalankan `/s_posisi` setelah memeriksa Indodax `getInfo`/`orderHistory`, dan hentikan real Scalper order flow sampai pair/amount terverifikasi.

---

## Scope — Scalper /s_analisa Historical Data & Gemini-Style Narrative

Memperbaiki command `/s_analisa <PAIR>` agar pair seperti `EDENIDR` tidak lagi gagal dengan pesan generik `Gagal mengambil data historis`, dan output analisa memakai narasi teknikal Indonesia bergaya Gemini untuk pair yang diminta saja.

## Root Cause — Scalper /s_analisa Historical Data & Gemini-Style Narrative

- Endpoint public Indodax trades valid untuk format compact lowercase seperti `edenidr` / `btcidr`; format underscore seperti `eden_idr` / `btc_idr` mengembalikan `invalid_pair` pada endpoint ini.
- Input Telegram bisa datang sebagai uppercase (`EDENIDR`) atau variasi lain, sehingga perlu normalisasi ke compact lowercase sebelum request.
- `date` dari response Indodax berupa unix seconds string; perlu dikonversi numeric dulu agar parse timestamp konsisten lintas versi pandas.
- Resample lama memakai alias `1T`; di environment saat ini alias itu gagal parse, sehingga diganti ke `1min`.

## Files Changed — Scalper /s_analisa Historical Data & Gemini-Style Narrative

- `scalper/scalper_module.py`
  - `cmd_analisa()` sekarang memakai `build_gemini_style_technical_analysis()` untuk narasi teknikal 15m dengan EMA 7/25/99.
  - Error historis kosong dibuat lebih informatif: pair sepi/belum aktif, format tidak dikenali, atau API Indodax bermasalah.
  - `_fetch_historical_data()` menormalisasi pair ke compact lowercase, mencoba compact form dulu, fallback underscore bila perlu, mengabaikan response API error dict, mengonversi timestamp string ke numeric, dan resample candle 1-menit dengan `1min`.
- `bot_parts/scalper_ai_analysis.py`
  - Helper pure untuk menghitung swing high/low, EMA, support/resistance, fase tren, dan merender narasi teknikal Indonesia gaya Gemini.
- `tests/test_scalper_historical_data_fetch.py`
  - Regression untuk normalisasi `EDENIDR` -> `edenidr`, fallback underscore, response kosong/API error, parsing OHLCV, dan candle output.
- `tests/test_scalper_ai_analysis.py`
  - Regression untuk metrik dan format narasi pair-specific.

## Verification — Scalper /s_analisa Historical Data & Gemini-Style Narrative

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_scalper_historical_data_fetch.py tests/test_scalper_ai_analysis.py tests/test_telegram_ui_formatting.py
# 17 passed, 2 warnings

python -m py_compile scalper/scalper_module.py bot_parts/scalper_ai_analysis.py tests/test_scalper_historical_data_fetch.py tests/test_scalper_ai_analysis.py
# OK

python - <<'PY'
import asyncio
from scalper.scalper_module import ScalperModule
async def main():
    for pair in ['EDENIDR', 'BTCIDR']:
        df = await ScalperModule._fetch_historical_data(None, pair)
        print(pair, 'None' if df is None else f'rows={len(df)} last={df.close.iloc[-1]}')
asyncio.run(main())
PY
# EDENIDR rows=148 last=1544.0
# BTCIDR rows=75 last=1360000000.0
```

## Safety Impact — Scalper /s_analisa Historical Data & Gemini-Style Narrative

- Tidak mengubah order execution path Indodax, balance sync, sizing, TP/SL trigger, atau real-trading gate.
- Perubahan hanya pada public market data fetch dan formatting analisa Telegram.
- Default AutoTrade tetap DRY RUN; Scalper real-order confirmation flow tidak disentuh.

## Rollback Plan — Scalper /s_analisa Historical Data & Gemini-Style Narrative

Revert perubahan `scalper/scalper_module.py`, hapus `bot_parts/scalper_ai_analysis.py`, `tests/test_scalper_ai_analysis.py`, dan `tests/test_scalper_historical_data_fetch.py` untuk kembali ke formatter analisa lama. Jika runtime anomali, nonaktifkan penggunaan `/s_analisa` sementara dan tetap gunakan `/price`/`/signal` untuk observasi market sampai patch dikembalikan.

