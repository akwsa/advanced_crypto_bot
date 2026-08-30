---
title: 'Remediasi Story 2.3 Deterministic Simulator Lifecycle'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 0
baseline_commit: '13c46fa231deb0de4606cea60f10e496c03f3877'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-2-2-market-snapshot-eligibility-remediation.md'
  - '{project-root}/advanced_crypto_bot/docs/AUDIT_FAKTUAL_MIGRASI_AUTOTRADE_NEXT_2026-08-30.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.3 hanya menamai delapan status tetapi simulator mengeluarkan satu event REJECTED/PARTIAL/FILLED, memakai process-randomized `hash(order_id)`, tidak memiliki shared VenuePort schema, lifecycle sequencing/race semantics, frozen cost/scenario input, atau bukti isolation yang memadai.

**Approach:** Bentuk pure deterministic lifecycle stream dengan shared immutable event/fill schema untuk simulator dan VenuePort, frozen versioned scenario/cost inputs, legal transition reducer, exact L2 fill/cost calculation, serta negative dependency/credential graph tests.

## Boundaries & Constraints

**Always:** Pertahankan `OrderStatus` identity untuk recovery, compatibility wrapper `simulate_execution`, Story 2.2 snapshot/rounding rules, exact scaled-integer math, UTC recorded time, content-bound IDs/events, monotonic sequence, duplicate idempotency, conflicting duplicate/out-of-order fail-closed, dan UNKNOWN entry-freeze semantics untuk consumer berikutnya. Fee dan tax dihitung dari exact per-level filled notional lalu dibulatkan konservatif naik pada frozen quote scale. Lifecycle race memakai recorded order: fill-before-cancel mempertahankan fill; cancel-before-fill menghasilkan CANCELLED; ambiguity menghasilkan UNKNOWN.

**Ask First:** Perubahan public API di luar compatibility wrapper; perubahan `MarketSnapshot`; perubahan accounting/recovery/safety persistence; maker queue model atau learned adverse-selection; runtime integration; file dirty milik pengguna.

**Never:** Python `hash()`, wall clock, UUID/random global, binary float, network/database/Redis, live adapter, private/trade credential read, order submission, accounting mutation, atau klaim deployment.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Full/partial lifecycle | Frozen snapshot, side/size, scenario, fee-tax rules | ACCEPTED→OPEN→FILLED atau PARTIAL; exact fills/costs | Typed rejection for invalid input |
| Terminal scenario | Explicit reject, expire, non-fill, or ambiguity | REJECTED, EXPIRED, CANCELLED, or UNKNOWN stream | No invented fill |
| Cancel/fill race | Recorded ordered actions | Deterministic precedence above | Equal/insufficient evidence → UNKNOWN |
| Duplicate/order fault | Same or conflicting event ID/sequence | Exact duplicate noop | Conflict/regression typed fail-closed |
| Replay | Identical frozen inputs across processes | Identical events, refs, terminal state | No external entropy |

</frozen-after-approval>

## Code Map

- `advanced_crypto_bot/autotrade_next/domain/simulator.py` -- shared lifecycle DTOs, scenario/cost contracts, reducer, deterministic engine, compatibility wrapper.
- `advanced_crypto_bot/autotrade_next/ports/venue.py` -- VenuePort Protocol consuming the exact shared lifecycle schema.
- `advanced_crypto_bot/autotrade_next/ports/__init__.py` dan `domain/__init__.py` -- explicit safe exports.
- `advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py` -- RED/GREEN lifecycle, race, cost, replay, schema compatibility matrix.
- `advanced_crypto_bot/tests/autotrade_next/contract/test_dry_run_isolation.py` -- AST dependency and sanitized credential-provider isolation contract.
- `advanced_crypto_bot/tests/autotrade_next/contract/test_identity_vectors.py` -- explicit layer/import allowlist untuk shared VenuePort baru.
- Story 2.3 artifact dan `sprint-status.yaml` -- factual evidence/status synchronization.

## Tasks & Acceptance

**Execution:**
- [x] Tambah RED contracts untuk seluruh matrix, subprocess determinism, legal transitions, shared schema, fees/tax, dan isolation.
- [x] Implementasikan versioned frozen lifecycle/cost/scenario contracts dan deterministic event stream tanpa I/O.
- [x] Tambahkan VenuePort Protocol yang memakai exact shared event/fill types; pertahankan wrapper lama.
- [x] Dokumentasikan RED/GREEN/full gates, findings, file list, dan status review.

**Acceptance Criteria:**
- Given input identik, when lifecycle dijalankan berulang dan lintas `PYTHONHASHSEED`, then ordered canonical event stream dan terminal result identik.
- Given setiap scenario/race, when reducer memproses evidence sequence, then hanya transition legal terjadi dan duplicate/out-of-order tidak menggandakan effect.
- Given maker/taker fee-tax dan adverse/latency input, when fill dibentuk, then exact notional/cost serta recorded timestamps deterministic dan content-bound.
- Given VenuePort atau simulator producer, when event diterbitkan, then keduanya memakai type/schema yang sama.
- Given DRY RUN dependency graph, when isolation contract diperiksa, then live-submit path dan trade-capable credential provider tidak reachable.

## Spec Change Log

- 2026-08-30: Implementation review-ready. RED menghasilkan 2 collection errors; focused GREEN awal 14/14 dan final boundary matrix 16/16; identity+focused 39/39; seluruh contracts 337/337; Strategy2/dry-run 61/61; compileall dan diff-check exit 0.
- 2026-08-30: Adversarial patch memperbaiki recorded-action timing, ambiguous ordering, lifecycle conservation/fill-prefix invariants, explicit nonterminal PARTIAL, single-rounding fee-tax, full subprocess replay, transitive isolation graph, dan serialized shared-schema proof. Final gates: focused 18/18, contracts 339/339, Strategy2/dry-run 61/61, compileall/diff-check exit 0.

## Design Notes

Advanced queue-position learning tetap ditunda. Baseline adverse selection berupa frozen deterministic scenario adjustment/corpus, bukan model yang mengklaim observed venue behavior. Event IDs dan pseudo-random stream harus berasal dari domain-separated SHA-256 atas version, scenario seed, order ID, dan sequence.

## Verification

**Commands:**
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider tests/autotrade_next/contract/test_simulator_lifecycle.py tests/autotrade_next/contract/test_dry_run_isolation.py` -- RED dahulu, lalu seluruh focused PASS.
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider tests/autotrade_next/contract` -- seluruh contract PASS.
- `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q -p no:cacheprovider tests/test_strategy2_contracts.py tests/test_strategy2_isolation.py tests/test_strategy2_repository.py tests/test_strategy2_state_machine.py tests/test_autotrade_dryrun_signal_cycle.py` -- 61 regression PASS.
- `PYTHONPYCACHEPREFIX=/tmp/story23-pycache venv/bin/python -m compileall -q autotrade_next` dan `git diff --check` -- exit 0.

## Suggested Review Order

**Frozen simulator contract**

- Mulai dari versioned scenario yang menghapus entropy eksternal dan Python hash.
  [`simulator.py:100`](../../advanced_crypto_bot/autotrade_next/domain/simulator.py#L100)

- Periksa shared event schema, content binding, dan cumulative quantity invariants.
  [`simulator.py:199`](../../advanced_crypto_bot/autotrade_next/domain/simulator.py#L199)

**Lifecycle integrity**

- Tinjau reducer legal transitions, duplicate handling, conservation, dan fill-prefix protection.
  [`simulator.py:307`](../../advanced_crypto_bot/autotrade_next/domain/simulator.py#L307)

- Ikuti execution engine untuk race timing, exact book walk, dan single-rounding costs.
  [`simulator.py:383`](../../advanced_crypto_bot/autotrade_next/domain/simulator.py#L383)

**Shared boundary dan isolation**

- Pastikan VenuePort menerima exact shared lifecycle event type.
  [`venue.py:8`](../../advanced_crypto_bot/autotrade_next/ports/venue.py#L8)

- Audit transitive dependency closure terhadap I/O, credential, dan submission paths.
  [`test_dry_run_isolation.py:48`](../../advanced_crypto_bot/tests/autotrade_next/contract/test_dry_run_isolation.py#L48)

**Regression evidence**

- Verifikasi ordered lifecycle, per-level fills, maker/taker fee, dan tax evidence.
  [`test_simulator_lifecycle.py:183`](../../advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py#L183)

- Periksa cancel/fill precedence dan UNKNOWN untuk evidence ambigu.
  [`test_simulator_lifecycle.py:251`](../../advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py#L251)

- Pastikan subprocess replay membandingkan full canonical lifecycle stream.
  [`test_simulator_lifecycle.py:360`](../../advanced_crypto_bot/tests/autotrade_next/contract/test_simulator_lifecycle.py#L360)

**Status dan bukti**

- Cocokkan RED/GREEN, review patches, dan seluruh final gates.
  [`2-3-menjalankan-satu-deterministic-simulator-lifecycle.md:37`](2-3-menjalankan-satu-deterministic-simulator-lifecycle.md#L37)

- Story tetap review sampai human acceptance diberikan.
  [`sprint-status.yaml:33`](sprint-status.yaml#L33)
