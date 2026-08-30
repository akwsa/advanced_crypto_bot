# Deferred Work

- source_spec: `spec-2-2-market-snapshot-eligibility-remediation.md`
  summary: Tetapkan fee rounding policy simulator berdasarkan exact walked notional, bukan rounded WAP.
  evidence: Review Story 2.2 menemukan ASK-ceil/BID-floor WAP dapat menggeser fee; ini merupakan kebijakan Story 2.3 yang tidak termasuk izin arithmetic quantity terbatas.

- source_spec: `spec-2-2-market-snapshot-eligibility-remediation.md`
  summary: Wiring orchestration wajib mengevaluasi InstrumentEligibility sebelum memanggil simulator.
  evidence: Simulator domain tetap dapat menerima snapshot stale, over-spread, non-member, atau systemic-failed jika caller melewati eligibility; integrasi runtime belum termasuk scope pure-domain Story 2.2.

- source_spec: `spec-2-4-fill-authoritative-settlement-kernel.md`
  summary: Implementasikan durable SQLite settlement UnitOfWork dengan persistent writer fence dan offline schema migration.
  evidence: Story 2.4 semantic kernel tidak dapat membuktikan production atomic commit sebelum dependency Story 3.1 dan 5.3 tersedia; verdict maksimal PARTIAL.

- source_spec: `spec-2-4-fill-authoritative-settlement-kernel.md`
  summary: Persist canonical account cash, per-instrument positions, reservations, dan account revision CAS dalam satu consistency boundary.
  evidence: Semantic UoW sekarang membawa expected account revision dan account+instrument lookup, tetapi reference memory adapter tidak membuktikan cross-order/cross-instrument concurrency atau reservation recovery; dependency Story 3.1/3.2/5.3.

- source_spec: `spec-2-4-fill-authoritative-settlement-kernel.md`
  summary: Persist dan pulihkan UNKNOWN entry freeze lintas restart/process sebelum runtime authority diberikan.
  evidence: Prepare handler fail-closed melalui `is_entry_frozen(scope, account)`, tetapi durable freeze cause, clear predicate, dan audited recovery merupakan dependency Story 3.4/3.7.

- source_spec: `spec-2-5-unified-protective-exit-kernel.md`
  summary: Implementasikan durable ExitUnitOfWork yang atomically mengikat Position/Policy transition, canonical event, outbox, Intent/Order, Story 2.4 settlement Fill, writer fence, dan expected sequence.
  evidence: Semantic composite bundle serta commit-fault reference tests lulus, tetapi belum ada SQLite adapter/migration/crash proof; dependency Story 3.1/5.3 dan verdict Story 2.5 maksimal PARTIAL.

- source_spec: `spec-2-5-unified-protective-exit-kernel.md`
  summary: Verifikasi operator/risk/reconciliation evidence reference melalui authenticated approval/cause registry sebelum runtime command diterima.
  evidence: Kernel tidak lagi menerima boolean self-attestation, tetapi reference existence/authorization verification merupakan dependency Story 3.4/3.7.

- source_spec: `spec-2-6-deterministic-recovery-plan.md`
  summary: Implementasikan durable startup loader/replay untuk recovery checkpoint, inbox/outbox acknowledgment, dispatcher redelivery, projection rebuild, and RTO/RPO crash matrix.
  evidence: Semantic checkpoint dan deterministic plan lulus contract tests, tetapi tidak membuktikan state process/database sesudah crash; dependency Story 3.1/5.3.

- source_spec: `spec-2-6-deterministic-recovery-plan.md`
  summary: Implementasikan authenticated, fenced, additive correction command handler untuk empat correction kinds.
  evidence: Correction request sudah memerlukan evidence, approval, idempotency, dan exact journal high-water; verifier/atomic journal commit masih dependency Story 3.7/5.3.

- source_spec: `spec-2-7-labeled-execution-calibration.md`
  summary: Ingest dan resolve actual shadow/venue TCA corpus ke frozen calibration window lalu persist/report ke promotion consumer.
  evidence: Pure report menolak label-authority mismatch dan non-observed venue scoring, tetapi reference resolver, scheduled corpus ingestion, persistence, dan promotion wiring belum tersedia.
