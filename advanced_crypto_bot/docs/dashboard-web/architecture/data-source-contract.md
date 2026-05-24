# Data Source Contract — Phase 1 Read-only Draft

> Contract ini diselaraskan untuk Phase 1 read-only. Dashboard boleh membaca source di bawah, tetapi tidak boleh menulis ke SQLite/Redis runtime keys kecuali bot heartbeat publisher yang sudah ada di `bot.py`.

---

## Known SQLite Sources

| Source | Path | Status | Notes |
|---|---|---|---|
| Trading DB default | `data/trading.db` | confirmed runtime default | `Config.DATABASE_PATH` default; backed up before dashboard work |
| Trading DB alternate | `core/trading.db` | discovered legacy/copy candidate | not canonical for Phase 1 unless separately verified |
| Signal DB | `data/signals.db` | confirmed signal source | managed by `signals/signal_db.py`; backed up before dashboard work |

---

## Known Trading DB Tables

| Table | Use for Dashboard | Phase |
|---|---|---|
| `watchlist` | active pairs candidate | 1 |
| `price_history` | OHLCV chart candidate | 1 |
| `trades` | trade history/open trades | 1 |
| `signals` | bot internal signals candidate; empty saat audit | fallback only |
| `app_settings` | config candidate, not assumed | future/read-only only |
| `portfolio` | portfolio summary candidate | future |
| `pair_performance` | pair analytics candidate | future |
| `adaptive_thresholds` | adaptive config read-only candidate | future |

---

## Known Signal DB Tables

| Table | Use for Dashboard | Notes |
|---|---|---|
| `signals` | latest signal / Telegram signal log | likely best source for Telegram history |
| `signal_metadata` | status/meta | optional |

---

## Known Redis Keys

| Key | Format | Status | Dashboard Usage |
|---|---|---|---|
| `price:{pair}` | string `price:timestamp` | existing | latest price |
| `state:position:{pair}` | JSON | existing | active positions |
| `state:pricedata:{pair}` | JSON | existing | richer price state |
| `state:historical:{pair}` | JSON | existing | historical cache |

---

## Proposed Dashboard Redis Keys

Use prefix `dashboard:` for new keys.

| Key | Format | Producer | Consumer |
|---|---|---|---|
| `dashboard:bot:heartbeat` | JSON/string heartbeat with TTL 30s | bot.py publisher | dashboard API Phase 1 |
| `dashboard:telegram:health` | JSON | future bot.py publisher | dashboard API future |
| `dashboard:hunter:smart:status` | JSON | future bot.py publisher | dashboard API future |
| `dashboard:hunter:ultra:status` | JSON | future bot.py publisher | dashboard API future |
| `dashboard:autotrade:status` | JSON | future bot.py publisher | dashboard API future |
| `dashboard:events` | Redis Pub/Sub JSON | future only | future realtime manager; not Phase 1 |

If proposed keys are missing, dashboard must show `unknown`, not fail. Phase 1 SSE can be implemented by dashboard API polling/read aggregation; it must not depend on future `dashboard:events`.

---

## Pair Normalization

Canonical pair format for API responses:

```text
btcidr
ethidr
```

Display format:

```text
BTC/IDR
ETH/IDR
```

Rules:

- Lowercase internal.
- Remove `/`.
- Ensure suffix `idr` if absent for Indodax IDR pairs.

---

## Data Freshness Contract

Every API response should include:

```json
{
  "meta": {
    "source": "redis|sqlite|indodax|mixed",
    "freshness": "fresh|stale|offline|unknown|empty|error",
    "last_updated": "2026-05-21T10:30:00Z",
    "stale_after_seconds": 300
  }
}
```

