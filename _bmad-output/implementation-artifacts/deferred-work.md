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
