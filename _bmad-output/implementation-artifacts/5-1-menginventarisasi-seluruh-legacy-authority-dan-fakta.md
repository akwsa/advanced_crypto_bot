---
story_id: "5.1"
title: "Menginventarisasi seluruh legacy authority dan fakta"
epic: "5"
status: "done"
baseline_commit: "5de4a38"
---

# Story 5.1: Menginventarisasi seluruh legacy authority dan fakta

Status: done

## Story

As a Officer,
I want mengetahui setiap writer, submitter, credential, process, file, order, trade, balance, dan Position legacy,
so that tidak ada mutator tersembunyi atau fakta ambigu yang lolos cutover.

## Acceptance Criteria

1. **Legacy Inventory & Classification**:
   - Mengklasifikasikan setiap entitas legacy menjadi `PROVEN_OPEN`, `PROVEN_CLOSED`, `AMBIGUOUS`, atau `NON_CANONICAL_HISTORY`.
   - Mengkarantina entitas ambigu (*ambiguous exposure*) dan menolak kesiapan cutover jika terdapat komponen yang belum terklasifikasi.
