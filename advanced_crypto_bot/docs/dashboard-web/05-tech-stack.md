# 05 — Tech Stack

## Backend Stack

| Layer | Teknologi | Catatan |
|---|---|---|
| API Framework | FastAPI | Async, OpenAPI, SSE via streaming response |
| Server | Uvicorn | ASGI server |
| DB Access | `sqlite3` initially; `aiosqlite` optional | Hindari import `bot.py`; direct read-only SQLite lebih aman |
| Cache | Redis | Read existing keys, heartbeat, graceful fallback |
| Validation | Pydantic v2 | Request/response schema |
| Rate Limit | slowapi or simple middleware | Basic API protection + Indodax fallback limit |
| Auth | Backend session/JWT/cookie | Admin key tidak boleh di frontend |
| Realtime Phase 1 | SSE (`EventSource`) | One-way server → browser; no Socket.IO |
| WebSocket | Deferred Phase 1.5+ | Hanya jika ada two-way communication |
| HTTP Client | httpx | Indodax public API fallback |
| Test | pytest, pytest-asyncio, pytest-cov | Unit/integration |
| Lint | ruff | Disarankan |

### Backend Dependencies Draft

```txt
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
pydantic>=2.5,<3.0
pydantic-settings>=2.1,<3.0
httpx>=0.27,<1.0
redis>=5.0,<8.0
slowapi>=1.0,<2.0
python-multipart>=0.0.9
pytest>=8.0,<10.0
pytest-asyncio>=0.23,<1.0
pytest-cov>=5.0,<7.0
ruff>=0.5,<1.0
```

Catatan audit runtime:

- Python env saat audit memiliki FastAPI `0.136.1`, Uvicorn `0.47.0`, Pydantic `2.12.5`, Redis package `7.4.0`, pytest `9.0.3`.
- `aiosqlite` belum terpasang; untuk Phase 1 bisa mulai dengan `sqlite3` read-only + threadpool/retry agar dependency minimal.
- `python-socketio` tidak dipakai.

---

## Frontend Stack

| Layer | Teknologi | Catatan |
|---|---|---|
| Framework | React 18 preferred | React 18 lebih stabil untuk library dashboard; React 19 hanya jika compatibility sudah dicek |
| Language | TypeScript | Required |
| Build | Vite | Fast dev/build |
| Styling | Tailwind CSS | Dark trading theme |
| UI | shadcn/ui / Radix | Component base |
| Chart | Lightweight Charts | Candlestick |
| Server State | TanStack Query | Polling/caching REST API |
| UI State | Zustand | Local dashboard state |
| Realtime | native `EventSource` | SSE Phase 1, no Socket.IO |
| Forms | Deferred | React Hook Form + Zod hanya future write/trade-ticket phase, bukan Phase 1 |
| Test | Vitest + Testing Library + Playwright | Unit/E2E |

### Frontend Dependencies Draft

```json
{
  "dependencies": {
    "@tanstack/react-query": "^5.0.0",
    "axios": "^1.7.0",
    "lightweight-charts": "^4.1.0",
    "zustand": "^4.5.0",
    "react-hook-form": "^7.51.0",
    "zod": "^3.23.0",
    "@hookform/resolvers": "^3.4.0",
    "lucide-react": "^0.400.0",
    "date-fns": "^3.6.0"
  }
}
```

Tidak dipakai untuk Phase 1:

```json
{
  "socket.io-client": "remove",
  "reconnecting-websocket": "defer until WebSocket is actually needed"
}
```

---

## Deployment Stack

| Layer | Teknologi | Catatan |
|---|---|---|
| Reverse proxy | Nginx | Serve frontend, proxy API/SSE |
| SSL | Let's Encrypt | Production |
| Process | TBD: systemd/PM2/Docker/manual | Bot saat audit berjalan manual; dashboard strategy harus dipilih eksplisit |
| Monitoring | Health endpoint + bot heartbeat + logs | MVP |
| Future | Prometheus/Grafana/Loki | Phase 2 |

---

## Hermes/BMAD Stack

Gunakan skill yang tersedia, bukan model names sebagai kontrak utama:

- `advanced-crypto-bot-development`
- `test-driven-development`
- `bmad-help`
- `bmad-agent-architect`
- `bmad-agent-pm`
- `bmad-agent-ux-designer`
- `bmad-quick-dev`
- `bmad-code-review`
- `bmad-check-implementation-readiness`

Agent assignment ada di [03-hermes-agent-roster.md](03-hermes-agent-roster.md).

---

## Security Notes

- Jangan expose admin API key via `VITE_*`.
- Read-only dashboard tetap sebaiknya dilindungi jika public internet.
- Future write endpoints wajib auth backend setelah approval terpisah.
- Real Trading control wajib additional confirmation dan audit; tidak masuk Phase 1.
- SSE endpoint public tetap perlu auth/session jika dashboard public.
