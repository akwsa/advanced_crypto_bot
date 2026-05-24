# 10 — Trading Cockpit Website Dashboard Design

> **Versi:** 1.1-long-term-design-phase1-readonly-aligned  
> **Tanggal:** 2026-05-21  
> **Status:** Rancangan long-term produk + arsitektur + UX. Belum implementasi.  
> **Scope saat ini:** Implementasi berikutnya hanya **Phase 1 read-only**: health, active pairs/chart, latest signals, trades/open positions, dan SSE stream. Fitur trade ticket, outbox write, DRY RUN trading, dan real trading adalah **future/deferred** sampai ada approval terpisah.

---

## 1. Executive Decision

Target baru dashboard bukan hanya monitoring, tetapi **Trading Cockpit**:

- Signal yang muncul di Telegram juga muncul di website.
- User bisa membaca signal, membuka chart, mengecek indikator, dan membuat rencana trade dari satu halaman.
- Website dapat berkembang dari read-only cockpit → trade ticket → DRY RUN trading → real trading gated.

Keputusan arsitektur utama:

1. `bot.py` tetap orchestrator utama.
2. Frontend tidak pernah menyimpan API key/token trading.
3. Phase 1 tetap aman: read-only + SSE, tanpa write endpoint.
4. Signal Telegram exact outbox adalah future enhancement, bukan scope Phase 1.
5. Trading via website wajib lewat backend dan audit log, bukan direct dari browser ke Indodax, dan bukan scope Phase 1.
6. Real trading web **disabled by default** sampai ada explicit approval dan feature flag.

---

## 2. Skill, BMAD, dan Agent yang Dipakai

### 2.1 Skill Hermes/BMAD

| Area | Skill | Kenapa Dipakai |
|---|---|---|
| Project safety | `advanced-crypto-bot-development` | Menjaga DRY RUN default, larangan ubah path trading tanpa approval, test wrapper project. |
| TDD | `test-driven-development` | Semua perubahan bot/backend dashboard harus RED → GREEN. |
| Architecture | `bmad-agent-architect`, `bmad-create-architecture` | Menentukan boundary bot/API/frontend, SSE, outbox, trade-intent, deployment. |
| Product/PRD | `bmad-agent-pm`, `bmad-create-prd` | Memecah scope cockpit menjadi fase aman dan acceptance criteria. |
| UX | `bmad-agent-ux-designer`, `bmad-create-ux-design` | Mendesain cockpit, signal detail, trade ticket, risk confirmation, mobile. |
| Dev execution | `bmad-quick-dev`, `bmad-dev-story` | Implementasi backend/frontend per story setelah approval. |
| Readiness | `bmad-check-implementation-readiness` | Validasi PRD/UX/architecture sebelum coding besar. |
| Review | `bmad-code-review`, `bmad-review-edge-case-hunter` | Review security, race condition, double order, stale signal, locked DB. |

### 2.2 BMAD Agent Mapping

| Agent | Peran | Deliverable untuk Trading Cockpit |
|---|---|---|
| Winston / Architect | System design | `architecture-trading-cockpit.md`, API contract, event contract, DB schema, deployment diagram. |
| John / PM | Product scope | PRD, priority matrix, acceptance criteria, approval gates. |
| Sally / UX | UI/UX | Wireframe desktop/mobile, design system, risk confirmation states. |
| Amelia-style Backend Dev | Backend implementation | FastAPI API, SQLite/Redis readers, SSE, outbox, trade-intent endpoints. |
| Alex-style Frontend Dev | Frontend implementation | React cockpit UI, signal feed, chart, trade ticket, EventSource client. |
| Peter-style QA/DevOps | QA/deploy | pytest, Playwright smoke, deployment checklist, rollback. |

### 2.3 Agent Prompt Style

Prompt harus goal-oriented, bukan terlalu prescriptive pada nama file.

Contoh benar:

```text
Bangun panel signal feed realtime yang menampilkan signal terbaru dari source terverifikasi, mendukung filter pair/recommendation/confidence, stale state, dan membuka signal detail.
```

Bukan:

```text
Buat src/components/panels/SignalFeedPanel.tsx.
```

---

## 3. AI API Key / Token Compatibility Audit

Audit dilakukan terhadap konfigurasi lokal tanpa menampilkan nilai secret.

### 3.1 Hermes AI Provider Keys Terdeteksi

File:

```text
/home/officer/.hermes/.env
/home/officer/.hermes/config.yaml
```

Key/provider yang tersedia secara redacted:

| Provider/Key | Status | Rekomendasi Pemakaian |
|---|---|---|
| `TOKENROUTER_API_KEY` | tersedia | Provider utama Hermes saat audit. Cocok untuk orchestrator dan coding agent. |
| `SWIFTROUTER_API_KEY` | tersedia | Fallback provider. Cocok untuk review/backup agent. |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | tersedia | Cocok untuk reasoning, review UX/architecture, vision jika diperlukan. |
| `FREEMODEL_API_KEY` | tersedia | Alternatif/fallback. |
| `OPENROUTER_API_KEY` | tersedia | Bisa dipakai jika provider dikonfigurasi. |
| `GLM_API_KEY` | tersedia | Alternatif jika routing mendukung. |
| `OPENCODE_API_KEY` / `OPENCODE_GO_API_KEY` | tersedia | Bisa dipakai untuk coding agent jika toolchain dipilih. |

Konfigurasi Hermes saat audit:

```text
model.default = openai/gpt-5.5
model.provider = tokenrouter
fallback_providers = swiftrouter, gemini
custom providers = freemodel, tokenrouter, swiftrouter, gemini-pro
```

Implikasi:

- Rancangan ini bisa dieksekusi dengan Hermes/BMAD yang ada sekarang.
- Tidak perlu menambah AI API key baru untuk perencanaan dan implementasi awal.
- Dokumen tidak boleh mengunci ke satu model permanen; gunakan provider runtime Hermes.

### 3.2 Project Bot/Trading Tokens Terdeteksi

File:

```text
/home/officer/advanced_crypto_bot/advanced_crypto_bot/.env
```

Token/key redacted:

| Key | Status | Aturan Dashboard |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | tersedia | Backend/bot only. Jangan expose ke frontend. |
| `SCALPER_BOT_TOKEN` | tersedia | Backend/bot only. Jangan expose ke frontend. |
| `INDODAX_API_KEY` | tersedia | Backend only. Jangan expose ke frontend. |
| `INDODAX_SECRET_KEY` | tersedia | Backend only. Jangan expose ke frontend. |

Kesimpulan safety:

- Website boleh menampilkan data trading, tetapi tidak boleh membaca secret langsung.
- Semua aksi trading harus lewat backend yang melakukan validasi, feature flag, audit log, dan idempotency.
- Frontend `.env` hanya boleh berisi URL publik seperti `VITE_API_BASE_URL`, bukan token.

---

## 4. Product Scope: Trading Cockpit Bertahap

### Phase 1 — Approved Read-only Cockpit

Tujuan: website menampilkan data runtime bot secara read-only agar user bisa memantau kondisi bot, market, signal, trade, dan position tanpa mengubah state trading.

Fitur:

1. Bot/system health dari `dashboard:bot:heartbeat`.
2. Active pairs dari `data/trading.db.watchlist`.
3. Pair chart dari `data/trading.db.price_history`.
4. Latest price dari Redis `price:{pair}` dengan fallback Indodax public API.
5. Latest signals dari `data/signals.db.signals`.
6. Trades/open positions dari `data/trading.db.trades` dan Redis position state jika tersedia.
7. SSE realtime untuk heartbeat, price, signal, dan trade update read-only.
8. Filter basic untuk pair/recommendation/confidence/source jika aman dan sederhana.

Tidak ada write endpoint, tidak ada save plan, tidak ada eksekusi order.

### Future Phase 1.5 — Exact Telegram Signal Outbox + Trade Ticket Calculator

Tujuan: website menampilkan pesan Telegram persis dan user bisa membuat rencana trade.

Fitur:

1. Table `dashboard_signal_outbox` untuk menyimpan exact message yang dikirim ke Telegram.
2. Signal detail menampilkan `message_text` persis Telegram.
3. Trade ticket calculator:
   - pair,
   - side,
   - entry,
   - amount IDR,
   - estimated coin amount,
   - stop loss,
   - take profit,
   - fee/slippage,
   - expected profit/loss,
   - risk/reward.
4. Save trade plan ke table dashboard baru.

Belum execute order.

### Future Phase 2 — DRY RUN Trading via Website

Tujuan: user bisa melakukan paper trade/simulasi dari website.

Fitur:

1. `POST /api/trade-intents` membuat request trade status `PENDING_CONFIRMATION`.
2. `POST /api/trade-intents/{id}/confirm` untuk DRY RUN execution.
3. Audit log lengkap.
4. Idempotency key untuk mencegah double-click double-order.
5. Feature flag:

```text
DASHBOARD_DRY_RUN_TRADING_ENABLED=true
DASHBOARD_REAL_TRADING_ENABLED=false
```

### Future Phase 3 — Real Trading via Website, Gated

Tujuan: real buy/sell dari website hanya setelah sistem aman.

Wajib sebelum aktif:

- Auth kuat.
- Admin-only role.
- 2-step confirmation.
- Typed confirmation untuk order besar.
- Feature flag explicit:

```text
DASHBOARD_REAL_TRADING_ENABLED=true
```

- Max order amount.
- Max daily loss guard.
- Emergency disable.
- Audit log.
- Idempotency.
- Backend/bot executor boundary jelas.

---

## 5. Target UX Website

### 5.1 Layout Desktop

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Top Bar: Bot Online | Redis OK | DB Fresh | DRY RUN | User/Admin      │
├───────────────┬──────────────────────────────────────┬───────────────┤
│ Signal Feed   │ Chart + Pair Cards                    │ Trades/Status │
│ - latest      │ - candlestick                         │ - open pos    │
│ - filters     │ - current price                       │ - history     │
│ - badges      │ - freshness                           │ - health      │
│               │                                      │ - freshness   │
├───────────────┴──────────────────────────────────────┴───────────────┤
│ Signal Detail: fields from signals DB | Indicators | Analysis        │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 Layout Mobile

Mobile memakai tabs:

1. Health
2. Signals
3. Chart
4. Trades/Positions
5. History

### 5.3 Design Language

- Dark trading terminal.
- BUY: green.
- SELL: red.
- HOLD/WAIT: amber/gray.
- Stale data: yellow warning.
- Offline: red banner.
- Real trading mode: persistent danger banner.

### 5.4 Signal Feed Row

Contoh:

```text
12:41:03  BTCIDR  BUY  82%  1,020,000,000  final_gate_v2  Telegram Sent
```

Click membuka detail.

### 5.5 Signal Detail

Isi:

- Telegram message preview.
- Pair/recommendation/price/confidence.
- RSI/MACD/MA/Bollinger/volume.
- ML confidence dan combined strength.
- `final_gate_source`.
- `price_source`.
- Created/sent time.
- Tombol:
  - Copy Signal,
  - Mark Reviewed (future/local-only until persistence approved).

Phase 1 tidak memiliki tombol Open Trade Ticket atau Save Plan.

### 5.6 Future Trade Ticket UX — Deferred, Not Phase 1

Default future Phase 1.5: calculator only. Section ini dipertahankan sebagai desain long-term; tidak masuk implementasi Phase 1.

Fields:

- Pair auto-filled dari signal.
- Side auto-filled dari recommendation.
- Entry price auto-filled dari signal/latest price.
- Amount IDR.
- Stop loss % / price.
- Take profit % / price.
- Fee rate.
- Slippage.
- Expected loss/profit.
- Risk/reward ratio.

Buttons by phase:

| Phase | Button | Status |
|---|---|---|
| 1.5 | Save Plan | enabled |
| 2 | Simulate Trade | enabled jika DRY RUN flag true |
| 3 | Real Buy/Sell | disabled default; enabled hanya dengan explicit flag + admin |

---

## 6. Architecture Design

### 6.1 System Context

```text
┌─────────────────────┐       SQLite/Redis       ┌──────────────────────┐
│ bot.py              │ ───────────────────────▶ │ FastAPI Dashboard API │
│ - Telegram sender   │                           │ - REST               │
│ - Signal pipeline   │                           │ - SSE                │
│ - Heartbeat SETEX   │                           │ - Auth               │
│ - Trading executor  │     future only, gated    │ - Read-only API       │
└─────────────────────┘                           └──────────┬───────────┘
                                                              │ HTTPS/SSE
                                                              ▼
                                                   ┌──────────────────────┐
                                                   │ React Dashboard       │
                                                   │ - Signal feed         │
                                                   │ - Chart               │
                                                   │ - Trades/status       │
                                                   └──────────────────────┘
```

### 6.2 Runtime Data Sources

| Domain | Primary Source | Fallback |
|---|---|---|
| Bot alive | Redis `dashboard:bot:heartbeat` | unknown/offline |
| Signal feed | `data/signals.db.signals` | `dashboard_signal_outbox` once available, or cached response |
| Exact Telegram message | `dashboard_signal_outbox.message_text` | frontend formatter from `signals.db` fields |
| Latest price | Redis `price:{pair}` | Indodax public API |
| Chart | `data/trading.db.price_history` | Indodax public OHLC if implemented |
| Watchlist | `data/trading.db.watchlist` | config fallback after audit |
| Positions | Redis `state:position:*` | SQLite `trades WHERE status='open'` |
| Trade plans | `dashboard_trade_plans` | future only; not Phase 1 |
| Trade intents | `dashboard_trade_intents` | future only; not Phase 1 |
| Audit | `dashboard_audit_log` | future write phases; not Phase 1 required unless auth/write added later |

### 6.3 Realtime Strategy

Phase 1 uses SSE:

```text
GET /api/v1/events/stream
```

Event examples:

```json
{
  "type": "signal.created",
  "data": {
    "id": 34630,
    "pair": "btcidr",
    "recommendation": "BUY",
    "price": 1020000000,
    "confidence": 0.82,
    "source": "signals_db"
  }
}
```

```json
{
  "type": "bot.heartbeat",
  "data": {
    "status": "online",
    "timestamp": 1779341810,
    "ttl": 24
  }
}
```

WebSocket baru dipertimbangkan jika Phase 2/3 butuh two-way interactive trading stream.

---

## 7. Database Design Draft

> **Future schema note:** Semua table pada section 7 adalah draft future. Tidak dibuat pada Phase 1 read-only.

### 7.1 `dashboard_signal_outbox` — Future Only

Tujuan: menyimpan exact signal message yang dikirim bot ke Telegram agar website bisa mirror persis.

```sql
CREATE TABLE IF NOT EXISTS dashboard_signal_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    pair TEXT NOT NULL,
    recommendation TEXT,
    price REAL,
    confidence REAL,
    message_text TEXT NOT NULL,
    message_format TEXT DEFAULT 'telegram_markdown',
    telegram_sent INTEGER DEFAULT 0,
    telegram_chat_id_hash TEXT,
    telegram_message_id TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP
);
```

Catatan:

- Jangan simpan raw private chat id jika tidak perlu; gunakan hash/masked value.
- `message_text` tidak boleh mengandung API key/token.
- Bot update row setelah Telegram send sukses jika message id tersedia.

### 7.2 `dashboard_trade_plans` — Future Only

```sql
CREATE TABLE IF NOT EXISTS dashboard_trade_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_outbox_id INTEGER,
    signal_id INTEGER,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    amount_idr REAL NOT NULL,
    estimated_asset_amount REAL,
    stop_loss_pct REAL,
    stop_loss_price REAL,
    take_profit_pct REAL,
    take_profit_price REAL,
    fee_rate REAL DEFAULT 0,
    slippage_pct REAL DEFAULT 0,
    expected_loss_idr REAL,
    expected_profit_idr REAL,
    risk_reward_ratio REAL,
    status TEXT DEFAULT 'DRAFT',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.3 `dashboard_trade_intents` — Future Only

```sql
CREATE TABLE IF NOT EXISTS dashboard_trade_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    trade_plan_id INTEGER,
    signal_id INTEGER,
    pair TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT DEFAULT 'MARKET',
    amount_idr REAL NOT NULL,
    requested_price REAL,
    mode TEXT NOT NULL DEFAULT 'DRY_RUN',
    status TEXT NOT NULL DEFAULT 'PENDING_CONFIRMATION',
    risk_snapshot_json TEXT,
    validation_errors_json TEXT,
    created_by TEXT,
    confirmed_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP,
    executed_at TIMESTAMP,
    result_json TEXT
);
```

Allowed statuses:

```text
PENDING_CONFIRMATION
VALIDATION_FAILED
CONFIRMED
EXECUTED_DRY_RUN
EXECUTED_REAL
REJECTED
CANCELLED
FAILED
```

### 7.4 `dashboard_audit_log` — Future Only

```sql
CREATE TABLE IF NOT EXISTS dashboard_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. API Design Draft

> **Phase 1 API note:** Canonical Phase 1 endpoints are defined in `api-contract/openapi-phase1-draft.yaml`. Endpoints below are aligned to that contract. POST/PUT/PATCH/DELETE routes are future-only.

### 8.1 Health

```text
GET /api/v1/health
GET /api/v1/system/data-sources
```

Response bot status:

```json
{
  "success": true,
  "data": {
    "bot_status": "online",
    "heartbeat_age_seconds": 8,
    "redis_status": "ok",
    "db_status": "ok",
    "mode": "DRY_RUN"
  }
}
```

### 8.2 Signals

```text
GET /api/v1/signals/latest?limit=50&pair=btcidr&recommendation=BUY&min_confidence=0.7
```

Response signal item:

```json
{
  "id": 34630,
  "pair": "btcidr",
  "recommendation": "BUY",
  "price": 1020000000,
  "ml_confidence": 0.82,
  "combined_strength": 0.76,
  "analysis": "...",
  "telegram_message_text": null,
  "telegram_sent": null,
  "signal_time": "2026-05-21T12:41:03Z",
  "source": "signals_db"
}
```

### 8.3 Charts and Prices

```text
GET /api/v1/pairs/active
GET /api/v1/pairs/{pair}/chart?timeframe=1h&limit=200
GET /api/v1/trades/history?limit=100&status=open|closed|all
GET /api/v1/positions/open
GET /api/v1/events/stream
```

### 8.4 Trade Plans

Future Phase 1.5 only:

```text
POST /api/trade-plans
GET /api/trade-plans?status=DRAFT
GET /api/trade-plans/{id}
PATCH /api/trade-plans/{id}
```

### 8.5 Trade Intents

Future Phase 2+ only:

```text
POST /api/trade-intents
POST /api/trade-intents/{id}/confirm
POST /api/trade-intents/{id}/cancel
GET /api/trade-intents/{id}
```

Rules:

- Required `Idempotency-Key` header.
- Backend validates feature flags.
- Real mode blocked unless `DASHBOARD_REAL_TRADING_ENABLED=true`.
- All write endpoints require auth and audit.

---

## 9. Security and Safety Model

### 9.1 Secret Handling

- Never expose `TELEGRAM_BOT_TOKEN`, `SCALPER_BOT_TOKEN`, `INDODAX_API_KEY`, `INDODAX_SECRET_KEY` to browser.
- Browser receives only data needed for display.
- Backend environment owns secrets.
- Logs must redact keys and tokens.

### 9.2 Feature Flags

```text
DASHBOARD_ENABLED=true
DASHBOARD_SIGNAL_OUTBOX_ENABLED=false
DASHBOARD_TRADE_TICKET_ENABLED=false
DASHBOARD_DRY_RUN_TRADING_ENABLED=false
DASHBOARD_REAL_TRADING_ENABLED=false
DASHBOARD_REQUIRE_ADMIN_CONFIRMATION=true
```

Default safe values:

- read-only on,
- signal outbox off until tested and approved,
- trade ticket off until tested and approved,
- dry run off until approved,
- real trading off.

### 9.3 Trading Guardrails

Before any DRY RUN/REAL execution:

1. User authenticated.
2. User has role `admin` or `trader`.
3. Feature flag allows mode.
4. Pair valid and tradable.
5. Amount within max limit.
6. Price freshness acceptable.
7. Signal not stale beyond configured max age.
8. Idempotency key not used.
9. Risk snapshot calculated.
10. Audit log written.

### 9.4 Real Trading Confirmation

For Phase 3:

- Confirmation modal shows pair, side, amount, estimated total, SL/TP, risk.
- User must type confirmation phrase for real orders:

```text
BUY BTCIDR REAL
```

- Real mode top banner always visible.
- Emergency stop button visible but also gated.

---

## 10. Implementation Roadmap

### Sprint 0 — Planning Finalization

Deliverables:

- This design reviewed.
- Final approval for Phase 1 scope.
- Auth decision.
- Deployment target decision.

### Sprint 1 — Read-only Signal Cockpit

Backend:

- FastAPI scaffold.
- SQLite reader for `signals.db` and `trading.db`.
- Redis reader for heartbeat and price.
- `/api/v1/health`, `/api/v1/system/data-sources`.
- `/api/v1/pairs/active`, `/api/v1/pairs/{pair}/chart`.
- `/api/v1/signals/latest`, `/api/v1/trades/history`, `/api/v1/positions/open`.
- `/api/v1/events/stream` SSE read-only.

Frontend:

- Dashboard shell.
- Signal feed.
- Signal detail.
- Chart panel.
- Health bar.

Tests:

- pytest reader tests for read-only DB/Redis services.
- SSE smoke test.
- Playwright smoke for health, active pairs, latest signals, and trades/positions panels.

### Sprint 2 — Telegram Exact Signal Outbox

Bot-side:

- Identify final Telegram signal send path.
- Add pure helper to persist signal outbox before/after send.
- Preserve Telegram behavior.
- TDD around outbox writer.

Dashboard:

- Render exact Telegram message preview from outbox.
- Show sent/unsent status.

### Sprint 3 — Trade Ticket Calculator

- Trade plan table migration.
- Trade ticket UI.
- Risk/reward calculation.
- Save/update plan.
- Audit log.

### Sprint 4 — DRY RUN Trading

- Trade intent table.
- Dry run executor boundary.
- Confirmation flow.
- Idempotency.
- Audit.

### Sprint 5 — Real Trading Gate, Optional

Only after explicit approval:

- Real executor integration.
- Strong confirmation.
- Limits.
- Emergency disable.
- Security review.

---

## 11. Testing Strategy

### Backend Tests

- SQLite read with busy retry.
- Redis missing/down fallback.
- Signal filter query.
- Trades/open positions read-only query.
- SSE event stream returns `text/event-stream`.
- Future-only tests after separate approval: outbox insert/update, trade ticket risk calculation, trade intent idempotency, real trading disabled by default.

### Frontend Tests

- Signal list renders.
- Signal detail opens as read-only.
- Active pairs/chart panel renders.
- Trades/open positions panel renders.
- Stale/offline states visible.
- SSE reconnect fallback polling.
- Future-only tests after separate approval: trade ticket calculation and real trade button disabled by default.

### Integration Tests

- Bot heartbeat visible in dashboard.
- New signal row appears via SSE/polling.
- Active pair price/chart freshness visible.
- Trade/open-position read endpoint does not mutate DB.
- Future-only tests after separate approval: outbox preview equality and double-click trade intent idempotency.

### Security Tests

- No secret values in frontend build.
- No write endpoints in Phase 1 API/routes.
- Future-only tests after separate approval: write endpoints require auth, real trading endpoint rejects when feature flag false, and audit log is written on write actions.

---

## 12. Open Questions / Approval Needed

Before Phase 1 implementation:

1. Auth pilihan jika dashboard public:
   - local admin password,
   - reverse proxy basic auth,
   - Telegram login widget,
   - or OAuth.
2. Deployment target:
   - local only,
   - VPS + Nginx,
   - Docker Compose,
   - PM2/systemd manual.

Already approved:

- Phase 1 read-only only.
- Health, active pairs/chart, latest signals, trades/open positions, SSE stream.
- No write/trading features in Phase 1.

Future approval, not needed for Phase 1:

1. Phase 1.5 outbox: apakah boleh menambah table dashboard baru.
2. Trade ticket/save plan.
3. Phase 2 DRY RUN trading.
4. Real trading: tetap disabled sampai approval eksplisit.

---

## 13. Recommended Next Step

Langkah aman berikutnya:

1. Scope Sprint 1 sudah approved: Phase 1 read-only cockpit.
2. Jalankan BMAD readiness check ulang terhadap dokumen dashboard-web setelah alignment ini.
3. Buat branch kerja khusus dashboard.
4. Implement FastAPI read-only API + tests untuk health, active pairs/chart, latest signals, trades/open positions, SSE.
5. Implement React dashboard shell + panel read-only.
6. Baru setelah Phase 1 stabil, minta approval terpisah untuk exact Telegram outbox / trade ticket.

Rekomendasi final:

> Bangun **Phase 1 read-only cockpit** dulu. Jangan mulai outbox write, trade ticket, DRY RUN trading, atau real trading dari website sebelum Phase 1 stabil dan ada approval terpisah.
