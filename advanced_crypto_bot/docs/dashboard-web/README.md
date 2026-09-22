# BOTPY WEB DASHBOARD — DOKUMENTASI PROYEK

> **Versi:** 1.3-phase1-readonly-aligned  
> **Tanggal:** 2026-05-21  
> **Status:** Phase 0 audit runtime selesai; Phase 1 read-only scope approved pada 2026-05-21 untuk health, active pairs/chart, latest signals, trades/open positions, dan SSE stream. Write/trading controls tetap deferred.

---

## Tujuan Dokumen

Dokumentasi ini adalah rancangan dashboard web untuk `bot.py` Advanced Crypto Trading Bot. Fokus revisi v1.3:

1. Memfinalkan audit awal DB/Redis/process runtime berdasarkan bot aktif.
2. Mengubah realtime Phase 1 dari WebSocket-first menjadi **SSE-first** untuk read-only feed.
3. Menambahkan **bot heartbeat Redis** agar dashboard tahu bot hidup/mati.
4. Menyelaraskan semua dokumen agar implementasi berikutnya hanya **Phase 1 read-only**.
5. Memindahkan outbox write, trade ticket, SL/TP write, DRY RUN trade intent, dan real trading ke future/deferred scope.
6. Menyesuaikan workflow dengan skill/agent BMAD dan Hermes yang benar-benar tersedia.

---

## Daftar Isi

1. [Executive Summary](01-executive-summary.md)
2. [Arsitektur Sistem](02-system-architecture.md)
3. [Hermes Agent Roster & AI API Keys](03-hermes-agent-roster.md)
4. [Epics & User Stories](04-epics-and-stories.md)
5. [Tech Stack](05-tech-stack.md)
6. [Implementation Roadmap](06-implementation-roadmap.md)
7. [Integration Points](07-integration-points.md)
8. [Execution Plan & Workflow](08-execution-plan.md)
9. [Current Codebase Audit](09-current-codebase-audit.md)
10. [Trading Cockpit Website Design](10-trading-cockpit-design.md)
11. [Approval Gates](planning/approval-gates.md)
12. [Data Source Contract](architecture/data-source-contract.md)
13. [Auth & Secrets Plan](security/auth-and-secrets.md)
14. [OpenAPI Phase 1 Draft](api-contract/openapi-phase1-draft.yaml)
15. [UX Specs Phase 1](ux-specs-phase1.md)
16. [Implementation Readiness Report](implementation-readiness-report-2026-05-21.md)
17. [Hermes Execution Cheatsheet](operations/hermes-execution-cheatsheet.md)
18. [Phase 1 Deploy & Runbook](operations/deploy-runbook-phase1.md)

---

## Ringkasan Proyek

Dashboard web adalah layer visualisasi read-only di atas `bot.py` untuk Phase 1. Dashboard tidak mengganti `bot.py`; bot tetap menjadi orchestrator utama untuk Telegram, analisis, hunter, dan trading logic.

### Prinsip Utama

- **Extend, don't replace** — dashboard berjalan paralel.
- **Bot-first safety** — dashboard tidak boleh menjatuhkan atau mengubah alur utama bot tanpa approval.
- **Read-only first** — MVP awal fokus monitoring.
- **SSE-first realtime** — Phase 1 memakai Server-Sent Events untuk push read-only; WebSocket/Socket.IO deferred jika benar-benar butuh two-way pada future phase.
- **Dangerous controls gated** — Real Trading toggle, Start/Stop Hunter, dan eksekusi trade langsung tidak masuk MVP awal.
- **Future write separated** — outbox write, trade ticket persistence, SL/TP write, dan trade intents tidak masuk Phase 1.
- **Audit before build** — schema SQLite dan Redis keys harus berdasarkan runtime aktual.

---

## MVP yang Direkomendasikan

### Phase 1 — Safe Read-only Dashboard MVP

MVP approved berisi 4 panel utama + SSE:

1. Bot/system health: API health, bot heartbeat, DB/Redis freshness.
2. Active pairs + mini candlestick/chart.
3. Latest signals.
4. Trades/open positions read-only.
5. SSE stream untuk update read-only.

Tidak termasuk Phase 1:

- Toggle Real Trading.
- Start/Stop SmartHunter.
- Execute buy/sell dari dashboard.
- Menulis ke tabel existing bot.
- Menulis ke table `dashboard_*` baru.
- Exact Telegram outbox persistence.
- Trade ticket/save plan.
- SL/TP write.
- DRY RUN trade intents.

### Future Phase 1.5+ — Deferred Write / Two-way Features

Future sub-scope yang butuh approval terpisah:

- Exact Telegram signal outbox.
- Trade ticket calculator + save plan.
- SL/TP config write ke table `dashboard_*` baru.
- Admin auth untuk write.
- Audit log.
- Bot-side reader yang eksplisit membaca future dashboard table.
- WebSocket boleh dipertimbangkan jika ada two-way communication.

### Future Phase 2/3 — Dangerous Controls

Fitur opsional setelah safety matang:

- DRY RUN trade intent dari website.
- Dry Run ↔ Real Trading toggle.
- Start/Stop Hunter.
- Emergency stop.
- Role-based access.
- Confirmation phrase dan audit trail penuh.

---

## Approval Gate

Sebelum Hermes Agent mengeksekusi implementasi dashboard utama, status approval adalah:

- Final scope MVP. **Approved 2026-05-21: Phase 1 read-only only — health, active pairs/chart, latest signals, trades/open positions, SSE stream.**
- Auth model. **Pending jika dashboard public.**
- Deployment target VPS/domain. **Pending.**
- Future write/trading features. **Deferred; perlu approval terpisah.**
- Dangerous controls. **Deferred; perlu approval eksplisit.**

Catatan: bot heartbeat sudah ditambahkan sebagai perubahan kecil best-effort karena aman, read-only, dan dibutuhkan untuk observability dashboard.
