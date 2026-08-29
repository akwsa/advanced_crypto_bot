---
story_id: "2.7"
title: "Menghasilkan execution calibration evidence"
epic: "2"
status: "done"
baseline_commit: "3c7c541"
---

# Story 2.7: Menghasilkan execution calibration evidence

Status: done

## Story

As a Officer,
I want predicted execution dibandingkan dengan shadow-observed behavior secara berlabel,
so that cost model dan simulator latency/shortfall terus terkalibrasi.

## Acceptance Criteria

1. **Execution Calibration Evidence**:
   - Membandingkan predicted slippage/shortfall/latency dengan observed fill metrics secara berlabel.
   - Menghasilkan `ExecutionCalibrationReport` immutable untuk penyesuaian cost policy.
