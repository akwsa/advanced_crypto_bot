---
title: AutoTrade Replacement
status: final
created: 2026-08-25
updated: 2026-08-25
---

# PRD: AutoTrade Replacement

## Executive Contract

PRD ini mendefinisikan pengganti penuh AutoTrade bagi Officer serta untuk workflow produk/arsitektur dan para implementer. Istilah domain dikunci di Glossary; kemampuan dikelompokkan sebagai fitur dengan Functional Requirement (FR) stabil. Detail mekanisme dan sumber riset berada di `addendum.md`. Semua hal yang belum dikonfirmasi ditandai `[ASSUMPTION]`.

AutoTrade Replacement adalah sistem pengambilan keputusan dan lifecycle perdagangan yang dapat membuktikan—bukan sekadar mengklaim—bahwa keputusan entry, hold, dan exit konsisten, dapat direplay, serta memiliki net expectancy positif setelah seluruh biaya.

Sistem tidak mengejar jumlah transaksi atau akurasi label mentah. Ia memilih tindakan hanya ketika edge terkalibrasi melampaui biaya dan ketidakpastian; selain itu ia abstain. Semua keputusan, order, fill, Position, cash, risiko, dan outcome berasal dari fakta canonical yang dapat direkonstruksi.

Produk dibangun sebagai sistem DRY RUN berintegritas tinggi terlebih dahulu. Penggunaan uang asli merupakan tahap terpisah yang hanya dapat dibuka setelah evidence gate, operational gate, dan persetujuan Officer terpenuhi.

## Confirmed Product Decisions dan Risk Envelope

- Produk adalah internal single-operator system untuk seluruh pair spot-IDR yang lolos dynamic eligibility.
- Primary horizon mencakup swing intraday sampai multi-day, dipisahkan sebagai Experiment/Horizon ID.
- Strategy legacy boleh menjadi Champion hanya setelah memenuhi canonical conformance dan lulus seluruh evidence gate.
- Portfolio risk limits dan breach behavior mengikuti **Normative Risk Envelope** di bawah; hard drawdown breach memicu risk reduction menuju zero exposure.
- Real trading hanya dibahas dalam PRD terpisah setelah Strategy-ready lulus dan Officer meminta live-readiness assessment.

### Normative Risk Envelope

Tabel ini adalah source of truth untuk numeric portfolio risk limits. FR, gate, dan acceptance test di bagian lain menerapkan—dan tidak mendefinisikan ulang—nilai berikut.

| Control | Normative limit | Reference equity | Breach behavior |
|---|---:|---|---|
| Maximum notional satu Position | 10% | Equity pada decision time | ENTER ditolak atau sizing diturunkan |
| Total open exposure | 40% | Canonical equity | ENTER ditolak atau sizing diturunkan |
| Daily loss | 2% | Start-of-day equity setelah cash-flow adjustment | Entry latch ditutup sampai sesi berikutnya |
| Planned loss ke hard stop per trade | 0,5% | Equity pada decision time | ENTER ditolak atau sizing diturunkan |
| Hard maximum portfolio drawdown | 10% | Equity peak setelah external cash-flow adjustment | Entry dibatalkan, entry latch ditutup, dan risk-reduction EXIT dimulai menuju zero exposure |

## MVP Scope dan Stage Gates

### In Scope
- Canonical decision/event/fill/Position kernel.
- Persisted Policy State dan unified exit path.
- Point-in-time snapshots, outcome labels, trial ledger, dan Evidence Report.
- Interpretable Champion baseline dan minimal satu isolated Challenger.
- Unified realistic simulator dan DRY RUN shadow operation.
- Risk Governor, kill/freeze, reconciliation, dan invariant dashboard.
- Legacy migration/quarantine dan removal dual-write.

### Out of Scope for MVP
- Submission Order dengan uang asli; ditunda hingga PRD live-readiness terpisah.
- Dynamic allocation di antara banyak strategy.
- Automated retraining/promotion.
- Mobile trading UI atau public access.

### MVP Exit Gates

- **Platform-ready:** acceptance untuk canonical replay, accounting, invariants, migration, recovery, kill, dan fault injection lulus; tahap ini tidak memerlukan strategy yang profitable.
- **Strategy-ready:** satu Champion dan satu Challenger menghasilkan sealed OOS/shadow Evidence Report serta salah satu policy lulus seluruh promotion gates.
- **Live-readiness:** terpisah dari MVP; memerlukan observed execution calibration, production operational controls, independent approval, dan PRD/change proposal baru.

### Stage and Authority Matrix

| Stage | Allowed authority | Required evidence | Approval |
|---|---|---|---|
| Platform-ready | Replay, simulation, DRY RUN, reconciliation, dan fault injection; tidak ada executable money Order | Canonical accounting/invariants, migration, recovery, kill, dan fault-injection acceptance lulus | Officer menerima platform evidence |
| Strategy-ready | Satu Champion dapat menghasilkan DRY RUN Intent; Challenger tetap isolated/shadow | Sealed OOS/shadow Evidence Report dan seluruh promotion gates | Officer menyetujui Champion/version |
| Live-readiness | Belum termasuk MVP; hanya dapat dinilai melalui PRD/change proposal baru | Venue-observed execution calibration, production operational controls, dan evidence tambahan yang dipersyaratkan proposal | Independent approval dan persetujuan Officer |

## Brownfield Migration Boundary

- **Retire:** legacy decision overrides, direct `close_trade` settlement, dual source-of-truth, in-memory-only Policy State, generic reason paths, dan execution side effects dari display pipeline.
- **Reuse only behind adapters:** Indodax clients, market collectors, Telegram/dashboard surfaces, dan legacy strategy calculations. Komponen yang digunakan kembali tidak memperoleh write authority.
- **Rebuild:** decision/event schemas, fill accounting, Position/Policy State, simulator, risk governor, experiment/evidence store, promotion control, and reconciliation.
- External operator commands tetap tersedia melalui compatibility adapter selama migration, tetapi setiap write command harus menghasilkan canonical Intent/audit event.

## Target User dan Key User Journeys

Target utama adalah Officer sebagai operator tunggal, pemilik risiko, dan approver promosi strategy.

### 2.1 Jobs To Be Done

- Mengetahui mengapa bot entry, hold, exit, atau abstain tanpa membaca log mentah.
- Memastikan posisi, cash, P&L, order, dan risiko tidak berbeda antar-komponen.
- Membandingkan strategy secara adil pada snapshot dan biaya yang sama.
- Menghentikan risiko baru seketika tanpa menghalangi exit/reconciliation.
- Memutuskan promotion atau demotion berdasarkan bukti out-of-sample yang tersegel.
- Memulihkan sistem setelah restart atau gangguan tanpa mengubah keputusan historis.

### 2.2 Non-Users v1

- Pengguna publik atau multi-tenant.
- Pengguna yang mengharapkan profit terjamin.
- Strategy developer yang dapat mempromosikan model tanpa approval operator.

### 2.3 Key User Journeys

- **UJ-1. Officer memeriksa keputusan terbaru.** Officer membuka dashboard read-only, melihat Candidate Snapshot, Canonical Decision, alasan gate, ketidakpastian, biaya, state posisi, dan outcome. Display, journal, dan execution memakai decision ID yang sama.
- **UJ-2. Sistem mengelola satu posisi hingga terminal.** Candidate menjadi Intent, Order menerima nol atau lebih Fill, Position berpindah melalui lifecycle sah, lalu exit menutup exposure dan membukukan biaya/P&L secara atomik. Restart menghasilkan state sama setelah replay/reconciliation.
- **UJ-3. Officer menangani integrity incident.** Invariant failure atau stale market data menutup entry latch, mempertahankan exit/reconciliation, menampilkan evidence, dan tidak dapat auto-clear.
- **UJ-4. Officer menilai challenger.** Officer membandingkan Champion, Challenger, no-trade, dan benchmark pada window terkunci. Promotion ditolak bila data, biaya, sample, calibration, integrity, atau approval tidak lengkap.

## Domain Model dan Glossary

| Term | Normative meaning |
|---|---|
| Candidate Snapshot | Rekaman immutable input point-in-time sebelum gate pertama, termasuk data/version/freshness. |
| Canonical Decision | Satu hasil versioned untuk `ENTER`, `HOLD`, `EXIT`, atau `ABSTAIN`, beserta reason, uncertainty, dan provenance. |
| Intent | Permintaan durable yang diturunkan dari tepat satu Canonical Decision. |
| Order | Lifecycle instruksi execution yang dapat rejected, open, partial, filled, cancelled, expired, atau unknown. |
| Fill | Fakta execution atomic yang menjadi satu-satunya sumber perubahan cash dan Position. |
| Position | Exposure canonical yang direkonstruksi dari Fill dan lifecycle events. |
| Policy State | State persisted untuk hysteresis, invalidation, partial profit, trailing, dan time stop. |
| Champion | Policy version tunggal yang berhak menghasilkan executable Intent pada mode yang diizinkan. |
| Challenger | Policy version yang berjalan shadow pada Candidate Snapshot sama tanpa menyentuh Champion ledger. |
| Experiment | Run dengan universe, data, feature, policy, calibrator, simulator, cost model, seed, dan gate version yang dibekukan. |
| Evidence Report | Hasil tersegel yang mengukur integrity, calibration, execution, risk, dan performance suatu Experiment. |
| Promotion | Perubahan version/config terkontrol yang memberi policy kewenangan lebih tinggi. |
| Demotion | Pengurangan kewenangan policy karena safety breach atau degradation evidence. |
| Abstention Zone | Wilayah ketidakpastian/edge tempat Policy mempertahankan state dan tidak menambah turnover. |
| Integrity Incident | Pelanggaran truth-layer, idempotency, freshness, ownership, atau conservation invariant. |
| Horizon ID | Identifier immutable untuk cadence decision, maturity label, dan maximum holding rules suatu Experiment. |
| ENTER | Action yang boleh membuat satu Intent penambah exposure ketika tidak melanggar Position/risk state. |
| HOLD | Action untuk Position yang sudah ada: exposure target tidak berubah dan tidak ada Intent baru. |
| EXIT | Action pengurang exposure dengan target quantity eksplisit, hingga nol untuk full exit. |
| ABSTAIN | Tidak membuat Intent dan tidak mengubah exposure karena evidence/edge tidak memadai; untuk keadaan tanpa Position. |

## Functional Requirements

Bagian ini adalah katalog capability normatif. Setiap `FR-*` mempertahankan stable ID. Kalimat pembuka setiap FR menyatakan outcome produk; paragraf, daftar, state machine, precedence, taxonomy, tolerance, dan field detail di bawahnya adalah **Normative Acceptance Contract** untuk FR yang sama, bukan saran implementasi opsional.

### 4.1 Canonical Decision Spine

Setiap scan menghasilkan Candidate Snapshot dan tepat satu Canonical Decision. Display, persistence, replay, shadow evaluation, dan execution menggunakan objek sama. Tidak ada processing yang diam-diam mengganti action.

#### FR-1: Immutable candidate capture
Sistem menyimpan Candidate Snapshot sebelum gate pertama, dengan event/receive time, source offset, freshness, universe, feature/data/config versions. Snapshot historis tidak dapat ditulis ulang.

##### Normative Acceptance Contract

Snapshot/replay manifest juga memuat ordered input event IDs, scheduler trigger, nilai clock yang dibaca Policy, algorithm dan state RNG, versi numeric/runtime/environment, instrument metadata, serta external responses yang memengaruhi hasil.

Candidate ID diturunkan deterministik dari pair, Horizon ID, canonical bar/event close, scan-trigger version, dan data revision. Candidate dibuat sekali per closed-bar trigger; open Position juga dapat menghasilkan protective event-triggered Candidate dengan parent Position ID. Duplicate delivery memakai Candidate ID sama. Late correction membuat revision baru yang menautkan original; decision historis tidak berubah.

#### FR-2: Single canonical action
Sistem menghasilkan tepat satu Canonical Decision per Candidate Snapshot dan Policy version. Displayed, persisted, replayed, dan executed action memiliki decision ID sama; setiap no-action path memiliki taxonomy reason spesifik.

##### Normative Acceptance Contract

**Action-state contract:**
- Tanpa Position: hanya `ENTER` atau `ABSTAIN` legal.
- Dengan Position: hanya `HOLD` atau `EXIT` legal; penambahan/pyramiding tidak termasuk MVP.
- Risk/integrity veto mengalahkan alpha action; veto entry menjadi `ABSTAIN`, sedangkan protective `EXIT` tidak boleh diturunkan menjadi `HOLD`.
- Setiap illegal transition ditolak dan menjadi Integrity Incident.

#### FR-3: Deterministic replay
Snapshot dengan seluruh version sama menghasilkan decision serta Policy State transition identik.

##### Normative Acceptance Contract

Acceptance membandingkan serialized decision/event bytes dengan mengabaikan hanya field yang secara eksplisit dinyatakan non-semantic. Perbedaan pada semantic field apa pun merupakan failure.

#### FR-4: Calibrated abstention
Policy hanya melakukan `ENTER` atau mempertahankan exposure ketika net edge setelah biaya melampaui uncertainty boundary yang dipraregistrasi; selain itu, Policy memilih `ABSTAIN` atau `HOLD` sesuai state.

##### Normative Acceptance Contract

Target adalah horizon-specific executable net-return distribution setelah biaya. Experiment membekukan calibration population, horizon, minimum effective sample size, proper scores/coverage statistic, uncertainty bound, utility, dan pass/fail boundary. Missing calibration evidence selalu abstain.

#### FR-5: Hysteresis
Policy menggunakan boundary masuk, bertahan, dan keluar berbeda agar noise kecil tidak menyebabkan churn.

##### Normative Acceptance Contract

Urutan precedence dari tertinggi ke terendah adalah: operator kill atau emergency zeroing → hard-drawdown risk reduction → hard invalidation atau stop → reconciliation-forced action → partial profit, trailing, atau time stop → alpha EXIT → HOLD. Calibration/change alarm memblokir ENTER tetapi tidak mengalahkan protective EXIT. Partial Fill mempertahankan precedence protection pada remaining quantity.

Setiap Policy version menyimpan enter/hold/exit boundaries, minimum confirmation count, debounce/dwell, gap behavior, dan boundary version di Policy State. Baseline Champion `[ASSUMPTION]` memerlukan dua consecutive closed-bar confirmations untuk ENTER, satu untuk protective EXIT, dan dua untuk alpha-only EXIT. Data gap mereset ENTER confirmation tetapi tidak mereset Position protection/high-water state.

### 4.2 Canonical Order, Fill, dan Position Lifecycle

Intent tidak langsung mengubah Position. Hanya Fill mengubah cash/exposure. Lifecycle events append-only, idempotent, ordered, dan dapat direkonstruksi.

#### FR-6: Intent-to-fill lifecycle
Sistem melacak Intent → Order → Fill → Position sampai terminal, termasuk partial fill, reject, cancel/fill race, expiry, duplicate, out-of-order, dan unknown result.

##### Normative Acceptance Contract

Setiap Order harus mencapai `FILLED`, `CANCELLED`, `REJECTED`, atau `EXPIRED`. `UNKNOWN` adalah recovery state dengan batas waktu query/retry `[ASSUMPTION]` 60 detik. Selama state ini, entry untuk account dan pair terkait dibekukan, dan resubmission dilarang sampai reconciliation membuktikan terminal state.

Intent dan outbox event disimpan secara atomik sebelum dispatch. Queue delivery menerima explicit acknowledgment hanya setelah durable settlement. Retry yang habis masuk dead-letter dengan original payload, attempt history, reason, dan operator-visible recovery action. Acknowledgment tanpa terminal decision atau explicit retry state adalah Integrity Incident.

#### FR-7: Fill-based accounting
Cash dan Position hanya berubah dari Fill tervalidasi; fee, tax, clearing, maker/taker role, dan rounding dibukukan per Fill dengan conservation checks.

#### FR-8: Atomic exit
SL, hard invalidation, partial profit, trailing, time stop, signal exit, dan operator exit memakai settlement path canonical sama.

##### Normative Acceptance Contract

Setiap EXIT membawa target quantity, precedence reason, deterministic event key, dan expected Policy State transition. Fill parsial mengurangi Position hanya sebesar Fill; sisa exposure tetap protected.

#### FR-9: Persisted Policy State
Sistem menyimpan entry-time parameters, remaining quantity, partial flags, high-water mark, trailing level, invalidation, time deadline, dan state sequence.

#### FR-10: Restart equivalence
Startup replay dan reconciliation mengembalikan Order, Position, cash, Policy State, dan pending action sama tanpa strategy decision baru.

#### FR-11: Reconciliation
Sistem membandingkan journal internal dengan recovery evidence. Mismatch membekukan entry dan memulai correction workflow yang teraudit; sistem tidak menimpa data secara diam-diam.

##### Normative Acceptance Contract

Exchange-confirmed execution/order/account evidence adalah authoritative untuk fakta venue; append-only internal journal authoritative untuk intent, approval, dan provenance. Correction hanya dapat berupa `ADJUSTMENT_QUARANTINE`, `EXTERNAL_FILL_IMPORT`, `ORDER_STATE_CORRECTION`, atau `FORCED_CLOSE_REQUEST`, masing-masing mereferensikan evidence dan approval. Correction tidak boleh memalsukan strategy decision atau menghapus event lama.

Indodax API v2 order, trade, dan account recovery endpoints wajib lulus contract/integration tests sebelum digunakan sebagai authoritative evidence. Deprecated legacy history endpoints tidak memenuhi acceptance.

### 4.3 Market Data dan Execution Realism

Keputusan dan simulator memakai harga executable, bukan last/candle close. Market data, instrument rules, latency, spread, depth, fee, dan fill uncertainty menjadi evidence.

#### FR-12: Point-in-time market state
Sistem menyimpan market snapshot yang cukup untuk menghitung executable price pada size diminta.

##### Normative Acceptance Contract

Snapshot minimum memuat ordered bid/ask depth yang cukup untuk melampaui requested size, sequence dan offset, event time dan receive time, instrument metadata version, serta source. Insufficient depth menghasilkan `ABSTAIN` dan tidak boleh diisi dengan candle/last-price fallback.

#### FR-13: Freshness and gap control
Stale, future-dated, gapped, atau unordered market data menyebabkan abstention/freeze sesuai severity.

##### Normative Acceptance Contract

Untuk executable decision, L2 age maksimum `[ASSUMPTION]` 3 detik, clock skew maksimum `[ASSUMPTION]` 1 detik, dan sequence gap nol. Gap/clock breach membekukan entry sampai snapshot recovery tervalidasi; exit menggunakan recovery-price policy konservatif yang versioned.

#### FR-14: Instrument constraints
Sistem memvalidasi min amount, precision, price increment, dan metadata version sebelum Order dibuat.

#### FR-15: Unified simulator
Historical replay dan live DRY RUN memakai simulator version sama, termasuk book-walk, latency, partial/non-fill, cancellation, rejection, adverse selection, dan seluruh biaya.

##### Normative Acceptance Contract

MVP fidelity wajib: deterministic L2 book-walk, versioned decision-to-submit/ack latency, maker/taker fee-tax, precision/minimums, partial/non-fill, reject, cancel/fill race, duplicate/out-of-order event corpus. Queue-position learning dan advanced adverse-selection model ditunda sampai baseline calibration tersedia.

#### FR-16: Execution calibration
Evidence Report membandingkan predicted versus observed fill probability, latency, implementation shortfall, spread, slippage, rejection, partial, dan cancel rate.

##### Normative Acceptance Contract

Evidence ditandai `OBSERVED`, `INFERRED`, atau `SIMULATED`; hanya venue/shadow-observed evidence dapat mengkalibrasi promotion menuju live-readiness. Setiap Experiment membekukan estimator, calibration window, tolerances, dan scenario corpus sebelum scoring.

### 4.4 Risk Governor dan Operational Safety

Risk Governor independen dari alpha Policy. Safety failure selalu mengalahkan performance target dan tidak menghalangi pengurangan risiko.

#### FR-17: Pre-trade risk controls
Sistem menerapkan max order/notional/Position, concentration, available cash, price collar, stale-data, daily loss, drawdown, turnover, dan portfolio exposure limits sesuai **Normative Risk Envelope**. Liquidity, correlation, stop distance, dan uncertainty hanya dapat menurunkan sizing.

#### FR-18: Entry-only circuit breaker
Risk breach menutup entry baru tetapi tetap mengizinkan cancel, exit, reconciliation, dan monitoring.

##### Normative Acceptance Contract

Canonical equity adalah cash + fresh executable liquidation value seluruh Position − liabilities/estimated exit costs. Equity peak adalah high-water mark yang disesuaikan terhadap external cash flow. Nilai ini tidak dapat diturunkan atau direset, kecuali ketika memulai Experiment atau portfolio baru dengan approval yang teraudit. Valuation dihitung pada setiap market update Position dan tepat sebelum entry. Pada hard maximum portfolio drawdown dalam **Normative Risk Envelope**: cancel seluruh unfilled entry Orders, latch entry, buat highest-precedence risk-reduction EXIT menuju zero exposure, dan eskalasi incident; slippage dapat membuat realized drawdown melebihi trigger, sehingga limit tersebut adalah trigger, bukan jaminan loss cap.

Jika mark stale/halted atau depth tidak cukup saat breach, latch tetap aktif, venue/account/Order state direconcile, working entry dibatalkan, dan EXIT dicoba melalui versioned conservative execution policy tanpa memakai fabricated price. Quantity di bawah minimum venue diklasifikasikan sebagai quarantined dust, disertai incident dan valuation; quantity tersebut tidak dianggap `CLOSED`. UNKNOWN Order diselesaikan sebelum exposure baru diasumsikan.

#### FR-19: Independent kill control
Operator dapat mengaktifkan kill latch yang tidak bisa dihapus otomatis; working Orders ditangani sesuai runbook.

##### Normative Acceptance Contract

Kill state machine: `ARMED → TRIGGERED → CANCEL_PENDING → EXIT_PENDING → RECONCILING → LATCHED_SAFE`. Trigger segera menolak entry, membatalkan working entry Orders dengan deadline/retry, meng-query UNKNOWN Orders sebelum resubmit, mempertahankan/menjalankan protective EXIT, lalu mewajibkan reconciliation. Hanya approval operator setelah evidence lengkap dapat kembali ke `ARMED`.

#### FR-20: Single-writer authority
Tepat satu runtime mempunyai hak menulis production queue/ledger; stale writer ditolak.

##### Normative Acceptance Contract

Setiap write membawa monotonically increasing fencing epoch dari lease authority. Database/outbox/queue consumers menolak epoch lebih rendah atau lease expired. Takeover hanya setelah lease expiry dan reconciliation; network partition tidak memberi writer lama grace write. Semua legacy/compatibility adapters wajib melewati fenced canonical command boundary; direct database write adalah Integrity Incident.

#### FR-21: Change/degradation governor
Change detector dan sequential monitor dapat menurunkan risk atau memindahkan policy ke shadow, tetapi tidak dapat mempromosikan atau auto-retrain sendiri.

Runtime mempunyai degradation states `HEALTHY`, `ENTRY_FROZEN`, `SHADOW_ONLY`, dan `SAFE_LATCHED`. Kegagalan notification atau Telegram tidak boleh mengubah Canonical Decision, queue settlement, Order handling, atau risk state. Notification adalah isolated non-authoritative consumer dengan retry/dead-letter sendiri.

### 4.5 Champion, Challenger, dan Experiment Governance

Champion sederhana dan dapat dijelaskan menjadi baseline. Challenger berjalan pada snapshot dan simulator sama dengan ledger terisolasi. Semua trial, termasuk gagal, tercatat.

#### FR-22: Frozen experiment
Setiap Experiment membekukan universe, windows, features, policy, calibrator, simulator, cost model, seed, dan gate version.

##### Normative Acceptance Contract

Formula dynamic eligibility dan effective-dated membership juga dibekukan pada satu point in time. Pair eligibility wajib mempertimbangkan metadata validity, listing age, history completeness, L2 freshness/depth at target size, spread, projected round-trip cost, precision/minimum, dan concentration/correlation; exclusion selalu memiliki reason code. Membership dievaluasi harian untuk Experiment berikutnya dan tidak ditulis ulang retrospektif.

MVP Horizon IDs adalah `[ASSUMPTION]` `15M`, `1H`, `4H`, dan `1D`. Label maturity yang berlaku adalah 1h, 4h, 24h, dan 72h. Satu Position dimiliki tepat satu strategy/Horizon ID. MVP melarang concurrent Position pada pair sama lintas Horizon; protective EXIT selalu mengalahkan ENTER Candidate lain.

#### FR-23: Immutable trial ledger
Sistem mencatat seluruh percobaan, parameter search, hasil gagal, dan data lineage agar selection bias dapat diukur.

#### FR-24: Leakage-safe evaluation
Evaluasi menggunakan chronological walk-forward dengan purge/embargo dari event/label horizon dan untouched forward/shadow window.

##### Normative Acceptance Contract

Outcome `UNSCORABLE` hanya legal untuk taxonomy tertutup: stale/gapped source, delisting/halt, missing required horizon data, atau invalid instrument metadata. Reason ditetapkan dari evidence yang tidak memakai realized outcome; post-hoc relabel dilarang. Jika `UNSCORABLE` > `[ASSUMPTION]` 5% matured Candidates pada evaluation window, Evidence Report tidak eligible untuk promotion.

#### FR-25: Common comparison
Champion, Challenger, no-trade, dan benchmark executable menerima Candidate Snapshot, cost assumptions, serta opportunity set sama.

##### Normative Acceptance Contract

Benchmark dipraregistrasi sebelum Experiment: cash/no-trade dan satu simple costed rule dengan exposure/opportunity matching, termasuk cash yield, rebalance, sizing, costs, dan replacement governance. Benchmark tidak dapat diganti setelah hasil window terlihat.

#### FR-26: Sealed Evidence Report
Promotion hanya membaca Evidence Report immutable berisi integrity, sample sufficiency, net expectancy distribution, calibration, drawdown/tail, turnover, concentration, DSR/PBO, dan execution calibration.

##### Normative Acceptance Contract

Sebelum window dibuka, Report membekukan: sampling unit (satu lifecycle Position; partial exit bukan trade baru), exposure-overlap clusters dan effective sample size, regime detector dan version, required regime observations, return series, benchmark, bootstrap/CV method, multiple-testing family, estimators, serta conjunctive pass logic. Profit concentration menggunakan absolute positive contribution. Exposure/risk concentration menggunakan treatment yang ditetapkan secara eksplisit ketika aggregate profit ≤0.

Sebelum Experiment dimulai, Officer menyetujui versioned Evidence Specification yang mengunci moving/block-bootstrap method dan block rule, DSR/PBO trial family, effective-sample minimum, confidence construction, calibration metrics, regime criteria, dan exact conjunctive pass logic. Missing field atau post-window method change membuat report tidak promotable.

Perubahan Evidence Specification selalu membuat Experiment family baru. Failed trials dan evidence family lama tetap dihitung dalam multiple-testing/trial history dan tidak dapat dihapus/reset untuk memperoleh gate lebih mudah. Cross-family comparison wajib mengungkap seluruh method/version changes.

#### FR-27: Staged promotion and demotion
Kewenangan meningkat hanya pada fixed review windows; safety breach segera halt, statistical degradation mengembalikan policy ke shadow.

##### Normative Acceptance Contract

Legacy strategy hanya eligible menjadi Champion setelah dipindahkan ke Canonical Decision Spine, Fill lifecycle, Policy State, dan seluruh truth-layer invariants; profitability legacy projection tidak cukup.

### 4.6 Operator Control dan Auditability

Officer memperoleh cockpit read-only untuk health, exposure, keputusan, evidence, dan promotion state. Write actions terpisah, authenticated, dan teraudit.

#### FR-28: Decision provenance
Officer dapat melihat Candidate Snapshot → Canonical Decision → Intent → Order → Fill → Position → outcome sebagai satu correlation trail.

#### FR-29: Integrity dashboard
Dashboard menampilkan writer authority, data freshness, invariant status, queue/order health, Position/cash reconciliation, dan active incidents.

#### FR-30: Strategy evidence dashboard
Dashboard membandingkan strategy/version per regime dan horizon tanpa mencampur train, validation, shadow, atau live evidence.

#### FR-31: Approval audit
Promotion, demotion override, kill reset, reconciliation correction, dan future live enablement membutuhkan actor, timestamp, reason, evidence reference, serta immutable audit event.

### 4.7 Legacy Retirement dan Migration

#### FR-32: Validated migration
Sistem memigrasikan fakta legacy yang dapat dibuktikan, mengarantina ambiguous records, dan menghasilkan pre/post reconciliation report dari backup tervalidasi.

##### Normative Acceptance Contract

Migration acceptance wajib menginventarisasi seluruh legacy orders/trades/pending/balances/positions dan mengklasifikasikannya sebagai `PROVEN_OPEN`, `PROVEN_CLOSED`, `AMBIGUOUS`, atau `NON_CANONICAL_HISTORY`. Evidence hierarchy: venue/recovery evidence → canonical Fill journal → atomic legacy execution evidence → projection only. Proven ghost positions ditutup melalui additive correction event yang menunjuk exit evidence; ambiguous exposure dikarantina, entry dibekukan, dan Officer menjadi approval owner. Monetary tolerance maksimum 1 IDR dan quantity tolerance maksimum satu instrument precision unit. Cutover mensyaratkan zero unexplained mismatch, zero UNKNOWN working Order, backup/restore drill lulus, serta semua ambiguous record memiliki disposition. Rollback mengembalikan code/config tetapi tidak menghapus migration/correction events.

Setiap migration/cutover mengikat source commit, environment manifest, database backup hash, schema version, event high-water mark, dan approved reconciliation report. Timeline ghost Position ACE/BICO/HUMANITY serta stale HOME/ACE PENDING orders dari insiden Agustus 2026 menjadi mandatory regression/recovery fixtures.

#### FR-33: No dual-write cutover
Setelah cutover, legacy tables menjadi projection/read-only dan tidak menjadi source of truth kedua.

#### FR-34: Rollback without history rewrite
Rollback code/config tidak menghapus event, decision, trial, fill, atau approval history.

## Quality and Safety Contract

Bagian ini menggabungkan guardrails, NFR, dan minimum invariants sebagai kontrak lintas-fitur.

### Safety
- MVP hanya DRY RUN/shadow; tidak mengirim Order uang asli.
- Tidak ada auto-promotion, auto-clear kill, atau reset drawdown untuk melewati gate.
- Missing/stale evidence menolak entry/promotion.
- Secrets tidak masuk snapshot, log, report, atau dashboard.

### Data Governance
- Event, snapshot, trial, dan report memiliki retention, schema version, checksum, dan provenance.
- Event time dan receive time disimpan terpisah; corrections additive dan tidak menghapus fakta asli.
- Threat model mencakup writer compromise, operator error, replay tampering, dan storage rollback. Write authority terpisah dari report verification; hash chain/checkpoint diverifikasi berkala, correction menunjuk event sebelumnya, dan acceptance membuktikan historical rewrite terdeteksi.
- Retention baseline `[ASSUMPTION]`: continuous raw L2 30 hari; Candidate market snapshots dan replay manifests 2 tahun; canonical decisions/intents/orders/fills/positions, trial ledger, Evidence Reports, incidents, corrections, dan approvals 7 tahun. Expiry tidak boleh menghapus evidence yang masih direferensikan Experiment/promosi aktif.

### Operational
- Deployment menghasilkan environment manifest dan dependency hash.
- Semua clocks yang memengaruhi decision/execution dimonitor.
- Exit/reconciliation memiliki priority budget di atas scanning/entry.

### Cross-Cutting NFRs

- **NFR-1 Reliability:** Tidak ada acknowledged event hilang; restart/replay equivalence 100% pada acceptance corpus.
- **NFR-2 Integrity:** Ledger, cash, Position, Policy State, dan projection invariants lulus setiap settlement/reconciliation.
- **NFR-3 Idempotency:** Duplicate/retry tidak menghasilkan duplicate effect.
- **NFR-4 Observability:** Setiap decision/event mempunyai correlation/causation ID, structured reason, version, dan latency timestamps.
- **NFR-5 Performance:** `[ASSUMPTION]` Canonical Decision selesai sebelum snapshot melewati freshness budget; batas numeriknya ditetapkan dalam architecture.
- **NFR-6 Recovery:** `[ASSUMPTION]` RTO DRY RUN ≤15 menit dan RPO event journal = 0 acknowledged events.
- **NFR-7 Security:** Least privilege, secret isolation, authenticated actions, dan tamper-evident audit.
- **NFR-8 Determinism:** Snapshot + versions + seed sama menghasilkan decision, simulated fills, dan accounting sama.
- **NFR-9 Operational SLO:** `[ASSUMPTION]` Queue oldest-age <60 detik; dead-letter growth menghasilkan immediate alert; database integrity check berjalan harian; disk warning berlaku pada 70% dan entry freeze pada 85%; log rotation tervalidasi; backup terenkripsi berjalan harian; restore drill berjalan bulanan. Architecture boleh memperketat baseline ini, tetapi tidak boleh melonggarkannya tanpa approval.

Minimum invariant set: exactly one active writer epoch; one Canonical Decision per Candidate/Policy; one Intent effect per decision/action; Fill quantity/fees/cash conservation; Position quantity equals ordered Fill aggregate; no terminal Order with unresolved quantity; no CLOSED Position with exposure; Policy State quantity equals Position; cash + reserved cash consistency; risk limits computed from same canonical equity; all projections reconcile to journal; correlation/causation chain complete.

## Non-Goals

- Menjamin profit atau memilih “AI paling akurat” dari leaderboard tunggal.
- Mengoptimalkan raw accuracy, win rate, jumlah trade, atau gross return.
- High-frequency/latency-arbitrage trading.
- Multi-exchange, derivatives, leverage, short selling, atau multi-user SaaS pada MVP.
- Membiarkan LLM membuat executable trading decision.
- Mempertahankan behavior strategy legacy tanpa evidence positif.

## Success and Promotion Metric Contract

| Metric layer | Measurement unit | Pass boundary source | Evidence source |
|---|---|---|---|
| Platform integrity | Candidate, event, decision, ledger/Position state, and replay corpus | SM-1–SM-3, SM-6–SM-8 dan NFR acceptance | Canonical journal, invariant checks, reconciliation, replay/fault-injection reports |
| Strategy evidence | Completed Position lifecycle dan exposure-overlap effective sample | SM-4–SM-5 dan Strategy Evidence/Promotion Gate; unresolved values point to A-03/A-04 | Sealed OOS/shadow Evidence Report |
| Counter-metrics | Trade count, raw accuracy/win rate, gross P&L, best backtest | Tidak pernah menjadi standalone pass boundary | Trial ledger dan Evidence Report |

### Platform Integrity Metrics
- **SM-1 Truth-layer integrity:** zero unexplained ledger/Position/cash/Policy State mismatch.
- **SM-2 Decision reproducibility:** 100% identical decision/state untuk identical replay.
- **SM-3 Evidence completeness:** 100% actionable Candidate terminal; 100% matured Candidate punya outcome/`UNSCORABLE`; generic reason <0,5%.
- **SM-4 Net edge:** `[ASSUMPTION]` net expectancy lower confidence bound >0 versus executable benchmark pada locked OOS/shadow evidence.

### Strategy Evidence dan Promotion Gate Awal
- `[ASSUMPTION]` Minimum 30 hari multi-regime dan 100 independent matured trades.
- `[ASSUMPTION]` Profit factor ≥1,20 dan probability net expectancy positif ≥95%; hard maximum portfolio drawdown mengikuti **Normative Risk Envelope**.
- `[ASSUMPTION]` DSR probability ≥95% dan PBO ≤10%, dengan seluruh trial tercatat.
- Zero Integrity Incident/unreconciled Order/Fill selama promotion window.
- Untuk Strategy-ready, simulated fills dan shadow-observed executable market costs berada dalam predeclared simulator envelope; venue-observed realized execution calibration baru wajib untuk Live-readiness.
- Tidak ada satu pair yang boleh menyumbang lebih dari 35% absolute positive contribution atau lebih dari 35% aggregate risk/exposure contribution. Aggregate net profit ≤0 selalu gagal.
- Sampling unit adalah completed Position lifecycle; overlapping exposures dikelompokkan dan effective sample size dilaporkan. Regime detector/version dan minimum observations dibekukan; jika required regimes tidak muncul, window diperpanjang dan tidak boleh dinyatakan lulus.
- DRY RUN counterfactual fills hanya dapat membuktikan Strategy-ready. Live-readiness memerlukan separately labeled venue-observed market/order/fill evidence; inferred/simulated values tidak dihitung sebagai observed calibration.

### Supporting Quality Metrics
- **SM-5 Calibration:** predicted distribution memenuhi proper-score dan coverage tolerance per horizon/regime.
- **SM-6 Recovery:** restart/reconciliation memenuhi RTO/RPO tanpa duplicate effect.
- **SM-7 Operations:** zero stale-writer acceptance, unresolved event-loop fault, dan pending-order terminal gap.
- **SM-8 Detector health:** 100% declared invariants mempunyai automated check/fault-injection coverage; detected/corrected incidents tetap dihitung dan tidak dihapus dari promotion evidence.
- **SM-9 Decision stability diagnostic:** Flip-rate `ENTER/ABSTAIN` dan `HOLD/EXIT` diukur per pair dan Horizon ID pada adjacent Candidate Snapshots, bersama perubahan edge, uncertainty, market revision, dan Policy State. Flip tanpa perubahan input/state material adalah failed determinism evidence, bukan performance metric untuk dioptimalkan.

### Counter-Metrics
- **SM-C1 Trade count:** lebih banyak trade bukan keberhasilan.
- **SM-C2 Raw accuracy/win rate:** tidak dioptimalkan tanpa payoff, biaya, calibration, dan abstention.
- **SM-C3 Gross P&L:** tidak dipakai tanpa biaya, exposure, dan drawdown.
- **SM-C4 Best backtest:** tidak dipakai tanpa trial ledger, leakage controls, DSR/PBO, dan forward evidence.

## Risk Register

| Risk | Trigger/evidence | Mitigation / controlling requirement | Owner |
|---|---|---|---|
| Overfitting | Trial selection atau OOS degradation | Trial ledger, locked windows, purge/embargo, benchmark, DSR/PBO; FR-23–FR-26 | Product/evidence owner |
| Non-stationarity | Calibration/change alarm | Abstention, calibration monitoring, change alarm sebagai risk governor; FR-4 dan FR-21 | Risk governor owner |
| Execution optimism | Simulator-observed divergence | Executable prices, conservative fill model, execution calibration; FR-12–FR-16 | Execution owner |
| State divergence | Invariant atau reconciliation failure | Append-only Fill facts, one settlement path, continuous invariants; FR-7–FR-11 | Truth-layer owner |
| Split-brain | Lease/fencing conflict | Writer fencing, independent kill, reconciliation; FR-19–FR-20 | Runtime owner |
| Scope explosion | Proposal di luar MVP boundary | Single operator, eligible spot-IDR universe, DRY RUN, satu Champion plus satu Challenger | Officer/Product owner |

## Open Questions

Tidak ada phase-blocking product question. Seluruh baseline assumption di bawah harus divalidasi melalui architecture atau telemetry sebelum ditetapkan sebagai requirement normatif.

## Decision and Assumption Register

Inline `[ASSUMPTION]` markers tetap menjadi penanda normatif bahwa nilai belum dikonfirmasi. Register ini adalah source of truth untuk lokasi, baseline, dan kebutuhan validasinya; architecture/telemetry wajib menunjuk evidence sebelum mengubah status.

- **A-01 · NFR-5:** latency diikat freshness budget; angka ditetapkan architecture.
- **A-02 · NFR-6:** DRY RUN RTO ≤15 menit dan RPO acknowledged event nol.
- **A-03 · SM-4:** lower confidence bound net expectancy harus positif.
- **A-04 · Promotion Gate:** angka sample/performance/risk adalah governance proposal awal, bukan konstanta universal.
- **A-05 · FR-13:** executable L2 age maksimum 3 detik dan clock skew maksimum 1 detik adalah baseline awal yang harus divalidasi architecture/observed telemetry.
- **A-06 · FR-6:** UNKNOWN recovery deadline 60 detik adalah baseline awal.
- **A-07 · FR-22:** Horizon IDs `15M/1H/4H/1D` dan label maturities 1h/4h/24h/72h adalah baseline awal.
- **A-08 · FR-24:** `UNSCORABLE` maksimum 5% matured Candidates adalah baseline awal.
- **A-09 · Data Governance:** retention 30 hari/2 tahun/7 tahun adalah baseline capacity assumption.
- **A-10 · FR-5:** baseline confirmation count dua ENTER, satu protective EXIT, dan dua alpha EXIT harus divalidasi per Horizon ID.
- **A-11 · NFR-9:** queue, disk, dan backup operational SLO adalah baseline awal yang harus divalidasi terhadap VM capacity.
