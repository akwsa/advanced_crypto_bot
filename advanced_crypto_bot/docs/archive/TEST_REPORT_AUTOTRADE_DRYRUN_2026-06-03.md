# Test Report — AutoTrade DRY RUN

**Tanggal:** 2026-06-03  
**Workspace:** `/home/officer/advanced_crypto_bot/advanced_crypto_bot`  
**Tujuan:** Verifikasi regresi dan safety untuk AutoTrade DRY RUN (termasuk auto-promote, decision-layer gating, dan market-intelligence gate) melalui automated tests.

## Environment

- Python: `/home/officer/advanced_crypto_bot/advanced_crypto_bot/venv/bin/python`
- Versi: 3.12.3
- OS: Linux (WSL2)

## Test Execution

### Command

```bash
./scripts/test.sh -q \
  tests/test_autotrade_dryrun_signal_cycle.py \
  tests/test_dryrun_safety.py \
  tests/test_autotrade_status_watchlist.py \
  tests/test_orderbook_market_intelligence.py \
  tests/test_signal_notification_controls.py
```

### Result

- Status: PASS
- Ringkasan: `49 passed in 78.62s`

## Coverage Fokus (berdasarkan suite yang dijalankan)

- AutoTrade DRY RUN:
  - Siklus sinyal DRY RUN (BUY/STRONG_BUY → posisi DRY RUN, serta SELL untuk penutupan) melalui jalur runtime.
  - Auto-promote watched pair ke `auto_trade_pairs` saat DRY RUN aktif.
  - Decision-layer gating (blok eksekusi untuk duplicate / PANTAU / alasan keputusan).
- Safety (No money automation):
  - Validasi jalur DRY RUN tidak melakukan private-order execution pada exchange.
  - Kontrol notifikasi (supaya tidak spam / tidak mengubah perilaku eksekusi).
- Market Intelligence / Orderbook gate:
  - Spread guard, MI filter, dan gating terkait orderbook pressure.

## Notes

- Suite ini adalah subset yang relevan untuk memastikan DRY RUN aman dan pipeline gating bekerja; tidak menjalankan full test suite repository.
