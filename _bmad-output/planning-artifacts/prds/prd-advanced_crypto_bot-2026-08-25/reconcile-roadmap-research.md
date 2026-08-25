# Reconciliation — Roadmap, Architecture Spine, dan Riset Teknis terhadap PRD AutoTrade Replacement

Tanggal rekonsiliasi: 2026-08-25
Mode: extract-only; dokumen sumber tidak diingest sebagai requirement baru dan `prd.md`/`addendum.md` tidak diubah.

## Input yang dibandingkan

1. `advanced_crypto_bot/docs/architecture/autotrade-profitability-2026-08-24/IMPLEMENTATION-ROADMAP.md`
2. `advanced_crypto_bot/docs/architecture/autotrade-profitability-2026-08-24/ARCHITECTURE-SPINE.md`
3. `_bmad-output/planning-artifacts/research/technical-autotrade-crypto-indodax-market-execution-risk-research-2026-08-12.md`
4. `_bmad-output/planning-artifacts/research/technical-crypto-autotrade-quant-profitability-research-2026-08-05.md`
5. `_bmad-output/planning-artifacts/research/technical-patient-net-profit-swing-autotrade-research-2026-08-16.md`

Target pembanding:

- `_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md`
- `_bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/addendum.md`

## Verdict

PRD dan addendum mempertahankan substansi utama seluruh input: one-accounting-authority, pure/versioned policy, complete decision attribution, realistic shared simulator, persisted exit state, canonical risk equity, single writer, challenger isolation, walk-forward evidence, fail-closed promotion, serta migration/reconciliation tanpa history rewrite. Scope PRD bahkan memperkeras beberapa sumber dengan risk envelope numerik, tamper-evident evidence, explicit stage authority, dan larangan live-money dalam MVP.

Tidak ditemukan gap yang membatalkan architecture/epics. Empat gap di bawah merupakan detail operasional/integrasi yang masih perlu diputuskan penempatannya: architecture, addendum, atau acceptance story.

## Reconciliation per input

### 1. IMPLEMENTATION-ROADMAP.md

**Terjaga di PRD/addendum**

- Phase 0 truth-layer recovery dipetakan ke FR-7–FR-11, FR-18–FR-20, FR-32–FR-34, NFR-1–NFR-3, dan SM-1/SM-6/SM-7.
- Candidate snapshots, terminal reason taxonomy, symmetric outcome coverage, dan executable net-return evaluation dipetakan ke FR-1–FR-5, FR-12–FR-16, FR-24–FR-26, SM-3–SM-5.
- Shared simulator, simple/explainable Champion, frozen windows, isolated Challenger, walk-forward comparison, sealed promotion, rollback, dan demotion dipetakan ke FR-15, FR-22–FR-27 dan MVP Exit Gates.
- Gate awal 30 hari/100 trade, profit factor 1,20, probability positive expectancy 95%, max drawdown 10%, serta pair contribution 35% tetap tampak sebagai proposal/`[ASSUMPTION]`; PRD menambah DSR/PBO dan effective-sample controls.
- Roadmap lama menyebut Strategy 1 sebagai Champion. PRD mengganti ini dengan keputusan pengguna yang lebih baru: legacy strategy *eligible*, tetapi hanya setelah canonical conformance dan evidence gate.

**Gap yang tersisa**

- Urutan delivery konkret `canonical equity → atomic close → single writer/Telegram repair` tidak dipertahankan sebagai sequencing requirement. Ini tepat bila dipindahkan ke architecture/epics, tetapi implementer tidak boleh menyimpulkan semua slice aman dikerjakan paralel tanpa dependency gate.

### 2. ARCHITECTURE-SPINE.md

**Terjaga di PRD/addendum**

- AD-1 sampai AD-14 seluruhnya memiliki padanan substantif: immutable experiment identity; fill journal authority; pure strategy; terminal decision attribution; symmetric counterfactuals; common realistic execution; walk-forward promotion; canonical equity; fenced writer; portfolio namespace/isolation; ordered/idempotent events; evidence-preserving migration; fail-closed promotion.
- Consistency conventions untuk versioning, event/receive time, fixed-scale accounting, correlations, immutable configuration, and replay muncul di FR acceptance contracts, Quality and Safety Contract, dan NFRs.
- Structural seed tetap konsisten dengan Brownfield Migration Boundary, tetapi PRD sengaja tidak mengunci folder/stack.
- Deferred live-money scope dan SQLite-until-needed tetap konsisten: MVP tidak memiliki money-order authority dan PRD tidak memaksakan migrasi database.

**Gap yang tersisa**

- Spine mengunci SHA-256 atas canonical JSON dengan sorted keys, fixed decimal strings, dan UTC timestamps. PRD mengharuskan deterministic IDs/checksum dan byte-equivalent replay, tetapi tidak mempertahankan algorithm/canonicalization profile tersebut sebagai requirement eksplisit. Ini dapat ditetapkan di architecture tanpa mengubah outcome produk.

### 3. technical-autotrade-crypto-indodax-market-execution-risk-research-2026-08-12.md

**Terjaga di PRD/addendum**

- Typed immutable intent, durable terminal decision, idempotency, exact one logical effect, fill-based ledger, structured gate evidence, freshness/sequence validation, dynamic instrument constraints, realistic fee/spread/slippage, and reconciliation-before-resubmit tercakup oleh FR-1–FR-16.
- Failure isolation, entry fail-closed/protective exit precedence, single runtime writer, Telegram/dashboard as non-authoritative surfaces, and provenance trail tercakup oleh FR-5, FR-18–FR-20, FR-28–FR-31.
- Modular monolith/event-driven core, Redis/SQLite choices, and Indodax references tetap sebagai architecture evidence di addendum, bukan product mandate.

**Gap yang tersisa**

- Riset mencatat endpoint history `/tapi` legacy berhenti 7 April 2026 dan mensyaratkan verifikasi reconciliation terhadap `/api/v2/order/histories` serta `/api/v2/myTrades`. Addendum hanya menautkan API resmi; compatibility cutoff dan acceptance check API v2 belum dinyatakan.
- Queue contract rinci belum lengkap: acknowledge hanya setelah decision/order durable, poison message masuk dead-letter state, dan transactional outbox untuk side effects/notifikasi. PRD menjamin idempotency serta durable lifecycle, tetapi belum menyebut ketiga boundary failure ini secara eksplisit.
- Riset meminta operational state machine `STARTING/OBSERVING/DRYRUN_READY/LIVE_READY/DEGRADED/HALTED` serta isolasi kegagalan Telegram. PRD memiliki stage/authority dan incident behavior, tetapi belum menetapkan runtime health-state semantics atau apakah engine boleh berjalan tanpa control plane.

### 4. technical-crypto-autotrade-quant-profitability-research-2026-08-05.md

**Terjaga di PRD/addendum**

- Correctness-before-alpha, replayable decisions, temporal leakage controls, calibrated probability/abstention, regime/pair analysis, risk-aware sizing, realistic costs, and forward evidence tercakup secara normatif.
- Startup reconstruction, persistent Position/Policy State, stale-entry freeze with protective exit, idempotent order lifecycle, and canonical fill accounting tercakup.
- Risk controls dari riset kini lebih tegas melalui limit confirmed: 10% per Position, 40% exposure, 2% daily loss, 0,5% planned loss, dan 10% hard drawdown.
- Pemisahan research/paper/live dan live gating diperkeras menjadi PRD live-readiness terpisah.

**Gap yang tersisa**

- Operational housekeeping yang dibuktikan audit—log rotation/retention untuk log multi-GB, disk alert, bounded queue/task/retry, DB contention metric, dan backup/restore schedule—hanya tercakup sebagian oleh generic retention, backup drill, observability, dan recovery NFR. Target/SLO operasional konkretnya belum dipertahankan.

### 5. technical-patient-net-profit-swing-autotrade-research-2026-08-16.md

**Terjaga di PRD/addendum**

- Inti kualitatif “patient net-profit swing” tidak hilang: expected executable net edge setelah biaya, calibrated abstention/no-trade band, hysteresis, persisted high-water/trailing/time-stop state, hard invalidation precedence, and multi-day Horizon IDs tercakup di FR-4–FR-5 dan FR-8–FR-9.
- Strategy 2 sebagai isolated Challenger dengan portfolio dan attribution terpisah, shared simulator, deterministic replay, walk-forward shadow evaluation, and promotion gate tercakup oleh FR-15 dan FR-22–FR-27.
- Riset meminta simple/explainable rule-based baseline, bukan menyalin strategy eksternal atau mengejar trade count; ini konsisten dengan Executive Contract, Non-Goals, dan Counter-Metrics.
- State lifecycle rinci (`CANDIDATE → ARMED → PENDING → OPEN_RISK → BREAK_EVEN → ... → CLOSED`) digeneralisasi dalam PRD menjadi Candidate/Decision/Intent/Order/Fill/Position plus persisted Policy State. Detail substate Strategy 2 tepat untuk experiment/architecture spec, bukan requirement global.

**Gap yang tersisa**

- Tidak ada gap produk unik tambahan. Detail exit-envelope reason codes dan Strategy 2 substate graph tetap perlu diturunkan dalam strategy experiment spec agar generalisasi PRD tidak kehilangan semantics saat implementasi.

## Gap terkonsolidasi untuk handoff

1. **Exchange compatibility:** tambahkan acceptance architecture bahwa recovery/reconciliation memakai endpoint Indodax API v2 yang berlaku dan memverifikasi deprecation legacy endpoint.
2. **Durable delivery boundary:** tetapkan queue acknowledgment, dead-letter/poison handling, dan transactional outbox semantics.
3. **Runtime degradation semantics:** tetapkan operational state machine dan failure isolation Telegram/control-plane dari decision/risk/exit loops.
4. **Operational capacity controls:** turunkan log/disk/queue/DB/backup evidence menjadi measurable operational SLO dan acceptance tests.

Catatan non-gap: delivery order, canonical hash encoding, dan Strategy 2 detailed state graph memang hilang dari level PRD, tetapi sumber menempatkannya secara alami di architecture, epics, atau experiment specification. Semua perlu dibawa ke handoff agar tidak hilang dalam dekomposisi.
