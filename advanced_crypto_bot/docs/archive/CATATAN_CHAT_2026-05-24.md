# Catatan Chat 2026-05-24 — AutoTrade DRY RUN BUY→SELL Cycle & Scalper REAL Position Entry Fix

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