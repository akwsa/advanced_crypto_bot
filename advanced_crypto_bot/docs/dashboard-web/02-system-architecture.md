# 02 — System Architecture

## Keputusan Arsitektur v1.3 — Phase 1 Read-only

Dashboard memakai pola **separate companion service**:

- `bot.py` tetap orchestrator utama.
- `dashboard_api` adalah FastAPI service terpisah.
- `dashboard_frontend` adalah React app yang dilayani Nginx.
- SQLite dan Redis menjadi integration boundary.
- Phase 1 hanya read-only terhadap tabel existing bot dan Redis runtime keys.
- Phase 1 realtime memakai **Server-Sent Events (SSE)**, bukan WebSocket/Socket.IO.
- Tidak ada write endpoint pada Phase 1.
- Semua write/trading capability ditunda ke future phase setelah approval terpisah.

---

## High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Browser                                                     │
│ React Dashboard                                             │
└──────────────┬───────────────────────────────┬──────────────┘
               │ HTTPS /api                    │ SSE /api/v1/events/stream
               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Nginx                                                       │
│ - Serve React static build                                  │
│ - Proxy /api/* → FastAPI                                    │
│ - SSL termination                                           │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Dashboard API — FastAPI + Uvicorn                           │
│ - REST read endpoints                                       │
│ - SSE read-only event endpoint                              │
│ - Auth middleware if public                                 │
│ - Data freshness metadata                                   │
│ - SQLite busy/retry/cache handling                          │
└─────────────┬───────────────────────────────┬───────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────────┐   ┌───────────────────────────┐
│ SQLite DB(s)                │   │ Redis                     │
│ - data/trading.db LIVE      │   │ - price:*                 │
│ - data/signals.db LIVE      │   │ - state:historical:*      │
│ - core/trading.db LEGACY 0B │   │ - dashboard:bot:heartbeat│
└─────────────┬───────────────┘   └────────────┬──────────────┘
              │                                │
              ▼                                ▼
┌─────────────────────────────────────────────────────────────┐
│ bot.py Existing Runtime                                     │
│ Telegram + signal pipeline + hunter + autotrade             │
│ Publishes best-effort dashboard heartbeat to Redis           │
└─────────────────────────────────────────────────────────────┘
```

---

## Realtime Decision: SSE First

Dokumen lama pernah mencampur FastAPI native WebSocket dengan `socket.io-client`. Itu tidak kompatibel. Revisi Phase 1 memilih SSE karena:

- Read-only dashboard butuh one-way server → browser.
- Browser `EventSource` punya auto-reconnect built-in.
- Lebih sederhana di-proxy oleh Nginx.
- Tidak perlu `socket.io-client` atau `reconnecting-websocket` untuk MVP.
- Mengurangi risiko implementasi.

Endpoint Phase 1:

```text
GET /api/v1/events/stream   # text/event-stream
```

Event Phase 1 bersifat informatif/read-only saja. Event tidak boleh mengeksekusi write/trading action.

---

## Component Breakdown

### Backend: `dashboard_api/`

Struktur berikut adalah contoh orientasi, bukan kewajiban file-by-file. Implementasi agent boleh memilih struktur lebih baik selama acceptance criteria terpenuhi.

```text
dashboard_api/
├── main.py
├── config.py
├── routers/
│   ├── health.py
│   ├── system.py
│   ├── pairs.py
│   ├── signals.py
│   ├── trades.py
│   └── events.py           # SSE Phase 1
├── services/
│   ├── db_retry.py
│   ├── trading_db_reader.py
│   ├── signal_db_reader.py
│   ├── redis_reader.py
│   ├── indodax_client.py
│   ├── freshness.py
│   ├── response_cache.py
│   └── sse_manager.py
├── models/
│   ├── schemas.py
│   └── errors.py
└── dependencies/
    ├── auth.py             # only if dashboard public
    └── rate_limit.py
```

Future-only modules seperti `sl_tp.py`, `trade_intents.py`, `hunters.py`, dan write migrations tidak dibuat dalam Phase 1 kecuali ada approval baru.

### Frontend: `dashboard_frontend/`

```text
dashboard_frontend/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   ├── events.ts          # EventSource wrapper
│   │   └── format.ts
│   ├── hooks/
│   │   ├── useEventStream.ts
│   │   ├── useActivePairs.ts
│   │   └── useFreshness.ts
│   ├── components/
│   │   ├── layout/
│   │   ├── charts/
│   │   ├── panels/
│   │   └── shared/
│   └── pages/
│       ├── Overview.tsx
│       ├── PairDetail.tsx
│       ├── Signals.tsx
│       └── Trades.tsx
```

Phase 1 frontend tidak menampilkan tombol execute trade, save trade plan, SL/TP write, hunter control, real-trading toggle, atau emergency stop.

---

## Data Sources Final Awal

| Data | Source | Status v1.3 |
|---|---|---|
| Watchlist / active pairs | `data/trading.db.watchlist` | LIVE, 65 rows saat audit |
| Price history OHLCV | `data/trading.db.price_history` | LIVE, 410k+ rows, cukup untuk candlestick banyak pair |
| Trade history | `data/trading.db.trades` | LIVE, 289 rows saat audit |
| Bot internal signals | `data/trading.db.signals` | table ada, 0 rows saat audit |
| Telegram/signal history | `data/signals.db.signals` | LIVE, 34k+ rows; primary candidate untuk latest signals |
| Cached latest price | Redis `price:{pair}` | LIVE, string `price:timestamp`, 40 keys saat audit |
| Position state | Redis `state:position:{pair}` | 0 keys saat audit; fallback ke open trades |
| Historical state | Redis `state:historical:{pair}` | LIVE, 67 keys saat audit |
| Bot heartbeat | Redis `dashboard:bot:heartbeat` | ditambahkan v1.2, TTL 30s |
| Telegram/Hunter health | belum final | tampil `unknown` sampai publisher eksplisit dibuat; bukan Phase 1 panel utama |
| AutoTrade mode | config/env + possible app_settings | tampil read-only jika aman; tidak ada toggle |

---

## REST API Contract Style

Semua endpoint mengembalikan wrapper konsisten:

```json
{
  "success": true,
  "data": {},
  "meta": {
    "timestamp": "2026-05-21T10:30:00Z",
    "source": "redis|sqlite|indodax|mixed|cache",
    "freshness": "fresh|stale|offline|unknown|empty|error",
    "last_updated": "2026-05-21T10:29:58Z"
  }
}
```

Error SQLite locked:

```json
{
  "success": false,
  "error": {
    "code": "SQLITE_LOCKED",
    "message": "Database temporarily unavailable",
    "retry_after_seconds": 2
  },
  "meta": {
    "timestamp": "2026-05-21T10:30:00Z"
  }
}
```

---

## SQLite Read Strategy

- Gunakan koneksi read-only URI: `file:data/trading.db?mode=ro` jika memungkinkan.
- Set `PRAGMA busy_timeout=4000` untuk setiap koneksi.
- Retry locked/busy maksimal 3x dengan backoff 1s, 2s, 4s.
- Cache response terakhir untuk endpoint utama; jika SQLite locked dan cache masih wajar, return cached response dengan `source=cache` dan warning metadata.
- Jika tidak ada cache, return error `SQLITE_LOCKED` + `retry_after_seconds`.
- Jangan import `bot.py` dari dashboard API.
- Jangan write ke tabel existing bot atau tabel dashboard pada Phase 1.

---

## Endpoint MVP Phase 1

```text
GET /api/v1/health
GET /api/v1/system/data-sources
GET /api/v1/pairs/active
GET /api/v1/pairs/{pair}/chart?timeframe=1h&limit=200
GET /api/v1/signals/latest?limit=50&source=auto
GET /api/v1/trades/history?limit=100&status=open|closed|all
GET /api/v1/positions/open
GET /api/v1/events/stream
```

Future candidates, not Phase 1:

```text
GET /api/v1/pairs/top-volume?limit=20
GET /api/v1/hunters/status
GET /api/v1/telegram/status
GET /api/v1/sl-tp/config
POST /api/v1/sl-tp/config/{pair}
POST /api/v1/trade-intents
POST /api/v1/hunters/toggle
POST /api/v1/autotrade/toggle
POST /api/v1/emergency-stop
```

---

## Security Architecture

### Jangan lakukan

- Jangan taruh admin API key di `VITE_*` frontend env.
- Jangan expose write endpoint tanpa login.
- Jangan izinkan Real Trading toggle tanpa confirmation phrase dan audit.
- Jangan membuat endpoint POST/PUT/PATCH/DELETE untuk trading/dashboard state pada Phase 1.

### Phase 1 jika dashboard private LAN/VPN

- Nginx basic auth atau single admin login cukup sebagai sementara.
- Read endpoints dapat dilindungi session/cookie jika dashboard public.

### Future Phase 1.5+

- Admin login endpoint.
- Session via HTTP-only secure cookie atau JWT yang tidak disimpan sebagai admin key di bundle.
- CSRF protection jika cookie auth.
- Audit log untuk semua write.
- Rate limiting.
- CORS whitelist domain dashboard.

---

## Data Freshness

Semua panel wajib menampilkan status:

- `fresh` — data valid dan baru.
- `stale` — data ada tapi melewati TTL.
- `offline` — source tidak tersedia atau heartbeat expired.
- `empty` — source valid tapi tidak ada data.
- `unknown` — publisher/source belum tersedia.
- `error` — query/API error.
