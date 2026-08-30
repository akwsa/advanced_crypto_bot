---
title: 'Story 2.7 Labeled Execution Calibration Evidence'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 1
baseline_commit: '79df26c'
---

## Intent

Replace the four-integer report with a content-bound frozen context and exactly eight TCA metrics per Horizon/size/regime. Labels must be authority-consistent; any non-observed datapoint makes venue-readiness `UNSCORABLE`, never caller-certified.

## Tasks

- [x] RED label/context/metric/tolerance/report contracts.
- [x] Pure immutable report and derived venue-readiness verdict.
- [x] Full gates, review, docs, isolated commits.

Durable corpus ingestion/runtime calibration remains deferred; verdict maximum PARTIAL.

## Verification

- RED import error; final calibration 6/6, calibration+identity 29/29, all contracts 378/378, Strategy2/dry-run 63/63 PASS; compile/diff-check exit 0.

## Review Disposition

- Patched full metric completeness/order, frozen grouping/context, content identity, scale/rate/window/sample guards, label-authority consistency, tolerance scoring, and derived `UNSCORABLE` for every non-observed mix.
- Deferred actual venue/shadow corpus ingestion, evidence-reference resolver, scheduled windows, report persistence, and promotion consumer wiring.
