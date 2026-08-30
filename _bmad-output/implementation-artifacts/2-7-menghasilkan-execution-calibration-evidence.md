---
story_id: "2.7"
title: "Menghasilkan execution calibration evidence"
epic: "2"
status: "review"
baseline_commit: "79df26c"
---

# Story 2.7: Menghasilkan execution calibration evidence

Status: review

## Story

As a Officer,
I want predicted execution dibandingkan dengan shadow-observed behavior secara berlabel,
so that cost model dan simulator latency/shortfall terus terkalibrasi.

## Acceptance Criteria

1. **Execution Calibration Evidence**:
   - Membandingkan predicted slippage/shortfall/latency dengan observed fill metrics secara berlabel.
   - Menghasilkan `ExecutionCalibrationReport` immutable untuk penyesuaian cost policy.

## Factual Reopen — 2026-08-30

- Baseline audit E13: **FAIL**.
- Existing report hanya menyimpan slippage/latency integers tanpa frozen estimator/window/tolerance/scenario, grouping, label authority, sample/evidence, atau metric completeness.
- Remediasi pure-domain; runtime observed corpus/ingestion tetap dependency sehingga verdict maksimal PARTIAL.

## Completion Evidence — 2026-08-30

- RED: import error karena labeled calibration types belum ada.
- Focused calibration 6/6; calibration+identity/import 29/29 PASS.
- Seluruh AutoTrade Next contracts 378/378; Strategy2/dry-run regression 63/63 PASS.
- `compileall` dan `git diff --check` exit 0.
- Frozen context mengikat instrument/Horizon/size/regime, estimator, window, tolerance version, dan scenario corpus.
- Tepat delapan metric wajib; setiap point mengikat predicted/comparison value, label, authority, sample count, dan evidence ref. Label-authority mismatch, missing/duplicate metric, invalid rate/scale/window, dan forged verdict fail closed.
- Venue calibration qualification diturunkan dari seluruh label `OBSERVED`; mixed inferred/simulated/counterfactual selalu `UNSCORABLE` walaupun error kecil.
- Factual verdict **PARTIAL**: runtime corpus ingestion dan bukti shadow/venue aktual belum tersedia.

## File List

- `advanced_crypto_bot/autotrade_next/domain/calibration.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_calibration.py`
- `_bmad-output/implementation-artifacts/spec-2-7-labeled-execution-calibration.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Labeled immutable calibration report review-ready; runtime observed corpus dependency tetap terbuka.
