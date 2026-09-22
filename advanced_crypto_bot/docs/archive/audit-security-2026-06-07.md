# 🔒 Security Audit — 2026-06-07

## Ringkasan

Audit keamanan dan code review pada Advanced Crypto Trading Bot.
Dari **20 temuan**, **2 telah diperbaiki**, **1 by-design**, **17 masih open**.

---

## ✅ Selesai Diperbaiki

| # | Issue | File | Fix |
|---|-------|------|-----|
| 1 | `.env` world-readable (`rwxrwxrwx`) | `.env` | `chmod 600` — owner-only |
| 2 | `create_order` error handler pakai `dir()` | `api/indodax_api.py:484-486` | Initialize `response=None`, check `is not None` |
| 3 | DRY RUN Amount=0 karena `position_multiplier=0.0` | `autotrade/runtime.py:1032` | Skip multiplier 0 di DRY RUN; guard minimum amount |
| 4 | `_calculate_dry_run_total_from_price()` tidak konsisten | `autotrade/runtime.py:251` | Rewrite: target 1.000.000-1.500.000 IDR per trade |

## ℹ️ By Design

| # | Issue | Alasan |
|---|-------|--------|
| 3 | Scalper `force_real_trading=True` | Scalper = satu-satunya jalur real money. AutoTrade/AutoHunter tetap DRY RUN. |

## 🔴 Masih Terbuka — 17 Issues

| # | Severity | Issue | File |
|---|----------|-------|------|
| 4 | 🔴 KRITIS | `.env` berisi live API keys (Telegram + Indodax) — amankan backup | `.env` |
| 5 | 🟠 HIGH | `asyncio.run()` di `_shutdown()` bisa clash dengan running loop | `bot.py:940,955` |
| 6 | 🟠 HIGH | `os._exit(3)` tanpa cleanup — bisa corrupt SQLite | `bot.py:1109` |
| 7 | 🟠 HIGH | `Config` mutable class attribute dibaca/tulis dari banyak thread tanpa lock | `bot.py:1797` |
| 8 | 🟠 HIGH | Webhook listen `0.0.0.0`, secret token opsional — siapa pun bisa kirim update | `config.py:279` |
| 9 | 🟠 HIGH | `_quant_cache` module-level dictionary tidak pernah di-clear — memory leak | `signal_pipeline.py:32` |
| 10 | 🟠 HIGH | V4 prediction kirim `symbol` string sebagai feature — bisa silent fail | `signal_pipeline.py:247` |
| 11 | 🟠 HIGH | `check_daily_loss_limit` tidak hitung unrealized PnL dari posisi terbuka | `risk_manager.py:78` |
| 12 | 🟠 HIGH | `load_scalper_env()` parse `.env` manual — fragile | `scalper_module.py:36-50` |
| 13 | 🟠 HIGH | Dua Telegram bot token (`TELEGRAM_BOT_TOKEN` + `SCALPER_BOT_TOKEN`) — dead code | `.env` |
| 14 | 🟡 MEDIUM | `close_trade` hitung `total_pnl_pct` inkonsisten (partial vs full) | `database.py:773` |
| 15 | 🟡 MEDIUM | V4 auto-train thread start sebelum `__init__` selesai | `bot.py:220` |
| 16 | 🟡 MEDIUM | `_vacuum_database()` rentan deadlock | `database.py:78-99` |
| 17 | 🟡 MEDIUM | Logger log `post_params` di `create_order` (walau tanpa secret) | `indodax_api.py:474` |
| 18 | 🟡 MEDIUM | Partial TP1 reset `triggered` tanpa proteksi loop | `price_monitor.py:368` |
| 19 | 🟡 MEDIUM | Tidak ada validasi ML model compatibility (sklearn version mismatch) | `signal_pipeline.py:192-234` |
| 20 | 🟢 LOW | `close_trade()` panggil `self._upsert_performance_for_date` di dalam conn transaksi — bisa blocking | `database.py:807` |

---

## Test Results

**91/91 passed** — test suite indodax API, dryrun safety, scalper, dan bug fixes.
**10/10 passed** — test autotrade dryrun signal cycle (3 updated for new formula).
**280/284 passed** — full suite (4 pre-existing failures unrelated to changes).
