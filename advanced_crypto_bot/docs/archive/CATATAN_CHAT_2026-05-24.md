# Catatan Chat 2026-05-24 — Scalper REAL Position Entry Fix

## Scope

Memperbaiki logic Telegram Scalper REAL mode agar `/s_posisi`, refresh posisi, dan SELL flow tidak lagi memakai entry/amount stale dari local `active_positions` saat akun Indodax sudah punya eksekusi BUY/SELL terbaru.

## Files Changed

- `api/indodax_api.py`
  - `get_trade_history()` sekarang memakai format pair private Indodax (`edenidr` → `eden_idr`) untuk `orderHistory`.
- `scalper/scalper_module.py`
  - REAL position sync membaca holding aktual dari Indodax `get_balance()`.
  - Entry REAL direkonstruksi dari Indodax order/trade history dengan lot accounting, bukan cache Telegram/local.
  - `/s_posisi`, refresh posisi, SELL callback, confirmed SELL, dan `/s_sell` melakukan sync holdings REAL sebelum menampilkan/menjual posisi.
- `tests/test_scalper_dryrun_positions.py`
  - Regression untuk kasus EDENIDR: local entry stale `1,648`, trade history terbaru `1,704`, tampilan harus `Entry 1,704`.
  - Regression SELL callback/confirmed SELL agar memakai entry dan amount hasil sync Indodax.
- `tests/test_indodax_api_order_params.py`
  - Regression format private pair untuk `orderHistory`.

## RED/GREEN Evidence

- RED: `test_posisi_real_mode_uses_indodax_trade_history_entry_not_stale_local_cache` gagal sebelum patch karena `/s_posisi` masih menampilkan `Entry 1,648`.
- GREEN: focused regression dan related tests sudah pass.

## Verification

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
scripts/test.sh -q tests/test_scalper_dryrun_positions.py tests/test_indodax_api_order_params.py
# 35 passed, 2 warnings

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