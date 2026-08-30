# Epic 2 Context: Officer dapat menjalankan posisi DRY RUN yang executable dan konsisten

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Epic ini membawa Candidate sampai terminal Position melalui market evidence Indodax yang qualified, harga dan kapasitas yang benar-benar executable pada ukuran diminta, satu simulator deterministik, Fill-authoritative accounting, jalur EXIT terpadu, serta restart dan reconciliation tanpa keputusan atau exposure baru. Hasilnya harus menghapus candle-price fill, ghost Position, P&L ganda, dan ketidakpastian setelah crash, sambil mempertahankan batas MVP DRY RUN yang secara fisik tidak dapat mengirim order live.

## Stories

- Story 2.1: Mengkualifikasi market evidence per produk Indodax
- Story 2.2: Membentuk executable MarketSnapshot dan instrument eligibility
- Story 2.3: Menjalankan satu deterministic simulator lifecycle
- Story 2.4: Menyelesaikan Intent dan Order melalui Fill-authoritative accounting
- Story 2.5: Mempertahankan Position protection melalui unified EXIT
- Story 2.6: Memulihkan lifecycle tanpa decision baru
- Story 2.7: Menghasilkan execution calibration evidence

## Requirements & Constraints

Market evidence harus dikualifikasi per produk dan channel—Public REST, Private REST API, Trade API 2.0, Market Data WebSocket, dan Private WebSocket—dengan kontrak terpisah untuk versi dokumentasi, auth scope, authoritative fields, cursor/sequence, timestamp, rate limit, snapshot/recovery route, dan contract-test artifact. Capability `UNQUALIFIED`, gap, disconnect, future timestamp, clock breach, atau continuity yang tidak terbukti tidak boleh menjadi canonical fact atau membuka entry; deprecated legacy history/fallback tidak authoritative.

Setiap executable Candidate memakai immutable point-in-time `MarketSnapshot`: ordered L2 depth yang melampaui requested size, venue dan ingest cursor yang dibedakan, event/receive time, freshness, instrument-rules version, effective-time universe membership, serta exclusion reason. Last price atau candle tidak boleh menggantikan depth. Minimum amount, precision, price increment, spread, freshness, capacity, dan metadata harus divalidasi. Kegagalan pair-local menghasilkan `INELIGIBLE/ABSTAIN`; kegagalan integritas sistemik membekukan portfolio entry sambil menjaga recovery dan protective exit. Baseline awal adalah L2 age maksimum 3 detik, clock skew maksimum 1 detik, dan authoritative sequence gap nol.

Historical replay dan live DRY RUN harus memakai simulator version dan lifecycle yang sama: `ACCEPTED/OPEN/PARTIAL/FILLED/CANCELLED/REJECTED/EXPIRED/UNKNOWN`, deterministic book-walk, latency, maker/taker fee-tax, precision/minimum, partial/non-fill, rejection, adverse selection, duplicate/out-of-order events, serta cancel/fill race. Artifact dan process DRY RUN tidak boleh membawa live submission adapter, trade-capable credential, atau jalur emergency menuju live submit.

Intent dan outbox harus committed sebelum dispatch. Hanya canonical Fill tervalidasi yang mengubah cash, fee, tax, quantity, exposure, dan Position; acknowledgment atau order response tanpa Fill tidak mengubah accounting. Venue Fill ID wajib dideduplikasi, seluruh effect idempotent, append-only, ordered, dan conservation-checked. Partial Fill mengubah hanya quantity yang terisi dan tidak melepaskan unfilled reservation; `UNKNOWN` tetap membekukan exposure baru.

Semua SL, hard invalidation, profit, trailing, time, alpha, dan operator exit memakai satu canonical EXIT dan `OrderCoordinator`. EXIT membawa target quantity, precedence reason, deterministic key, expected sequence, serta persisted Policy State transition. Partial exit harus mempertahankan protection untuk sisa quantity. Remainder di bawah venue minimum menjadi quarantined dust dengan incident dan valuation, bukan Position `CLOSED` palsu.

Restart/reconciliation harus memulihkan Order, Position, cash, Policy State, pending command, inbox/outbox, dan projections ke high-water yang sama tanpa strategy evaluation atau duplicate submit. Ambiguous acknowledgment wajib `query-before-resubmit`. Mismatch hanya boleh dikoreksi secara additive melalui `ADJUSTMENT_QUARANTINE`, `EXTERNAL_FILL_IMPORT`, `ORDER_STATE_CORRECTION`, atau `FORCED_CLOSE_REQUEST` yang mereferensikan evidence dan approval. Target awal recovery adalah RTO 15 menit, RPO nol acknowledged canonical events, dan UNKNOWN recovery 60 detik; lewat deadline scope tetap entry-frozen.

Execution calibration harus membandingkan predicted dan shadow-observed fill probability, latency, spread, slippage, implementation shortfall, reject, partial, dan cancel rate per Horizon, size, dan regime. Estimator, calibration window, tolerances, dan scenario corpus dibekukan sebelum scoring. Setiap datapoint diberi label `OBSERVED`, `INFERRED`, `SIMULATED`, atau `COUNTERFACTUAL`; hanya venue/shadow-observed evidence boleh diperlakukan sebagai observed calibration untuk live-readiness.

## Technical Decisions

Gunakan hexagonal modular monolith: domain bebas dari database/exchange/framework, seluruh I/O melalui typed ports, dan hanya bootstrap menjadi composition root. `OrderCoordinator` adalah satu-satunya submit/cancel owner; simulator dan `VenuePort` berbagi event schema serta state machine. IDs, idempotency keys, timestamps replay, dan ordering keys diturunkan deterministik dari canonical inputs; uang, harga, fee, dan quantity memakai `Decimal` atau scaled integer, bukan binary float.

Seluruh mutasi melewati satu application command handler dan transaction-scoped Unit of Work. Satu transaction memverifikasi writer fence dan expected sequence, melakukan domain transition, lalu mengikat canonical event dan `PENDING` outbox. Tidak ada network/Redis call di dalam transaction. Delivery at-least-once harus aman melalui inbox dedupe, idempotent effects, dan acknowledgment setelah commit.

SQLite adalah canonical journal/store; Redis, venue responses, UI, dan legacy tables hanya transport, evidence, atau rebuildable projections. Lifecycle facts append-only dan replayable. Replay bundle membekukan ordered input IDs, snapshot, cursor, rules/fees, simulator, cost model, schema, dependency/runtime versions, RNG seed, clocks, dan external responses; clean replay wajib menghasilkan terminal state serta semantic hash identik tanpa external call.

## Cross-Story Dependencies

Story 2.1 mengkualifikasi source dan recovery semantics yang diperlukan Story 2.2 untuk membentuk snapshot executable. Snapshot dan frozen rules dari Story 2.2 menjadi input deterministik Story 2.3, lalu simulator lifecycle memasok evidence kepada settlement Story 2.4. Canonical Fill dan persisted Position/Policy State dari Story 2.4 adalah dasar unified EXIT Story 2.5. Semua lifecycle, idempotency, journal, dan outbox pada Stories 2.3–2.5 harus tersedia agar Story 2.6 dapat replay dan reconcile tanpa keputusan baru. Story 2.7 bergantung pada estimator/simulator yang dibekukan serta lifecycle evidence berlabel dari Stories 2.1–2.6; hasil calibration tidak boleh mengubah sejarah execution yang sudah committed.
