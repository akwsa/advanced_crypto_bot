# Deferred Work

- source_spec: `spec-3-3-versioned-risk-governor.md`
  summary: Resolve authenticated RiskPolicy/equity/market/adjustment evidence dan atomically persist RiskState, reservation, decision, event, serta outbox through fenced expected-sequence CAS.
  evidence: Pure RiskGovernor menegakkan seluruh canonical ceilings dan quantity monotonicity, tetapi ContentRef existence/authority dan runtime state mutation belum diverifikasi; Story 3.3 maksimal PARTIAL.

- source_spec: `spec-3-1-durable-fenced-journal.md`
  summary: Wire `SQLiteFencedJournal.append` sebagai satu-satunya commit boundary untuk settlement, protective EXIT, recovery correction, safety/risk policy, inbox, outbox, dan projection high-water.
  evidence: Persistent adapter dan crash/fence contracts lulus, tetapi handler saat ini masih memakai port/reference memory UoW sehingga Story 3.1 belum membuktikan bahwa setiap canonical mutation melewati fence.

- source_spec: `spec-3-1-durable-fenced-journal.md`
  summary: Tambahkan versioned production schema migration, backup/restore, multi-process crash/restart matrix, dan operational deployment evidence untuk fenced journal.
  evidence: `initialize()` hanya membuat isolated test foundation; offline migration/cutover dan VM runtime belum diotorisasi atau dijalankan.

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

- source_spec: `spec-2-7-labeled-execution-calibration.md`
  summary: Ingest dan resolve actual shadow/venue TCA corpus ke frozen calibration window lalu persist/report ke promotion consumer.
  evidence: Pure report menolak label-authority mismatch dan non-observed venue scoring, tetapi reference resolver, scheduled corpus ingestion, persistence, dan promotion wiring belum tersedia.

- source_spec: `spec-fix-legacy-regression-gate.md`
  summary: Perbaiki fixture trade-review idempotency agar membuat parent user sebelum trade ber-foreign-key.
  evidence: `TestTradeReviewIdempotency.test_create_trade_review_skips_when_exists` gagal saat setup `trades.user_id=256024600`, sebelum kontrak idempotency dijalankan; bukan akibat perubahan admin-ID atau quant cache.
  resolved_by: `spec-fix-legacy-regression-gate-2.md` — fixture sekarang membuat parent user dan full file lulus 15/15.

- source_spec: `spec-fix-legacy-regression-gate.md`
  summary: Pulihkan enforcement VaR/CVaR pada `TradingEngine.should_execute_trade` untuk BUY berisiko ekstrem.
  evidence: Dua test quant mengharapkan VaR -4% dan CVaR -6% ditolak, tetapi engine mengizinkan trade; perlu perubahan di luar dua blocker yang disetujui dan tidak ada test yang dikecualikan.
  resolved_by: `spec-fix-legacy-regression-gate-2.md` — test production-threshold sekarang eksplisit dan full file lulus 42/42.

- source_spec: `spec-fix-legacy-regression-gate-2.md`
  summary: Diagnosis dan pulihkan penyelesaian test dashboard safety status yang menggantung.
  evidence: Full regression melewati seluruh tiga failure target, lalu konsisten berhenti di `tests/test_dashboard_api_phase1.py::test_safety_status_reports_dry_run_locked`; test terisolasi juga timeout setelah 60 detik dan tidak berubah dari baseline `1d57a82`.
