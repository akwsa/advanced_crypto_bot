---
title: 'Konsistensi Equity, Pending Cancellation, dan NO_ENTRY AutoTrade'
type: 'bugfix'
created: '2026-08-16'
status: 'in-review'
baseline_commit: 'a279933f25f170317a7271b54f8f0d8b650f2bce'
review_loop_iteration: 0
context:
  - advanced_crypto_bot/docs/AUDIT_2026-08-14_autotrade_24h_checkpoint.md
  - _bmad-output/implementation-artifacts/spec-autotrade-dryrun-decision-execution-spine.md
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dry-run BUY tidak mendebit virtual cash sehingga equity dan peak menghitung posisi dua kali; cancellation pending hanya mengubah ledger legacy; dan banyak early return berakhir sebagai `NO_ORDER_CREATED`/`OTHER`, membuat circuit breaker serta funnel keputusan tidak dapat dipercaya.

**Approach:** Jadikan virtual cash bagian transaksi atomik BUY/SELL, settlement cancellation terminal pada legacy dan normalized ledger, dan wajibkan reason code spesifik untuk setiap jalur tanpa order. Setelah test, backup dan deploy ke VM, rekonsiliasi state lama secara terverifikasi, restart hanya dalam dry-run, lalu kumpulkan sampel baru.

## Boundaries & Constraints

**Always:** Debit BUY sebesar `total+fee`; kredit SELL sebesar `proceeds-fee`; replay tidak mengubah cash dua kali; equity adalah cash ditambah mark-to-market posisi OPEN; cancellation memperbarui pending/order/intent dalam satu transaksi; setiap actionable intent berakhir dengan reason code non-generik; migrasi VM didahului backup dan invariant check.

**Ask First:** Jika VM memiliki posisi OPEN saat migrasi, histori non-AutoTrade yang memengaruhi virtual balance, test mengharuskan perubahan threshold, atau rekonsiliasi tidak dapat dibuktikan deterministik.

**Never:** Mengubah threshold alpha/risk, memanggil private order API, mengaktifkan live trading, menghapus ledger/backlog, mereset peak tanpa menghitung equity konsisten, atau menandai cancellation sebagai fill.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Immediate/deferred BUY | Cash cukup, intent baru | Cash turun `total+fee`; order/fill/position atomik | Insufficient cash atau fault injection rollback semua write |
| Partial/full SELL | Posisi valid | Cash naik `proceeds-fee`; quantity/basis konsisten | Replay no-op; oversell ditolak |
| Pending cancellation | Legacy dan normalized PENDING | Keduanya CANCELLED; intent terminal dengan reason spesifik | ID/order mismatch rollback dan tidak menyisakan drift |
| Actionable signal ditolak | BUY gate atau SELL tanpa posisi | Structured terminal reason, bukan generic fallback | Unknown early return menjadi test failure/explicit internal reason |
| Deploy state lama | Tidak ada OPEN position, histori closed valid | Cash dan peak direkonsiliasi dari baseline plus realized P&L | Posisi OPEN atau invariant gagal menghentikan migrasi/restart |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/core/database.py` -- atomic virtual-cash debit/credit, cancellation settlement, dan state reconciliation primitives.
- `advanced_crypto_bot/bot.py` -- equity/circuit breaker dan pending-order monitor.
- `advanced_crypto_bot/autotrade/runtime.py` -- complete reason taxonomy untuk semua terminal no-entry paths.
- `advanced_crypto_bot/tests/test_autotrade_ledger.py` -- cash, replay, rollback, pending cancellation, partial/full SELL.
- `advanced_crypto_bot/tests/test_autotrade_dispatch_lifecycle.py` -- structured decision taxonomy.
- `advanced_crypto_bot/tests/test_bug_fixes_verification.py` -- equity/peak regression.
- `advanced_crypto_bot/docs/autotrade-dryrun-decision-spine.md` -- accounting invariant, migration, monitoring, dan rollback.

## Tasks & Acceptance

**Execution:**
- [x] `core/database.py` -- debit/kredit virtual cash hanya ketika fill baru berhasil, serta atomic cancellation yang menyelesaikan normalized order dan intent.
- [x] `bot.py` -- gunakan cash+marked-open-position equity dan panggil cancellation settlement canonical; sediakan fail-closed migration checks.
- [x] `autotrade/runtime.py` -- klasifikasikan edge score, liquidity/price/sizing/pair/chase/correlation, dan `NO_OPEN_POSITION`; tidak ada actionable path generik.
- [x] Tests -- cover immediate/deferred/replay/rollback, insufficient cash, partial/full SELL, cancellation parity, equity mark-to-market, dan reason taxonomy.
- [ ] Documentation/deploy -- backup DB, test VM, rekonsiliasi cash+peak hanya bila no OPEN position, restart service dry-run, dan audit sampel baru.

**Acceptance Criteria:**
- Given cash Rp50 juta dan BUY Rp2 juta dengan fee Rp6 ribu, when fill commit, then cash Rp47,994 juta dan equity tidak melonjak Rp2 juta.
- Given SELL proceeds Rp1,98 juta dengan fee, when commit/replay, then cash dikredit sekali dan realized NAV konsisten.
- Given pending legacy+normalized, when cancel chase/timeout, then kedua status CANCELLED dan intent terminal membawa reason `PENDING_CHASE_CANCELLED` atau `PENDING_TIMEOUT_CANCELLED`.
- Given BUY/SELL tanpa order, when worker settles, then reason code menjelaskan gate/no-position dan bukan `NO_ORDER_CREATED` atau `OTHER`.
- Given targeted suite dan VM smoke, when selesai, then tidak ada private-order call, threshold diff, ledger drift, atau circuit-breaker peak semu.

## Spec Change Log

## Design Notes

`users.balance` tetap virtual cash canonical agar sizing, portfolio, dan risk manager memakai sumber yang sama. Existing closed-only VM dapat direkonsiliasi satu kali menjadi `baseline cash + Σ realized P&L`; bila ada posisi OPEN, deployment berhenti untuk audit manual. Peak setelah migrasi diset ke equity hasil model baru, bukan angka historis double-counted.

## Verification

**Commands:**
- `cd advanced_crypto_bot && venv/bin/python -m pytest -q tests/test_autotrade_ledger.py tests/test_autotrade_dispatch_lifecycle.py tests/test_bug_fixes_verification.py tests/test_runtime_fill_reconciliation.py tests/test_autotrade_dryrun_signal_cycle.py tests/test_dryrun_safety.py` -- expected: seluruh regression lulus tanpa network/private order.
- `git diff --check` -- expected: tidak ada whitespace error.
- VM preflight SQL + targeted pytest + service/log/Redis audit -- expected: backup ada, no OPEN position saat migration, dry-run aktif, cash/peak konsisten, dan sampel baru memiliki reason spesifik.

## Suggested Review Order

**Accounting dan migrasi**

- Transaksi fill mengubah kas virtual tepat sekali bersama ledger normalized.
  [`database.py:554`](../../advanced_crypto_bot/core/database.py#L554)

- BUY atomik mengikat legacy trade, fill, position, dan debit kas.
  [`database.py:1385`](../../advanced_crypto_bot/core/database.py#L1385)

- Rekonsiliasi closed-only menolak ownership drift dan coverage legacy tidak lengkap.
  [`database.py:1957`](../../advanced_crypto_bot/core/database.py#L1957)

- Equity membaca kas canonical lalu menambahkan mark-to-market posisi OPEN.
  [`bot.py:8619`](../../advanced_crypto_bot/bot.py#L8619)

**Cancellation dan observability**

- Cancellation menyelesaikan legacy, normalized order, dan intent secara atomik.
  [`database.py:1610`](../../advanced_crypto_bot/core/database.py#L1610)

- Classifier memetakan seluruh gate dikenal ke reason code spesifik.
  [`runtime.py:107`](../../advanced_crypto_bot/autotrade/runtime.py#L107)

- SELL tanpa posisi berakhir sebagai `NO_OPEN_POSITION`.
  [`runtime.py:2052`](../../advanced_crypto_bot/autotrade/runtime.py#L2052)

**Regression dan operasi**

- Ledger tests membuktikan rollback, replay, cancellation parity, dan rekonsiliasi.
  [`test_autotrade_ledger.py:94`](../../advanced_crypto_bot/tests/test_autotrade_ledger.py#L94)

- Runbook menjelaskan accounting invariant, taxonomy, migration, dan rollback.
  [`autotrade-dryrun-decision-spine.md:32`](../../advanced_crypto_bot/docs/autotrade-dryrun-decision-spine.md#L32)
