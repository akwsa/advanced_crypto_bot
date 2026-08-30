---
title: "Spec Story 3.3 — Versioned Portfolio Risk Governor"
story: "3.3"
status: done
baseline_commit: "9b97fb6"
date: "2026-08-30"
---

# SPEC Kernel

## Intent

Membangun RiskGovernor fail-closed yang menggunakan canonical equity/current-risk snapshot, policy limits versioned, exact common-scale arithmetic, dan deterministic quantity clamps yang tidak pernah memperbesar requested quantity.

## Required Limits

- Position ≤10%; portfolio exposure ≤40%; daily loss ≤2%; planned loss ≤0.5%; hard drawdown trigger 10%; rolling entry turnover baseline ≤40%.
- Liquidity, correlation, stop distance, volatility, cost, dan uncertainty hanya dapat menurunkan quantity.
- Missing stop/exit capacity, stale/future mark, insufficient minimum depth, atau high-water mismatch menolak entry tanpa fabricated valuation.
- Risk-reducing EXIT dibatasi position quantity tetapi tidak memakai entry-turnover gate.

## Scope Boundary

- Rewrite file bersih `domain/risk_governor.py`, public exports, contracts, dan strict dependency matrix.
- Arithmetic lokal; tidak mengedit atau mengandalkan dirty `numeric.py`.
- Runtime persistence/policy registry/valuation ingestion dan VM tetap out of scope.

## Completion Policy

Pure kernel dapat menaikkan factual verdict dari FAIL ke PARTIAL. PASS memerlukan authenticated policy registry, persisted RiskState/reservation integration, dan runtime entry/EXIT wiring melalui fenced CAS.

## Execution Record

- RED: import collection gagal karena versioned policy/context types belum ada.
- GREEN awal: 12/12 focused PASS; adjustment fixture diperbaiki karena enam clamp 50% secara benar jatuh di bawah minimum quantity.
- Review fixes: exact stop-derived planned-loss floor, result reason/allowance invariants, equity freshness, hard drawdown equality trigger, dan strict policy/context ref kinds.
- Final: risk 14/14; risk+identity 37/37; all contracts 416/416; Strategy2/dry-run 61/61; compile/diff gates PASS.
- Disposition: implementation scope selesai; Story tetap `review/PARTIAL` berdasarkan Completion Policy.
