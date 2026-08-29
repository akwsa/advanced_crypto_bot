---
story_id: "5.4"
title: "Mengimpor fakta terbukti dan mengarantina ambiguity"
epic: "5"
status: "done"
baseline_commit: "941de92"
---

# Story 5.4: Mengimpor fakta terbukti dan mengarantina ambiguity

Status: done

## Story

As a Officer,
I want hanya legacy execution yang terbukti menjadi canonical fact,
so that migration tidak memalsukan strategy decision atau ghost Position.

## Acceptance Criteria

1. **Legacy Fact Import & Ambiguity Quarantine**:
   - Mengimpor eksekusi legacy yang terbukti (*proven execution*) menjadi `ApprovedExternalFact`.
   - Mengarantina fakta ambigu (*ambiguous facts*) dan memisahkan histori non-kanonikal.
