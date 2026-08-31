---
title: "Spec Story 3.4 — Additive Safety Cause Lattice"
story: "3.4"
status: in-progress
baseline_commit: "9ab1897"
date: "2026-08-30"
---

# SPEC Kernel

## Intent

Mengganti delete-by-ID safety state dengan deterministic active-cause lattice dan additive clear history yang hanya menerima cause-specific predicate, new evidence, exact sequence, serta authenticated authority reference.

## Invariants

1. Scope order canonical `ORDER < INSTRUMENT < PORTFOLIO < AUTHORITY`; severity join adalah maximum dan active cause tidak saling menghapus.
2. Cause ID diturunkan dari kind/scope/evidence/predicate/sequence/time; caller tidak memilih ID.
3. Canonical cause matrix menentukan minimum scope/severity, clear predicate, dan protective actions.
4. Effective protective behavior adalah intersection active causes; entry tetap frozen selama satu freeze/halt cause aktif.
5. Clear proof harus exact active cause/predicate/sequence, membawa evidence baru, terjadi sesudah cause, dan diikat authority ref.
6. Clear menghasilkan additive record dan hanya menghapus cause target dari active set.

## Completion Policy

Pure lattice maksimal PARTIAL sampai cause/clear persistence, authenticated evidence resolver, restart replay, dan runtime entry/protective gating melalui fenced CAS tersedia.
