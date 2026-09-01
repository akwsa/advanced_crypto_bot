---
title: 'Melengkapi fixture pair-delete dengan database reader'
type: 'bugfix'
created: '2026-09-01'
status: 'done'
route: 'one-shot'
---

# Melengkapi fixture pair-delete dengan database reader

## Intent

**Problem:** Test notifikasi pair-delete memakai bot parsial tanpa `db`, sehingga runtime SELL gagal sebelum menyelesaikan jalur notifikasi yang sedang diuji.

**Approach:** Tambahkan stub sinkron `get_open_trades()` yang mengembalikan kondisi tanpa posisi pada fixture saja; runtime dan assertion tetap tidak berubah.

## Suggested Review Order

- Fixture menyediakan dependency minimum agar jalur SELL selesai tanpa posisi buatan.
  [`test_pair_delete_cleanup.py:78`](../../advanced_crypto_bot/tests/test_pair_delete_cleanup.py#L78)
