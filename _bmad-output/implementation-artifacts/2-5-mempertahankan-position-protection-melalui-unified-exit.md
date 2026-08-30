---
story_id: "2.5"
title: "Mempertahankan Position protection melalui unified EXIT"
epic: "2"
status: "review"
baseline_commit: "9244accad0acd82361b6aa43bfa8aaef82525e2d"
---

# Story 2.5: Mempertahankan Position protection melalui unified EXIT

Status: review

## Story

As a Officer,
I want SL, invalidation, profit, trailing, time, alpha, dan operator exit memakai satu canonical path,
so that remaining quantity selalu protected dan tidak ditutup dua kali.

## Acceptance Criteria

1. **Unified Exit Processing**:
   - Menyatukan seluruh pemicu EXIT (Stop-Loss, Take-Profit, Invalidation, Trailing, Time Expiry, Alpha Exit, Operator Exit) dalam satu alur terpusat `ExitEvaluator`.
   - Mencegah penutupan ganda (*double exit*) dengan memverifikasi sisa kuantitas posisi aktif.

## Factual Reopen — 2026-08-30

- Baseline audit E11: **FAIL**.
- Source hanya mencakup operator/time/SL/TP dan memakai raw-unit comparison yang salah pada mixed scale.
- Missing: fixed full precedence, invalidation/drawdown/reconciliation/trailing/alpha, persisted high-water/deadline/remaining quantity, deterministic key, expected sequence, same coordinator, partial Fill protection, dan quarantined dust evidence.
- Remediasi dibatasi ke semantic kernel/UoW contract; durable persistence tetap dependency sehingga verdict maksimal PARTIAL.

## Implementation Plan

- Ganti evaluator raw-unit dengan immutable Position protection transition dan exact common-scale arithmetic.
- Terapkan precedence AD-04: operator → drawdown → invalidation/stop → reconciliation → profit/trailing/time → alpha → hold.
- Gunakan evidence reference untuk operator/drawdown/invalidation/reconciliation/alpha; jangan percaya boolean self-attestation.
- Bentuk deterministic Position event/outbox dan Story 2.4 SELL `ExecutionPreparation` dalam satu composite commit bundle sebelum dispatch.
- Kurangi remaining Position hanya dari canonical SELL `SettlementEntry`; pertahankan protection pada partial Fill dan quarantine dust dengan valuation evidence.

## Completion Evidence — 2026-08-30

- Review-ready implementation commit: `a568aee`.
- RED: collection error `autotrade_next.application.exit` belum tersedia.
- Focused unified EXIT + identity/import matrix: 39/39 PASS.
- Seluruh AutoTrade Next contracts: 367/367 PASS.
- Strategy2/dry-run regression: 63/63 PASS.
- `compileall` dan `git diff --check`: exit 0.
- Adversarial hardening mencakup mixed-scale price/quantity, bounded scale, event/command/composite binding, monotonic time, evidence references, deterministic pending order, commit-before-dispatch, exact retry, commit fault, partial/full Fill, overfill/double-close, preexisting/post-Fill dust, dan valuation provenance.
- Factual verdict: **PARTIAL**, bukan PASS/done, karena durable persistence/fence/restart dan atomic coupling ke settlement adapter belum tersedia.

## Known Limits / Dependency Blockers

- `ExitUnitOfWork` masih port + reference memory evidence; belum ada SQLite transaction, writer fence, migration, crash/restart, atau replay proof.
- `apply_exit_fill` sudah memerlukan canonical Story 2.4 `SettlementEntry`, tetapi durable adapter yang mengikat order settlement dan Position protection transition dalam transaction yang sama belum ada.
- Evidence references untuk operator/risk/reconciliation sudah fail-closed sebagai reference, tetapi authorization/approval verification adalah dependency Story 3.7.
- Protective EXIT sengaja tidak memakai entry-freeze gate; runtime composition yang membuktikan bypass hanya untuk risk-reducing action masih deferred.

## File List

- `advanced_crypto_bot/autotrade_next/domain/exit_protection.py`
- `advanced_crypto_bot/autotrade_next/domain/__init__.py`
- `advanced_crypto_bot/autotrade_next/ports/exit.py`
- `advanced_crypto_bot/autotrade_next/ports/__init__.py`
- `advanced_crypto_bot/autotrade_next/application/exit.py`
- `advanced_crypto_bot/autotrade_next/application/__init__.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_exit_protection.py`
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py`
- `_bmad-output/implementation-artifacts/spec-2-5-unified-protective-exit-kernel.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-08-30: Semantic unified protective EXIT kernel review-ready; durable dependency tetap terbuka.
