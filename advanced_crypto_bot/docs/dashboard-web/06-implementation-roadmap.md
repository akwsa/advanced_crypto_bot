# 06 — Implementation Roadmap

> Roadmap v1.3 diselaraskan dengan approval user: implementasi berikutnya hanya Phase 1 read-only. Semua write/trading features deferred sampai approval terpisah.

---

## Phase 0 — Discovery & Final Review

**Estimasi:** 2–4 hari  
**Status:** Audit awal selesai 2026-05-21; Phase 1 read-only scope approved 2026-05-21.

Deliverables:

- `09-current-codebase-audit.md` final awal.
- DB source of truth: `data/trading.db` + `data/signals.db`.
- Redis key contract final awal.
- Bot heartbeat publisher.
- MVP scope approval.
- Auth decision jika dashboard akan dipublikasikan.
- Deployment decision.

Exit Criteria:

- [x] DB runtime path jelas.
- [x] Signal source awal jelas.
- [x] Redis keys runtime jelas.
- [x] Bot heartbeat publisher tersedia.
- [x] User menyetujui Phase 1 read-only only.
- [x] Real Trading controls ditunda dari Phase 1.
- [ ] Auth model dipilih jika dashboard public.
- [ ] Deployment target dipilih.

---

## Phase 1 — Read-only Backend API

**Estimasi:** 7–10 hari  
**Status:** Ready for implementation planning setelah auth/deploy decision minimal.

Approved scope:

1. Health.
2. Active pairs/chart.
3. Latest signals.
4. Trades/open positions.
5. SSE stream.

Tasks:

- FastAPI scaffold.
- Health endpoint dengan bot heartbeat reader.
- Data source status endpoint.
- DB readers untuk `data/trading.db` dan `data/signals.db`.
- Redis readers untuk `price:*`, `state:position:*`, `state:historical:*`, `dashboard:bot:heartbeat`.
- Read-only endpoints:
  - `GET /api/v1/health`
  - `GET /api/v1/system/data-sources`
  - `GET /api/v1/pairs/active`
  - `GET /api/v1/pairs/{pair}/chart`
  - `GET /api/v1/signals/latest`
  - `GET /api/v1/trades/history`
  - `GET /api/v1/positions/open`
  - `GET /api/v1/events/stream`
- Data freshness metadata.
- SQLite retry/backoff/cache handling.
- Indodax fallback + rate limit for latest price only when Redis data missing/stale.
- Unit tests.

Exit Criteria:

- [ ] Semua read endpoint MVP jalan.
- [ ] Tidak ada write endpoint pada Phase 1.
- [ ] Tidak ada write ke table existing bot.
- [ ] Tidak ada write ke table `dashboard_*`.
- [ ] SSE test pass.
- [ ] API docs/OpenAPI Phase 1 tersedia.
- [ ] Dashboard API gagal tidak memengaruhi bot.

---

## Phase 2 — Read-only Frontend Dashboard

**Estimasi:** 10–15 hari

Tasks:

- React/Vite scaffold.
- Layout + routing minimal.
- Health panel.
- Active pairs panel dengan mini candlestick/chart.
- Latest signals panel.
- Trades/open positions panel.
- Fresh/stale/offline/unknown UI states.
- Native EventSource client with fallback polling.
- Frontend tests.

Exit Criteria:

- [ ] Health panel tampil.
- [ ] Active pairs/chart panel tampil.
- [ ] Latest signals panel tampil.
- [ ] Trades/open positions panel tampil.
- [ ] Data stale/offline jelas di UI.
- [ ] SSE reconnect/fallback polling bekerja.
- [ ] Mobile basic responsive.
- [ ] Tidak ada tombol write/trading controls pada Phase 1 UI.

---

## Phase 3 — Deploy Read-only MVP

**Estimasi:** 5–7 hari

Tasks:

- Pilih process manager: systemd/PM2/Docker/manual.
- Nginx config untuk `/api` dan SSE `/api/v1/events/stream`.
- HTTPS jika public.
- Smoke tests.
- Basic auth/session jika public.
- Deployment guide.

Exit Criteria:

- [ ] Dashboard bisa diakses via HTTPS jika public.
- [ ] Bot tetap berjalan.
- [ ] Smoke test pass.
- [ ] Rollback docs tersedia.
- [ ] Secret tidak muncul di frontend/log.

---

## Future Phase 4 — Exact Signal Outbox / Trade Ticket / Controlled Write

**Estimasi:** 1–2 minggu per sub-scope  
**Status:** Deferred. Requires explicit user approval and readiness check.

Possible sub-phases:

- Phase 4A — Exact Telegram signal outbox.
- Phase 4B — Trade ticket calculator and optional save trade plan.
- Phase 4C — Controlled SL/TP write.

Exit Criteria minimum sebelum future write dimulai:

- [ ] Approval eksplisit scope write.
- [ ] Backup/rollback tested.
- [ ] Admin auth dipilih dan diuji.
- [ ] Audit log design selesai.
- [ ] Table baru hanya `dashboard_*`, tidak mengubah table bot existing.
- [ ] Bot tetap berjalan jika table dashboard tidak ada.

---

## Future Phase 5 — Dangerous Controls

**Estimasi:** 1–2 minggu  
**Status:** Optional, requires explicit user approval.

Fitur:

- DRY RUN trade intent dari website.
- Toggle Dry Run/Real Trading.
- Start/Stop Hunter.
- Emergency stop.

Exit Criteria:

- [ ] Confirmation phrase.
- [ ] Re-auth.
- [ ] Audit log.
- [ ] Idempotency key untuk action order/trade intent.
- [ ] Cooldown.
- [ ] Bot-side safety validation.
- [ ] Rollback/emergency procedure.
- [ ] Real trading tetap disabled by default sampai flag dan approval aktif.

---

## Timeline Realistis

| Scope | Estimasi |
|---|---:|
| Read-only Backend API + Frontend + Deploy | 4–5 minggu |
| + exact outbox / trade ticket / controlled write | +1–2 minggu per sub-scope |
| + dangerous controls | +1–2 minggu |

Catatan: timeline memasukkan waktu untuk SQLite lock handling, SSE/fallback, auth, deploy, dan smoke testing.
