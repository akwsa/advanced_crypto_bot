# 08 — Execution Plan & Workflow

> File ini adalah rencana kerja Hermes/BMAD. Phase 0 audit dan bot heartbeat sudah dikerjakan; implementasi berikutnya dibatasi ke **Phase 1 read-only only** sesuai approval user 2026-05-21.

---

## Workflow Aman v1.3

```text
PHASE 0: Discovery + Small Safe Prereq
├── Audit DB runtime
├── Audit Redis runtime
├── Add bot heartbeat publisher
└── Update docs

PHASE 1: Human Review Gate
├── User approve MVP scope: DONE, Phase 1 read-only only
├── User choose auth model if public
└── User choose deploy target

PHASE 2: Architecture + PRD + UX Finalization via BMAD
├── Winston: architecture final for read-only Phase 1
├── John: stories/acceptance criteria final for Phase 1
└── Sally: UX final for read-only panels

PHASE 3: Read-only MVP Implementation
├── Amelia: backend REST + SSE read-only
├── Alex: frontend read-only dashboard
└── Peter: tests/deploy

FUTURE PHASE 4: Optional Outbox / Trade Ticket / Controlled Write
└── Only after separate approval

FUTURE PHASE 5: Optional Dangerous Controls
└── Only after explicit approval
```

---

## Skill/Agent Selection

Gunakan skill yang tersedia:

| Workstream | Skill |
|---|---|
| Project safety/TDD | `advanced-crypto-bot-development`, `test-driven-development` |
| BMAD help/routing | `bmad-help` |
| Architecture | `bmad-agent-architect`, `bmad-create-architecture` |
| PRD/product | `bmad-agent-pm`, `bmad-create-prd` |
| UX | `bmad-agent-ux-designer`, `bmad-create-ux-design` |
| Development | `bmad-quick-dev`, `bmad-dev-story` |
| Readiness check | `bmad-check-implementation-readiness` |
| Review | `bmad-code-review`, `bmad-review-edge-case-hunter` |

Provider/model dipilih dari konfigurasi Hermes runtime saat eksekusi; jangan mengunci rencana pada model name yang mungkin berubah.

---

## Prompt Draft — Discovery Agent

Status: sebagian besar sudah dikerjakan. Gunakan ulang untuk validasi produksi.

```text
Audit codebase Advanced Crypto Bot untuk persiapan dashboard web.

Tasks:
1. Inspect SQLite DB paths: data/trading.db, core/trading.db, data/signals.db.
2. Identify runtime DB path from bot process cwd, env DATABASE_PATH, and Config.DATABASE_PATH.
3. Document schemas, tables, columns, row counts, and freshness.
4. Inspect Redis key patterns using SCAN, not KEYS * for large production.
5. Decide source of truth for active pairs, price history, trades, signals, positions.
6. Update docs/dashboard-web/09-current-codebase-audit.md.

Rules:
- Do not run destructive commands.
- Do not print secrets.
- Documentation only unless explicitly approved.
```

---

## Prompt Draft — Winston Architect

```text
Create final architecture for read-only BotPy Web Dashboard.

Context:
- Existing bot.py remains orchestrator.
- Dashboard API is FastAPI separate process.
- Frontend is React served by Nginx.
- Phase 1 read-only uses REST + SSE, not Socket.IO/WebSocket.
- Bot heartbeat key exists: dashboard:bot:heartbeat TTL 30s.
- Runtime DB: data/trading.db; signal DB: data/signals.db.
- Redis keys: price:*, state:historical:*, dashboard:bot:heartbeat.
- Approved Phase 1 endpoints: health, data-sources, active pairs, pair chart, latest signals, trade history, open positions, SSE stream.
- Future write/trading features are deferred: outbox write, trade ticket save, SL/TP write, DRY RUN trade intents, real trading, hunter controls, emergency stop.

Deliver:
1. architecture-dashboard.md
2. OpenAPI YAML for Phase 1 endpoints
3. SSE event contract
4. Redis/DB data contract
5. SQLite retry/backoff/cache strategy
6. Security model for read-only/public access
7. Deployment diagram
```

---

## Prompt Draft — John PM

```text
Create final PRD for BotPy Web Dashboard.

Focus:
- Phase 1 read-only MVP limited to approved panels:
  1. health/heartbeat,
  2. active pairs + chart,
  3. latest signals,
  4. trades/open positions,
  5. SSE stream.
- Do not include outbox write, trade ticket persistence, SL/TP write, DRY RUN trade intents, real trading, hunter controls, or emergency stop in Phase 1.
- Acceptance criteria must use BDD and include stale/offline/error/unknown states.
- Human approval gates should mark Phase 1 read-only approved and write/trading features deferred.

Deliver:
1. PRD-dashboard-web.md
2. prioritization-matrix.md
3. launch-readiness-checklist.md
```

---

## Prompt Draft — Sally UX

```text
Design UX for crypto trading dashboard.

Requirements:
- Dark trading terminal theme.
- MVP pages/panels: Health, Active Pairs/Chart, Latest Signals, Trades/Open Positions.
- Fresh/stale/offline/empty/error/unknown states.
- Mobile responsive.
- Phase 1 UI is read-only: no Save Plan, no SL/TP write, no Simulate Trade, no Real Buy/Sell, no Start/Stop Hunter, no Emergency Stop.
- Future trading controls can be documented as deferred risk states only.

Deliver:
1. ux-specs.md
2. wireframe-desktop.md
3. wireframe-mobile.md
4. design-system.md
5. interaction-specs.md
```

---

## Prompt Draft — Amelia Backend

```text
Implement read-only FastAPI dashboard API.

Rules:
- Do not modify bot.py unless explicitly approved.
- Do not write to existing bot tables.
- Do not create write endpoints in Phase 1.
- Use DB/Redis contract from audit.
- Use SSE for Phase 1 realtime.
- Return freshness metadata.
- Gracefully handle missing Redis keys and DB lock.
- Apply Redis down and SQLite locked fallback strategy from docs.

Approved endpoints:
- GET /api/v1/health
- GET /api/v1/system/data-sources
- GET /api/v1/pairs/active
- GET /api/v1/pairs/{pair}/chart
- GET /api/v1/signals/latest
- GET /api/v1/trades/history
- GET /api/v1/positions/open
- GET /api/v1/events/stream

Deliver:
- dashboard_api/ scaffold and code
- tests
- README-backend.md
```

---

## Prompt Draft — Alex Frontend

```text
Implement React read-only dashboard.

Rules:
- Use native EventSource for SSE, not socket.io-client.
- Do not embed admin API keys in frontend.
- Show stale/offline/empty/error/unknown states.
- Build goal-oriented panels, not hard-coded file names:
  - health/heartbeat panel,
  - active pairs panel with mini candlestick/chart,
  - latest signals panel,
  - trades/open positions panel.
- Do not show Phase 1 write/trading controls.

Deliver:
- dashboard_frontend/ scaffold and code
- README-frontend.md
```

---

## Prompt Draft — Peter QA/DevOps

```text
Create QA and deployment setup for read-only dashboard.

Tasks:
- pytest plan
- Playwright smoke tests
- Docker Compose, PM2, or systemd strategy recommendation
- Nginx config for /api and /api/v1/events/stream SSE
- SSL checklist
- rollback checklist
- bot heartbeat expiry test
- no-write-endpoints check for Phase 1

Do not configure dangerous controls.
```

---

## Guardrails

Hermes/BMAD Agent tidak boleh:

- Mengaktifkan Real Trading.
- Menaruh admin API key di frontend.
- Menghapus/mengubah table existing bot.
- Menjalankan migration production tanpa backup dan approval.
- Membuat write endpoint pada Phase 1.
- Menambah outbox/trade ticket/SLTP/trade intent persistence pada Phase 1.
- Menggunakan Socket.IO pada Phase 1.
- Menggunakan WebSocket pada Phase 1 kecuali arsitektur direvisi ulang.
- Membuat prompt implementasi yang terlalu prescriptive pada nama file; tulis goal dan acceptance criteria.

---

## Pre-Execution Checklist Dashboard Utama

- [x] DB audit final awal.
- [x] Redis audit final awal.
- [x] Bot heartbeat tersedia.
- [x] User approve Phase 1 read-only only.
- [ ] Auth model dipilih jika dashboard public.
- [ ] Deployment target dipilih.
- [ ] Branch kerja dibuat.
- [ ] Backup DB tersedia sebelum migration apa pun.
- [ ] OpenAPI Phase 1 sudah aligned.
- [ ] No write/trading scope in Sprint 1 docs.
