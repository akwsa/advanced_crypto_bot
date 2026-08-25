---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/prd.md
  - _bmad-output/planning-artifacts/prds/prd-advanced_crypto_bot-2026-08-25/addendum.md
workflowType: research
lastStep: 6
research_type: technical
research_topic: impactful modern trading methods for AutoTrade Replacement architecture
research_goals: identify current evidence-backed methods that materially improve net trading outcomes and translate them into architecture decisions
user_name: Officer
date: 2026-08-25
web_research_enabled: true
source_verification: true
---

# Research Report: Technical

**Date:** 2026-08-25
**Author:** Officer
**Research Type:** Technical

---

## Research Overview

Riset ini menilai metode trading dan pola implementasi mutakhir yang dapat mengubah hasil bersih AutoTrade Replacement setelah biaya, slippage, ketidakpastian, dan perubahan regime. Temuan hanya dibawa ke Architecture Spine bila menghasilkan constraint, measurement contract, atau evidence gate yang dapat diuji. Sumber diprioritaskan dari dokumentasi resmi, standard, dan paper primer; klaim baru atau yang belum tervalidasi pada INDODAX diberi batas confidence dan tidak dipromosikan menjadi default.

Kesimpulan utamanya adalah bahwa peningkatan terbesar kemungkinan datang dari disiplin `forecast → abstain → size → execute → reconcile`, bukan penambahan indikator atau kompleksitas model. Architecture-mandatory findings adalah cost-aware abstention, point-in-time universe, calibrated uncertainty, fill-aware execution/TCA, leakage-safe evidence, portfolio risk separation, dan change detection sebagai risk control. Alpha methods tetap diperlakukan sebagai Challenger sampai net-of-cost evidence pada pair IDR membuktikannya. Ringkasan lengkap berada pada bagian **Research Synthesis**.

## Executive Summary

AutoTrade Replacement sebaiknya dibangun sebagai hexagonal modular monolith dengan satu canonical writer, append-only trading facts, fill-derived accounting, transactional outbox, dan read-only projections. INDODAX V2, Redis, Telegram, dashboard, simulator, dan Strategy adalah adapters; tidak satu pun memperoleh authority untuk membentuk Position atau equity di luar canonical settlement path.

Temuan trading paling menjanjikan untuk diuji adalah simple long/cash momentum sebagai baseline Challenger dan signed order flow sebagai higher-complexity Challenger. Initial executable policy tetap no-entry sampai salah satu kandidat lulus gate. Keduanya memerlukan venue-specific costs, point-in-time eligibility, calibrated abstention, dan forward shadow evidence. Regime detection dan conformal uncertainty lebih kuat sebagai protection/deferral mechanism daripada alpha generator. Mean reversion 15 menit, triangular arbitrage, deep/RL-first, indicator zoo, dan unrestricted Kelly tidak layak menjadi default.

Temuan operasional terbaru mengubah keputusan storage: runtime saat ini memakai SQLite 3.45.1, yang termasuk rentang WAL-reset corruption bug. SQLite WAL hanya dapat dipakai setelah deployment runtime menggunakan exact qualified build; pin awal yang current pada tanggal riset adalah SQLite 3.53.4, sedangkan 3.51.3 hanya safe floor historis dan numeric lower bound saja tidak cukup untuk menolak withdrawn/unqualified releases.

## Table of Contents

1. Technical Research Scope Confirmation
2. Technology Stack Analysis
3. Integration Patterns Analysis
4. Architectural Patterns and Design
5. Implementation Approaches and Technology Adoption
6. Technical Research Recommendations
7. Research Synthesis
8. Methodology, Limitations, and Source Register

## Technical Research Scope Confirmation

**Research Topic:** Impactful modern trading methods for AutoTrade Replacement architecture
**Research Goals:** Mengidentifikasi metode terkini berbasis bukti yang berdampak material pada net trading outcome dan menerjemahkannya menjadi keputusan arsitektur.

**Technical Research Scope:**

- Architecture Analysis — design patterns, frameworks, dan system architecture
- Implementation Approaches — development methodologies dan coding patterns
- Technology Stack — languages, frameworks, tools, dan platforms
- Integration Patterns — APIs, protocols, dan interoperability
- Performance Considerations — scalability, optimization, dan operational patterns

**Research Methodology:**

- Current web data dengan verifikasi sumber primer
- Multi-source validation untuk klaim kritis
- Confidence level untuk informasi yang belum pasti
- Penilaian dampak bersih sesudah biaya dan risiko overfitting

**Scope Confirmed:** 2026-08-25

---

## Technology Stack Analysis

### Programming Language

Python tetap menjadi pilihan paling rendah risiko untuk brownfield ini karena seluruh runtime, model kuantitatif, dan test corpus sudah berada di Python. Baseline pengembangan nyata memakai Python 3.12.3, sedangkan Dockerfile masih memakai Python 3.11; perbedaan runtime ini harus dihapus sebelum hasil replay atau evidence dianggap reproducible. Python 3.12 menyediakan `asyncio.TaskGroup` untuk structured concurrency dan propagasi kegagalan yang lebih kuat daripada task lepas. Free-threaded Python yang muncul sejak 3.13 tidak dipilih karena belum diperlukan untuk beban I/O bot dan akan memperbesar matriks kompatibilitas library.

**Dampak arsitektur:** `[ASSUMPTION]` pertahankan line Python 3.12 dan pin current security release CPython 3.12.14 yang sama untuk development, CI, simulator, dan deployment; semua dependensi memakai lock dengan hash. CPU-heavy research/backtest berjalan di process terisolasi, bukan di event loop trading.

Sumber versi: [Python versions](https://www.python.org/doc/versions/).

Sumber: [Python 3.12 asyncio tasks](https://docs.python.org/3.12/library/asyncio-task.html), [Python free-threading](https://docs.python.org/3/howto/free-threading-python.html).

### Frameworks dan Libraries

Tidak diperlukan web framework atau distributed-computing framework baru pada MVP. Domain kernel harus berupa Python package murni dengan ports/adapters; `asyncio` digunakan di runtime orchestration, sedangkan NumPy, pandas, SciPy, dan scikit-learn dibatasi pada feature/research adapters. Requirement sekarang memakai lower bounds (`>=`) sehingga environment dapat berubah tanpa perubahan source; ini tidak kompatibel dengan deterministic replay.

**Dampak arsitektur:** pertahankan library numerik yang ada, tetapi pisahkan schema/domain types dari DataFrame dan model objects. Tambahkan dependency lock serta model/feature artifact digest sebagai bagian Experiment ID. `[ASSUMPTION]` Pydantic atau dataclass tervalidasi dipilih saat implementation spike berdasarkan biaya serialisasi; Architecture Spine hanya mengikat schema versioning dan canonical serialization, bukan library schema tertentu.

### Database dan Durable Storage

SQLite WAL cocok untuk satu host dan low writer concurrency: reader dan writer dapat berjalan bersamaan, tetapi hanya ada satu writer. Ini selaras dengan single-writer authority PRD, selama database berada di local filesystem, transaksi singkat, checkpoint diawasi, dan durability menggunakan `synchronous=FULL`. PostgreSQL memberi transaksi multi-session dan jalur skalabilitas lebih kuat, tetapi menambah beban operasi yang belum dibenarkan untuk single-operator VPS.

**Dampak arsitektur:** `[ASSUMPTION]` MVP memakai satu SQLite canonical store dalam WAL mode hanya setelah exact-version/source-ID gate terpenuhi, dengan writer fencing pada aplikasi, explicit transaction boundary, `busy_timeout`, one checkpoint owner, integrity checks, online backup, dan restore drill. Runtime saat ini memakai SQLite 3.45.1; dokumentasi resmi menyatakan WAL-reset corruption bug terdapat pada 3.7.0–3.51.2 dan diperbaiki pada 3.51.3+ serta backport tertentu. Karena numeric floor dapat menerima release withdrawn atau build yang tidak terbukti, initial qualified image dipin ke SQLite 3.53.4 dan memverifikasi source ID/compile options library yang benar-benar dilink. Redis tidak pernah menjadi ledger. Migrasi ke PostgreSQL dipicu oleh multi-host deployment, sustained write contention, atau kebutuhan HA—bukan sekadar pertumbuhan row count.

Sumber: [SQLite release history](https://www.sqlite.org/changes.html), [SQLite WAL dan WAL-reset bug](https://www.sqlite.org/wal.html#the_wal_reset_bug), [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [appropriate uses for SQLite](https://www.sqlite.org/whentouse.html), [PostgreSQL transaction blocks](https://www.postgresql.org/docs/current/sql-begin.html).

### Messaging dan Cache

Redis yang sudah tersedia layak untuk cache harga dan transport proyeksi/notification. Redis Streams mendukung consumer groups, acknowledgement, pending-entry recovery, dan replay terbatas. Namun persistence serta replication Redis tetap dapat kehilangan data pada konfigurasi/failover tertentu; karena itu stream tidak boleh menjadi sumber kebenaran trading.

**Dampak arsitektur:** canonical transaction menulis event dan outbox row secara atomik ke SQLite. Relay baru mengirim ke Redis Streams setelah commit. Consumer wajib idempotent, menggunakan explicit ack, bounded retry, pending recovery, dan durable dead-letter record. Redis Pub/Sub dilarang untuk event yang harus dipulihkan.

Sumber: [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/), [Redis streaming pattern](https://redis.io/docs/latest/develop/use-cases/streaming/), [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).

### Development, Testing, dan Evidence Tools

Git dan pytest tetap menjadi toolchain utama. Unit/integration tests perlu dilengkapi deterministic replay corpus, property-based invariant tests, fault injection, migration rehearsal, dan sealed evidence-report generation. Current full-suite baseline yang tidak hijau harus dipisahkan dari acceptance gate replacement agar kegagalan legacy tidak disamarkan dan fitur baru tidak mewarisi kontrak rusak.

**Dampak arsitektur:** CI mempunyai gate terpisah untuk canonical kernel, adapters, deterministic replay, migration, dan full brownfield regression. Tidak ada model atau Strategy version yang dapat dipromosikan bila artifact, dataset window, seed, cost model, dan source commit tidak terkunci.

### Infrastructure dan Deployment

Single-host Docker Compose masih sesuai untuk MVP, tetapi image saat ini tidak reproducible karena base runtime berbeda dari development dan dependencies tidak dipin. Redis menggunakan image major tag serta kebijakan `allkeys-lru`; event stream yang berbagi instance dengan evictable cache dapat hilang karena pressure.

**Dampak arsitektur:** `[ASSUMPTION]` tetap single VPS/Compose untuk MVP, dengan immutable image digest, non-root runtime, read-only application image, persistent canonical volume, dan environment terpisah untuk replay/test serta DRY RUN. Jika Redis dipakai untuk reliable transport, cache dan transport wajib memakai instance/persistence/eviction domain berbeda; logical namespace atau Redis DB saja tidak cukup. Kubernetes, Kafka, serverless, dan multi-cloud ditunda sampai ada scaling trigger terukur.

### Adoption Assessment

Perubahan stack yang paling berdampak bukan mengganti bahasa atau menambah platform, melainkan menghilangkan environment drift, menjadikan database transaction sebagai batas kebenaran, memisahkan durable outbox dari cache, dan membuat setiap experiment reproducible. Confidence: **tinggi** untuk Python/SQLite/Redis fit pada MVP single-host; **sedang** untuk keputusan mempertahankan SQLite sampai load/failover test memberi angka migrasi.

---

## Integration Patterns Analysis

### Venue API Boundary

INDODAX kini menyediakan Trade API V2 dengan endpoint REST terpisah untuk create/cancel/get order, open orders, account, order history, dan individual trade fills. API V2 memakai millisecond timestamp atau monotonic nonce, `recvWindow`, HMAC-SHA256, IP whitelist wajib untuk trading, rate limits, serta `clientOrderId`. Dokumentasi resmi juga menyatakan endpoint legacy akan didekomisioningkan setelah masa transisi.

**Dampak arsitektur:** hanya `VenuePort` yang boleh mengenal payload INDODAX. Adapter V2 menormalisasi symbol, decimal, status, timestamp, fee/tax, maker/taker, dan error taxonomy ke schema canonical. Legacy V1 tidak boleh bocor ke domain kernel. `[ASSUMPTION]` MVP DRY RUN mengimplementasikan read/reconciliation adapter V2 lebih dahulu; executable submit tetap feature-disabled sampai live-readiness PRD.

Sumber: [INDODAX Trade API 2.0](https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md), [panduan integrasi resmi](https://help.indodax.com/hc/id/articles/5315217255833-Bagaimana-Cara-Mengintegrasikan-API-INDODAX).

### Order Identity dan Ambiguous Outcome Recovery

API V2 mengembalikan `orderId`, `fullOrderId`, dan caller-defined `clientOrderId`; lookup order dan trade history dapat difilter dengan client/order ID. Error jaringan setelah submission tidak membuktikan order gagal—retry buta dapat menggandakan intent atau order.

**Dampak arsitektur:** canonical Intent ID menghasilkan deterministic `clientOrderId` yang sama pada retry. Timeout menghasilkan status `UNKNOWN`, bukan `REJECTED`. Recovery melakukan bounded lookup melalui order/open-order/history/trade endpoints sebelum resubmit. Venue fill/trade ID menjadi deduplication key; cumulative quantity tidak boleh diperlakukan sebagai fill baru. Submission response hanya observation, bukan bukti settlement.

Sumber: [INDODAX order and trade-history contracts](https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md).

### Streaming dan Reconciliation

Private WebSocket menyediakan order update, individual fill quantity, cumulative filled quantity, fee/tax/clearing, maker/taker role, dan token expiry. Stream dapat terputus atau melewatkan window; REST history membatasi default/range query sehingga cursor harus dipersist dan window harus dioverlap untuk deduplication.

**Dampak arsitektur:** WebSocket adalah low-latency observation, bukan source of truth tunggal. REST reconciliation berjalan saat startup, reconnect, unknown outcome, periodic cadence, dan sebelum evidence sealing. Persisted high-water marks memakai overlap window dan venue IDs. Kesenjangan yang tidak dapat dipulihkan membuat state `UNRECONCILED`, menutup entry tetapi tidak memblokir cancel/exit/recovery.

Sumber: [INDODAX Private WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-websocket.md), [INDODAX Trade API 2.0](https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md).

### Transactional Outbox dan Event Delivery

Menulis state database lalu mengirim message merupakan dual-write hazard. Transactional outbox mengikat domain mutation dan outbox insert dalam transaksi yang sama; delivery tetap at-least-once sehingga consumer harus idempotent dan ordering harus eksplisit.

**Dampak arsitektur:** setiap canonical mutation menghasilkan event envelope dan outbox record secara atomik. Relay hanya membaca committed rows dan mengirim berdasarkan aggregate sequence. Consumer menyimpan processed-message key atau menerapkan idempotent upsert sebelum ack. Retry dibatasi; poison message masuk durable dead-letter store dan memicu degradation alert. Redis Streams boleh menjadi transport, tetapi replay authoritative membaca canonical event journal.

Sumber: [AWS Transactional Outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html), [AWS asynchronous communication](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-integrating-microservices/asynchronous.html).

### Canonical Data Envelope

JSON biasa tidak menjamin byte-identical serialization. RFC 8785 menetapkan canonical property sorting dan primitive serialization untuk hashing/repeatability, tetapi decimal keuangan tidak boleh bergantung pada binary floating point.

**Dampak arsitektur:** event envelope memiliki `event_id`, `event_type`, `schema_version`, `aggregate_id`, `aggregate_seq`, `occurred_at`, `recorded_at`, `correlation_id`, `causation_id`, `producer_version`, dan payload. Harga, quantity, fee, tax, serta currency amount dikirim sebagai decimal string dengan instrument scale; timestamps UTC integer microseconds atau RFC 3339 yang ditentukan tunggal. Artifact hash memakai canonical JSON profile yang diuji lintas runtime.

Sumber: [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html).

### Risk Control Integration

INDODAX menyediakan dead-man switch untuk membatalkan open orders setelah countdown dan Self-Trade Prevention (STP) yang berlaku sejak Juli 2026. STP cancellation dapat terlihat lewat WebSocket dan `cancelReason` pada order history.

**Dampak arsitektur:** dead-man switch menjadi defense-in-depth saat live-readiness, bukan pengganti internal kill/reconciliation. Strategy tidak menentukan STP; execution policy memakai safe default dan mencatat venue cancellation reason. Opposing orders dari strategy berbeda tetap dicegah oleh portfolio-level Order Coordinator sebelum mencapai venue.

Sumber: [INDODAX Deadman Switch](https://github.com/btcid/indodax-official-api-docs/blob/master/Deadman-switch.md), [INDODAX Self-Trade Prevention](https://github.com/btcid/indodax-official-api-docs/blob/master/Self-Trade%20Prevention-TradeAPI.md).

### Notification dan Operator Interfaces

Telegram Bot API adalah external HTTP interface yang berubah independen dari trading runtime. Formatting, throttling, dan delivery failure tidak boleh mengubah Decision atau settlement.

**Dampak arsitektur:** Telegram hanya consumer projection dari outbox dengan sanitized structured templates, rate limiting, deduplication, retry, dan DLQ. Operator command masuk sebagai authenticated Command dan menghasilkan canonical audit event; callback handler tidak boleh menulis Position atau Order secara langsung.

Sumber: [Telegram Bot API](https://core.telegram.org/bots/api).

### Interoperability Assessment

REST/JSON, WebSocket, SQLite transaction, dan Redis Stream cukup untuk MVP; GraphQL, gRPC, service mesh, ESB, Saga, dan API gateway tidak menyelesaikan risiko utama single-host bot. Perubahan berdampak besar adalah adapter V2 yang contract-tested, deterministic order identity, WebSocket-plus-REST recovery, transactional outbox, dan isolasi Telegram. Confidence: **tinggi**, berdasarkan kontrak resmi venue dan failure semantics yang terdokumentasi.

---

## Architectural Patterns and Design

### System Architecture Pattern

Paradigma yang paling sesuai adalah **modular monolith dengan Hexagonal Architecture**, augmented oleh append-only domain facts dan CQRS ringan. Brownfield saat ini memiliki banyak module yang langsung menulis tabel yang sama; memecahnya menjadi microservices akan mendistribusikan konflik ownership tanpa memperbaikinya. Domain kernel harus terisolasi dari INDODAX, SQLite, Redis, Telegram, DataFrame, dan model artifact melalui ports.

Sumber: [AWS Hexagonal Architecture best practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/hexagonal-architectures/best-practices.html).

### Domain Boundaries dan Dependency Direction

Bounded contexts yang dibutuhkan adalah Market Data, Decision, Portfolio & Risk, Execution, Accounting & Reconciliation, Experiment & Evidence, dan Operations. Dependency selalu mengarah dari adapters menuju application ports lalu domain; domain tidak mengimpor adapters. Cross-context mutation hanya melalui command/event contracts, tidak melalui shared mutable objects atau direct SQL.

**Dampak:** Strategy menghasilkan Candidate, Decision mengeluarkan satu action, Risk Governor menyetujui/mengecilkan/menolak, Order Coordinator membentuk Intent, Execution mengobservasi lifecycle, lalu Accounting/Reconciliation membentuk Position/equity dari Fill. Tidak ada komponen lain yang boleh melewati urutan ownership ini.

### State Mutation dan CQRS

CQRS dipakai untuk memisahkan satu canonical write path dari read-only projections tanpa memaksakan dua authoritative database. Command diproses pada aggregate/policy boundary dan menghasilkan canonical event; dashboard, notification, dan analytics membaca projections yang boleh dibangun ulang. Event sourcing penuh hanya dipakai pada lifecycle/risk/accounting facts yang memerlukan replay, bukan seluruh tick market data.

Sumber: [Microsoft CQRS](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs), [Microsoft Event Sourcing](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing).

### Scalability dan Performance

Vertical scaling dan process-role isolation cukup untuk MVP. Trading writer diprioritaskan dan tidak menjalankan training/backtest/Telegram delivery inline. Market snapshots dibatch secara bounded; projections dan evidence jobs boleh tertinggal tanpa mengubah trading truth. Migrasi menuju services hanya dipicu oleh measured contention, independent scaling need, atau fault-containment need.

**Dampak:** backpressure harus menghasilkan explicit degradation state. Queue growth, snapshot staleness, DB busy duration, reconciliation lag, dan decision latency diukur. Dropping canonical events untuk menjaga throughput dilarang.

### Integration dan Communication

Synchronous call dibatasi untuk domain command di dalam process dan bounded venue requests. Semua side effect non-critical memakai committed outbox. Simulator dan Venue adapter menerapkan port lifecycle yang sama, sehingga DRY RUN tidak memiliki decision path kedua. API adapters menerjemahkan error eksternal ke small canonical taxonomy dan menyimpan raw observation hash untuk audit.

### Security Architecture

Least privilege berlaku per process dan credential. DRY RUN memakai key read-only; permission withdrawal dilarang. Secret tidak masuk event, log, snapshot, artifact, atau exception. Operator commands diautentikasi dan diaudit; network locality tidak memberikan implicit trust.

Sumber: [NIST Zero Trust Architecture](https://www.nist.gov/publications/zero-trust-architecture), [INDODAX API permission controls](https://help.indodax.com/hc/id/articles/5315217255833-Bagaimana-Cara-Mengintegrasikan-API-INDODAX).

### Data Architecture

Canonical store memegang event journal, aggregate state, Fill facts, risk-policy state, outbox, experiment metadata, and evidence seals. Market data store memegang immutable point-in-time observations dengan lineage, tetapi tidak ikut mengotorisasi Position. Projection tables selalu disposable/rebuildable; corrective facts ditambahkan sebagai compensating events dan sejarah tidak ditulis ulang.

### Deployment dan Operations

`[ASSUMPTION]` MVP memakai satu immutable deployment artifact pada satu host dengan process roles terpisah: trading writer, ingestion/reconciliation, projection/notification, dan research/evidence. Hanya trading writer memperoleh mutation lease. Structured logs, metrics, dan traces memakai correlation/causation identifiers yang kompatibel dengan OpenTelemetry; backend telemetry tertentu ditunda.

Sumber: [OpenTelemetry logs correlation](https://opentelemetry.io/docs/specs/otel/logs/), [OpenTelemetry metrics](https://opentelemetry.io/docs/specs/otel/metrics/).

### Pattern Assessment

Arsitektur ini sengaja menolak microservices, service mesh, full distributed event sourcing, dan polyglot persistence pada MVP. Keempatnya menambah failure modes sebelum source-of-truth dan evidence discipline selesai. Confidence: **tinggi** untuk Hexagonal modular monolith dan ownership flow; **sedang** untuk batas granular event journal yang perlu divalidasi melalui replay prototype.

---

## Implementation Approaches and Technology Adoption

### Technology Adoption Strategy

Replacement dilakukan secara incremental dengan compatibility boundary dan shadow comparison, bukan big-bang code deployment. Namun canonical settlement tidak pernah dual-write: legacy atau replacement memegang write authority, tidak keduanya. Urutan transform–coexist–eliminate diterapkan pada input/read/projection surfaces; state mutation berpindah melalui hard cutover dengan rollback manifest.

Sumber: [AWS Strangler Fig pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-aspnet-web-services/fig-pattern.html).

### Development Workflow dan Tooling

Setiap perubahan melewati format/lint, focused module tests, canonical acceptance tests, migration/replay tests, lalu full brownfield suite. Dependency lock, source commit, schema version, model digest, and dataset manifest disimpan bersama artifact. Container dirujuk dengan immutable digest; build provenance dapat memakai artifact attestation bila repository plan mendukungnya.

Sumber: [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

### Testing dan Quality Assurance

Test pyramid ditambah domain-specific evidence layers:

1. Pure domain unit tests untuk legality, sizing, accounting, dan precedence.
2. Property/state-machine tests untuk arbitrary command/fill/restart sequences.
3. Contract tests terhadap recorded INDODAX V2 fixtures dan schema drift.
4. Deterministic replay serta restart equivalence.
5. Fault injection: duplicate/reorder/late/partial fill, timeout, reconnect, clock skew, Redis/Telegram failure, SQLite busy, disk pressure, dan process crash di setiap transaction boundary.
6. Migration rehearsal memakai ACE/BICO/HUMANITY, stale pending orders, dan snapshot produksi yang disanitasi.
7. Sealed OOS/shadow evidence untuk Strategy—not conflated with platform tests.

Gate replacement dipisahkan dari full brownfield baseline, tetapi keduanya dilaporkan. Test yang flaky atau gagal tidak boleh dikecualikan tanpa owner, reason, dan expiry.

### Deployment dan Operations

Urutan deployment: preflight → online backup → backup hash dan restore smoke test → schema migration → immutable artifact start dalam entry-disabled mode → reconciliation → invariant verification → writer lease handoff → shadow/DRY RUN enable. Rollback memindahkan authority dan mempertahankan append-only history.

SQLite backup menggunakan Online Backup API, bukan menyalin file aktif secara buta. `quick_check` berjalan sering; `integrity_check` dan `foreign_key_check` berjalan pada gate terjadwal serta sebelum evidence sealing. Restore drill menjadi bukti operasional, bukan sekadar keberadaan file backup.

Sumber: [SQLite Online Backup API](https://www.sqlite.org/backup.html), [SQLite PRAGMA integrity checks](https://www.sqlite.org/pragma.html).

### Team Organization dan Skills

Walau operator tunggal, ownership ditetapkan per module: Truth/Accounting, Decision/Strategy, Execution/Venue, Evidence/Research, dan Operations/Surfaces. Pull request yang mengubah lebih dari satu ownership boundary wajib menyertakan contract change dan cross-boundary tests. Kemampuan minimum: Python async, SQLite transactions, exchange lifecycle, numerical precision, time-series validation, observability, dan incident recovery.

### Cost dan Resource Management

Single VPS 4 GB tetap menjadi constraint MVP. Trading writer memiliki reserved CPU/memory dan tidak berbagi event-loop dengan training/backtest. Market-data retention bertingkat; raw high-frequency data dikompresi/diarsipkan berdasarkan reproducibility need. Redis, Kafka, Kubernetes, PostgreSQL, dan telemetry backend baru hanya ditambahkan bila metric menunjukkan kebutuhan.

### Risk Assessment dan Mitigation

| Risiko | Mitigasi implementasi |
|---|---|
| Legacy write tetap aktif | DB/boundary-level writer fencing dan negative authorization tests |
| Unknown venue outcome | Deterministic client ID, bounded lookup, entry freeze |
| Replay berbeda antar-environment | Runtime/dependency/artifact pinning dan canonical serialization |
| Migration merusak truth | Backup hash, dry rehearsal, reconciliation, invariant gate, rollback manifest |
| Queue/notification menghambat writer | Transactional outbox dan isolated consumers |
| Evidence terlihat bagus karena leakage | Locked split/embargo/cost model/trial ledger dan sealed report |
| VPS resource exhaustion | Hard quotas, queue-age/disk alerts, entry degradation, offline research process |

Google SRE merekomendasikan SLO yang memetakan dampak pengguna, actionable alerts, kesiapan insiden, dan postmortem. Untuk bot ini, “pengguna” adalah integrity contract: decision freshness, unknown-order age, reconciliation lag, outbox age, and invariant health.

Sumber: [Google SRE Incident Management Guide](https://sre.google/resources/practices-and-processes/incident-management-guide/), [Google SRE SLO adoption](https://sre.google/resources/practices-and-processes/slo-adoption-and-usage/).

## Technical Research Recommendations

### Implementation Roadmap

1. Freeze source/schema/environment/model/data baseline dan failure corpus.
2. Bangun typed canonical kernel, event journal, Policy State, dan invariant checker.
3. Bangun persistence, transactional outbox, projections, replay, backup/restore.
4. Bangun Indodax V2 read/reconciliation dan simulator adapters.
5. Bungkus legacy strategy dan satu Challenger sebagai side-effect-free Candidate providers.
6. Jalankan shadow comparison tanpa dual settlement.
7. Rehearse migration, lalu hard cutover satu writer dalam DRY RUN.
8. Kumpulkan platform evidence, kemudian Strategy evidence.

### Technology Stack Recommendation

CPython 3.12.14, exact-qualified SQLite 3.53.4 WAL canonical store, Redis cache/transport non-authoritative, pytest plus property/state-machine testing, Docker Compose single-host, dan structured OpenTelemetry-compatible telemetry. `[ASSUMPTION]` Python 3.12 line tetap dipertahankan; dependency library pins ditetapkan dalam committed lock. SQLite version, source ID, compile options, dan effective PRAGMA harus diperiksa dari runtime library yang benar-benar tertanam dalam image.

### Skill Development Requirements

Prioritas kemampuan: exchange order/fill semantics, transactional state machines, time-series experimental design, numerical/decimal correctness, async failure handling, and recovery operations. Deep learning infrastructure bukan prioritas sebelum evidence pipeline dan baseline sederhana terbukti.

### Success Metrics dan KPIs

- 100% replay/restart equivalence pada acceptance corpus.
- Nol duplicate economic effect dari duplicate delivery.
- Nol unauthorized legacy write setelah cutover.
- Semua unknown orders resolved atau entry-frozen dalam bounded SLO.
- Backup restore serta migration rehearsal lulus.
- Strategy promotion hanya dari sealed net-of-cost evidence.
- Brownfield failures tetap visible sampai diperbaiki atau retired secara eksplisit.

---

## Research Synthesis

### Impact Thesis

Tidak ada metode yang dapat menjamin profit. Temuan yang “berdampak” dalam riset ini berarti mempunyai bukti ekonomi setelah biaya atau secara material menurunkan risiko keputusan palsu. Dampak terbesar bukan predictive accuracy mentah, melainkan mengurangi low-edge turnover, mencegah accounting/state divergence, menyesuaikan exposure saat uncertainty naik, dan menolak promosi hasil backtest yang overfit.

### Method Impact Matrix

| Metode / capability | Klasifikasi | Evidence signal | Keputusan untuk AutoTrade Replacement |
|---|---|---|---|
| Cost-aware abstention | Architecture mandatory | Naive sign trading dapat runtuh sesudah biaya; threshold edge menurunkan turnover secara tajam | `ABSTAIN` sebagai canonical action; gunakan lower-bound net edge |
| Point-in-time universe + liquidity/capacity | Architecture mandatory | Alpha crypto sering terkonsentrasi pada small/illiquid assets | Dynamic eligibility disimpan bersama setiap Candidate Snapshot |
| Calibrated/selective uncertainty | Architecture mandatory; conformal sebagai Challenger | Risk–coverage formal dan adaptive interval di bawah shift | Simpan Calibration Artifact; stale/drifted calibration menutup entry |
| Execution/TCA model | Architecture mandatory | Fee, spread, impact, fill risk, dan depth dapat menghapus apparent edge | Simulator dan venue berbagi lifecycle; cost berupa distribusi, bukan konstanta |
| Leakage-safe evaluation + DSR/PBO | Architecture mandatory | Ordinary holdout tidak cukup setelah banyak trial | Frozen evidence spec, trial ledger, purge/embargo, DSR/PBO, forward shadow |
| Volatility/correlation/downside sizing | Architecture mandatory separation; allocator methods sebagai Challenger | Risk scaling dapat memperbaiki risk-adjusted outcome tetapi estimator rapuh | Hard PRD envelope tetap superior; compare simple vs regularized allocator |
| Change/regime detection | Mandatory untuk risk; Challenger untuk alpha | Berguna mendeteksi shift, tetapi regime-RL belum menunjukkan OOS gain konsisten | Alarm boleh de-risk/freeze/recalibrate, tidak boleh membuka trade |
| Simple momentum/trend long–cash | Baseline Challenger, eligible for Champion | Crypto momentum terdokumentasi, tetapi horizon/state/cost sensitive | Uji rule transparan sesuai intraday–multi-day; jangan transfer parameter paper |
| Signed order flow nonlinear model | Higher-complexity Challenger | Peer-reviewed 2026 menunjukkan OOS value pada world flow daily/weekly | Bangun provenance-aware flow features; buktikan local intraday IDR transferability |
| Legacy Strategy | Candidate, bukan privileged default | Existing reality, belum evidence-equivalent | Bungkus pure adapter dan uji dengan gate identik |
| 15-minute mean reversion | Reject as default | Gross edge sekitar 1.3 bp vs sekitar 5 bp round-trip benchmark | Research registry only sampai venue evidence melewati cost band + margin |
| Triangular arbitrage | Reject as default | Observed opportunities hilang setelah fee/slippage/depth | Tidak masuk MVP |
| Deep learning / RL first | Reject as default | Complexity belum menunjukkan robust incremental OOS value | Hanya Challenger setelah simple baseline dan ablation |
| Unrestricted Kelly | Reject as default | Sensitif terhadap estimation error dan tail misspecification | Research benchmark only di bawah hard risk envelope |

### Evidence Behind the Trading Recommendations

**Cost-aware abstention.** Walk-forward BTC study 2018–2026 menemukan sign-based strategies gagal setelah biaya 10 bp, sementara cost threshold memotong turnover dan memulihkan hasil pada konfigurasi tertentu; hasil terbaik tetap tidak terbukti unggul signifikan terhadap buy-and-hold setelah koreksi. Ini mendukung decision contract, bukan parameter universal. Sumber: [Machine Learning-Based Bitcoin Trading Under Transaction Costs](https://arxiv.org/abs/2606.00060).

**Momentum sebagai baseline, bukan kepastian.** Peer-reviewed research menemukan crypto-specific momentum dan studi lain menunjukkan cross-sectional momentum sekitar 2–4 minggu lalu reversal; penelitian lebih baru juga menunjukkan state dependence dan economic constraints. Karena primary horizon produk intraday–multi-day, formation/holding period harus diuji ulang dan parameter multi-week tidak langsung diadopsi. Sumber: [Risks and Returns of Cryptocurrency](https://doi.org/10.1093/rfs/hhaa113), [Cryptocurrency Momentum and Reversal](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3913263), [State transitions and momentum](https://doi.org/10.1016/j.frl.2025.108356).

**Signed order flow.** Journal of Financial Markets 2026 melaporkan world order flow daily/weekly mempunyai predictive power OOS dan nonlinear portfolio memberi economic value. Transfer ke INDODAX intraday masih unproven karena paper memakai international flow dalam banyak currency dan sample lama; local-flow model harus menjadi Challenger dengan ablation. Sumber: [Order flow and cryptocurrency returns](https://doi.org/10.1016/j.finmar.2026.101047).

**Mean reversion tidak otomatis tradable.** Preprint non-peer-reviewed 22 Agustus 2026 dengan frozen holdout pada Binance menemukan widespread 15-minute reversal, tetapi maximum gross edge sekitar 1.3 bp tidak melewati sekitar 5 bp benchmark round-trip cost. Sumber: [Short-horizon mean reversion in cryptocurrency markets](https://arxiv.org/abs/2608.21888).

**Uncertainty dan shift.** Selective prediction memberi risk–coverage contract; adaptive conformal methods dapat beradaptasi terhadap distribution shift, tetapi coverage bukan probabilitas profit dan tidak menciptakan alpha. Sumber: [Reject-option classifiers](https://www.jmlr.org/papers/v24/21-0048.html), [Conformal inference under arbitrary distribution shifts](https://www.jmlr.org/beta/papers/v25/22-1218.html).

**Regime sebagai safety signal.** Crypto regime-switching RL menunjukkan promising training results tetapi tidak mendeteksi improvement OOS. Oleh karena itu regime observation tidak diberi authority untuk memilih trade. Sumber: [Regime switching forecasting for cryptocurrencies](https://doi.org/10.1007/s42521-024-00123-2).

**Execution realism.** Peer-reviewed execution research menunjukkan maker/taker schedule, fill probability, order-book level, dan market condition mengubah implementation shortfall. Triangular-arbitrage research menunjukkan jumlah opportunity bukan bukti profit karena cost/depth menghapusnya. Sumber: [Optimal trade execution in cryptocurrency markets](https://doi.org/10.1007/s42521-023-00103-y), [Exploitability of triangular arbitrage](https://doi.org/10.1016/j.frl.2024.106508).

**Backtest governance.** DSR mengoreksi selection bias dan non-normal returns; PBO menunjukkan ordinary holdout dapat tetap menyesatkan setelah strategy search. Sumber: [Deflated Sharpe Ratio](https://doi.org/10.2139/ssrn.2460551), [Probability of Backtest Overfitting](https://escholarship.org/uc/item/4w1110bb).

### Architecture Consequences

1. Forecast dan Strategy output tidak pernah langsung menjadi order.
2. Satu immutable Candidate Snapshot menghasilkan satu Canonical Decision tanpa downstream override.
3. `ABSTAIN`, `HOLD`, `ENTER`, dan quantity-targeted `EXIT` memiliki reason, expected cost distribution, uncertainty, dan provenance; risk reduction memakai `EXIT`, bukan action kelima.
4. Strategy, calibration, risk allocation, execution, dan accounting adalah ownership boundaries terpisah.
5. Promotion membandingkan incremental net expectancy terhadap simple Champion pada simulator dan evidence protocol identik.
6. Model complexity mendapat explicit penalty/gate; incremental value harus datang dari feature information, bukan hanya capacity.
7. Semua architectural safety controls berlaku pada legacy maupun Challenger secara identik.

### Critical Current-Technology Finding

SQLite WAL-reset bug adalah release blocker yang ditemukan melalui current-source verification. Deployment tidak boleh menganggap distro/Python patch membawa fix tanpa membaca `sqlite3.sqlite_version` pada artifact yang diuji. Minimum gate:

- exact SQLite version/source-ID allowlist; initial qualified image 3.53.4, dengan 3.51.3 hanya historical safe floor;
- one canonical writer dan one checkpoint owner;
- local filesystem, no inherited connection across fork;
- short write transactions, `SQLITE_BUSY` handling, and `[ASSUMPTION] synchronous=FULL`;
- concurrency/crash/disk fault tests;
- Online Backup API, hashed manifest, isolated restore drill, `integrity_check`, dan `foreign_key_check`.

Sumber: [SQLite WAL-reset bug](https://www.sqlite.org/wal.html#the_wal_reset_bug), [SQLite Online Backup](https://www.sqlite.org/backup.html).

### Recommended Build Order

1. Canonical types, decimal/time/ID contracts, event journal, and state machines.
2. SQLite safe-runtime gate, transactional store/outbox, replay, invariants, backup/restore.
3. Point-in-time market snapshots, eligibility, and INDODAX V2 reconciliation.
4. Risk Governor and portfolio allocator beneath the normative PRD envelope.
5. Shared Venue/Simulator lifecycle and TCA.
6. Pure Strategy Port with legacy and simple momentum baseline.
7. Shadow comparison, migration rehearsal, and hard single-writer cutover.
8. Order-flow, calibrated uncertainty, regime-conditioned momentum, and downside allocator Challengers.

### Future Outlook

Near-term research should optimize information and evidence quality, not infrastructure breadth. PostgreSQL becomes relevant only after multi-host/HA or measured write contention; Kafka/Kubernetes only after queue/scale evidence. Neural/RL models become relevant only when simpler models saturate and a new information source demonstrates incremental OOS value. Real trading remains a separate product decision after platform-ready and Strategy-ready gates.

## Methodology, Limitations, and Source Register

### Methodology

- Brownfield scan of 113 production Python files, database writes, process topology, tests, and deployment definitions.
- Current primary-source verification for Python, SQLite, Redis, INDODAX, Telegram, AWS/Microsoft architecture patterns, OpenTelemetry, GitHub, and Google SRE.
- Academic source review prioritizing peer-reviewed papers, with preprints clearly identified.
- Translation framework: each finding classified as architecture mandatory, Challenger only, or reject/defer.
- Transfer test: no external result is assumed valid for spot-IDR without venue-specific evidence.

### Limitations

- Public research rarely studies INDODAX spot-IDR directly.
- World order flow is not equivalent to local order flow.
- Paper cost assumptions, liquidity, and shorting capability may not match this product.
- Conformal coverage and regime classification do not guarantee economic profit.
- Latest 2026 preprints may not yet have peer review.
- Exact third-party library pins and refinement of provisional operational SLO thresholds require implementation benchmarks and versioned approval.

### Confidence

- **High:** truth ownership, fill accounting, transactional outbox, deterministic replay, cost-aware gating principle, leakage controls, execution realism, safe SQLite version gate.
- **Medium:** simple momentum transfer, local order-flow Challenger, volatility/downside allocator choice.
- **Low to medium:** conformal PnL benefit, regime-selected alpha, newest preprint effects.

## Technical Research Conclusion

Architecture must make it difficult to trade on weak evidence and impossible to hide lifecycle/accounting divergence. The recommended product does not promise a universally accurate predictor; it builds a controlled competition in which simple and complex strategies face the same point-in-time data, costs, risk limits, replay, and forward evidence. Only strategies that survive that contract may become Champion.

**Technical Research Completion Date:** 2026-08-25
**Source Verification:** Current primary/official sources with explicit limitations
**Overall Confidence:** High for architecture and governance; medium for transferable trading alpha
