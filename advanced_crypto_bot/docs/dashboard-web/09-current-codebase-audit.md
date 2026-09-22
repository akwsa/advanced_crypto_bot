# 09 — Current Codebase Audit

> Audit runtime awal berdasarkan bot aktif pada 2026-05-21. Validasi ulang tetap wajib sebelum deploy production.

---

## 09 Gaps Checklist — Status

| # | Gap | Status | Hasil |
|---:|---|---|---|
| 1 | DB runtime aktual saat bot aktif | ✅ Resolved | `data/trading.db` |
| 2 | `data/trading.db` vs `core/trading.db` | ✅ Resolved awal | `data/trading.db` live; `core/trading.db` 0 byte |
| 3 | Redis keys aktual | ✅ Resolved awal | `price:*`, `state:historical:*`, `signal_queue:*`; dashboard heartbeat added |
| 4 | Source signal final | ✅ Resolved awal | Primary `data/signals.db.signals`; `trading.db.signals` empty |
| 5 | `price_history` cukup untuk candlestick? | ✅ Resolved awal | 410k+ rows; banyak pair punya ~6.3k candles |
| 6 | Process manager bot | ✅ Resolved awal | Manual terminal via VS Code/WSL; PM2 empty; no systemd unit; docker daemon unavailable |
| 7 | Telegram/Hunter health publish | ⏳ Ditunda | Bot heartbeat done; Telegram/Hunter detail publisher Sprint 2 |

---

## Runtime Bot Process

Ditemukan proses aktif:

```text
pid 87968 cmd: python bot.py
cwd: /home/officer/advanced_crypto_bot/advanced_crypto_bot
DATABASE_PATH=<unset>
REDIS_HOST=<unset>
REDIS_PORT=<unset>
REDIS_DB=<unset>
AUTO_TRADING_ENABLED=<unset>
AUTO_TRADE_DRY_RUN=<unset>
```

Implikasi:

- Bot memakai default config dari `core/config.py`.
- DB runtime default: `data/trading.db`.
- Redis default: localhost:6379 db 0.
- Safe mode default masih dry-run karena `AUTO_TRADE_DRY_RUN` default true di config.

Process manager:

- Bot berjalan dari shell/terminal VS Code WSL.
- PM2 terpasang tapi list kosong.
- `advanced-crypto-bot.service` tidak ada di systemd user.
- Docker daemon tidak aktif/tersedia.

---

## DB Paths yang Ditemukan

```text
/home/officer/advanced_crypto_bot/advanced_crypto_bot/data/trading.db
/home/officer/advanced_crypto_bot/advanced_crypto_bot/data/signals.db
/home/officer/advanced_crypto_bot/advanced_crypto_bot/core/trading.db
```

Status file saat audit:

| DB | Size | Status |
|---|---:|---|
| `data/trading.db` | ~61.9 MB | live runtime |
| `data/signals.db` | ~10.7 MB | live signal history |
| `core/trading.db` | 0 byte | legacy/placeholder, bukan source dashboard |

---

## Trading DB Schema Runtime

`data/trading.db` tables:

- `adaptive_thresholds` — 5 rows.
- `app_settings` — 3 rows.
- `drawdown_state` — 0 rows.
- `ml_metadata` — 0 rows.
- `pair_performance` — 5 rows.
- `pending_orders` — 0 rows.
- `performance` — 28 rows.
- `portfolio` — 0 rows.
- `price_history` — 410081 rows.
- `regime_history` — 0 rows.
- `signals` — 0 rows.
- `trade_outcomes` — 93 rows.
- `trade_reviews` — 93 rows.
- `trades` — 289 rows.
- `users` — 2 rows.
- `watchlist` — 65 rows.

Important columns:

- `watchlist`: `id`, `user_id`, `pair`, `added_at`, `is_active`.
- `price_history`: `id`, `pair`, `timestamp`, `open`, `high`, `low`, `close`, `volume`.
- `trades`: `id`, `user_id`, `pair`, `type`, `price`, `amount`, `total`, `fee`, `signal_source`, `ml_confidence`, `status`, `opened_at`, ...
- `signals`: `id`, `pair`, `timestamp`, `signal_type`, `price`, `confidence`, `indicators`, `ml_prediction`, `recommendation`.

Freshness:

- `price_history.timestamp` min/max: `2026-04-21 13:57:41` → `2026-05-21 12:36:42`.
- `trading.db.signals` empty.

---

## Signal DB Runtime

`data/signals.db` tables:

- `signals` — 34629 rows.
- `signal_metadata` — 0 rows.

Kolom utama `signals`:

- `symbol`
- `price`
- `recommendation`
- `rsi`
- `macd`
- `ma_trend`
- `bollinger`
- `volume`
- `ml_confidence`
- `combined_strength`
- `analysis`
- `final_gate_source`
- `price_source`
- `signal_time`
- `received_at`
- `received_date`
- `source`
- `created_at`

Keputusan awal:

- `/signals/latest` Phase 1 memakai `data/signals.db.signals` sebagai primary source.
- `trading.db.signals` tidak dipakai sebagai primary karena kosong saat audit.
- Merged mode boleh ditambahkan nanti.

---

## Price History Sufficiency

`price_history` cukup untuk candlestick MVP:

- Total rows: 410081.
- Banyak pair aktif punya sekitar 6300 candle.
- Contoh pair dengan data panjang: `solvidr`, `phaidr`, `vvvidr`, `novaidr`, `redidr`, `zerebroidr`, `dogeidr`, dll.
- Rentang data sekitar 2026-04-21 sampai 2026-05-21.

Catatan:

- Perlu query timeframe/aggregation untuk chart 1h/4h/daily jika raw rows bukan interval yang diinginkan.
- Jika pair tertentu kosong, fallback ke Indodax API atau tampil empty state.

---

## Redis Runtime Keys

Redis aktif:

```text
redis-cli ping -> PONG
```

Key counts saat audit:

| Pattern | Count |
|---|---:|
| `price:*` | 40 |
| `state:position:*` | 0 |
| `state:pricedata:*` | 0 |
| `state:historical:*` | 67 |
| `signal_queue:*` | 2 |
| `dashboard:*` | 0 sebelum heartbeat |

Sample `price:*`:

```text
price:chillguyidr ttl=92 val=245.0:1779341810.944197
price:apuidr ttl=83 val=0.512:1779341802.7489421
```

Existing code confirms:

- `price:{pair}` from `cache/redis_price_cache.py`, string `{price}:{timestamp}`, TTL default 300.
- `state:position:{pair}`, `state:pricedata:{pair}`, `state:historical:{pair}` from `cache/redis_state_manager.py`, JSON, TTL default 86400.

---

## Dashboard Heartbeat Added

New bot-side helper:

```text
bot_parts/dashboard_heartbeat.py
```

Contract:

```text
SETEX dashboard:bot:heartbeat 30 {unix_timestamp}
```

Integration:

- `bot.py` starts daemon thread after Redis state syncer.
- Interval: 10 seconds.
- Best-effort only; Redis/dashboard failure does not crash bot.
- Existing running bot must be restarted to start publishing this new heartbeat.

Tests:

```text
scripts/test.sh -q tests/test_dashboard_heartbeat.py
4 passed
```

---

## AutoTrade Config dari `core/config.py`

Config env:

```python
AUTO_TRADING_ENABLED = os.getenv('AUTO_TRADING_ENABLED', 'false').lower() == 'true'
AUTO_TRADE_DRY_RUN = os.getenv('AUTO_TRADE_DRY_RUN', 'true').lower() == 'true'
```

Runtime env saat audit unset, jadi default:

- `AUTO_TRADING_ENABLED = false`.
- `AUTO_TRADE_DRY_RUN = true`.

Implikasi:

- Dashboard Phase 1 cukup menampilkan read-only status jika status bisa dipublish.
- Toggle runtime tidak boleh diasumsikan cukup dengan menulis Redis; bot harus eksplisit membaca dan memvalidasi perubahan.

---

## Rekomendasi Final Awal

1. Phase 1 API membaca direct SQLite read-only dari `data/trading.db` dan `data/signals.db`.
2. Redis reader memahami `price:{pair}` sebagai string, bukan JSON.
3. Bot heartbeat `dashboard:bot:heartbeat` menjadi health signal utama.
4. Telegram/Hunter tampil `unknown` sampai publisher detail dibuat.
5. Phase 1 realtime pakai SSE, bukan WebSocket/Socket.IO.
6. Jangan implement Real Trading toggle sampai ada bot-side control contract dan approval eksplisit.
7. Jangan jalankan migration sebelum backup dan approval; Phase 1 tidak butuh migration.
