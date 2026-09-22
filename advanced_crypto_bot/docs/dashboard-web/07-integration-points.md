# 07 — Integration Points

## Prinsip Integrasi

- Dashboard dan `bot.py` adalah proses terpisah.
- SQLite dan Redis adalah boundary integrasi.
- Phase 1 read-only terhadap data existing.
- Phase 1 realtime memakai SSE, bukan WebSocket.
- Phase 1.5 write hanya ke table `dashboard_*`.
- Tidak ada import/run `bot.py` dari dashboard.
- Import modul `core.*` hanya boleh setelah audit side effect; default lebih aman pakai koneksi SQLite langsung.

---

## SQLite Reality Check — Resolved Awal 2026-05-21

Bot aktif ditemukan sebagai:

```text
pid 87968: python bot.py
cwd: /home/officer/advanced_crypto_bot/advanced_crypto_bot
DATABASE_PATH=<unset>
```

Karena `core/config.py`:

```python
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/trading.db')
```

maka runtime DB aktif adalah:

```text
data/trading.db
```

DB lain:

```text
core/trading.db     # 0 byte, legacy/placeholder saat audit
data/signals.db     # live signal history
```

---

## SQLite Tables Runtime

`data/trading.db` saat audit:

- `watchlist`: 65 rows.
- `price_history`: 410081 rows.
- `trades`: 289 rows.
- `signals`: 0 rows.
- `app_settings`: 3 rows.
- `performance`: 28 rows.
- `trade_outcomes`: 93 rows.
- `trade_reviews`: 93 rows.
- Plus table lain dari `core/database.py`.

`data/signals.db` saat audit:

- `signals`: 34629 rows.
- `signal_metadata`: 0 rows.

Implikasi:

- Watchlist/active pairs: `data/trading.db.watchlist`.
- Candlestick: `data/trading.db.price_history`.
- Trade history/open trades: `data/trading.db.trades`.
- Latest signals primary: `data/signals.db.signals`.
- `data/trading.db.signals` boleh menjadi future secondary/merged source, tetapi saat audit kosong.

---

## Redis Reality Check — Resolved Awal 2026-05-21

Redis aktif (`redis-cli ping` = `PONG`). Key counts saat audit:

| Pattern | Count | Status |
|---|---:|---|
| `price:*` | 40 | live |
| `state:position:*` | 0 | kosong, fallback ke SQLite open trades |
| `state:pricedata:*` | 0 | kosong |
| `state:historical:*` | 67 | live |
| `signal_queue:*` | 2 | live stats |
| `dashboard:*` | 0 sebelum heartbeat | prefix baru |

`price:*` format:

```text
price:chillguyidr = "245.0:1779341810.944197"
TTL sekitar 300s
```

Existing Redis patterns dari code:

| Key | Format | Source |
|---|---|---|
| `price:{pair}` | string `price:timestamp` | `redis_price_cache.py` |
| `state:position:{pair}` | JSON | `redis_state_manager.py` |
| `state:pricedata:{pair}` | JSON | `redis_state_manager.py` |
| `state:historical:{pair}` | JSON | `redis_state_manager.py` |

---

## Bot Heartbeat Contract

Bot sekarang punya publisher ringan:

```text
Redis SETEX dashboard:bot:heartbeat 30 {unix_timestamp}
```

Rules:

- Publish interval: 10 detik.
- TTL: 30 detik.
- Value: Unix timestamp integer sebagai string.
- Write best-effort; Redis failure tidak crash bot.
- Dashboard membaca key ini untuk status bot:
  - key ada + timestamp age ≤ 30–45s → `online`.
  - key missing/expired → `offline`.
  - Redis down → `unknown` atau `offline` dengan source `redis_offline`.

---

## Proposed Future Dashboard Keys

Keys yang masih proposal dan perlu bot-side publisher jika panel detail diambil:

| Proposed Key | Purpose | Phase |
|---|---|---|
| `dashboard:telegram:health` | Telegram bot health | Sprint 2 |
| `dashboard:hunter:smart:status` | SmartHunter status | Sprint 2 |
| `dashboard:hunter:ultra:status` | UltraHunter status | Sprint 2 |
| `dashboard:autotrade:status` | AutoTrade mode/status | Sprint 2 |
| `dashboard:events` | Pub/Sub event stream | Optional |

Gunakan prefix `dashboard:` untuk key baru agar tidak bentrok dengan existing key.

---

## Data Source Contract Draft

| Domain | Primary Source | Fallback | Phase |
|---|---|---|---|
| Bot alive | Redis `dashboard:bot:heartbeat` | unknown/offline | 1 |
| Active pairs | `data/trading.db.watchlist` | Config/watch pairs after audit | 1 |
| OHLCV chart | `data/trading.db.price_history` | Indodax public API | 1 |
| Latest price | Redis `price:{pair}` | Indodax public API | 1 |
| Positions | Redis `state:position:*` | open trades from SQLite | 1 |
| Trade history | `data/trading.db.trades` | none | 1 |
| Signals | `data/signals.db.signals` | merged mode with `trading.db.signals` later | 1 |
| Telegram health | future `dashboard:telegram:health` | unknown state | 2 |
| Hunter status | future `dashboard:hunter:*:status` | unknown state | 2 |
| SL/TP settings | `dashboard_sl_tp_settings` | none | 1.5 |

---

## Fallback Strategy

### Jika Redis down

- Latest price: fallback ke Indodax public API dengan timeout dan rate limit.
- Positions: fallback ke SQLite `trades WHERE status='open'`.
- Bot/Telegram/Hunter status: tampilkan `unknown` atau `offline` sesuai source.
- Endpoint tetap return `success=true` jika fallback berhasil, dengan meta `source=mixed` dan warning.

### Jika SQLite locked/busy

- Retry 3x dengan backoff 1s, 2s, 4s.
- Gunakan `PRAGMA busy_timeout=4000`.
- Jika retry gagal dan cached response ada, return cached response dengan meta:
  - `source=cache`
  - `freshness=stale`
  - warning `SQLITE_LOCKED_USING_CACHE`
- Jika retry gagal tanpa cache, return:

```json
{
  "success": false,
  "error": {
    "code": "SQLITE_LOCKED",
    "retry_after_seconds": 2
  }
}
```

### Jika Indodax API rate-limited/down

- Return cached price/chart if available.
- Mark source `cache` and freshness `stale`.
- Jangan retry agresif dari banyak browser; backend yang mengatur throttle.

---

## Indodax Rate Limit Strategy

- Semua fallback Indodax lewat backend service tunggal, bukan langsung frontend.
- Timeout pendek, misalnya 5–10 detik.
- Per-pair TTL cache minimal 15–60 detik tergantung endpoint.
- Global concurrency limit untuk request public API.
- Jika API gagal, degrade panel, jangan fail seluruh dashboard.

---

## Dashboard Tables Phase 1.5

```sql
CREATE TABLE IF NOT EXISTS dashboard_sl_tp_settings (
    pair TEXT PRIMARY KEY,
    direction TEXT NOT NULL DEFAULT 'LONG_SPOT',
    entry_price REAL NOT NULL,
    stop_loss_pct REAL NOT NULL,
    stop_loss_price REAL NOT NULL,
    take_profit_pct REAL NOT NULL,
    take_profit_price REAL NOT NULL,
    fee_rate REAL DEFAULT 0,
    slippage_pct REAL DEFAULT 0,
    expected_loss_idr REAL,
    expected_profit_idr REAL,
    risk_reward_ratio REAL,
    is_active INTEGER DEFAULT 1,
    updated_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

Gunakan UPSERT, bukan `INSERT OR REPLACE`.

---

## Bot-side Changes yang Dibutuhkan

Sudah ditambahkan:

- Bot heartbeat publisher `dashboard:bot:heartbeat`.

Masih future:

- Telegram health publisher.
- Hunter status publisher.
- Autotrade status publisher.
- Optional Redis pub/sub event publisher.

Rules:

- Bot-side publisher harus best-effort.
- Semua Redis write dibungkus try/except.
- Kegagalan Redis/dashboard tidak boleh crash bot.
- Default status di dashboard adalah `unknown` jika key belum ada.

---

## Migration Safety

1. Stop write-heavy jobs jika perlu.
2. Backup DB.
3. Run migration di copy DB.
4. Validate schema.
5. Apply production migration.
6. Smoke test.
7. Rollback jika gagal.

---

## Safety Guards

- LIMIT di semua query list.
- Parameterized query.
- Busy timeout SQLite.
- Read-only mode untuk GET jika memungkinkan.
- Graceful error response.
- Data freshness metadata.
- No write to bot existing tables pada Phase 1.
