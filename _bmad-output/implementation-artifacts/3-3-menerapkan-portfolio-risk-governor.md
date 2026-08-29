---
story_id: "3.3"
title: "Menerapkan portfolio RiskGovernor"
epic: "3"
status: "done"
baseline_commit: "cb811db"
---

# Story 3.3: Menerapkan portfolio RiskGovernor

Status: done

## Story

As a Officer,
I want sizing dan entry mematuhi satu canonical equity serta risk envelope,
so that alpha atau pair iteration tidak dapat memperbesar batas risiko.

## Acceptance Criteria

1. **Portfolio Risk Governor**:
   - Membatasi batas risiko maksimum: Position ≤10%, Portfolio Exposure ≤40%, Daily Loss ≤2%, Planned Loss ≤0.5%, Hard Drawdown Limit 10%.
   - Mengembalikan evaluasi `RiskEvaluationResult` yang menolak pembukaan posisi jika salah satu batas terlampaui.
