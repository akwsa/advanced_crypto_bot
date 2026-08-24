---
title: 'Klasifikasikan Pair Loss Streak Secara Spesifik'
type: 'bugfix'
created: '2026-08-24'
status: 'done'
route: 'one-shot'
---

# Klasifikasikan Pair Loss Streak Secara Spesifik

## Intent

**Problem:** Rejection normal `PAIR_LOSS_STREAK` tersimpan sebagai `UNCLASSIFIED_INTERNAL_ERROR`, sehingga generic-rate funnel 24 jam mencapai 1,38% dan gagal melewati gate integritas 0,5%.

**Approach:** Kenali reason-code `PAIR_LOSS_STREAK` secara exact dan case-insensitive dengan prioritas eksplisit, lalu petakan ke bucket stabil `PAIR_GUARD` tanpa memperluas pencocokan ke pesan lain yang hanya mengandung substring serupa.

## Suggested Review Order

**Klasifikasi taxonomy**

- Reason-code exact mencegah false positive dan menang sebelum keyword pesan lain.
  [`runtime.py:108`](../../advanced_crypto_bot/autotrade/runtime.py#L108)

**Batas regresi**

- Contract test menjaga mapping producer aktual ke bucket `PAIR_GUARD`.
  [`test_autotrade_dispatch_lifecycle.py:9`](../../advanced_crypto_bot/tests/test_autotrade_dispatch_lifecycle.py#L9)

- Boundary test menjaga case normalization, precedence, dan penolakan near-match.
  [`test_autotrade_dispatch_lifecycle.py:42`](../../advanced_crypto_bot/tests/test_autotrade_dispatch_lifecycle.py#L42)
