---
story_id: "3.3"
title: "Menerapkan portfolio RiskGovernor"
epic: "3"
status: "review"
baseline_commit: "cb811db"
---

# Story 3.3: Menerapkan portfolio RiskGovernor

Status: review

## Story

As a Officer,
I want sizing dan entry mematuhi satu canonical equity serta risk envelope,
so that alpha atau pair iteration tidak dapat memperbesar batas risiko.

## Acceptance Criteria

1. **Portfolio Risk Governor**:
   - Membatasi batas risiko maksimum: Position ≤10%, Portfolio Exposure ≤40%, Daily Loss ≤2%, Planned Loss ≤0.5%, Hard Drawdown Limit 10%.
   - Mengembalikan evaluasi `RiskEvaluationResult` yang menolak pembukaan posisi jika salah satu batas terlampaui.

## Factual Reopen — 2026-08-30

- Baseline audit E16/R03: **FAIL**; raw-unit position/exposure checks dapat salah lintas scale dan limit material lain tidak diterapkan.
- Remediasi pure-domain di file bersih, tanpa menyentuh dirty `numeric.py` atau file Gemini/user lain.
- Target verdict maksimal **PARTIAL** sampai policy/state persistence dan runtime wiring tersedia.

## Completion Evidence — 2026-08-30

- RED: import/collection gagal karena versioned RiskGovernor context types belum ada.
- Focused risk 14/14; risk+identity/import 37/37 PASS.
- Seluruh AutoTrade Next contracts 416/416; canonical Strategy2/dry-run regression 61/61 PASS.
- `compileall` dan `git diff --check` exit 0.
- Versioned policy hanya dapat memperketat canonical ceilings: position 10%, exposure 40%, daily loss 2%, planned loss 0.5%, hard drawdown trigger 10%, dan rolling entry turnover 40%.
- Canonical equity/current-risk/high-water context menggunakan exact mixed-scale arithmetic. Daily loss/drawdown diturunkan dari facts, dan planned loss tidak dapat di-understate di bawah exact quantity × mark-to-stop loss.
- Position/exposure/planned-loss/turnover/depth/exit-capacity serta enam adjustment kinds hanya dapat menurunkan quantity; constructor menolak hasil yang meningkat atau allowed dengan rejection reason.
- Stale/future mark, stale equity, missing stop/exit capacity, insufficient minimum depth/capacity, dan high-water mismatch menghasilkan zero-quantity fail-closed result. Risk-reducing EXIT turnover-exempt tetapi position-bounded.
- Factual verdict **PARTIAL**: authenticated policy/evidence resolver, persisted RiskState/reservation update, dan runtime entry/EXIT composition melalui fenced CAS belum ada.

## File List

- `advanced_crypto_bot/autotrade_next/domain/risk_governor.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_risk_governor.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-3-3-versioned-risk-governor.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Versioned RiskGovernor semantic kernel review-ready; authenticated persistence/runtime integration tetap terbuka.
