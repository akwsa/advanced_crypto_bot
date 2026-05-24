---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
includedDocuments:
  prdCandidates:
    - docs/dashboard-web/01-executive-summary.md
    - docs/dashboard-web/10-trading-cockpit-design.md
  architecture:
    - docs/dashboard-web/02-system-architecture.md
    - docs/dashboard-web/07-integration-points.md
    - docs/dashboard-web/architecture/data-source-contract.md
    - docs/dashboard-web/api-contract/openapi-phase1-draft.yaml
  epics:
    - docs/dashboard-web/04-epics-and-stories.md
  uxCandidates:
    - docs/dashboard-web/10-trading-cockpit-design.md
  security:
    - docs/dashboard-web/security/auth-and-secrets.md
    - docs/dashboard-web/planning/approval-gates.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-05-21  
**Project:** Advanced Crypto Bot — Dashboard Web / Trading Cockpit  
**Assessor:** Hermes Agent using `bmad-check-implementation-readiness` workflow  
**Scope assessed:** Dashboard-web planning docs, including new Trading Cockpit design.

---

## Step 1 — Document Discovery

### PRD Files Found

**Whole Documents:**
- Tidak ditemukan file dengan pola `*prd*.md`.

**Sharded Documents:**
- Tidak ditemukan folder/file dengan pola `*prd*/index.md`.

**Candidate PRD Content:**
- `01-executive-summary.md` — ringkasan visi, scope Phase 1/1.5/2, success criteria, risiko.
- `10-trading-cockpit-design.md` — product scope bertahap, roadmap cockpit, API draft, DB draft, UX, safety model.

### Architecture Files Found

**Whole Documents:**
- `02-system-architecture.md` — 10855 bytes — modified 2026-05-21T12:43:40.
- Supporting architecture/contract docs:
  - `07-integration-points.md`
  - `architecture/data-source-contract.md`
  - `api-contract/openapi-phase1-draft.yaml`

**Sharded Documents:**
- Tidak ditemukan folder/file dengan pola `*architecture*/index.md`.

### Epics & Stories Files Found

**Whole Documents:**
- `04-epics-and-stories.md` — 7612 bytes — modified 2026-05-21T12:44:44.

**Sharded Documents:**
- Tidak ditemukan folder/file dengan pola `*epic*/index.md`.

### UX Design Files Found

**Whole Documents:**
- Tidak ditemukan file eksplisit dengan pola `*ux*.md`.

**Sharded Documents:**
- Tidak ditemukan folder/file dengan pola `*ux*/index.md`.

**Candidate UX Content:**
- `10-trading-cockpit-design.md` section 5 — layout desktop/mobile, design language, signal row, signal detail, trade ticket UX, state real-trading danger banner.

### Issues Found in Discovery

#### Warning — PRD filename tidak eksplisit
Tidak ada file eksplisit bernama PRD. Assessment ini memakai gabungan `01-executive-summary.md` dan `10-trading-cockpit-design.md` sebagai PRD candidate. Untuk readiness yang lebih kuat, buat/rename satu dokumen PRD eksplisit atau tambahkan section “PRD Source of Truth” di README.

#### Warning — UX filename tidak eksplisit
Tidak ada file eksplisit bernama UX. Assessment memakai section UX di `10-trading-cockpit-design.md`, tetapi implementasi frontend akan lebih aman jika ada dokumen UX/wireframe dedicated.

#### No duplicate critical issue
Tidak ditemukan konflik whole-vs-sharded untuk PRD, Architecture, Epics, atau UX.

---

## Step 2 — PRD Analysis

### Functional Requirements Extracted

FR1: Dashboard harus menjadi companion service; tidak mengganti `bot.py`, dan `bot.py` tetap orchestrator utama untuk Telegram, signal pipeline, hunter, dan trading executor.

FR2: Phase 1 harus read-only terhadap existing bot tables/runtime state.

FR3: Dashboard harus menampilkan bot/system health: API health, bot heartbeat Redis `dashboard:bot:heartbeat`, DB status, Redis status, dan data freshness.

FR4: Bot heartbeat harus tampil online ketika Redis key fresh dan offline/unknown ketika key expired/hilang atau Redis down.

FR5: Dashboard harus menampilkan pair aktif/watchlist dari `data/trading.db.watchlist`.

FR6: Dashboard harus menampilkan mini candlestick/chart dari `data/trading.db.price_history`.

FR7: Dashboard harus menampilkan latest signals, dengan primary source awal `data/signals.db.signals`.

FR8: Signal feed harus mendukung filter minimal pair, recommendation/direction, confidence/strength/source jika tersedia.

FR9: Dashboard harus menampilkan trades/open positions read-only dari `data/trading.db.trades` dan/atau Redis `state:position:*` dengan fallback aman.

FR10: REST API Phase 1 harus menyediakan endpoint health, data sources, active pairs, chart, latest signals, trade history, open positions, dan event stream.

FR11: API response harus memakai wrapper konsisten berisi `success`, `data`, dan `meta` dengan source/freshness/last_updated.

FR12: Realtime Phase 1 harus memakai SSE/native `EventSource`, bukan Socket.IO/WebSocket-first.

FR13: SSE harus mengirim event minimal heartbeat, price update, signal update, dan trade update jika data berubah.

FR14: Jika SSE gagal, frontend harus fallback ke polling REST.

FR15: Dashboard API harus membaca SQLite dengan read-only strategy, `busy_timeout`, retry/backoff, dan cache fallback untuk locked DB.

FR16: Jika SQLite locked dan cache tersedia, API boleh return cached response dengan metadata; jika tidak ada cache, return `SQLITE_LOCKED` dan retry hint.

FR17: Jika Redis down, API tetap hidup; price fallback ke Indodax public API, positions fallback ke SQLite open trades, status tampil unknown/offline.

FR18: Indodax public fallback harus punya timeout dan rate limit.

FR19: Semua panel harus menampilkan freshness state: fresh, stale, offline, empty, unknown, atau error.

FR20: Jika dashboard public, akses harus dilindungi auth; admin secret/API key tidak boleh masuk frontend bundle.

FR21: Phase 1.5 write hanya boleh ke table `dashboard_*` baru, dengan auth/admin-only, audit log, migration, backup, dan rollback.

FR22: Controlled SL/TP management harus menulis ke dashboard table baru dan bot-side reader harus eksplisit serta aman jika table tidak ada.

FR23: Trading Cockpit harus menampilkan signal Telegram di website, idealnya dengan exact Telegram outbox `dashboard_signal_outbox`.

FR24: Trading Cockpit harus menyediakan signal detail dengan Telegram-like preview, indikator, final gate/source, copy signal, mark reviewed, open/save plan actions.

FR25: Phase 1.5 Trading Cockpit harus menyediakan trade ticket calculator: pair, side, entry, amount IDR, estimated coin amount, SL, TP, fee/slippage, expected P/L, risk/reward.

FR26: Trade plans harus dapat disimpan ke table dashboard baru, tanpa execute order.

FR27: Phase 2 DRY RUN trading via website harus melalui backend trade intents, status confirmation, audit log, idempotency key, dan feature flag.

FR28: Phase 3 real trading via website harus disabled by default dan hanya aktif setelah approval eksplisit, auth kuat, admin role, two-step/typed confirmation, limits, emergency disable, audit, dan idempotency.

FR29: Frontend UX harus menyediakan top health bar, signal feed, chart + signal marker, signal detail, Telegram-like preview, trade ticket, mobile tabs, dan real-trading danger banner.

FR30: Deployment harus memakai Nginx for static frontend + proxy `/api` and `/events`, SSL jika public, dan process manager dipilih eksplisit sebelum deploy.

FR31: Dashboard implementation harus tidak mengimpor `bot.py` dari Dashboard API.

FR32: Dashboard failure tidak boleh mematikan `bot.py` atau mengganggu trading runtime.

**Total FRs:** 32

### Non-Functional Requirements Extracted

NFR1: Dashboard initial load target Phase 1 < 3 detik pada VPS normal.

NFR2: API p95 read response target < 300 ms untuk query cached/simple.

NFR3: SSE latency target < 1 detik server-to-browser untuk event cached.

NFR4: Bot offline detection harus terlihat ≤ 30–45 detik setelah heartbeat expired.

NFR5: Dashboard harus fail-safe: error dashboard tidak mematikan `bot.py`.

NFR6: Phase 1 tidak boleh write ke existing bot tables.

NFR7: Secret/token/API key tidak boleh terekspos ke frontend, log, commit, atau dokumentasi.

NFR8: Frontend `.env` hanya boleh berisi public values seperti API base URL, bukan admin/trading secrets.

NFR9: Public dashboard harus memakai HTTPS valid.

NFR10: CORS harus whitelist domain dashboard.

NFR11: Rate limiting harus diterapkan untuk auth/write/public fallback endpoints.

NFR12: SQLite access harus menghindari long locks dan memakai retry bounded.

NFR13: Redis key scan di produksi harus memakai prefix/scan pattern, bukan `KEYS *` untuk produksi besar.

NFR14: Missing optional publishers seperti Telegram/Hunter status harus tampil `unknown`, bukan error palsu.

NFR15: Audit log untuk write actions harus append-only dan mencatat actor, action, entity, old/new value, IP/user-agent, timestamp.

NFR16: Real trading mode harus punya persistent danger banner dan confirmation phrase.

NFR17: Telegram chat id tidak perlu disimpan raw; gunakan hash/masked value bila outbox menyimpan metadata Telegram.

NFR18: API dan UI harus menampilkan stale/empty/offline states secara eksplisit, bukan silent failure.

**Total NFRs:** 18

### Additional Requirements / Constraints

- Default trading mode tetap DRY RUN; real trading tidak boleh diaktifkan tanpa approval eksplisit.
- Existing `MAX_DRAWDOWN_PCT = 0.10` tidak terkait dashboard dan tidak boleh diubah.
- Bot runtime audit menyatakan current bot berjalan manual `python bot.py`; deployment dashboard tidak boleh mengasumsikan PM2/systemd/docker sebelum dipilih.
- Source of truth signal saat audit adalah `data/signals.db.signals`; `data/trading.db.signals` ada tetapi kosong saat audit.
- Realtime harus konsisten: Phase 1 SSE-first; WebSocket baru jika benar-benar perlu two-way Phase 1.5+.

### PRD Completeness Assessment

PRD content cukup kuat untuk Phase 1 read-only backend/API discovery, tetapi belum siap langsung untuk implementasi penuh Trading Cockpit karena scope baru di `10-trading-cockpit-design.md` belum disejajarkan dengan `04-epics-and-stories.md`, OpenAPI draft, dan approval gates. Dokumen PRD/UX juga belum eksplisit sebagai source-of-truth file.

---

## Step 3 — Epic Coverage Validation

### Coverage Matrix

| FR | Requirement Summary | Epic Coverage | Status |
|---|---|---|---|
| FR1 | Dashboard companion; `bot.py` tetap orchestrator | Epic 0, Architecture docs | Covered |
| FR2 | Phase 1 read-only | Epic 1, Gate 2 | Covered |
| FR3 | Health panel with heartbeat/DB/Redis/freshness | US-1.1, US-6.2 | Covered |
| FR4 | Heartbeat online/offline behavior | US-1.1, US-6.2 | Covered |
| FR5 | Active pairs from watchlist | US-1.2 | Covered |
| FR6 | Candlestick/chart from price_history | US-1.2, US-3.2 | Covered |
| FR7 | Latest signals from signals.db | US-1.3 | Covered |
| FR8 | Signal filters | US-1.3 | Partially covered; confidence/source filtering stronger in `10` than epics |
| FR9 | Trades/open positions read-only | US-1.4 | Covered |
| FR10 | Phase 1 REST endpoints | US-1.1–1.4, US-6.2 | Partially covered; OpenAPI missing some endpoints |
| FR11 | Standard response wrapper/meta | Architecture; not explicit in stories | Partial |
| FR12 | SSE/native EventSource, no Socket.IO | US-2.1 | Covered |
| FR13 | SSE event types | US-2.1 | Covered |
| FR14 | SSE fallback polling | US-2.1 | Covered |
| FR15 | SQLite read-only/retry/cache | US-2.2; Architecture | Covered |
| FR16 | SQLITE_LOCKED cached/error response | US-2.2; Architecture | Covered |
| FR17 | Redis down fallback | US-2.2 | Covered |
| FR18 | Indodax timeout/rate limit | US-2.2, US-3.1 | Covered |
| FR19 | Freshness states all panels | US-1.1–1.4, Architecture | Covered |
| FR20 | Auth/no frontend secret if public | US-5.1, Security doc | Covered |
| FR21 | Phase 1.5 writes only dashboard_* with audit/migration | Epic 4, US-5.2 | Covered for SL/TP, not for new trade plans/outbox |
| FR22 | SL/TP bot-side reader safe fallback | US-4.3 | Covered |
| FR23 | Exact Telegram signal outbox | Not in `04-epics-and-stories.md` | Missing |
| FR24 | Signal detail + Telegram preview/actions | Partially in `10`; not in epics | Missing/Partial |
| FR25 | Trade ticket calculator | Not in `04-epics-and-stories.md` | Missing |
| FR26 | Save trade plans | Not in `04-epics-and-stories.md` | Missing |
| FR27 | DRY RUN trade intents with idempotency/audit | Not in `04-epics-and-stories.md`; dangerous controls generic only | Missing |
| FR28 | Real trading gated disabled default | Epic 7 generic; `10` stronger | Partial |
| FR29 | Full cockpit UX layout/mobile/ticket/banner | Not in epics as frontend stories | Missing/Partial |
| FR30 | Nginx/SSL/process manager | US-6.1 | Covered |
| FR31 | Dashboard API must not import bot.py | Architecture only | Partial; add AC |
| FR32 | Dashboard failure must not affect bot.py | Executive summary; not explicit AC except safety notes | Partial; add AC |

### Missing Requirements

#### Critical Missing FRs

FR23: Exact Telegram signal outbox `dashboard_signal_outbox` is not represented in the epics/stories file.
- Impact: new core cockpit promise “signal Telegram muncul juga di website” has no implementation path.
- Recommendation: add Epic/Story for Telegram signal outbox writer, DB migration, masked chat metadata, and dashboard preview.

FR25–FR26: Trade ticket calculator and saved trade plans are not represented in `04-epics-and-stories.md`.
- Impact: Phase 1.5 in `10-trading-cockpit-design.md` conflicts with older Phase 1.5 SL/TP scope; implementation agents will build different things depending on which doc they read.
- Recommendation: add a new Epic “Trade Ticket & Plans” or replace/merge old SL/TP Phase 1.5 into the Trading Cockpit roadmap.

FR27: DRY RUN trade intents with idempotency/audit/confirmation are not mapped to detailed stories.
- Impact: Phase 2 roadmap exists, but there is no implementable story set for safe write flow.
- Recommendation: add explicit stories for trade intent creation, confirmation, idempotency, feature flag rejection, dry-run executor boundary, and audit.

FR29: Frontend cockpit UX has no story coverage for specific UI panels/states.
- Impact: frontend agent may only build generic monitoring dashboard, not the Trading Cockpit described in `10`.
- Recommendation: add UX-driven stories for health top bar, signal feed, chart marker, signal detail, mobile tabs, trade ticket disabled/enabled states.

#### High Priority Partial Coverage

FR10/FR11: OpenAPI and architecture endpoint contracts are inconsistent/incomplete.
- `02-system-architecture.md` lists `/api/v1/events/stream` and `/api/v1/positions/open`.
- `openapi-phase1-draft.yaml` omits `/api/v1/events/stream` and `/api/v1/positions/open`.
- `10-trading-cockpit-design.md` uses non-versioned examples like `/api/signals/latest` and `/events/signals`.
- Recommendation: standardize all docs on `/api/v1/...` and `/api/v1/events/stream` or intentionally document separate event paths.

FR31/FR32: “Do not import bot.py” and “dashboard failure must not affect bot runtime” are architecture constraints but should become explicit AC in backend stories.

### Coverage Statistics

- Total PRD FRs: 32
- Covered: 21
- Partial: 6
- Missing: 5
- Effective readiness coverage: not enough for implementation without reconciling the missing/partial items.

---

## Step 4 — UX Alignment Assessment

### UX Document Status

No dedicated UX file was found. UX is embedded in `10-trading-cockpit-design.md`, especially section 5.

### UX ↔ PRD Alignment

Aligned areas:
- Desktop layout maps to Trading Cockpit PRD: health, signals, chart, ticket, details.
- Mobile tabs map to user need for compact access.
- Design language covers BUY/SELL/HOLD/stale/offline/real-trading danger states.
- Trade ticket fields align with Phase 1.5 calculator concept.

Gaps:
- No explicit empty/error/loading states per panel beyond freshness terms.
- No detailed user flow for selecting a signal → opening detail → opening ticket → saving plan.
- No wireframe for “real trading disabled” vs “DRY RUN enabled” vs “calculator-only” states.
- No accessibility/responsive breakpoints beyond a high-level mobile tab list.

### UX ↔ Architecture Alignment

Aligned areas:
- SSE/EventSource supports realtime signal feed and heartbeat top bar.
- REST endpoints support signal list/detail/chart/trades.
- Feature flags support disabled dangerous controls.

Gaps:
- Chart + signal marker requires an endpoint or join model for signal timestamps against OHLC candles; this is described in UX but not specified in OpenAPI.
- Signal detail wants Telegram preview; architecture still treats outbox as future and epics do not cover it.
- Trade ticket requires calculation service/schema; architecture has draft DB tables in `10` but no API contract/schema in OpenAPI.

### Warnings

UX is implied and important because this is a user-facing trading dashboard. The current embedded UX section is useful for direction but not sufficient for frontend execution without additional acceptance criteria and API alignment.

---

## Step 5 — Epic Quality Review

### Critical Violations

#### 1. Phase 1.5 scope conflict
`README.md`, `01-executive-summary.md`, and `04-epics-and-stories.md` describe Phase 1.5 mainly as controlled SL/TP management. The new `10-trading-cockpit-design.md` describes Phase 1.5 as exact Telegram outbox + trade ticket calculator + trade plans.

**Impact:** agents may implement the wrong Phase 1.5.  
**Recommendation:** choose one Phase 1.5 source of truth or split into:
- Phase 1.5A: Telegram outbox + exact signal preview.
- Phase 1.5B: Trade ticket calculator + saved plans.
- Phase 1.6 or later: SL/TP controlled write.

#### 2. New Trading Cockpit database/API tables not mapped to epics
`dashboard_signal_outbox`, `dashboard_trade_plans`, `dashboard_trade_intents`, and `dashboard_audit_log` are drafted in `10` but not all represented in stories.

**Impact:** DB schema can be created prematurely or inconsistently.  
**Recommendation:** each table should be created only in the story that first needs it, with migration and rollback AC.

#### 3. Approval gates are still unresolved
US-0.3 and approval gate files still require user decisions for scope, auth model, deployment target, and dangerous controls.

**Impact:** implementation can accidentally choose unsafe defaults.  
**Recommendation:** before coding dashboard scaffold, approve: Phase 1 read-only only; private/basic-auth vs session; local/VPS/Docker/systemd target; explicitly defer real trading.

### Major Issues

#### 1. Several epics are technical milestones, not user-value epics
Examples: “SSE Realtime & Fallbacks”, “Security, Auth & Audit”, “Deployment & Observability”. These are important, but BMAD best practice prefers user-value slices.

**Recommendation:** keep them as platform/enabler epics only if labeled as such, or fold AC into user-facing stories where possible.

#### 2. Acceptance criteria are checklists, not BDD scenarios
The AC are mostly testable but not Given/When/Then. This is workable for planning, but less precise for TDD implementation.

**Recommendation:** convert Sprint 1 stories into BDD style before coding, especially Redis down, SQLite locked, empty state, stale data, and SSE fallback.

#### 3. Story sizing too broad
US-1.2 includes active pairs, mini candlestick, latest candle, latest signal, freshness, search/sort/filter, SSE, and fallback polling.

**Recommendation:** split US-1.2 into backend active-pairs reader, chart endpoint, frontend card, and realtime/fallback behavior.

#### 4. OpenAPI draft includes Sprint 2 endpoints but omits Phase 1 endpoints
It includes `/api/v1/pairs/top-volume`, `/api/v1/hunters/status`, `/api/v1/telegram/status`, but omits `/api/v1/events/stream` and `/api/v1/positions/open`.

**Recommendation:** update OpenAPI to exactly match approved Phase 1, then separately mark Sprint 2 endpoints as future.

### Minor Concerns

- `architecture/data-source-contract.md` still says “probable runtime default” for data sources even though audit docs now resolved `data/trading.db` and `data/signals.db` as live sources.
- `dashboard:events` description in data-source contract says websocket manager, while architecture says SSE-first. Update wording to event stream/SSE or future pub/sub.
- `10-trading-cockpit-design.md` endpoint examples mix `/api/...` and `/events/...` without versioning. Standardize.

---

## Step 6 — Summary and Recommendations

### Approval Update — 2026-05-21

User approved **Phase 1 read-only only** with the following implementation scope:

- health,
- active pairs/chart,
- latest signals,
- trades/open positions,
- SSE stream.

This approval explicitly does **not** include Phase 1.5+ write/trading features. Deferred items remain: SL/TP write, exact signal outbox writes, trade ticket persistence, DRY RUN trade intents, real trading from website, hunter controls, and emergency stop.

### Overall Readiness Status

**NEEDS WORK before implementation of Trading Cockpit.**

The documents are strong enough to start a very small Phase 1 read-only API spike only if scope is explicitly constrained. They are **not yet ready** for broad Trading Cockpit implementation because the new cockpit scope is not fully propagated into epics, OpenAPI, approval gates, and UX implementation stories.

### Critical Issues Requiring Immediate Action

1. Resolve the Phase 1.5 scope conflict: SL/TP controlled write vs exact Telegram outbox + trade ticket calculator.
2. Update `04-epics-and-stories.md` to include the new cockpit requirements: signal outbox, signal detail/preview, trade ticket, trade plans, trade intents.
3. Update `api-contract/openapi-phase1-draft.yaml` to include `/api/v1/events/stream`, `/api/v1/positions/open`, and remove/mark future endpoints not in Phase 1.
4. Standardize endpoint naming/versioning across all docs.
5. Complete approval gates for scope, auth, deployment, and real-trading deferral before coding.

### Recommended Next Steps

1. **Approve Phase 1 scope as read-only only**: health, active pairs/chart, latest signals, trades/open positions, SSE stream. Keep trade ticket/outbox out until Phase 1 works.
2. **Patch docs for consistency**:
   - Update `04-epics-and-stories.md` with new Trading Cockpit stories.
   - Update OpenAPI Phase 1 draft to match architecture.
   - Update `architecture/data-source-contract.md` resolved statuses and SSE wording.
3. **Create a dedicated UX spec or story appendix** for Signal Mirror Read-only Cockpit before frontend coding.
4. **After doc alignment, start Sprint 1 with TDD** on backend readers/API: bot status + latest signals first, then chart/trades, then SSE.
5. **Keep all trading/write controls disabled** until a separate readiness pass covers trade intents, auth, audit, and idempotency.

### Final Note

This assessment found **5 critical/missing requirements**, **6 partial coverage items**, and multiple doc consistency issues. The safest continuation is documentation alignment first, then a narrow TDD implementation of read-only Sprint 1. Real trading remains disabled and out of implementation scope unless explicitly approved later.
