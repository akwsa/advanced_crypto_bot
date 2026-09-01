---
title: 'Membuat legacy regression gate menguji kontrak yang dimaksud'
type: 'bugfix'
created: '2026-09-01'
status: 'done'
baseline_commit: '1d57a82'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dua bagian legacy regression gate masih gagal sebelum atau di luar kontrak yang hendak diuji. Fixture trade-review memasukkan trade tanpa parent user yang diwajibkan foreign key, sedangkan test VaR production-threshold berjalan dengan default `AUTO_TRADE_DRY_RUN=True` yang memang memakai threshold lebih longgar.

**Approach:** Perbaiki hanya setup test: buat parent user sebelum fake trade dan pin test VaR/CVaR threshold ke production mode. Pertahankan implementasi runtime, ekspektasi assertion, serta seluruh quality gate tanpa deselection atau bypass.

## Boundaries & Constraints

**Always:** Gunakan schema publik yang dibuat `Database`; buat relasi fixture valid sebelum trade; patch `autotrade.trading_engine.Config.AUTO_TRADE_DRY_RUN=False` hanya selama test threshold production; pulihkan konfigurasi otomatis setelah test; pertahankan semua assertion yang ada.

**Ask First:** Setiap kebutuhan mengubah threshold VaR/CVaR runtime, kebijakan dry-run, schema database, implementasi trade-review, atau expected result test.

**Never:** Jangan menonaktifkan/deselect/xfail test, jangan mengendurkan assertion, jangan mengubah credential atau runtime live, dan jangan menyentuh domain AutoTrade Next.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Trade-review fixture | DB baru dengan foreign key aktif | Parent user dibuat sebelum fake trade; kontrak idempotency berjalan | Setup tidak boleh mematikan foreign key |
| VaR normal production | VaR -2%, production mode | Tidak ditolak oleh VaR gate | Gate lain tidak dianggap failure VaR |
| VaR ekstrem production | VaR -4%, CVaR -6%, production mode | BUY ditolak dengan alasan VaR | Tidak memakai threshold dry-run |
| Config isolation | Test selesai atau gagal | Nilai `AUTO_TRADE_DRY_RUN` dikembalikan otomatis | Gunakan scoped mock/patch |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/tests/test_audit_2026_06_07_remaining_fixes.py` -- fixture SQLite dan kontrak trade-review idempotency.
- `advanced_crypto_bot/tests/test_quant_integration.py` -- kontrak VaR/CVaR hard gate untuk nilai normal dan ekstrem.
- `advanced_crypto_bot/core/database.py` -- schema users/trades/trade_reviews sebagai referensi read-only.
- `advanced_crypto_bot/autotrade/trading_engine.py` -- perbedaan threshold dry-run/production sebagai referensi read-only.

## Tasks & Acceptance

**Execution:**
- [x] `advanced_crypto_bot/tests/test_audit_2026_06_07_remaining_fixes.py` -- buat parent user sebelum fake trade agar test mencapai assertion idempotency tanpa mengubah foreign-key enforcement.
- [x] `advanced_crypto_bot/tests/test_quant_integration.py` -- scope seluruh test yang mengklaim threshold production dengan `AUTO_TRADE_DRY_RUN=False` agar deterministic dan selaras dengan kontraknya.
- [x] Jalankan test fokus, kedua file legacy penuh, AutoTrade Next, lalu full regression fail-fast tanpa pengecualian.

**Acceptance Criteria:**
- Given database fixture baru, when fake trade dan dua trade-review dibuat, then foreign key valid dan hanya review pertama yang dipertahankan.
- Given nilai VaR normal dan ekstrem, when production-threshold tests dijalankan, then nilai normal tidak ditolak oleh VaR dan nilai ekstrem ditolak dengan alasan VaR.
- Given seluruh perubahan hanya pada test setup, when regression gate dijalankan, then tiga failure legacy sebelumnya hilang tanpa perubahan runtime maupun quality-gate exception.

## Spec Change Log

## Verification

**Commands:**
- `venv/bin/python -m pytest -q tests/test_audit_2026_06_07_remaining_fixes.py` -- expected: 15 passed.
- `venv/bin/python -m pytest -q tests/test_quant_integration.py` -- expected: 42 passed.
- `venv/bin/python -m pytest -q tests/autotrade_next` -- expected: 478 passed.
- `venv/bin/python -m pytest -q -x --tb=short` -- expected: tidak berhenti pada tiga failure legacy yang disetujui.
- `git diff --check` -- expected: tidak ada whitespace error.

## Suggested Review Order

**Production-threshold test isolation**

- Pin production mode secara scoped untuk membuktikan jalur hard-gate ekstrem.
  [`test_quant_integration.py:394`](../../advanced_crypto_bot/tests/test_quant_integration.py#L394)

- Nilai normal memakai mode sama agar kedua sisi threshold konsisten.
  [`test_quant_integration.py:419`](../../advanced_crypto_bot/tests/test_quant_integration.py#L419)

- Duplikasi kontrak realistis mengunci batas normal dan ekstrem secara eksplisit.
  [`test_quant_integration.py:529`](../../advanced_crypto_bot/tests/test_quant_integration.py#L529)

**Relational fixture validity**

- Parent user dibuat sebelum trade tanpa mematikan enforcement foreign key.
  [`test_audit_2026_06_07_remaining_fixes.py:162`](../../advanced_crypto_bot/tests/test_audit_2026_06_07_remaining_fixes.py#L162)
