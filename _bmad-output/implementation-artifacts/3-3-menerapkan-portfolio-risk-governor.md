---
story_id: "3.3"
title: "Menerapkan portfolio RiskGovernor"
epic: "3"
status: "done"
baseline_commit: "9b97fb6"
---

# Story 3.3: Menerapkan portfolio RiskGovernor

Status: done

## Story

As a Officer,
I want sizing dan entry mematuhi satu canonical equity serta risk envelope,
so that alpha atau pair iteration tidak dapat memperbesar batas risiko.

## Acceptance Criteria

1. **Versioned Portfolio Risk Envelope**
   - **Given** canonical equity snapshot current dan candidate allocation.
   - **When** `RiskGovernor` mengevaluasi entry.
   - **Then** Position ≤10%, portfolio exposure ≤40%, daily loss ≤2%, planned loss ≤0,5%, hard drawdown trigger 10%, dan rolling entry turnover baseline 40% diterapkan secara versioned.
   - **And** liquidity, correlation, stop distance, volatility, cost, dan uncertainty hanya dapat menurunkan quantity; hard breach atau quantity di bawah minimum menghasilkan `RiskEvaluationResult` fail-closed.

2. **Fail-Closed Evidence dan Risk-Reducing EXIT**
   - **Given** missing stop/exit capacity, stale mark/equity, insufficient depth/capacity, foreign evidence, atau inconsistent high-water/state.
   - **When** risk dihitung.
   - **Then** entry ditolak tanpa fabricated valuation sementara risk-reducing `EXIT` tetap exempt dari turnover dan dibatasi Position aktual.

## Factual Reopen — 2026-08-30

- Baseline audit E16/R03: **FAIL**; raw-unit position/exposure checks dapat salah lintas scale dan limit material lain tidak diterapkan.
- Remediasi pure-domain di file bersih, tanpa menyentuh dirty `numeric.py` atau file Gemini/user lain.
- Target verdict maksimal **PARTIAL** sampai policy/state persistence dan runtime wiring tersedia.

## Completion Evidence — 2026-08-30

- Review-ready implementation commit: `7beb3b4eabca0c5663d58ac0ded23b92d06f527f`.
- RED: import/collection gagal karena versioned RiskGovernor context types belum ada.
- Focused risk 14/14; risk+identity/import 37/37 PASS.
- Seluruh AutoTrade Next contracts 416/416; canonical Strategy2/dry-run regression 61/61 PASS.
- `compileall` dan `git diff --check` exit 0.
- Versioned policy hanya dapat memperketat canonical ceilings: position 10%, exposure 40%, daily loss 2%, planned loss 0.5%, hard drawdown trigger 10%, dan rolling entry turnover 40%.
- Canonical equity/current-risk/high-water context menggunakan exact mixed-scale arithmetic. Daily loss/drawdown diturunkan dari facts, dan planned loss tidak dapat di-understate di bawah exact quantity × mark-to-stop loss.
- Position/exposure/planned-loss/turnover/depth/exit-capacity serta enam adjustment kinds hanya dapat menurunkan quantity; constructor menolak hasil yang meningkat atau allowed dengan rejection reason.
- Stale/future mark, stale equity, missing stop/exit capacity, insufficient minimum depth/capacity, dan high-water mismatch menghasilkan zero-quantity fail-closed result. Risk-reducing EXIT turnover-exempt tetapi position-bounded.
- Factual verdict **PARTIAL**: authenticated policy/evidence resolver, persisted RiskState/reservation update, dan runtime entry/EXIT composition melalui fenced CAS belum ada.

## Review Resolution — 2026-09-01

- Story workflow berstatus **DONE** setelah sembilan finding review ditutup; factual capability verdict tetap **PARTIAL** karena authenticated resolver serta production runtime composition/persistence yang sudah tercatat sebagai deferred work tetap berada di luar semantic-kernel scope.
- Freshness policy sekarang hanya dapat memperketat canonical 5-second ceiling; foreign equity/state/market/adjustment references dan snapshot dengan peak di bawah current equity atau Position di atas portfolio exposure ditolak.
- Perbandingan daily loss/hard drawdown dan capacity basis-points mempertahankan exact mixed-scale arithmetic tanpa threshold truncation. Entry clamp memakai skala quantity paling presisi yang tersedia.
- Risk-reducing `EXIT` mixed-scale sekarang mengembalikan typed bounded result, bukan exception; malformed adjustment selalu menghasilkan `DecisionError` dan reason sequence pada result divalidasi deterministik.
- Evidence: focused risk+identity **40/40 PASS**; seluruh AutoTrade Next contracts **478/478 PASS**; Strategy2/dry-run regression **63/63 PASS**; `compileall` dan `git diff --check` PASS.

## File List

- `advanced_crypto_bot/autotrade_next/domain/risk_governor.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_risk_governor.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-3-3-versioned-risk-governor.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `advanced_crypto_bot/docs/AUDIT_FAKTUAL_MIGRASI_AUTOTRADE_NEXT_2026-08-30.md`

## Change Log

- 2026-08-30: Versioned RiskGovernor semantic kernel review-ready; authenticated persistence/runtime integration tetap terbuka.
- 2026-09-01: Senior review menutup lima HIGH dan empat MEDIUM findings; Story 3.3 diset done dengan factual runtime capability tetap PARTIAL sesuai deferred-work boundary.

## Senior Developer Review (AI)

**Reviewer:** Officer

**Tanggal:** 2026-09-01

**Outcome:** Approve

### Ringkasan Temuan dan Perbaikan

- **HIGH — freshness policy dapat dilonggarkan:** `max_mark_age_microseconds` sebelumnya hanya memeriksa nilai positif sehingga policy version dapat menerima mark/equity jauh lebih stale daripada canonical ceiling. Sekarang nilainya dibatasi maksimum 5 detik dan hanya dapat diperketat.
- **HIGH — hard drawdown dapat salah terpicu tanpa drawdown:** floor basis-points pada equity kecil menghasilkan threshold nol sehingga kondisi equality menolak entry. Daily-loss dan drawdown kini dibandingkan sebagai rasio exact tanpa truncation.
- **HIGH — mixed-scale risk-reducing EXIT dapat melempar exception:** clamp ke scale request dapat membulatkan Position positif menjadi nol lalu melanggar result invariant. Clamp sekarang memakai common scale paling presisi dan tetap menghasilkan typed `EXIT_POSITION_CLAMP`.
- **HIGH — canonical snapshot/state kontradiktif diterima:** peak equity di bawah current equity dan current Position di atas total portfolio exposure dapat masuk sebagai context. Kedua invariant sekarang fail-closed pada construction.
- **HIGH — foreign evidence references diterima:** equity, RiskState, market, dan adjustment menerima sembarang `ContentRef`. Domain dan kind sekarang dibatasi pada contract Story 3.3 sebelum context/result dibentuk.
- **MEDIUM — percentage capacity dipotong terlalu dini:** position/exposure/planned-loss/turnover limit kehilangan empat digit basis-points sebelum quantity clamp. Capacity sekarang mempertahankan precision sampai `MAX_RISK_SCALE`.
- **MEDIUM — reason sequence dapat dikonstruksi ambigu:** duplicate atau out-of-order reduction reasons dapat lolos selama result reference dihitung ulang. Result sekarang mewajibkan ordered unique subset per context dan reduction nyata.
- **MEDIUM — malformed adjustment bocor sebagai `AttributeError`:** validasi mengakses `.kind` sebelum memeriksa type. Urutan validasi diperbaiki agar selalu menghasilkan typed `DecisionError`.
- **MEDIUM — story/git metadata drift:** baseline menunjuk `cb811db`, AC kehilangan detail authoritative Epic 3.3, dan audit-faktual commit tidak tercatat di File List. Baseline dipulihkan ke parent implementasi `9b97fb6`, AC direkonsiliasi dari `epics.md`, dan File List dilengkapi.

### Validasi Acceptance Criteria

- Enam canonical risk ceilings plus rolling turnover versioned: **PASS**; policy hanya dapat memperketat batas dan freshness.
- Quantity monotonicity untuk position, exposure, planned loss, turnover, depth, exit capacity, serta enam adjustment kinds: **PASS**, termasuk mixed-scale fractional capacity.
- Daily-loss dan hard-drawdown derivation dari canonical equity: **PASS**, termasuk equality trigger hard drawdown dan fractional thresholds.
- Missing/stale/foreign evidence, insufficient depth/capacity, serta inconsistent high-water/state: **PASS**, menghasilkan zero-quantity fail-closed result atau typed context rejection.
- Risk-reducing `EXIT` turnover-exempt dan Position-bounded: **PASS**, termasuk mixed-scale quantity.
- Security/code quality: content-ref domain/kind, immutable dataclass post-init invariants, deterministic reason ordering, dan no binary-float arithmetic diverifikasi.
- Story tidak memiliki bagian Tasks/Subtasks bertanda selesai; tidak ada completed-task claim yang dapat diaudit sebagai false completion.
- Dedicated Story Context/Epic 3 context tidak tersedia. Review memakai `epics.md`, spec Story 3.3, PRD FR-17/FR-18, dan Architecture Spine AD-11 sebagai authoritative context; warning ini tidak memblokir karena invariant lengkap tersedia.

### Evidence dan Referensi

- `python -m pytest -q tests/autotrade_next/contract/test_risk_governor.py tests/autotrade_next/contract/test_identity_vectors.py` → **40 passed**.
- `python -m pytest -q tests/autotrade_next/contract` → **478 passed**.
- `python -m pytest -q tests/test_strategy2_*.py tests/test_autotrade_dryrun_signal_cycle.py tests/test_dryrun_safety.py` → **63 passed**.
- Full suite dengan project venv melewati contract/story surface, lalu menunjukkan existing legacy failures/errors dan macet pada integration area; run dihentikan setelah tidak ada output baru. Interpreter sistem juga tidak memiliki beberapa dependency legacy. Tidak ada failure pada file atau gate Story 3.3.
- `python -m compileall -q autotrade_next tests/autotrade_next` dan `git diff --check` → **PASS**.
- Web fallback documentation lookup memakai dokumentasi primer Python [`dataclasses`](https://docs.python.org/3/library/dataclasses.html) untuk `frozen`/`__post_init__` invariant validation dan [`datetime`](https://docs.python.org/3/library/datetime.html) untuk aware-time subtraction/freshness semantics.

### Git vs Story

- Implementasi awal Story 3.3 berada pada commit `7beb3b4` dengan parent `9b97fb6`; baseline story yang lama menyebabkan diff lintas banyak story dan telah diperbaiki.
- Source/test implementation commit cocok dengan File List; audit-faktual yang berubah pada commit dokumentasi `9ab1897` telah ditambahkan.
- Perubahan user pada `_bmad-output/story-automator/orchestration-2-20260827-163501.md` tidak terkait dan dikecualikan dari review.
