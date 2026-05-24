# 04 — Epics & User Stories

> Revisi v1.2 memisahkan discovery resolved, MVP read-only kecil, controlled write, dan dangerous controls.

---

## EPIC 0 — Discovery, Audit & Approval Gate

**Prioritas:** P0  
**Status:** Sebagian besar resolved pada 2026-05-21; validasi ulang sebelum deploy production.  
**Tujuan:** Memastikan implementasi berdasarkan runtime aktual, bukan asumsi.

### US-0.1 — Audit SQLite Schema Aktual

Acceptance Criteria:

- [x] Audit `data/trading.db`, `core/trading.db`, dan `data/signals.db`.
- [x] Tentukan DB runtime yang dipakai bot aktif: `data/trading.db`.
- [x] Dokumentasikan table, kolom, dan row count non-sensitive.
- [x] Tentukan source of truth awal untuk watchlist, trades, price history, dan signals.
- [ ] Validasi ulang di environment production sebelum deploy dashboard.

### US-0.2 — Audit Redis Keys Aktual

Acceptance Criteria:

- [x] Verifikasi key existing: `price:*`, `state:historical:*`, `signal_queue:*`.
- [x] Verifikasi format `price:*`: string `price:timestamp`.
- [x] Dokumentasikan key yang belum ada: Telegram health, hunter status.
- [x] Tambahkan bot heartbeat publisher: `dashboard:bot:heartbeat` TTL 30s.
- [ ] Tambahkan publisher Telegram/Hunter jika panel detail diambil Sprint 2.

### US-0.3 — Approval Scope Sebelum Coding Dashboard Utama

Acceptance Criteria:

- [x] User memilih Phase 1 only atau Phase 1 + 1.5. **Approved 2026-05-21: Phase 1 read-only only — health, active pairs/chart, latest signals, trades/open positions, SSE stream.**
- [ ] User memutuskan Real Trading toggle ditunda atau tidak.
- [ ] User menyetujui auth model.
- [ ] User menyetujui deployment target.

---

## Approved Phase 1 Scope — Read-only Only

**Approval:** 2026-05-21  
**Status:** Approved for implementation planning.  
**Batas:** Phase 1 hanya read-only terhadap data runtime bot.

Allowed Phase 1 scope:

1. Health.
2. Active pairs/chart.
3. Latest signals.
4. Trades/open positions.
5. SSE stream.

Not included in Phase 1:

- SL/TP write.
- Telegram exact outbox write.
- Trade ticket persistence.
- DRY RUN trade intents.
- Real trading from website.
- Hunter controls.
- Emergency stop.

---

## EPIC 1 — User Bisa Memantau Bot dan Market Secara Read-only

**Prioritas:** P0  
**Phase:** Approved Phase 1 read-only.  
**Tujuan user:** User bisa membuka dashboard dan melihat kondisi bot, pair aktif, signal terbaru, trade/position, dan update realtime tanpa mengubah state trading.

### US-1.1 — Bot/System Health Read-only

Sebagai user, saya ingin melihat status API, bot heartbeat, Redis, DB, dan freshness agar tahu dashboard dan bot sedang sehat atau bermasalah.

BDD Acceptance Criteria:

- [ ] **Given** API dashboard hidup, **when** user membuka health panel, **then** panel menampilkan API status dan timestamp response.
- [ ] **Given** Redis memiliki key `dashboard:bot:heartbeat` yang masih fresh, **when** API membaca bot status, **then** response menampilkan `bot_status=online` dan heartbeat age.
- [ ] **Given** key `dashboard:bot:heartbeat` expired/hilang, **when** API membaca bot status, **then** response menampilkan `bot_status=offline` atau `unknown` tanpa crash.
- [ ] **Given** Redis down, **when** user membuka health panel, **then** API tetap hidup, `redis_status=offline`, dan bot heartbeat tampil `unknown/offline`.
- [ ] **Given** SQLite source bisa dibuka read-only, **when** data source endpoint dipanggil, **then** DB status dan freshness tampil.

### US-1.2A — Active Pairs API

Sebagai user, saya ingin melihat pair aktif dari watchlist agar tahu pair mana yang sedang dipantau bot.

BDD Acceptance Criteria:

- [ ] **Given** `data/trading.db.watchlist` berisi pair aktif, **when** `GET /api/v1/pairs/active` dipanggil, **then** response berisi daftar pair canonical lowercase seperti `btcidr`.
- [ ] **Given** watchlist kosong, **when** endpoint dipanggil, **then** response sukses dengan data kosong dan `freshness=empty`.
- [ ] **Given** SQLite locked, **when** endpoint dipanggil, **then** reader retry bounded dan mengembalikan cache jika tersedia atau error `SQLITE_LOCKED` jika tidak ada cache.
- [ ] **Given** endpoint sukses, **then** response memakai wrapper `success`, `data`, dan `meta`.

### US-1.2B — Latest Price untuk Active Pairs

Sebagai user, saya ingin melihat harga terbaru pair aktif agar bisa membaca kondisi market saat ini.

BDD Acceptance Criteria:

- [ ] **Given** Redis memiliki key `price:{pair}` dengan format `price:timestamp`, **when** active pairs diminta dengan latest price, **then** response menampilkan price dan `last_updated`.
- [ ] **Given** Redis price missing untuk pair tertentu, **when** fallback Indodax public API tersedia, **then** response memakai fallback dengan source `indodax`.
- [ ] **Given** Redis dan Indodax fallback gagal, **then** pair tetap muncul dengan freshness `unknown/offline`, bukan crash.
- [ ] **Given** price timestamp melewati TTL freshness, **then** response menandai data `stale`.

### US-1.2C — Pair Chart Endpoint

Sebagai user, saya ingin melihat data chart/candle per pair agar bisa membaca trend harga tanpa membuka tool lain.

BDD Acceptance Criteria:

- [ ] **Given** `data/trading.db.price_history` berisi OHLCV untuk pair, **when** `GET /api/v1/pairs/{pair}/chart?timeframe=1h&limit=200` dipanggil, **then** response berisi candle berurutan.
- [ ] **Given** pair tidak punya price history, **then** response sukses dengan data kosong dan `freshness=empty`.
- [ ] **Given** limit melebihi batas maksimal, **then** endpoint membatasi ke maksimum yang disetujui.
- [ ] **Given** SQLite locked, **then** retry/cache/error behavior mengikuti fallback strategy Phase 1.

### US-1.2D — Active Pair Cards UI

Sebagai user, saya ingin melihat kartu pair aktif dengan harga dan freshness agar dashboard cepat dipahami.

BDD Acceptance Criteria:

- [ ] **Given** `/api/v1/pairs/active` sukses, **when** dashboard dibuka, **then** UI menampilkan kartu pair, latest price, dan freshness badge.
- [ ] **Given** data loading, **then** UI menampilkan loading state yang jelas.
- [ ] **Given** API mengembalikan empty/error/stale, **then** UI menampilkan empty/error/stale state yang jelas.
- [ ] **Given** user mengetik search/filter minimal, **then** daftar pair terfilter tanpa mengubah data backend.

### US-1.2E — Mini Chart UI

Sebagai user, saya ingin melihat mini candlestick/line chart pada pair card agar bisa cepat membaca trend.

BDD Acceptance Criteria:

- [ ] **Given** chart endpoint mengembalikan candle, **when** pair card dirender, **then** mini chart tampil untuk pair tersebut.
- [ ] **Given** chart data kosong, **then** UI menampilkan placeholder chart/empty state.
- [ ] **Given** chart endpoint error, **then** pair card tetap tampil dan chart area menampilkan degraded state.

### US-1.3 — Latest Signals Read-only

Sebagai user, saya ingin melihat signal terbaru agar bisa memantau rekomendasi bot tanpa membuka Telegram.

BDD Acceptance Criteria:

- [ ] **Given** `data/signals.db.signals` berisi signal, **when** `GET /api/v1/signals/latest?limit=50` dipanggil, **then** response menampilkan 50 signal terbaru atau kurang jika data kurang.
- [ ] **Given** query filter pair/recommendation diberikan, **then** response hanya berisi signal yang cocok.
- [ ] **Given** confidence/strength tersedia di source, **then** field tersebut tampil; jika tidak tersedia, field boleh `null` tanpa error.
- [ ] **Given** source utama `data/signals.db.signals`, **then** response meta/source menandai `signal_db`.
- [ ] **Given** signal DB kosong/tidak tersedia, **then** API return empty/error state yang jelas tanpa mengganggu endpoint lain.

### US-1.4 — Trades & Open Positions Read-only

Sebagai user, saya ingin melihat trade history dan open position secara read-only agar tahu kondisi trading bot tanpa melakukan aksi.

BDD Acceptance Criteria:

- [ ] **Given** `data/trading.db.trades` berisi trades, **when** `GET /api/v1/trades/history` dipanggil, **then** response berisi pair, type, price, amount, total, status, dan P&L jika tersedia.
- [ ] **Given** filter `status=open|closed|all`, **then** response mengikuti filter.
- [ ] **Given** Redis `state:position:*` tersedia, **when** `GET /api/v1/positions/open` dipanggil, **then** response memakai Redis position state.
- [ ] **Given** Redis positions kosong, **then** endpoint fallback ke SQLite `trades WHERE status='open'`.
- [ ] **Given** tidak ada open position, **then** response sukses dengan `freshness=empty`.

---

## EPIC 2 — Dashboard Update Realtime dengan Fallback Aman

**Prioritas:** P0  
**Phase:** Approved Phase 1 read-only.  
**Tujuan user:** Dashboard bisa update otomatis, tetapi tetap usable jika SSE/Redis/SQLite bermasalah.

### US-2.1 — SSE Event Stream Read-only

Sebagai user, saya ingin dashboard menerima update realtime agar signal, price, trade, dan health tidak perlu refresh manual.

BDD Acceptance Criteria:

- [ ] **Given** API dashboard berjalan, **when** browser membuka `GET /api/v1/events/stream`, **then** response content type adalah `text/event-stream`.
- [ ] **Given** heartbeat berubah, **then** stream dapat mengirim event `heartbeat`.
- [ ] **Given** price/signal/trade source berubah atau polling interval mendeteksi perubahan, **then** stream dapat mengirim `price_update`, `signal_update`, atau `trade_update`.
- [ ] **Given** koneksi SSE putus, **then** browser auto-reconnect memakai native `EventSource`.
- [ ] **Given** Phase 1 read-only, **then** tidak ada event yang mengeksekusi write/trading action.
- [ ] **Given** implementasi frontend Phase 1, **then** tidak memakai `socket.io-client`.

### US-2.2 — Read Fallback Strategy

Sebagai user, saya ingin dashboard tetap menampilkan status yang jujur saat source data bermasalah.

BDD Acceptance Criteria:

- [ ] **Given** Redis down, **when** price/position/heartbeat dibaca, **then** price fallback ke Indodax public API jika aman, position fallback ke SQLite open trades, dan status Redis tampil `offline`.
- [ ] **Given** SQLite locked, **when** endpoint read dipanggil, **then** API retry maksimal 3x dengan backoff 1s/2s/4s.
- [ ] **Given** retry gagal dan cache tersedia, **then** API return cached response dengan meta `source=cache` dan warning/freshness yang sesuai.
- [ ] **Given** retry gagal tanpa cache, **then** API return error `SQLITE_LOCKED` dan `retry_after_seconds`.
- [ ] **Given** Indodax fallback dipakai, **then** client memakai timeout dan rate limit agar dashboard tidak membebani public API.

---

## EPIC 3 — Sprint 2 Monitoring Expansion

**Prioritas:** P1

### US-3.1 — Top 20 Volume Indodax

Acceptance Criteria:

- [ ] Tabel 20 pair volume tertinggi.
- [ ] Last price, volume, change 24h.
- [ ] Auto refresh configurable.
- [ ] Stale/offline indicator jika Indodax API gagal.
- [ ] Rate limit Indodax public API diterapkan.

### US-3.2 — Pair Detail Page

Acceptance Criteria:

- [ ] Route `/pairs/{pair}`.
- [ ] Full chart.
- [ ] Latest signal.
- [ ] Recent trades untuk pair.
- [ ] Current position/read-only status.
- [ ] Current SL/TP config jika Phase 1.5 sudah aktif.

### US-3.3 — Telegram/Hunter Health Detail

Acceptance Criteria:

- [ ] Menampilkan connected/degraded/offline/unknown.
- [ ] Last heartbeat per publisher jika sudah tersedia.
- [ ] Jika key belum tersedia, tampilkan `unknown` bukan error palsu.
- [ ] Dokumen menyebut bot-side publisher yang dibutuhkan.

---

## EPIC 4 — SL/TP Controlled Write

**Prioritas:** P1, hanya Phase 1.5 setelah approval.

### US-4.1 — SL/TP Config Table

Acceptance Criteria:

- [ ] Migration membuat table `dashboard_sl_tp_settings`.
- [ ] Migration membuat `dashboard_audit_log`.
- [ ] Backup DB sebelum migration.
- [ ] Rollback script tersedia.
- [ ] Tidak mengubah table existing bot.

### US-4.2 — SL/TP Visual Config

Acceptance Criteria:

- [ ] Entry price editable.
- [ ] Direction eksplisit minimal `LONG_SPOT`.
- [ ] SL/TP percent dan price preview.
- [ ] Estimasi profit/loss IDR.
- [ ] Fee/slippage input atau default config.
- [ ] Risk/reward ratio.
- [ ] Save hanya admin.
- [ ] Semua save tercatat di audit log.

### US-4.3 — Bot-side SL/TP Reader

Acceptance Criteria:

- [ ] Bot membaca table `dashboard_sl_tp_settings` secara eksplisit.
- [ ] Bot mengabaikan config inactive/stale.
- [ ] Bot tetap berjalan jika table dashboard tidak ada.
- [ ] Unit/integration test membuktikan fallback aman.

---

## EPIC 5 — Security, Auth & Audit

**Prioritas:** P0 for public dashboard, P1 for private LAN.  
**Phase:** Decision only for Phase 1 read-only; write auth/audit details are future.

### US-5.1 — Auth Model

Acceptance Criteria:

- [ ] Jika dashboard public, read endpoints dilindungi oleh selected auth model.
- [ ] Tidak ada admin key di frontend bundle.
- [ ] CORS whitelist jika dashboard public.
- [ ] Rate limiting minimal untuk public deployment.
- [ ] Future write endpoints remain deferred until separate approval.

### US-5.2 — Future Audit Log for Write Phases

Acceptance Criteria:

- [ ] Future write action masuk audit log setelah write scope approved.
- [ ] Audit log berisi actor, action, old value, new value, IP/user agent, timestamp.
- [ ] Audit log read-only di dashboard admin jika future admin module dibuat.
- [ ] Phase 1 read-only tidak membuat write audit table sebagai requirement implementasi.

---

## EPIC 6 — Deployment & Observability

**Prioritas:** P0

### US-6.1 — Deployment Strategy

Acceptance Criteria:

- [ ] Karena bot saat audit berjalan manual via terminal, pilih strategi dashboard yang tidak mengganggu proses bot.
- [ ] Docker Compose, PM2, atau systemd dipilih eksplisit sebelum deploy.
- [ ] Nginx serve frontend dan proxy `/api` + `/events`.
- [ ] Let's Encrypt SSL jika public.

### US-6.2 — Health & Smoke Test

Acceptance Criteria:

- [ ] `/api/v1/health`.
- [ ] `/api/v1/system/data-sources`.
- [ ] Smoke test semua read endpoint.
- [ ] SSE connection test.
- [ ] Bot heartbeat expiry test.

---

## EPIC 7 — Dangerous Controls

**Prioritas:** P2, tidak masuk MVP kecuali user approve eksplisit.

Fitur:

- Toggle Dry Run ↔ Real Trading.
- Start/Stop SmartHunter.
- Emergency stop.

Acceptance Criteria minimum jika nanti diambil:

- [ ] Confirmation phrase, contoh `ENABLE REAL TRADING`.
- [ ] Re-auth admin.
- [ ] Audit log.
- [ ] Cooldown.
- [ ] Bot-side safety validation.
- [ ] Emergency rollback.
