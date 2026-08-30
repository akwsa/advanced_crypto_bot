---
title: 'Remediasi Story 2.2 MarketSnapshot dan Instrument Eligibility'
type: 'bugfix'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 1
baseline_commit: '5a83c99bc67f44917ac08188b45003c057bd88cb'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/advanced_crypto_bot/docs/AUDIT_FAKTUAL_MIGRASI_AUTOTRADE_NEXT_2026-08-30.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.2 masih membandingkan raw `ScaledInteger.units`, tidak membekukan requested size/rules/universe proof, dan belum membedakan pair-local ineligibility dari systemic entry freeze. Akibatnya order book mixed-scale dapat menghasilkan ordering, capacity, WAP, dan eligibility yang salah meskipun contract suite hijau.

**Approach:** Perketat pure domain contract `MarketSnapshot` dan `InstrumentEligibility`, bind seluruh decision input ke content ref, serta tambahkan negative contract tests lebih dahulu. Exact coverage adalah `capacity >= requested_size`; WAP dibulatkan konservatif pada instrument price scale: ASK naik, BID turun.

## Boundaries & Constraints

**Always:** Pertahankan tuple return `(capacity, avg_price)`, field order `OrderBookLevel(price, quantity)`, UTC event/receive time terpisah, venue/ingest cursor terpisah, immutable tuple/content binding, typed errors/reasons, dan zero network/database/framework dependency. Bandingkan nilai ekonomi pada common scale; reject nonpositive value dan silent precision loss. Eligibility pair-local tetap `INELIGIBLE` agar Decision layer yang menghasilkan ABSTAIN. Systemic failure hanya menghasilkan immutable signal/request yang cukup bagi layer berikutnya; recovery dan protective path tetap allowed tanpa memutasi SafetyState.

**Ask First:** Perubahan pada dirty user-owned `numeric.py`, `accounting.py`, `fencing.py`, atau `core/config.py`; perubahan behavior simulator Story 2.3 selain normalisasi arithmetic quantity common-scale yang secara eksplisit diizinkan pengguna pada 2026-08-30; public re-export yang bertabrakan dengan `candidate.EligibilityReason`; perubahan rounding/coverage contract yang sudah disetujui; file baru di luar code map.

**Never:** Reset/checkout/stash/clean perubahan pengguna; binary float; last-price/candle fallback; live API/credential; persistence atau mutable SafetyState; simulator/accounting/recovery implementation; status `done`; memasukkan `scalper_pairs.txt` ke scope.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Executable mixed-scale book | Qualified L2, frozen rules/universe proof, depth exactly target | Immutable snapshot; economic ordering/capacity benar; deterministic side-aware WAP | N/A |
| Invalid level/book | Zero/negative value, wrong type, unordered/crossed book, empty execution side | Snapshot tidak terbentuk | Typed `MarketEvidenceError` tanpa partial result |
| Insufficient depth | Economic capacity di bawah target | Entry tidak executable | Pair-local `INELIGIBLE/INSUFFICIENT_DEPTH` |
| Invalid instrument rule | Min/precision/tick/step/metadata/effective membership gagal | Pair-local entry veto dengan reason spesifik | Tidak ada fallback |
| Systemic integrity failure | Qualified input menyatakan shared source integrity failure | Portfolio entry-freeze signal; recovery/protective allowed | Tidak membersihkan/memutasi SafetyState |
| Repeated input | Input identik dievaluasi 100 kali | Snapshot ref, capacity, WAP, dan eligibility identik | N/A |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/autotrade_next/domain/market.py` -- Story 2.2 types, snapshot construction, book walk, eligibility, dan existing Story 2.1 freeze/recovery contracts.
- `advanced_crypto_bot/tests/autotrade_next/contract/test_market_snapshot_eligibility.py` -- primary RED/GREEN contract matrix.
- `advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py` -- compatibility consumer untuk `MarketSnapshot.create` dan tuple executable-price.
- `advanced_crypto_bot/autotrade_next/domain/simulator.py` -- normalisasi arithmetic quantity common-scale yang diizinkan pengguna; lifecycle dan fee policy tidak berubah.
- `_bmad-output/implementation-artifacts/2-2-membentuk-executable-market-snapshot-dan-instrument-eligibility.md` -- completion evidence/file list setelah gates.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` -- sinkronisasi ke `review`, bukan `done`.

## Tasks & Acceptance

**Execution:**
- [x] `advanced_crypto_bot/tests/autotrade_next/contract/test_market_snapshot_eligibility.py` -- tambah RED matrix untuk invalid values/types, mixed scales, exact/insufficient coverage, requested-size/hash binding, instrument rules, effective membership, systemic scope, rounding, immutability, dan 100-run determinism.
- [x] `advanced_crypto_bot/autotrade_next/domain/market.py` -- implementasikan typed frozen rules/universe evidence, invariant level/book, exact common-scale comparison/book walk, requested-size binding, conservative WAP, specific eligibility reasons, dan systemic signal tanpa persistence.
- [x] `advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py` -- migrasikan hanya fixture/call signature yang diperlukan dan buktikan `(capacity, avg_price)` tetap kompatibel.
- [x] `advanced_crypto_bot/autotrade_next/domain/simulator.py` dan simulator contract test -- bandingkan capacity/requested quantity pada common scale dan buktikan equivalent mixed-scale quantity menghasilkan fill yang benar.
- [x] `_bmad-output/implementation-artifacts/2-2-membentuk-executable-market-snapshot-dan-instrument-eligibility.md` dan `sprint-status.yaml` -- catat plan, RED/GREEN/gates, file list, lalu set konsisten ke `review` setelah independent review-ready gate.

**Acceptance Criteria:**
- Given mixed-scale ordered L2 dan target quantity positif, when snapshot dibuat dan execution side dihitung, then capacity memakai nilai ekonomi, exact coverage diterima, dan WAP deterministic pada instrument price scale dengan ASK-ceil/BID-floor.
- Given qualified point-in-time metadata dan universe membership, when snapshot dibentuk, then requested size, rules/metadata version, effective membership proof, timestamps, cursors, depth, serta relevant quality input immutable dan content-bound.
- Given minimum, precision, increment, spread, freshness, depth, metadata, atau membership failure, when eligibility dievaluasi, then hasil pair-local `INELIGIBLE` memiliki reason spesifik tanpa fallback.
- Given shared/systemic source integrity failure, when eligibility dievaluasi, then hasil membawa portfolio entry-freeze signal serta recovery/protective allowance tanpa mutable safety transition.
- Given malformed, nonpositive, lossy, unordered, crossed, or caller-mutated input, when public boundary dipanggil, then fail-closed typed behavior terjadi dan tidak ada partial executable snapshot.
- Given input identik, when construction/evaluation diulang 100 kali, then canonical reference dan semantic result identik tanpa float, clock, network, atau global mutable state.

## Spec Change Log

- 2026-08-30: Implementasi review-ready selesai. RED terkonfirmasi 14 gagal/7 lulus; focused GREEN 21/21; seluruh contract 319/319; Strategy2/dry-run 61/61; compileall dan diff-check exit 0.
- 2026-08-30 (review loop 1): Blind review menemukan raw-unit arithmetic simulator tidak kompatibel dengan normalized snapshot capacity. Pengguna mengizinkan perubahan terbatas common-scale plus regression test; lifecycle dan fee policy wajib dipertahankan (KEEP: frozen snapshot, ASK-ceil/BID-floor, pair-local eligibility, systemic signal, seluruh gate hijau).
- 2026-08-30 (review loop 1 implementation): simulator RED 1 gagal/2 lulus, lalu GREEN 3/3; final focused 24/24, seluruh contract 322/322, Strategy2/dry-run 61/61, compileall dan diff-check exit 0. Hardening review juga membatasi market scale dan menolak hasil eligibility kontradiktif.
- 2026-08-30 (review loop 1 final patches): requested-size comparison dibuat economic/common-scale, fee diberi exact notional scale, systemic signal mengikat originating snapshot, aggregate overflow menjadi typed market error, serta tick/overflow/provenance/fee regression ditambah. Final gates: focused 26/26, contracts 324/324, Strategy2/dry-run 61/61, compileall dan diff-check exit 0.

## Design Notes

Gunakan local exact/common-scale helpers dalam `market.py`; `numeric.py` tetap read-only karena memiliki dirty change milik pengguna. Downscale hanya boleh terjadi melalui rounding policy WAP yang eksplisit. Jangan re-export market `EligibilityReason` dari `domain.__init__` karena nama itu sudah dipakai Candidate contract.

## Verification

**Commands:**
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider tests/autotrade_next/contract/test_market_snapshot_eligibility.py` -- expected RED sebelum implementation, lalu seluruh focused tests PASS.
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider tests/autotrade_next/contract` -- expected seluruh baseline 304 dan test baru PASS.
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider tests/test_strategy2_contracts.py tests/test_strategy2_isolation.py tests/test_strategy2_repository.py tests/test_strategy2_state_machine.py tests/test_autotrade_dryrun_signal_cycle.py` -- expected baseline 61 dan seluruh regression PASS.
- `PYTHONPYCACHEPREFIX=$(mktemp -d) venv/bin/python -m compileall -q autotrade_next` -- expected exit 0 dan tidak mengubah tracked workspace.
- `git diff --check -- advanced_crypto_bot/autotrade_next/domain/market.py advanced_crypto_bot/tests/autotrade_next/contract/test_market_snapshot_eligibility.py advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py` -- expected exit 0 dari repository root.

## Suggested Review Order

**Frozen executable evidence**

- Mulai dari aggregate immutable snapshot dan seluruh decision input yang content-bound.
  [`market.py:1186`](../../advanced_crypto_bot/autotrade_next/domain/market.py#L1186)

- Periksa common-scale book walk serta ASK-ceil dan BID-floor WAP.
  [`market.py:1252`](../../advanced_crypto_bot/autotrade_next/domain/market.py#L1252)

**Eligibility dan systemic safety**

- Tinjau pair-local veto, exact depth coverage, serta typed failure reasons.
  [`market.py:1414`](../../advanced_crypto_bot/autotrade_next/domain/market.py#L1414)

- Pastikan systemic freeze signal mengikat snapshot penyebab dan menjaga recovery.
  [`market.py:1365`](../../advanced_crypto_bot/autotrade_next/domain/market.py#L1365)

**Simulator compatibility**

- Verifikasi arithmetic quantity common-scale tanpa mengubah lifecycle simulator.
  [`simulator.py:121`](../../advanced_crypto_bot/autotrade_next/domain/simulator.py#L121)

**Regression evidence**

- Uji precision pair-local dan execution-side binding lebih dahulu.
  [`test_market_snapshot_eligibility.py:129`](../../advanced_crypto_bot/tests/autotrade_next/contract/test_market_snapshot_eligibility.py#L129)

- Uji overflow capacity tetap menjadi typed market failure.
  [`test_market_snapshot_eligibility.py:209`](../../advanced_crypto_bot/tests/autotrade_next/contract/test_market_snapshot_eligibility.py#L209)

- Uji mixed-scale simulator dan fee-scale economic correctness.
  [`test_simulator_lifecycle.py:87`](../../advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py#L87)

**Status dan bukti**

- Cocokkan semua hasil RED/GREEN serta final verification gates.
  [`2-2-membentuk-executable-market-snapshot-dan-instrument-eligibility.md:44`](2-2-membentuk-executable-market-snapshot-dan-instrument-eligibility.md#L44)

- Pastikan Story 2.2 tetap review sampai human acceptance.
  [`sprint-status.yaml:32`](sprint-status.yaml#L32)
