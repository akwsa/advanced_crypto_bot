---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - specs/spec-autotrade-replacement/SPEC.md
  - planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md
  - planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/ARCHITECTURE-SPINE.md
  - planning-artifacts/architecture/architecture-advanced_crypto_bot-2026-08-25/IMPLEMENTATION-NOTES.md
---

# advanced_crypto_bot - Epic Breakdown

## Overview

Dokumen ini menyediakan breakdown epic dan story lengkap untuk AutoTrade Replacement berdasarkan SPEC, PRD final, dan Architecture Spine final.

## Requirements Inventory

### Functional Requirements

- FR1: Menyimpan Candidate Snapshot immutable sebelum gate pertama dengan input, clock, RNG, runtime, data, dan configuration provenance lengkap.
- FR2: Menghasilkan tepat satu Canonical Decision legal per Candidate dan Policy version dengan structured reason.
- FR3: Mereplay snapshot dan version yang sama menjadi decision, event, dan Policy State transition yang identik.
- FR4: Memilih ENTER/HOLD hanya ketika conservative net edge setelah biaya melampaui preregistered uncertainty boundary; selainnya abstain.
- FR5: Menerapkan persisted hysteresis, confirmation, gap behavior, dan fixed protective-exit precedence.
- FR6: Melacak Intent→Order→Fill→Position hingga terminal termasuk partial, duplicate, out-of-order, cancel race, expiry, dan UNKNOWN recovery.
- FR7: Mengubah cash dan Position hanya dari Fill tervalidasi dengan fee/tax/rounding conservation.
- FR8: Menyatukan seluruh jalur EXIT melalui atomic canonical settlement.
- FR9: Menyimpan Policy State termasuk quantity, high-water, trailing, invalidation, deadline, dan sequence.
- FR10: Menghasilkan Order/Position/cash/Policy State/pending-action setara setelah restart tanpa decision baru.
- FR11: Mereconcile journal dengan venue/recovery evidence dan melakukan correction additive yang teraudit.
- FR12: Menyimpan point-in-time ordered L2 snapshot yang cukup untuk executable requested size.
- FR13: Menolak/freeze stale, future-dated, gapped, unordered, atau clock-breached market evidence.
- FR14: Memvalidasi instrument minimum, precision, increment, dan metadata version sebelum Intent/Order.
- FR15: Memakai simulator version sama untuk replay dan live DRY RUN dengan book-walk, latency, fees, partial/non-fill, reject, cancellation, adverse-selection corpus.
- FR16: Mengukur predicted versus observed fill probability, latency, shortfall, spread, slippage, reject, partial, dan cancel rate dengan evidence labels.
- FR17: Menerapkan pre-trade portfolio/risk envelope, capacity, liquidity, correlation, stop-distance, uncertainty, dan turnover controls.
- FR18: Membekukan entry pada breach sambil mempertahankan cancel, protective exit, reconciliation, dan drawdown zeroing.
- FR19: Menyediakan independent persisted kill state machine yang hanya dapat di-reset operator setelah evidence lengkap.
- FR20: Menjamin tepat satu fenced writer; stale epoch, expired lease, dan direct compatibility write ditolak.
- FR21: Menurunkan runtime melalui HEALTHY→ENTRY_FROZEN→SHADOW_ONLY→SAFE_LATCHED tanpa auto-promotion/retrain.
- FR22: Membekukan Experiment, dynamic universe, Horizon registry, data/model/cost/simulator/seed/gate versions.
- FR23: Mencatat seluruh Trial, parameter search, failed result, dan lineage secara immutable.
- FR24: Menjalankan leakage-safe chronological evaluation dengan purge/embargo, frozen holdout, dan closed UNSCORABLE taxonomy.
- FR25: Membandingkan Champion, Challenger, no-trade, dan benchmark pada snapshot, opportunity, cost, dan exposure context sama.
- FR26: Menyegel Evidence Report berisi integrity, effective sample, net expectancy, calibration, risk/tail, concentration, DSR/PBO, dan execution calibration.
- FR27: Meningkatkan authority hanya pada fixed review dan demote/halt pada safety/degradation evidence.
- FR28: Menampilkan correlation trail Candidate→Decision→Intent→Order→Fill→Position→outcome.
- FR29: Menampilkan writer, freshness, invariant, queue/order, reconciliation, dan incident health.
- FR30: Membandingkan strategy/version per regime/Horizon tanpa evidence-set mixing.
- FR31: Mengaudit approval/reset/correction/live-enablement dengan actor, time, reason, evidence, dan immutable event.
- FR32: Memigrasikan fakta legacy terbukti, mengarantina ambiguity, dan menghasilkan backup/reconciliation/cutover proof.
- FR33: Mengubah legacy tables menjadi projection/read-only setelah fenced cutover tanpa dual write.
- FR34: Melakukan rollback code/config tanpa menghapus atau menulis ulang canonical history.

### NonFunctional Requirements

- NFR1 Reliability: Tidak ada acknowledged event hilang; restart/replay equivalence 100% pada acceptance corpus.
- NFR2 Integrity: Ledger, cash, Position, Policy State, risk reservation, dan projection invariants lulus pada setiap settlement/reconciliation.
- NFR3 Idempotency: Duplicate/retry tidak menghasilkan duplicate semantic effect.
- NFR4 Observability: Setiap decision/event mempunyai correlation/causation IDs, structured reason, versions, event/receive time, dan latency timestamps.
- NFR5 Performance: Canonical Decision p99 selesai ≤1 detik dan sebelum snapshot age 3 detik pada baseline awal.
- NFR6 Recovery: DRY RUN RTO ≤15 menit dan RPO acknowledged canonical event nol.
- NFR7 Security: Least privilege, physical live-path exclusion, secret isolation, authenticated command, dan tamper-evident audit.
- NFR8 Determinism: Snapshot, versions, seed, clock, dan external evidence sama menghasilkan decision, fills, IDs, serta accounting sama.
- NFR9 Operational SLO: queue age, dead-letter, database integrity, disk, log, encrypted backup, dan restore drill mengikuti versioned fail-closed thresholds.

### Additional Requirements

- Gunakan hexagonal modular monolith pada namespace `autotrade_next`; enforce import matrix AD-01 melalui contract test.
- Implementasikan canonical encoding/identity golden vectors, authority-scope journal sequence/hash chain, expected-sequence CAS, dan typed command outcomes.
- Application command handler menjadi satu-satunya UnitOfWork owner; tidak ada network call di dalam transaction.
- `PortfolioAllocation` menjadi atomic serialization aggregate untuk Decision batch, pair ownership, reservations, RiskState, events, dan outbox.
- Reservation ledger menjaga `initial = consumed + active_remainder + released` pada partial/multi Fill.
- SafetyState memakai cause/scope matrix AD-27; kill, drawdown, UNKNOWN, continuity, reconciliation, storage, clock, dan fence loss memiliki clear predicate normatif.
- SQLite canonical store hanya satu application writer, WAL/FULL/local filesystem; Redis optional dan non-authoritative dengan cache/transport domain terpisah.
- Runtime memakai offline forward migration; startup memverifikasi schema dan tidak menjalankan DDL.
- Build recipe mem-pin CPython 3.12.14, SQLite 3.53.4 source ID, uv ≥ initial qualified 0.11.15 artifact/checksum, dependency lock, image/base digest, dan SBOM.
- DRY RUN artifact/process secara fisik tidak memuat live submit adapter atau trade-capable credential; negative artifact test wajib.
- Indodax Public REST, Private REST, Trade API 2.0, Market Data WebSocket, dan Private WebSocket memiliki versioned capability registry serta contract test terpisah.
- Dashboard/Telegram hanya membaca versioned projections; sensitive write memakai authenticated/audited command surface terpisah.
- Backup memakai consistent Online Backup semantics, encrypted off-host copy, isolated restore, integrity/foreign-key checks, event replay, projection rebuild, dan reconciliation.
- Retention reference-aware: raw L2 30 hari, Candidate/replay 2 tahun, canonical/evidence/audit 7 tahun sebagai baseline assumption.
- Migration wajib menginventarisasi semua writer/submitter/credential/process/file serta mengklasifikasi legacy path sebagai remove, adapter, projection, atau migration-only.
- Mandatory fault suite mencakup crash boundaries, duplicate/delayed/out-of-order Fill, partial Fill, cancel race, UNKNOWN, WebSocket gap, Redis loss, SQLITE_BUSY, disk-full, clock rollback, stale epoch, dan compound recovery.

### UX Design Requirements

Tidak ada UX design contract terpisah. Dashboard behavior yang mengikat tercakup oleh FR28–FR31 dan AD-17; visual redesign berada di luar decomposition ini.

### FR Coverage Map

FR1: Epic 1 — Candidate point-in-time dapat dibuktikan.
FR2: Epic 1 — Satu action canonical dan reason legal.
FR3: Epic 1 — Decision/Policy State replay identik.
FR4: Epic 1 — Cost-aware calibrated abstention.
FR5: Epic 1 — Persisted hysteresis dan protective precedence.
FR6: Epic 2 — Intent-to-Fill lifecycle lengkap.
FR7: Epic 2 — Fill-only accounting conservation.
FR8: Epic 2 — Unified atomic exit.
FR9: Epic 2 — Persisted Position protection state.
FR10: Epic 2 — Restart equivalence.
FR11: Epic 2 — Evidence-based reconciliation/correction.
FR12: Epic 2 — Executable point-in-time market depth.
FR13: Epic 2 — Freshness, gap, dan clock control.
FR14: Epic 2 — Instrument-rule validation.
FR15: Epic 2 — Unified deterministic simulator.
FR16: Epic 2 — Execution/TCA calibration evidence.
FR17: Epic 3 — Pre-trade risk envelope.
FR18: Epic 3 — Entry breaker dan drawdown zeroing.
FR19: Epic 3 — Independent operator kill lifecycle.
FR20: Epic 3 — Persistently fenced single writer.
FR21: Epic 3 — Degradation governor dan isolated notification.
FR22: Epic 4 — Frozen Experiment/Horizon/universe.
FR23: Epic 4 — Immutable complete trial ledger.
FR24: Epic 4 — Leakage-safe outcome/evaluation.
FR25: Epic 4 — Common Champion/Challenger comparison.
FR26: Epic 4 — Sealed Evidence Report.
FR27: Epic 4 — Approval-bound promotion/demotion.
FR28: Epic 1 — End-to-end decision provenance.
FR29: Epic 3 — Integrity/risk incident cockpit.
FR30: Epic 4 — Strategy evidence comparison cockpit.
FR31: Epic 3 — Approval/reset/correction audit.
FR32: Epic 5 — Validated legacy migration/quarantine.
FR33: Epic 5 — No-dual-write fenced cutover.
FR34: Epic 5 — Additive rollback tanpa history rewrite.

## Epic List

### Epic 1: Officer dapat membuktikan setiap keputusan

Officer dapat menelusuri satu Candidate point-in-time menjadi satu action canonical yang cost-aware, state-legal, dan byte-stable saat replay, lengkap dengan alasan serta provenance yang sama pada journal dan read projection.

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR28.

### Epic 2: Officer dapat menjalankan posisi DRY RUN yang executable dan konsisten

Officer dapat menjalankan Candidate hingga terminal Position melalui qualified market evidence, deterministic simulator, Fill-authoritative accounting, unified exit, restart, dan reconciliation tanpa jalur submit live atau ghost exposure.

**FRs covered:** FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16.

### Epic 3: Officer dapat membatasi dan memulihkan risiko secara fail-closed

Officer dapat mempercayai portfolio envelope, reservation, single-writer fencing, safety cause, kill/drawdown zeroing, degraded operation, incident cockpit, dan audited recovery tanpa menghalangi protective action yang aman.

**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR29, FR31.

### Epic 4: Officer dapat memilih strategy dari evidence yang adil dan tersegel

Officer dapat menjalankan Champion/Challenger pada Experiment yang dibekukan, mencatat seluruh Trial, menilai leakage-safe costed outcomes, membandingkan benchmark yang sama, dan menyetujui promotion hanya dari sealed Evidence Report.

**FRs covered:** FR22, FR23, FR24, FR25, FR26, FR27, FR30.

### Epic 5: Officer dapat memindahkan authority dari legacy tanpa kehilangan sejarah

Officer dapat menginventarisasi dan mengarantina fakta legacy, membuktikan backup/restore/reconciliation, melakukan stop-the-world higher-epoch cutover tanpa dual settlement, dan rollback secara additive tanpa menghapus canonical history.

**FRs covered:** FR32, FR33, FR34.

## Epic 1: Officer dapat membuktikan setiap keputusan

Officer dapat menelusuri satu Candidate point-in-time menjadi satu action canonical yang cost-aware, state-legal, dan byte-stable saat replay, lengkap dengan alasan serta provenance yang sama pada journal dan read projection.

### Story 1.1: Menghasilkan identity dan canonical bytes yang stabil

As a Officer,
I want setiap entity dan event memiliki encoding serta identity deterministik,
So that producer, persistence, simulator, dan replay tidak dapat mengartikan fakta yang sama secara berbeda.

**Requirements:** FR1, FR3, NFR8.

**Acceptance Criteria:**

**Given** canonical encoding profile AD-26 dan golden fixtures lintas numeric/time/Unicode/null
**When** Candidate, Decision, Intent, event envelope, dan client-order identity dibentuk berulang kali
**Then** canonical bytes dan lowercase SHA-256 identity selalu identik
**And** unsupported float/type, scale ambiguity, field projection drift, atau recipe version mismatch ditolak dengan typed error tanpa persistence parsial.

**Given** schema atau identity recipe baru
**When** compatibility suite dijalankan
**Then** ID lama tidak ditulis ulang dan version baru hanya diterima setelah seluruh golden vectors lulus.

### Story 1.2: Menangkap Candidate Snapshot point-in-time

As a Officer,
I want setiap scan membekukan semua input sebelum gate pertama,
So that saya dapat membuktikan keputusan memakai data, clock, universe, dan configuration yang tersedia saat itu.

**Requirements:** FR1, NFR4.

**Acceptance Criteria:**

**Given** satu closed-bar trigger atau protective event trigger yang valid
**When** Candidate dibuat
**Then** snapshot immutable menyimpan ordered input IDs, event/receive time, source cursors, freshness/quality, universe/instrument version, scheduler, clock, RNG, runtime, data/model/config references, dan deterministic Candidate ID
**And** duplicate trigger menghasilkan semantic ID sama sementara late correction menghasilkan revision baru yang menunjuk original.

**Given** required provenance tidak lengkap atau canonical Candidate sudah committed
**When** capture atau overwrite dicoba
**Then** Candidate menjadi non-executable/ditolak dan fakta historis tidak berubah.

### Story 1.3: Menghasilkan satu action yang legal dan beralasan

As a Officer,
I want setiap Candidate berakhir pada tepat satu Canonical Decision yang legal terhadap Position state,
So that dashboard, journal, dan execution tidak dapat menunjukkan action berbeda.

**Requirements:** FR2, NFR2, NFR3.

**Acceptance Criteria:**

**Given** Candidate flat atau exposed dan satu Policy version
**When** DecisionService mengevaluasi action
**Then** flat hanya menghasilkan `ENTER|ABSTAIN`, exposed hanya `HOLD|EXIT`, setiap result memiliki structured reason/boundary/snapshot reference, dan satu uniqueness constraint mencegah Decision kedua
**And** veto entry menjadi `ABSTAIN` sementara protective `EXIT` tidak dapat diturunkan menjadi `HOLD`.

**Given** transition ilegal atau downstream overwrite
**When** command diproses
**Then** mutation ditolak, Integrity Incident dicatat, dan original Decision tetap immutable.

### Story 1.4: Menerapkan cost-aware abstention dan hysteresis

As a Officer,
I want policy hanya menambah exposure ketika conservative net edge cukup kuat dan confirmation state terpenuhi,
So that bot tidak overtrade karena gross signal, biaya, atau noise kecil.

**Requirements:** FR4, FR5.

**Acceptance Criteria:**

**Given** proposal gross, size-specific shortfall distribution, calibration reference, dan frozen Policy State
**When** conservative edge tidak melewati preregistered margin atau calibration missing/stale
**Then** flat menghasilkan `ABSTAIN` dan exposed tidak menambah exposure tanpa menghalangi protective `EXIT`.

**Given** baseline confirmation policy
**When** consecutive closed bars atau data gap diproses
**Then** ENTER memerlukan dua confirmation, protective EXIT satu, alpha EXIT dua, gap hanya mereset ENTER confirmation, dan Position high-water/protection tidak pernah direset.

### Story 1.5: Membuktikan deterministic decision replay

As a Officer,
I want Candidate dan manifest yang sama menghasilkan transition dan decision yang sama dari clean store,
So that historical behavior dapat diverifikasi tanpa external side effect.

**Requirements:** FR3, NFR1, NFR8.

**Acceptance Criteria:**

**Given** frozen replay bundle dengan ordered inputs, initial state, versions, seed, clock, dan recorded external responses
**When** decision/lifecycle regeneration dijalankan dua kali pada clean store
**Then** terminal state dan versioned semantic hash identik serta external-call counter nol
**And** perbedaan field semantic menghasilkan failure dengan exact diff, bukan silent tolerance.

**Given** observability-only fields yang dikecualikan
**When** replay dibandingkan
**Then** hanya field yang tercantum explicit pada semantic projection version yang boleh berbeda.

### Story 1.6: Menyajikan provenance decision read-only

As a Officer,
I want melihat Candidate→Decision correlation trail dari projection read-only,
So that alasan action dapat dipahami tanpa membaca database canonical atau log mentah.

**Requirements:** FR28, NFR4.

**Acceptance Criteria:**

**Given** committed Candidate dan Decision outbox events
**When** projection consumer menerima duplicate atau out-of-order delivery
**Then** view idempotent menampilkan snapshot reference, action, reason, cost/uncertainty, Policy version/state, correlation/causation IDs, dan projection high-water yang konsisten
**And** consumer tidak mempunyai mutation port atau trade-capable credential.

**Given** notification/dashboard consumer gagal
**When** canonical Decision commit berlangsung
**Then** commit tidak tertahan, failure masuk isolated retry/dead-letter, dan action canonical tidak berubah.

## Epic 2: Officer dapat menjalankan posisi DRY RUN yang executable dan konsisten

Officer dapat menjalankan Candidate hingga terminal Position melalui qualified market evidence, deterministic simulator, Fill-authoritative accounting, unified exit, restart, dan reconciliation tanpa jalur submit live atau ghost exposure.

### Story 2.1: Mengkualifikasi market evidence per produk Indodax

As a Officer,
I want hanya market capability yang terbukti masuk ke Candidate,
So that bot tidak menganggap local cursor, stream gap, atau endpoint legacy sebagai venue truth.

**Requirements:** FR11, FR13.

**Acceptance Criteria:**

**Given** Public REST, Private REST, Trade API 2.0, Market Data WebSocket, dan Private WebSocket
**When** capability registry dibangun
**Then** setiap product/channel mempunyai documentation version, auth scope, authoritative fields, cursor/sequence semantics, snapshot/recovery route, timestamps, rate limit, dan contract-test artifact terpisah
**And** capability `UNQUALIFIED` tidak dapat mengisi canonical fact atau membuka entry.

**Given** gap, disconnect, future timestamp, clock skew, atau continuity yang tidak terbukti
**When** adapter memproses evidence
**Then** affected scope dibekukan sampai snapshot/recovery dan reconciliation contract lulus tanpa fallback legacy.

### Story 2.2: Membentuk executable MarketSnapshot dan instrument eligibility

As a Officer,
I want Candidate memakai depth dan rules point-in-time pada requested size,
So that DRY RUN tidak mengisi order pada candle/last price yang tidak executable.

**Requirements:** FR12, FR13, FR14.

**Acceptance Criteria:**

**Given** qualified L2, target quantity, instrument metadata, dan universe membership efektif-waktu
**When** MarketSnapshot dibuat
**Then** ordered depth melampaui requested size, event/receive time dan cursors terpisah, metadata/eligibility version dibekukan, dan executable price/capacity dihitung deterministik
**And** minimum, precision, increment, spread, freshness, depth, atau metadata failure menghasilkan pair-local `INELIGIBLE/ABSTAIN` dengan reason spesifik.

**Given** systemic source integrity failure
**When** eligibility dievaluasi
**Then** portfolio entry dibekukan tetapi recovery dan protective path tetap tersedia.

### Story 2.3: Menjalankan satu deterministic simulator lifecycle

As a Officer,
I want historical replay dan live DRY RUN memakai venue lifecycle serta simulator version yang sama,
So that evidence fill tidak berasal dari model berbeda.

**Requirements:** FR15, NFR7, NFR8.

**Acceptance Criteria:**

**Given** Intent valid, frozen L2, instrument rules, fee/tax, latency, dan scenario seed
**When** simulator menjalankan Order
**Then** lifecycle mendukung accepted/open/partial/filled/cancelled/rejected/expired/UNKNOWN, book walk, maker/taker cost, precision, non-fill, adverse selection, cancel/fill race, duplicate, dan out-of-order corpus secara deterministik
**And** simulator event schema sama dengan VenuePort lifecycle schema.

**Given** artifact/process DRY RUN
**When** dependency dan credential graph diuji
**Then** live submission adapter tidak dapat di-import/reach dan trade-capable credential tidak tersedia.

### Story 2.4: Menyelesaikan Intent dan Order melalui Fill-authoritative accounting

As a Officer,
I want setiap execution effect dicatat sekali dan hanya Fill mengubah cash/exposure,
So that partial/retry tidak menciptakan ghost Position atau P&L ganda.

**Requirements:** FR6, FR7, NFR2, NFR3.

**Acceptance Criteria:**

**Given** Canonical Decision executable
**When** Intent dibuat dan simulator evidence kembali
**Then** Intent+outbox committed sebelum dispatch, deterministic order/idempotency key dipakai, venue Fill ID dideduplikasi, dan Fill atomically mengubah cash, fee, tax, quantity, Position, event, serta outbox
**And** submission acknowledgment tanpa Fill tidak mengubah accounting.

**Given** partial/multiple Fill, duplicate, delayed, out-of-order, atau cancel/fill race
**When** events disettle
**Then** conservation, aggregate sequence, terminal quantity, dan idempotency properties tetap lulus.

### Story 2.5: Mempertahankan Position protection melalui unified EXIT

As a Officer,
I want SL, invalidation, profit, trailing, time, alpha, dan operator exit memakai satu canonical path,
So that remaining quantity selalu protected dan tidak ditutup dua kali.

**Requirements:** FR8, FR9.

**Acceptance Criteria:**

**Given** open/partially-filled Position dengan persisted Policy State
**When** trigger exit berprecedence tertinggi muncul
**Then** EXIT menyimpan target quantity, deterministic key, reason, expected sequence, high-water/trailing/invalidation/deadline transition, dan memakai OrderCoordinator yang sama
**And** partial exit hanya mengurangi Fill quantity sementara remaining quantity/protection tetap persisted.

**Given** quantity di bawah minimum venue
**When** full zeroing dicoba
**Then** remainder diklasifikasi quarantined dust dengan incident/valuation dan tidak ditandai `CLOSED` secara palsu.

### Story 2.6: Memulihkan lifecycle tanpa decision baru

As a Officer,
I want restart dan reconciliation mengembalikan state yang sama,
So that crash atau ambiguous acknowledgment tidak mengubah sejarah atau menambah exposure.

**Requirements:** FR10, FR11, NFR1, NFR6.

**Acceptance Criteria:**

**Given** crash pada setiap boundary sebelum/sesudah commit/publish/ack
**When** startup replay dan recovery berjalan
**Then** Order, Position, cash, Policy State, pending command, inbox/outbox, dan projection kembali ke high-water yang sama tanpa strategy evaluation baru atau duplicate submit.

**Given** UNKNOWN atau mismatch venue/internal
**When** recovery dilakukan
**Then** query-before-resubmit berlaku, entry tetap frozen, dan hanya correction taxonomy `ADJUSTMENT_QUARANTINE|EXTERNAL_FILL_IMPORT|ORDER_STATE_CORRECTION|FORCED_CLOSE_REQUEST` dengan evidence/approval dapat committed.

### Story 2.7: Menghasilkan execution calibration evidence

As a Officer,
I want predicted execution dibandingkan dengan shadow-observed behavior secara berlabel,
So that simulator fidelity dan strategy evidence tidak mencampur observasi dengan inferensi.

**Requirements:** FR16.

**Acceptance Criteria:**

**Given** frozen estimator, calibration window, tolerance, dan scenario corpus
**When** TCA report dibuat
**Then** fill probability, latency, spread, slippage, implementation shortfall, reject, partial, dan cancel rate dibandingkan per Horizon/size/regime
**And** setiap datapoint berlabel `OBSERVED`, `INFERRED`, `SIMULATED`, atau `COUNTERFACTUAL` tanpa promotion memperlakukan non-observed sebagai venue calibration.

## Epic 3: Officer dapat membatasi dan memulihkan risiko secara fail-closed

Officer dapat mempercayai portfolio envelope, reservation, single-writer fencing, safety cause, kill/drawdown zeroing, degraded operation, incident cockpit, dan audited recovery tanpa menghalangi protective action yang aman.

### Story 3.1: Menegakkan fenced command authority

As a Officer,
I want hanya satu writer epoch dapat melakukan canonical mutation,
So that restart, takeover, atau network partition tidak menciptakan split brain.

**Requirements:** FR20, NFR3, NFR7.

**Acceptance Criteria:**

**Given** one writer authority row per scope
**When** process mengklaim atau mengambil alih authority
**Then** `BEGIN IMMEDIATE` CAS menaikkan epoch/token monotonik dan setiap append memverifikasi scope, epoch, token, lease, expected aggregate sequence di transaction sama
**And** PID/file/Redis lock/timestamp sendiri tidak pernah memberi authority.

**Given** stale epoch, fence loss, clock anomaly, `SQLITE_BUSY`, crash sebelum commit, atau indeterminate commit return
**When** command handler memproses mutation/retry
**Then** typed outcome benar, stale write nol, retry hanya memakai command identity sama, dan tidak ada transaction melintasi network.

### Story 3.2: Mengalokasikan exposure dan reservation secara atomik

As a Officer,
I want seluruh Candidate pada cutoff yang sama berbagi satu portfolio/risk consistency cut,
So that pair, Horizon, capacity, dan exposure tidak bergantung pada scan order atau stale Fill state.

**Requirements:** FR17, FR20, NFR2.

**Acceptance Criteria:**

**Given** frozen opportunity set, equity, market cutoff, journal high-water, Positions, working orders, dan RiskState
**When** `PortfolioAllocation` meng-commit batch
**Then** final Decisions, unique pair-to-Horizon ownership, reservations, RiskState, events, dan outbox committed melalui satu CAS tanpa partial executable batch
**And** stale constituent checkpoint menolak seluruh risk-increasing decision dengan structured reason.

**Given** partial/multiple Fill atau terminal cancel/reject/expiry
**When** reservation berubah
**Then** notional, planned loss, fees, slippage/impact buffer, dan turnover memenuhi `initial = consumed + active_remainder + released`; UNKNOWN/partial tidak melepaskan remainder dan rounding residual tetap reserved.

### Story 3.3: Menerapkan portfolio RiskGovernor

As a Officer,
I want sizing dan entry mematuhi satu canonical equity serta risk envelope,
So that alpha atau pair iteration tidak dapat memperbesar batas risiko.

**Requirements:** FR17, FR18.

**Acceptance Criteria:**

**Given** canonical equity snapshot current dan candidate allocation
**When** RiskGovernor mengevaluasi entry
**Then** Position ≤10%, portfolio exposure ≤40%, daily loss ≤2%, planned loss ≤0,5%, hard drawdown trigger 10%, dan rolling entry turnover baseline 40% diterapkan secara versioned
**And** liquidity, correlation, stop distance, volatility, cost, dan uncertainty hanya dapat menurunkan quantity.

**Given** missing stop/exit capacity, stale mark, insufficient depth, or inconsistent high-water
**When** risk dihitung
**Then** entry ditolak tanpa fabricated valuation sementara risk-reducing EXIT tetap exempt dari turnover.

### Story 3.4: Menggabungkan safety cause tanpa premature clear

As a Officer,
I want setiap incident memiliki cause, scope, severity, evidence, dan clear predicate canonical,
So that satu subsystem tidak membuka entry ketika cause lain masih aktif.

**Requirements:** FR18, FR21, NFR2.

**Acceptance Criteria:**

**Given** causes pada Safety Cause Matrix AD-27
**When** stale data, continuity gap, UNKNOWN, reconciliation, delivery, clock, storage, or fence incident terjadi
**Then** cause disimpan dengan deterministic ID, scope lattice `ORDER<INSTRUMENT<PORTFOLIO<AUTHORITY`, severity join, allowed protective behavior, evidence refs, dan expected sequence
**And** effective state adalah join tertinggi serta clearing satu cause tidak menurunkan state selama cause lain aktif.

**Given** automatic recovery evidence atau operator clear command
**When** clear predicate belum lengkap
**Then** mutation ditolak dan audit mencatat missing evidence tanpa administrative UNKNOWN close.

### Story 3.5: Menjalankan kill dan hard-drawdown zeroing

As a Officer,
I want kill/drawdown menghentikan exposure baru dan mengurangi exposure menuju nol,
So that emergency control tetap deterministik melewati retry dan restart.

**Requirements:** FR18, FR19, NFR6.

**Acceptance Criteria:**

**Given** operator kill command yang authenticated atau hard drawdown breach
**When** SafetyState transition dimulai
**Then** entry segera ditolak, working entry dibatalkan, UNKNOWN di-query sebelum resubmit, protective EXIT menuju target zero dipertahankan, dan reconciliation wajib
**And** kill mengikuti `ARMED→TRIGGERED→CANCEL_PENDING→EXIT_PENDING→RECONCILING→LATCHED_SAFE` dengan cancel deadline/retry persisted.

**Given** process restart atau partial/dust exit
**When** recovery berlangsung
**Then** latch/state/remainder tidak hilang; hanya evidence lengkap plus operator approval dapat mengembalikan `ARMED`, dan hard drawdown tidak diklaim sebagai realized-loss guarantee.

### Story 3.6: Menjalankan degradation dan delivery secara terisolasi

As a Officer,
I want runtime menurunkan authority sebelum availability failure menjadi trading failure,
So that reconciliation dan protective action tetap hidup ketika scanning, Redis, atau notification terganggu.

**Requirements:** FR21, NFR1, NFR9.

**Acceptance Criteria:**

**Given** SLI/SLO breach atau safety cause aktif
**When** degradation dievaluasi
**Then** runtime bergerak deterministik `HEALTHY→ENTRY_FROZEN→SHADOW_ONLY→SAFE_LATCHED`, memblokir ENTER lebih dahulu dan mempertahankan reconciliation/protective EXIT sesuai evidence quality
**And** safety invariant tidak dapat dibudgetkan oleh availability/error budget.

**Given** Redis total loss, backlog, dead-letter, atau Telegram/dashboard failure
**When** recovery dilakukan
**Then** canonical correctness pulih dari SQLite outbox, cache tidak menjadi transport authority, dan notification failure tidak mengubah trading state.

### Story 3.7: Menyajikan integrity cockpit dan audited recovery

As a Officer,
I want melihat authority, freshness, safety, risk, queue, order, reconciliation, dan approval evidence dalam satu cockpit read-only,
So that saya dapat memutuskan recovery tanpa direct database mutation.

**Requirements:** FR29, FR31, NFR4, NFR7.

**Acceptance Criteria:**

**Given** versioned projections dan active incidents
**When** Officer membuka integrity cockpit
**Then** view menampilkan writer epoch, source/projection high-water, data quality, SafetyState causes, risk envelope/reservations, queue/order health, Position/cash mismatch, dead-letter, disk/backup health, dan exact evidence/action link
**And** stale projection terlihat jelas serta tidak menghitung health sendiri.

**Given** promotion override, kill reset, reconciliation correction, atau sensitive recovery
**When** Officer mengirim command
**Then** actor, role, timestamp, reason, evidence reference, idempotency key, expected sequence, dan immutable approval/audit event wajib; unauthorized/direct write ditolak.

## Epic 4: Officer dapat memilih strategy dari evidence yang adil dan tersegel

Officer dapat menjalankan Champion/Challenger pada Experiment yang dibekukan, mencatat seluruh Trial, menilai leakage-safe costed outcomes, membandingkan benchmark yang sama, dan menyetujui promotion hanya dari sealed Evidence Report.

### Story 4.1: Membekukan Experiment dan opportunity universe

As a Officer,
I want setiap Experiment mengunci seluruh input dan eligibility sebelum window dibuka,
So that universe, Horizon, cost, atau method tidak dapat diganti setelah outcome terlihat.

**Requirements:** FR22.

**Acceptance Criteria:**

**Given** Experiment draft dan effective-time market/instrument history
**When** EvidenceSpecification disetujui
**Then** universe formula/membership, windows, Horizon/maturity, features, strategy/model/calibrator, simulator, cost, benchmark, seed, schema/runtime/config, sampling, purge/embargo, regime, DSR/PBO, concentration, dan conjunctive pass logic dibekukan dengan hashes
**And** membership exclusion mempunyai reason serta tidak ditulis ulang retrospektif.

**Given** perubahan specification setelah seal
**When** run dimulai
**Then** perubahan menghasilkan Experiment family/version baru dan trial family lama tetap tercatat.

### Story 4.2: Menjalankan Champion dan Challenger secara terisolasi

As a Officer,
I want semua policy dinilai pada Candidate, cost, dan opportunity context sama,
So that legacy atau model kompleks tidak mendapat keuntungan authority/data tersembunyi.

**Requirements:** FR25, FR27.

**Acceptance Criteria:**

**Given** one CandidateSnapshot dan frozen Experiment context
**When** NoEntryChampion, simple baseline, legacy candidate, dan Challenger dievaluasi
**Then** seluruhnya memakai pure StrategyPort, isolated state/decision/outcome ledger, same input/cost, dan no shared mutable state
**And** hanya approved Champion output dapat mencapai Intent sementara Challenger Fill selalu `COUNTERFACTUAL`.

**Given** hidden online state, automatic retrain/promotion, atau Challenger submit attempt
**When** contract tests berjalan
**Then** attempt ditolak dan Integrity Incident/evidence failure tercatat.

### Story 4.3: Menyimpan Trial dan matured outcome lengkap

As a Officer,
I want setiap percobaan serta outcome Candidate tercatat termasuk kegagalan,
So that multiple testing dan selection bias tidak dapat disembunyikan.

**Requirements:** FR23, FR24.

**Acceptance Criteria:**

**Given** feature/parameter/threshold/model search atau failed run
**When** Trial dimulai/berakhir
**Then** immutable ledger menyimpan family, lineage, inputs, code/config/model hashes, parameters, status, results, failure, timestamps, dan causation tanpa delete/reset
**And** retry/replay tidak membuat semantic Trial baru.

**Given** matured Candidate tanpa scoreable outcome
**When** outcome classifier berjalan
**Then** hanya closed taxonomy `STALE_OR_GAPPED_SOURCE|DELISTING_OR_HALT|MISSING_REQUIRED_HORIZON_DATA|INVALID_INSTRUMENT_METADATA` legal, reason memakai point-in-time evidence, dan post-hoc/outcome-aware relabel ditolak.

### Story 4.4: Menjalankan leakage-safe common comparison

As a Officer,
I want Champion, Challenger, cash/no-trade, dan executable benchmark dibandingkan dengan method terkunci,
So that backtest terbaik tidak dipilih dari leakage atau benchmark yang diganti.

**Requirements:** FR24, FR25.

**Acceptance Criteria:**

**Given** sealed EvidenceSpecification dan completed outcomes
**When** chronological walk-forward evaluation berjalan
**Then** purge/embargo mengikuti maximum label/holding overlap, final holdout tetap untouched, exposure-overlap clusters/effective sample dilaporkan, regime requirements diterapkan, dan costed opportunity/exposure matching konsisten
**And** `UNSCORABLE` >5% baseline atau required regime/sample missing membuat report non-promotable.

**Given** method/benchmark/post-window threshold change
**When** evaluator mendeteksi drift
**Then** evaluation gagal seal dan membutuhkan Experiment family baru tanpa menghapus failed evidence.

### Story 4.5: Menyegel Evidence Report yang reproducible

As a Officer,
I want satu report immutable menggabungkan integrity, calibration, execution, risk, dan performance,
So that promotion dapat diputuskan dari evidence lengkap dan dapat direproduksi.

**Requirements:** FR26, NFR8.

**Acceptance Criteria:**

**Given** completed evaluation dengan full lineage
**When** report dihasilkan dan disegel
**Then** report memuat sample/effective sample, net expectancy distribution, proper scores/coverage, drawdown/tail, turnover, absolute-profit dan exposure concentration, DSR/PBO, simulator/TCA calibration, benchmark delta, regime/Horizon, trial family, integrity incidents, assumptions, dan conjunctive verdict
**And** aggregate net profit ≤0, concentration >35%, missing field, unexplained mismatch, atau unresolved Order/Fill selalu gagal.

**Given** identical inputs dan report recipe
**When** report dibangun ulang
**Then** semantic hash identik dan seal lama tidak berubah.

### Story 4.6: Mengontrol promotion, demotion, dan evidence cockpit

As a Officer,
I want membandingkan sealed policy evidence dan memberi/menurunkan authority secara teraudit,
So that performance tidak dapat mengalahkan safety atau mempromosikan dirinya sendiri.

**Requirements:** FR27, FR30, FR31.

**Acceptance Criteria:**

**Given** strategy evidence projection
**When** Officer membandingkan policy
**Then** train/validation/OOS/shadow evidence, Horizon, regime, versions, costs, sample, calibration, drawdown, concentration, DSR/PBO, integrity, dan promotion blockers ditampilkan tanpa set mixing
**And** projection menunjuk sealed report/trial/evidence high-water.

**Given** fixed review window dan promotable report
**When** promotion command dikirim
**Then** human approval, actor/reason/evidence/config hash/effective time diperlukan dan authority change menghasilkan canonical audit event
**And** safety breach dapat immediate halt/demote sementara statistical degradation hanya kembali ke shadow; tidak ada auto-promotion/retrain.

## Epic 5: Officer dapat memindahkan authority dari legacy tanpa kehilangan sejarah

Officer dapat menginventarisasi dan mengarantina fakta legacy, membuktikan backup/restore/reconciliation, melakukan stop-the-world higher-epoch cutover tanpa dual settlement, dan rollback secara additive tanpa menghapus canonical history.

### Story 5.1: Menginventarisasi seluruh legacy authority dan fakta

As a Officer,
I want mengetahui setiap writer, submitter, credential, process, file, order, trade, balance, dan Position legacy,
So that tidak ada mutator tersembunyi atau fakta ambigu yang lolos cutover.

**Requirements:** FR32, NFR7.

**Acceptance Criteria:**

**Given** brownfield repository, runtime config, process topology, databases, Redis, dan venue evidence
**When** inventory tool dijalankan
**Then** setiap mutation/submission path diklasifikasi `remove|adapter|projection|migration-only`, setiap record diklasifikasi `PROVEN_OPEN|PROVEN_CLOSED|AMBIGUOUS|NON_CANONICAL_HISTORY`, dan unclassified item menolak readiness
**And** credential/process graph membuktikan target DRY RUN terisolasi dari live authority.

**Given** mandatory ACE/BICO/HUMANITY/HOME incident fixtures
**When** classifier/recovery suite berjalan
**Then** ghost Position, stale pending order, ambiguous exposure, dan evidence hierarchy menghasilkan disposition deterministik.

### Story 5.2: Menghasilkan qualified immutable runtime artifact

As a Officer,
I want build target dapat direproduksi dan diverifikasi sebelum menyentuh canonical store,
So that host, Docker, dependency, dan SQLite drift tidak mengubah behavior.

**Requirements:** FR32, NFR7, NFR8.

**Acceptance Criteria:**

**Given** committed `pyproject.toml`, `uv.lock`, build recipe, and pinned artifacts
**When** CI membangun target
**Then** CPython 3.12.14, SQLite 3.53.4 exact source ID/compile options, qualified uv artifact/checksum, base/application digests, lock hash, schema/config/policy hashes, dan SBOM masuk manifest
**And** test/promotion memakai digest sama tanpa runtime resolution.

**Given** version/source ID/PRAGMA/schema/digest mismatch atau vulnerable/unqualified tool
**When** startup gate berjalan
**Then** runtime fail-closed sebelum writer acquisition.

### Story 5.3: Menjalankan offline migration serta backup/restore gate

As a Officer,
I want schema dan source database dipindahkan hanya melalui proses offline yang dapat dipulihkan,
So that migration/cutover tidak bergantung pada copy database aktif atau runtime DDL.

**Requirements:** FR32, NFR1, NFR6.

**Acceptance Criteria:**

**Given** core writer stopped dan source inventory sealed
**When** forward migrator berjalan
**Then** ordered migration ID/checksum, source/target schema, artifact/backup references, event high-water, dan result tercatat; runtime startup hanya memverifikasi supported schema
**And** raw active-WAL file copy atau implicit startup migration ditolak.

**Given** coordinated Online Backup snapshot
**When** restore gate dijalankan terisolasi
**Then** encrypted off-host checksum, integrity/foreign-key checks, event replay, projection rebuild, invariants, RPO/RTO, and reconciliation lulus sebelum source/target replacement.

### Story 5.4: Mengimpor fakta terbukti dan mengarantina ambiguity

As a Officer,
I want hanya legacy execution yang terbukti menjadi canonical fact,
So that migration tidak memalsukan strategy decision atau ghost Position.

**Requirements:** FR32, NFR2.

**Acceptance Criteria:**

**Given** sealed inventory dan evidence hierarchy
**When** import dijalankan
**Then** proven fills/orders menjadi approved external facts dengan original evidence/provenance; projection-only history tetap non-canonical; ambiguous exposure masuk quarantine dan membekukan entry
**And** monetary mismatch >1 IDR atau quantity mismatch >one precision unit menolak reconciliation.

**Given** ghost close atau order correction
**When** disposition disetujui
**Then** additive correction menunjuk original evidence/approval dan tidak menghapus atau mengubah legacy/canonical history.

### Story 5.5: Melakukan stop-the-world fenced cutover

As a Officer,
I want memindahkan virtual portfolio authority ke replacement tepat satu kali,
So that legacy dan target tidak pernah submit atau settle scope yang sama bersamaan.

**Requirements:** FR33, NFR3, NFR7.

**Acceptance Criteria:**

**Given** platform-ready artifact, inventory, backup/restore, import, reconciliation, and fault suite lulus
**When** cutover dijalankan
**Then** config/entry freeze, stop seluruh legacy scheduler/direct writer, outbox drain, checkpoint/backup, zero unresolved working UNKNOWN/mismatch, higher epoch claim, exact target start, replay/projection verification, lalu controlled entry enable dilakukan berurutan dan teraudit
**And** shadow file/namespace tetap terpisah sampai authority claim.

**Given** stale legacy process mencoba write/submit setelah cutover
**When** boundary menerima request
**Then** fence/physical exclusion menolak effect dan Integrity Incident terlihat pada cockpit.

### Story 5.6: Melakukan additive rollback dan evidence retention

As a Officer,
I want rollback memulihkan safe replacement release tanpa menghidupkan writer lama atau menimpa fakta baru,
So that recovery tidak mengorbankan history dan evidence.

**Requirements:** FR34, NFR1, NFR6.

**Acceptance Criteria:**

**Given** post-cutover failure
**When** rollback diputuskan
**Then** entry freeze, stop/drain, reconciliation, schema/event compatibility proof, dan higher epoch claim memindahkan authority ke previous replacement release atau `SHADOW_ONLY/SAFE_LATCHED`
**And** legacy writer tidak dapat diaktifkan lewat config serta backup lama tidak menimpa post-cutover facts.

**Given** retention cleanup
**When** raw L2/Candidate/replay/canonical/evidence/audit mencapai baseline expiry
**Then** active Experiment/promotion/incident/legal/replay references menahan deletion, cleanup menghasilkan authenticated deletion manifest/tombstone, dan canonical lifecycle facts tidak dihapus in-place.
