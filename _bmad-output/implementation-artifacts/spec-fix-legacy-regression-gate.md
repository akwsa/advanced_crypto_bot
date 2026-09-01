---
title: 'Memulihkan legacy regression gate untuk Story 3.4'
type: 'bugfix'
created: '2026-09-01'
status: 'done'
baseline_commit: 'f1d1f6b97e8e145310d072a71b255015e2231aed'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Full regression gate Story 3.4 gagal karena dua kontrak legacy: `_filter_admin_ids(None)` mengubah sentinel `None` menjadi list kosong, dan `signals.signal_pipeline` tidak menyediakan helper LRU `_quant_cache_get`, `_quant_cache_set`, serta `_quant_cache_clear` yang diwajibkan test audit.

**Approach:** Pulihkan kontrak sentinel admin-ID dan pusatkan akses quant cache melalui helper LRU yang bounded, lalu gunakan helper tersebut pada jalur enrichment yang sudah ada. Verifikasi test audit, test quant terkait, AutoTrade Next, dan regression fail-fast tanpa membuat pengecualian quality gate.

## Boundaries & Constraints

**Always:** Pertahankan perilaku fail-closed terhadap test-user IDs; bedakan `None` dari list kosong; quant cache tetap process-local, deterministic, dan dibatasi `QUANT_CACHE_MAX_PAIRS`; helper clear mengembalikan jumlah entry yang dihapus; perubahan kompatibel dengan caller yang masih membaca `_quant_cache` sebagai dict.

**Ask First:** Setiap kebutuhan untuk mengecualikan test, mengubah ekspektasi test, mengubah kebijakan production admin-ID, atau menyentuh fitur di luar dua blocker legacy ini.

**Never:** Jangan menonaktifkan test, jangan menerima pengecualian quality gate secara diam-diam, jangan mengubah AutoTrade Next domain, dan jangan menyentuh credential/runtime live.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Admin sentinel | `ids_list=None` | Mengembalikan `None` | Tidak dikonversi menjadi `[]` |
| Admin empty list | `ids_list=[]` | Mengembalikan `[]` | Tidak menambah ID |
| Admin mixed IDs | test dan production IDs | Hanya production IDs | Invalid IDs ditolak oleh predicate yang ada |
| Quant get | key ada/tidak ada | Value atau `None`; hit dipromosikan ke MRU | Missing key tidak raise |
| Quant set over cap | pair baru saat cache penuh | LRU lama dikeluarkan | Cap minimum aman dan deterministic |
| Quant clear | cache berisi N entry | Cache kosong, return N | Empty cache return 0 |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/core/config.py` -- filter dan parsing ADMIN_IDS.
- `advanced_crypto_bot/signals/signal_pipeline.py` -- cache quant enrichment process-local.
- `advanced_crypto_bot/tests/test_audit_2026_06_07_remaining_fixes.py` -- kontrak regression kedua bug legacy.
- `advanced_crypto_bot/tests/test_quant_integration.py` -- kompatibilitas cache quant yang sudah ada.

## Tasks & Acceptance

**Execution:**
- [x] `advanced_crypto_bot/core/config.py` -- pertahankan sentinel `None` sambil mempertahankan filtering production ID untuk iterable nyata.
- [x] `advanced_crypto_bot/signals/signal_pipeline.py` -- tambahkan bounded LRU helper API dan arahkan jalur enrichment ke helper tersebut.
- [x] `advanced_crypto_bot/tests/test_audit_2026_06_07_remaining_fixes.py` -- jalankan kontrak audit tanpa mengubah ekspektasi; tambahkan test hanya bila edge case belum tercakup.

**Acceptance Criteria:**
- Given dua blocker legacy saat ini, when focused regression dijalankan, then seluruh test audit admin-ID dan quant cache lulus tanpa deselection.
- Given cache melebihi cap, when entry baru ditulis, then entry LRU dikeluarkan dan get mempromosikan entry menjadi MRU.
- Given perbaikan selesai, when AutoTrade Next dan regression fail-fast dijalankan, then tidak ada failure dari dua blocker ini dan tidak ada pengecualian quality gate baru.

## Spec Change Log

## Verification

**Commands:**
- `venv/bin/python -m pytest -q tests/test_audit_2026_06_07_remaining_fixes.py` -- seluruh test audit lulus.
- `venv/bin/python -m pytest -q tests/test_quant_integration.py` -- integrasi quant cache tetap lulus.
- `venv/bin/python -m pytest -q tests/autotrade_next` -- seluruh kontrak AutoTrade Next tetap lulus.
- `venv/bin/python -m pytest -q -x --tb=short` -- tidak berhenti pada dua blocker legacy ini.
- `git diff --check` -- tidak ada whitespace error.

## Suggested Review Order

**Bounded quant-cache contract**

- Mulai dari helper LRU atomik, cap deterministic, dan clear yang terukur.
  [`signal_pipeline.py:33`](../../advanced_crypto_bot/signals/signal_pipeline.py#L33)

- Jalur enrichment memakai helper tanpa mengubah TTL maupun payload quant.
  [`signal_pipeline.py:812`](../../advanced_crypto_bot/signals/signal_pipeline.py#L812)

**Admin-ID sentinel compatibility**

- Sentinel `None` dipertahankan sebelum filtering production ID yang sudah ada.
  [`config.py:88`](../../advanced_crypto_bot/core/config.py#L88)
