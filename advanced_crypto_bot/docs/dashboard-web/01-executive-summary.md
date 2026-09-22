# 01 — Executive Summary

## Visi Proyek

Membangun web dashboard untuk Advanced Crypto Trading Bot agar trader bisa memantau pasar, signal, trade, dan kondisi runtime bot secara visual tanpa harus bergantung penuh pada Telegram.

Dashboard **bukan pengganti `bot.py`**. Dashboard adalah companion service yang membaca state bot dari SQLite/Redis. Untuk scope yang sudah disetujui saat ini, dashboard **hanya read-only** dan tidak boleh mengubah state trading.

---

## Status Revisi v1.3 — Phase 1 Read-only Approved

Phase 0 audit runtime awal sudah dilakukan pada 2026-05-21:

- Bot aktif sebagai proses manual: `python bot.py` dari terminal VS Code/WSL, bukan PM2/systemd/docker.
- Runtime DB live adalah `data/trading.db` karena `DATABASE_PATH` unset dan cwd bot adalah folder project.
- `core/trading.db` ada tapi ukuran 0 byte; dianggap legacy/placeholder, bukan runtime live.
- Redis aktif dan memiliki key runtime `price:*`, `state:historical:*`, `signal_queue:*`; belum ada `dashboard:*` sebelum heartbeat ditambahkan.
- Bot heartbeat ditambahkan dengan key `dashboard:bot:heartbeat` TTL 30 detik.
- User sudah approve **Phase 1 read-only only**: health, active pairs/chart, latest signals, trades/open positions, dan SSE stream.

---

## Problem Statement

Saat ini operasi utama dilakukan via Telegram:

- Signal muncul dalam chat.
- Status bot/hunter berupa text command.
- Tidak ada overview visual banyak pair.
- Tidak ada chart dashboard.
- Health bot dan source data belum terlihat dalam satu panel web.

Catatan: ide SL/TP, trade ticket, dan trading dari website tetap disimpan sebagai roadmap future, tetapi **bukan scope implementasi Phase 1**.

---

## Solusi Bertahap

### Phase 1 — Approved Read-only Dashboard MVP

Dashboard menampilkan MVP kecil:

1. Bot/system health, termasuk heartbeat bot.
2. Pair aktif dan chart/candlestick.
3. Signal terbaru.
4. Trade history dan open positions secara read-only.
5. Realtime read-only memakai **Server-Sent Events (SSE)**.

Realtime Phase 1 memakai SSE karena dashboard read-only butuh push satu arah server → browser. WebSocket/Socket.IO tidak dipakai pada Phase 1.

### Future Phase 1.5+ — Deferred Write / Two-way Features

Semua fitur berikut **ditunda** sampai ada approval terpisah:

- Exact Telegram signal outbox write.
- Trade ticket calculator dan save trade plan.
- Controlled SL/TP write ke tabel `dashboard_*`.
- WebSocket/two-way communication jika memang dibutuhkan.

### Future Phase 2/3 — Trading Controls / Real Trading

Fitur berisiko tinggi seperti DRY RUN trade intent, Real Trading toggle, Start/Stop Hunter, dan emergency stop hanya dikerjakan setelah user menyetujui security model, auth, audit log, idempotency, dan safety gate khusus.

---

## Scope

### In Scope Phase 1

- REST API read-only.
- SSE endpoint untuk realtime read-only price/signal/health/trade event.
- Read SQLite existing tables.
- Read Redis existing keys.
- Bot heartbeat Redis `dashboard:bot:heartbeat`.
- Active pairs dari `data/trading.db.watchlist`.
- Chart/candle dari `data/trading.db.price_history`.
- Latest signals dari `data/signals.db.signals`.
- Trades/open positions dari `data/trading.db.trades` dan Redis position state jika tersedia.
- Fallback polling jika SSE atau Redis bermasalah.
- Nginx reverse proxy + HTTPS jika dipublikasikan.
- Basic login/private network protection jika dashboard dipublikasikan ke internet.

### Explicitly Out of Scope Phase 1

- Write ke tabel existing bot.
- Write ke tabel `dashboard_*` baru.
- SL/TP write.
- Exact Telegram signal outbox persistence.
- Trade ticket persistence / save plan.
- DRY RUN trade intent dari website.
- Eksekusi trade langsung dari dashboard.
- Toggle Real Trading.
- Start/Stop Hunter.
- Emergency stop.
- Multi-user granular RBAC.
- Mobile native app.
- Backtesting visual.
- Exchange selain Indodax.

---

## Success Criteria Awal

| Kriteria | Target Phase 1 |
|---|---:|
| Dashboard initial load | < 3 detik pada VPS normal |
| API p95 read response | < 300 ms untuk query cached/simple |
| SSE latency | < 1 detik server-to-browser untuk event cached |
| Bot heartbeat detection | Offline terlihat ≤ 30–45 detik setelah key expired |
| Data freshness visible | Semua panel menampilkan `last_updated` / stale state |
| Bot safety | Kegagalan dashboard tidak mematikan `bot.py` |
| SQLite safety | Tidak ada write ke tabel existing bot atau dashboard table pada Phase 1 |
| HTTPS | Valid SSL certificate jika public |

---

## Risiko Utama

1. Query dashboard mengunci SQLite saat bot aktif jika busy handling buruk.
2. Signal final perlu keputusan: `data/signals.db` sebagai primary, `trading.db.signals` kosong pada audit runtime.
3. Redis key actual harus dibaca dengan scan/prefix, bukan `KEYS *` pada produksi besar.
4. Native FastAPI WebSocket tidak kompatibel dengan Socket.IO; Phase 1 memilih SSE untuk menghindari mismatch.
5. Admin API key tidak boleh ditaruh di frontend.
6. Real Trading toggle terlalu berbahaya untuk MVP awal dan tetap deferred.

---

## Rekomendasi Keputusan

Untuk tahap pertama, bangun **Phase 1 read-only dashboard** dulu dengan REST + SSE. Jangan mulai SL/TP write, trade ticket, DRY RUN trading, atau real trading dari website sampai ada approval terpisah dan readiness check baru.
