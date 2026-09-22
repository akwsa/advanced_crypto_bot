---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - _bmad-output/implementation-artifacts/investigations/autotrade-tidak-membuka-posisi-investigation.md
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'AutoTrade crypto Indodax: kondisi pasar, execution, signal filtering, dan risk management'
research_goals: 'Mengaudit praktik dan informasi trading terbaru, membandingkannya dengan implementasi AutoTrade, dan menentukan penyesuaian yang diperlukan tanpa mengorbankan keselamatan'
user_name: 'Officer'
date: '2026-08-12'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-08-12
**Author:** Officer
**Research Type:** technical

---

## Research Overview

Riset ini mengaudit kondisi pasar crypto, perubahan platform Indodax, dan praktik teknis terbaru yang relevan untuk AutoTrade, lalu membandingkannya dengan bukti source, konfigurasi, test, log, dan database proyek. Verifikasi memakai dokumentasi primer Indodax, Python, SQLite, Redis, Telegram, OpenTelemetry, Google SRE/ML, AWS, Microsoft, GitHub, dan OWASP.

Kesimpulan utamanya: zero-position tidak disebabkan satu threshold atau kondisi pasar sesaat. Engine/lifecycle, dispatch contract, gate architecture, dan ledger integrity sama-sama bermasalah; rekomendasi lengkap serta roadmap terdapat pada bagian **Research Synthesis**.

---

## Technical Research Scope Confirmation

**Research Topic:** AutoTrade crypto Indodax: kondisi pasar, execution, signal filtering, dan risk management
**Research Goals:** Mengaudit praktik dan informasi trading terbaru, membandingkannya dengan implementasi AutoTrade, dan menentukan penyesuaian yang diperlukan tanpa mengorbankan keselamatan

**Technical Research Scope:**

- Architecture Analysis - design patterns, frameworks, system architecture
- Implementation Approaches - development methodologies, coding patterns
- Technology Stack - languages, frameworks, tools, platforms
- Integration Patterns - APIs, protocols, interoperability
- Performance Considerations - scalability, optimization, patterns

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-08-12

## Technology Stack Analysis

### Programming Language dan Concurrency

Python tetap sesuai untuk bot ini karena ekosistem analisis data, ML, HTTP, dan testing-nya matang. Risiko utama bukan pilihan bahasa, melainkan topologi concurrency: proyek mencampur thread poller dan beberapa event loop. Dokumentasi resmi Python mensyaratkan pengiriman coroutine lintas thread melalui `asyncio.run_coroutine_threadsafe()` dan callback melalui `loop.call_soon_threadsafe()`; primitive `asyncio` tidak dirancang untuk sinkronisasi lintas thread. Temuan historis `Future attached to a different loop` dan trigger gap saat ini konsisten dengan pelanggaran boundary tersebut.

_Penilaian:_ Pertahankan Python, tetapi gunakan satu owner event loop untuk signal-to-trade atau boundary thread-safe yang eksplisit. **Confidence: High.**
_Sumber:_ [Python asyncio — scheduling from other threads](https://docs.python.org/3.12/library/asyncio-task.html#scheduling-from-other-threads)

### Exchange Market-Data dan Execution API

Dokumentasi resmi Indodax menyediakan REST serta Market Data WebSocket yang mencakup chart ticks, trade activity, market summary, dan order book. Stream order book mendefinisikan `ask` dan `bid` secara eksplisit serta menyediakan offset; ini lebih cocok untuk freshness, spread, depth, dan reconstruction dibanding mengandalkan polling ticker sebagai satu-satunya sumber. Repositori proyek justru menonaktifkan WebSocket sementara REST poller tidak men-dispatch AutoTrade, menciptakan ketidaksesuaian arsitektur dengan kemampuan platform.

_Penilaian:_ Gunakan satu market-data adapter kanonik dengan schema validation, freshness/sequence tracking, reconnect recovery, dan fallback REST. Jangan mengaktifkan WebSocket langsung tanpa soak test karena parser/orderbook historis pernah menghasilkan crossed market. **Confidence: High.**
_Sumber:_ [Dokumentasi resmi Indodax Market Data WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md), [repositori API resmi Indodax](https://github.com/btcid/indodax-official-api-docs)

### Signal Queue dan Event Transport

Redis Streams menyediakan append-only event history, consumer groups, explicit acknowledgment, pending-entry inspection, replay, dan recovery pesan worker yang crash. Kapabilitas ini langsung menjawab kegagalan saat ini: worker queue kehilangan objek sinyal dan tidak tersedia audit trail deterministik dari signal ID sampai trade/rejection.

_Penilaian:_ Queue harus membawa immutable `TradeIntent` lengkap—signal ID, pair, timestamp/freshness, recommendation, confidence, price snapshot, decision flags, dan idempotency key. Gunakan acknowledge setelah keputusan persisten, bukan sebelum proses. Migrasi penuh ke Streams bersifat opsional; contract dan idempotency wajib walaupun backend queue lama dipertahankan. **Confidence: High.**
_Sumber:_ [Redis streaming pattern](https://redis.io/docs/latest/develop/use-cases/streaming/), [Redis Streams dan consumer groups](https://redis.io/docs/latest/develop/data-types/streams/)

### Database dan Position Ledger

SQLite masih memadai untuk bot single-node dengan volume moderat. WAL memungkinkan reader dan writer berjalan bersamaan, tetapi hanya ada satu writer; checkpoint dan transaksi pendek tetap penting. Dokumentasi SQLite terbaru juga mengungkap WAL-reset race langka yang diperbaiki pada SQLite 3.51.3 dan backport tertentu. Karena proyek memakai beberapa thread/koneksi dan ledger saat ini mempunyai `amount=0`/`total=0`, versi SQLite serta atomic write path perlu diaudit sebelum mempercayai hasil dry-run.

_Penilaian:_ Pertahankan SQLite untuk sekarang, dengan satu repository/transaction boundary untuk trade + position + outcome, foreign-key/invariant checks, WAL/busy-timeout terverifikasi, dan rekonsiliasi startup. Cek versi runtime terhadap fix WAL-reset sebelum deployment. **Confidence: High untuk ledger design; Medium untuk paparan bug WAL sampai versi runtime diverifikasi.**
_Sumber:_ [SQLite Write-Ahead Logging](https://www.sqlite.org/wal.html), [SQLite PRAGMA reference](https://www.sqlite.org/pragma.html)

### Telegram Control Plane

Telegram menyatakan long polling (`getUpdates`) dan webhook saling eksklusif. Bukti lokal menunjukkan duplicate polling conflict kemudian shutdown. Telegram seharusnya menjadi control/notification plane, bukan dependency yang mematikan market-data dan risk loop.

_Penilaian:_ Terapkan single-instance ownership untuk polling atau pindah ke webhook; isolasikan kegagalan Telegram dari engine trading. Startup harus gagal cepat dengan diagnosis jelas bila ownership tidak diperoleh, atau menjalankan mode engine-without-control-plane sesuai kebijakan eksplisit. **Confidence: High.**
_Sumber:_ [Telegram Bot API](https://core.telegram.org/bots/api#getting-updates), [Telegram Bots FAQ](https://core.telegram.org/bots/faq#how-do-i-get-updates)

### Testing dan Replay Platform

Pytest tetap cocok, tetapi dua test rekonsiliasi gagal karena mencoba mem-patch atribut konfigurasi yang tidak ada. Dokumentasi pytest menekankan patch pada target yang benar; drift ini berarti invariant finansial tidak benar-benar diuji. Unit gate individual yang lulus tidak membuktikan konfigurasi efektif gabungan dapat meloloskan satu trade realistis.

_Penilaian:_ Tambahkan deterministic market replay dan contract test dari `TradeIntent` sampai ledger, memakai konfigurasi produksi yang disalin dan secret-free. Setiap gate harus menghasilkan structured reason; acceptance test harus mencakup satu pass, setiap reject class, idempotency, restart recovery, dan invariant `total ≈ amount × fill_price`. **Confidence: High.**
_Sumber:_ [Dokumentasi pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)

### Cloud Infrastructure dan Deployment

Artefak menyediakan systemd dan Docker Compose, tetapi pada workspace audit tidak ada service terdaftar maupun daemon workload. Dual deployment mechanism tanpa satu source of truth meningkatkan risiko duplicate bot instance—persis failure Telegram yang teramati.

_Penilaian:_ Pilih satu deployment authority per environment, gunakan singleton lock/lease, health/readiness probes, restart policy terbatas, commit SHA pada heartbeat, serta preflight yang memverifikasi DB, Redis, market-data freshness, queue consumer, dan Telegram ownership. **Confidence: High berdasarkan bukti lokal; status VM produksi masih Missing Evidence.**

### Technology Adoption dan Keputusan Arsitektur

Teknologi inti tidak perlu ditulis ulang. Penyesuaian bernilai tertinggi adalah mengurangi ambiguity: satu market-data adapter, satu event-loop owner, satu typed trade-intent contract, satu ledger transaction boundary, dan satu deployment authority. WebSocket, Redis Streams, dan WAL bukan tujuan tersendiri; masing-masing hanya layak bila menambah observability, replay, dan recovery yang saat ini hilang.

**Kesimpulan tahap stack:** zero-position lebih konsisten dengan kegagalan lifecycle/dispatch/data contract daripada keterbatasan Python atau kebutuhan mengganti database. Melonggarkan threshold sebelum fondasi tersebut diperbaiki akan meningkatkan risiko tanpa menjamin munculnya posisi.

## Integration Patterns Analysis

### Public Market-Data Integration

Integrasi market data harus memisahkan snapshot REST dari stream WebSocket. REST cocok untuk bootstrap, sanity cross-check, dan recovery; WebSocket cocok untuk price/order-book freshness. Payload resmi Indodax membawa offset pada stream dan memisahkan `ask`/`bid`, sehingga adapter harus menolak crossed book (`best_bid >= best_ask`), timestamp/offset mundur, depth kosong, dan symbol mismatch sebelum data memasuki signal engine.

**Audit terhadap sistem:** Jalur sekarang memiliki dua sumber yang tidak ekuivalen: WebSocket canonical dinonaktifkan, sedangkan REST poller hanya memanggil notifier. Ini bukan fallback; ini loss of functionality.
**Penyesuaian diperlukan:** Satu `MarketDataSnapshot` tervalidasi dengan `source`, `observed_at`, `exchange_at/offset`, `best_bid`, `best_ask`, `last`, depth, dan freshness status. **Confidence: High.**
_Sumber:_ [Indodax Market Data WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md), [Indodax Public REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md)

### Private Trading API dan Reconciliation

Dokumentasi Indodax menyatakan endpoint order/trade history lama melalui `/tapi` dijadwalkan berhenti pada **7 April 2026**; endpoint dedicated `/api/v2/order/histories` dan `/api/v2/myTrades` tersedia sejak 20 Januari 2026 untuk stabilitas dan konsistensi ID yang lebih baik. Karena tanggal audit sudah Agustus 2026, setiap reconciliation yang masih bergantung pada history lama adalah compatibility risk aktual, bukan hipotesis masa depan.

**Audit terhadap sistem:** Adapter harus diperiksa terhadap migrasi endpoint 2026 sebelum real trading dipertimbangkan.
**Penyesuaian diperlukan:** Pisahkan `submit_order` dari `reconcile_order`; perlakukan timeout/5xx sebagai status `UNKNOWN`, lalu query order/trade history baru sebelum retry. Nonce/timestamp harus monotonic dan clock drift dimonitor. **Confidence: High.**
_Sumber:_ [Indodax Trade API 2.0](https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md), [Indodax Private REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-RestAPI.md)

### TradeIntent Contract

Boundary signal-to-execution saat ini tidak aman: queue menerima sinyal actionable, tetapi consumer memanggil runtime dengan `signal=None`. Contract yang benar bukan sekadar `(pair, signal=None)`, melainkan immutable envelope ber-version:

`intent_id`, `signal_id`, `pair`, `side`, `created_at`, `expires_at`, `signal_price`, `market_snapshot_id`, recommendation/confidence, decision flags, strategy/config/model versions, dry-run/live mode, dan correlation/trace ID.

Consumer harus memvalidasi schema dan expiry, lalu menghasilkan tepat satu `ExecutionDecision` persisten: `ACCEPTED`, `REJECTED(reason_code)`, `PENDING`, atau `ERROR_RETRYABLE`. **Confidence: High.**

### Delivery, Idempotency, dan Acknowledgment

Redis Streams mendukung consumer groups, pending-entry tracking, acknowledgment, recovery, dan replay. Redis 8.6 juga menawarkan producer idempotency, tetapi proyek tidak boleh bergantung pada versi server baru untuk keselamatan finansial. Idempotency domain tetap harus ditegakkan lewat unique constraint pada `intent_id`/client order key dan transactional decision ledger.

**Penyesuaian diperlukan:** Acknowledge queue hanya setelah decision/order state tersimpan. Retry terhadap message yang sama harus mengembalikan state sebelumnya, bukan membuat posisi/order kedua. Gunakan dead-letter state untuk poison message, bukan silent drop. **Confidence: High.**
_Sumber:_ [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/), [Redis idempotent message processing](https://redis.io/docs/latest/develop/data-types/streams/idempotency/)

### Transactional Ledger dan Outbox

Trade, position, outcome, dan notification tidak boleh ditulis melalui side effect terpisah tanpa correlation ID. Transactional outbox menyimpan perubahan domain dan event yang akan diterbitkan dalam transaksi database yang sama; relay dapat retry, sedangkan consumer harus idempotent. Untuk aplikasi single-node, pola ini lebih tepat daripada distributed saga yang kompleks.

**Audit terhadap sistem:** `amount=0`, `total=0`, portfolio kosong, tetapi notes menyebut quantity nonzero menunjukkan multiple representation dan write path tidak memiliki invariant tunggal.
**Penyesuaian diperlukan:** `orders` menjadi fakta exchange/simulasi; `fills` menjadi fakta kuantitas/harga; `positions` adalah projection terrekonsiliasi; `trades` tidak boleh mengandalkan notes sebagai data. **Confidence: High.**
_Sumber:_ [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html)

### Failure Isolation dan Circuit Breaker

Market-data, Telegram, model inference, Redis, SQLite, dan exchange API memiliki failure domain berbeda. Circuit breaker trading harus bereaksi pada data/execution integrity—stale price, reconciliation unknown, loss/drawdown—bukan mematikan engine karena Telegram duplicate polling. Sebaliknya, kegagalan market-data tidak boleh fail-open menjadi order berbasis cache tua.

**Penyesuaian diperlukan:** State machine operasional eksplisit: `STARTING`, `OBSERVING`, `DRYRUN_READY`, `LIVE_READY`, `DEGRADED`, `HALTED`. Setiap transition menyimpan reason dan timestamp. Telegram boleh `DEGRADED`; market-data stale atau ledger reconciliation gagal harus `HALTED` untuk entry baru. **Confidence: High.**

### Deadman Switch dan Open-Order Safety

Indodax menyediakan `/countdownCancelAll`: heartbeat memperbarui countdown dan exchange membatalkan open order bila heartbeat berhenti. Ini relevan untuk real limit order, tetapi tidak boleh diaktifkan dalam perubahan dry-run pertama karena merupakan write eksternal.

**Penyesuaian diperlukan untuk fase live terpisah:** Gunakan deadman switch dengan interval dan countdown konservatif, hanya setelah order reconciliation dan singleton ownership terbukti. Uji pada demo environment terlebih dahulu. **Confidence: High.**
_Sumber:_ [Indodax Deadman Switch](https://github.com/btcid/indodax-official-api-docs/blob/master/Deadman-switch.md)

### Observability dan Reject Funnel

Log teks saat ini bisa menghitung sebagian rejection, tetapi silent cooldown dan signal object yang hilang membuat funnel tidak lengkap. OpenTelemetry merekomendasikan propagation context producer-to-consumer dan semantic naming bagi send/receive/process/settle operations.

**Penyesuaian diperlukan:** Propagasikan `trace_id`/`intent_id` dari signal creation sampai ledger. Rekam counters ber-cardinality rendah: `signals_total`, `intents_total`, `decisions_total{reason}`, `orders_total{state}`, `positions_total`, queue lag, market-data age, dan reconciliation age. Pair/detail tetap di structured log, bukan metric label tak terbatas. **Confidence: High.**
_Sumber:_ [OpenTelemetry messaging spans](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/), [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)

### Integration Security

Public market data tidak membutuhkan secret, sedangkan private API memakai API key dan HMAC-SHA512. Secret tidak boleh masuk TradeIntent, Redis payload, log, trace, atau test fixture. Mode dry-run harus secara struktural menggunakan exchange execution adapter yang tidak memiliki kemampuan private-order call, bukan hanya boolean branch dekat baris submit.

**Kesimpulan tahap integrasi:** Penyesuaian memang diperlukan. Prioritas bukan tuning sinyal, melainkan memperbaiki contract dan delivery: typed TradeIntent, canonical market-data adapter, idempotent decision ledger, API v2 reconciliation, failure isolation, dan end-to-end reject telemetry. Ini akan membuat penyebab zero-entry terukur dan mencegah double order ketika eksekusi kelak diaktifkan.

## Architectural Patterns and Design

### System Architecture Pattern

Arsitektur yang tepat bukan microservices penuh. Untuk skala bot personal/single-node, **modular monolith dengan event-driven core** memberi batas domain jelas tanpa operational overhead distributed system. Satu proses utama dapat memiliki modul Market Data, Signal, Decision, Risk, Execution, Ledger, dan Notification, tetapi komunikasi antar tahap memakai typed event serta state transition persisten.

Event-driven architecture memisahkan producer dan consumer, tetapi membawa tantangan guaranteed delivery dan eventual consistency. Karena itu event tidak boleh menjadi fire-and-forget; setiap `TradeIntent` harus berakhir pada keputusan persisten. **Confidence: High.**
_Sumber:_ [Azure Event-Driven Architecture](https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/event-driven)

### Target Control Flow

Arsitektur target yang direkomendasikan:

```text
Indodax WS/REST
      ↓
Validated MarketDataSnapshot
      ↓
Signal Pipeline → immutable SignalEvent
      ↓
TradeIntent Builder (eligibility + expiry)
      ↓
Decision Pipeline
  ├─ Signal policy
  ├─ Market-data integrity
  ├─ Liquidity/execution cost
  ├─ Portfolio/risk
  └─ Strategy/model validation
      ↓
ExecutionDecision Ledger
  ├─ REJECTED(reason)
  ├─ PENDING
  └─ ACCEPTED → DryRunExecutionAdapter
                    ↓
                 Fill Ledger
                    ↓
              Position Projection
```

Notification dan dashboard hanya membaca event/outbox; keduanya tidak memiliki kuasa mengubah lifecycle engine kecuali lewat command handler terautorisasi.

### Gate Architecture: Policy Pipeline, Bukan Return Maze

Lebih dari 20 early-return gate saat ini membuat observability buruk dan interaksi threshold sulit diuji. Semua gate tidak perlu dihapus, tetapi harus diklasifikasikan:

- **Integrity gates:** stale/invalid price, crossed book, schema error, duplicate intent. Selalu fail-closed.
- **Risk gates:** drawdown, exposure, daily loss, position count. Selalu fail-closed.
- **Execution gates:** spread, liquidity, fees, slippage, minimum order. Dapat berbeda untuk dry-run dan live, tetapi harus realistis.
- **Alpha gates:** SQE, S/R, V4, MTF, meta-label, calibration. Harus menghasilkan score/evidence terkalibrasi; hindari banyak veto yang mengukur fenomena sama.

Decision pipeline harus mengumpulkan seluruh hasil gate yang aman untuk dievaluasi, lalu satu policy final menentukan keputusan. Ini mempertahankan alasan primer dan sekunder serta memungkinkan counterfactual replay—misalnya berapa trade yang akan lolos jika satu alpha gate diubah—tanpa mengubah produksi.

### CQRS Secukupnya

Pisahkan command/write model (`TradeIntent`, `ExecutionDecision`, `Order`, `Fill`) dari query projection (`open_positions`, dashboard stats, trade reports). CQRS dasar dapat memakai SQLite yang sama; tidak perlu database terpisah. Dokumentasi Microsoft memperingatkan CQRS/event sourcing penuh menambah kompleksitas, sehingga gunakan hanya pemisahan interface dan projection yang diperlukan.

**Keputusan:** ledger write adalah source of truth; portfolio/dashboard adalah materialized projection yang dapat dibangun ulang. **Confidence: High.**
_Sumber:_ [CQRS Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)

### Reliability dan Failure Isolation

Gunakan bulkhead/failure isolation per dependency:

- Telegram gagal → notification degraded, decision engine tetap hidup.
- Redis gagal → fallback durable local outbox atau halt intent ingestion; jangan kehilangan signal diam-diam.
- Model gagal → policy eksplisit fallback atau reject; jangan mengubah rekomendasi tanpa provenance.
- Market data stale → halt entry, tetap monitor/rekonsiliasi posisi.
- Exchange response unknown → block retry order sampai reconciliation.
- Ledger write gagal → jangan acknowledge message dan jangan menganggap posisi terbuka.

Circuit breaker harus dimiliki tiap dependency, bukan satu global boolean yang mencampur drawdown dengan service health. State transition circuit breaker wajib menjadi telemetry event. **Confidence: High.**
_Sumber:_ [Azure Circuit Breaker Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker), [AWS Reliability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html)

### Scalability dan Performance

Throughput proyek tidak membutuhkan horizontal scaling agresif. Correctness per pair lebih penting daripada volume scan. Satu consumer decision dapat memproses intent secara serial per pair menggunakan keyed lock; pair berbeda boleh paralel dengan concurrency terbatas. Competing consumers baru layak setelah idempotency dan ordering terbukti.

Optimasi yang relevan:

- Cache snapshot immutable dengan TTL/freshness, bukan global mutable dataframe tanpa versi.
- Batch REST bootstrap, lalu incremental stream.
- Batasi concurrent exchange calls dan gunakan backoff/rate-limit budget.
- Ukur latency tiap tahap serta queue lag sebelum meningkatkan scan frequency.

_Sumber:_ [Competing Consumers Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/competing-consumers)

### ML/Strategy Architecture

Model V1–V4, SQE, S/R, meta-label, dan calibration saat ini berpotensi menjadi ensemble veto yang tidak terkalibrasi sebagai satu sistem. Model architecture perlu menyimpan `code_version`, `model_version`, `feature_version`, dan `config_version` pada setiap keputusan. Google merekomendasikan monitoring model berdasarkan versi code/model/data, live serving quality, latency, serta deployment compatibility.

**Keputusan:** Jangan retrain atau melonggarkan model berdasarkan 24 trade lama yang ledger-nya inkonsisten. Kumpulkan dry-run bersih melalui champion/challenger shadow evaluation; challenger tidak boleh mengeksekusi order. **Confidence: High.**
_Sumber:_ [Google Production ML Monitoring](https://developers.google.com/machine-learning/crash-course/production-ml-systems/monitoring), [Google ML Deployment Testing](https://developers.google.com/machine-learning/crash-course/production-ml-systems/deployment-testing)

### Security Architecture

Pisahkan capability berdasarkan adapter:

- `DryRunExecutionAdapter`: tidak menerima/menyimpan API secret dan secara tipe tidak memiliki private order client.
- `LiveExecutionAdapter`: hanya aktif lewat deployment flag + credential scope + readiness gate + explicit operator approval.
- Notification/dashboard: read-only terhadap ledger kecuali command endpoint yang terautorisasi dan diaudit.

Real trading membutuhkan least-privilege API key, secret injection saat runtime, redaction, singleton lease, deadman switch, dan reconciliation readiness. Tidak satu pun boleh diaktifkan hanya karena `AUTO_TRADING_ENABLED=true`.

### Data Architecture dan Invariants

Source of truth minimal:

- `market_snapshots` atau reference/hash snapshot terpilih.
- `signals` immutable.
- `trade_intents` unique dan immutable payload.
- `execution_decisions` append-only revisions.
- `orders` dengan state machine.
- `fills` immutable.
- `positions` projection dengan reconciliation marker.
- `outbox_events` untuk notification/telemetry.

Invariant wajib: quantity positif untuk fill; notional konsisten dengan quantity × price ± fee; satu intent tidak menghasilkan lebih dari satu logical order; posisi berasal dari agregasi fill; closed position memiliki realized P&L yang dapat direproduksi; notes bukan field finansial.

### Deployment and Operations Architecture

Satu environment hanya boleh memiliki satu deployment authority dan satu active trading-engine lease. Readiness bukan sekadar process hidup; minimal harus membuktikan market-data fresh, queue consumer aktif, DB writable/integrity pass, config/model version termuat, reconciliation selesai, dan mode dry-run/live eksplisit. Rollout dilakukan bertahap: offline replay → unit/contract → local dry-run → VM shadow → VM dry-run soak → baru evaluasi live secara terpisah.

### Architectural Verdict

Perbaikan total layak pada **decision/execution spine**, tetapi rewrite seluruh bot tidak diperlukan. Pertahankan modul analisis yang masih berguna, lalu bangun jalur kanonik yang deterministic dan observable. Sasaran pertama bukan “lebih banyak trade”; sasaran pertama adalah memastikan setiap kandidat mempunyai satu jejak lengkap dan setiap posisi dapat direkonstruksi. Setelah itu barulah gate alpha dapat dikonsolidasikan dan dituning menggunakan counterfactual evidence.

## Implementation Approaches and Technology Adoption

### Technology Adoption Strategy

Gunakan incremental replacement/strangler pattern, bukan big-bang rewrite. Jalur baru dibangun di samping modul lama, menerima mirror input dalam shadow mode, lalu menggantikan bagian lama setelah contract, replay, dan ledger invariants lulus. Pendekatan ini mengurangi blast radius dan menyediakan rollback yang jelas.

_Sumber:_ [AWS Strangler Fig Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-aspnet-web-services/fig-pattern.html)

### Development Workflow and Tooling

Setiap perubahan dibuat kecil dan terpisah berdasarkan domain: contracts, dispatch, gate policy, ledger, market-data adapter, telemetry, deployment. Branch protection/status checks sebaiknya mewajibkan unit, contract, replay, dry-run safety, migration, dan static secret scan sebelum merge. Artefak build/deploy harus mencatat commit SHA dan config schema version.

_Sumber:_ [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges/managing-protected-branches/about-protected-branches)

### Testing and Quality Assurance

Urutan test:

1. Perbaiki dua test fill-reconciliation yang drift.
2. Tambahkan pure contract/invariant tests.
3. Buat deterministic market replay dengan fixture realistis dan tanpa network.
4. Test satu BUY yang lolos, seluruh reject class, duplicate intent, stale data, crossed book, restart recovery, serta failure injection.
5. Jalankan shadow comparison antara decision lama dan baru.
6. Pastikan dry-run adapter secara struktural tidak dapat memanggil private-order client.

Acceptance wajib: 100% intent memiliki terminal/pending decision; tidak ada silent drop; satu intent tidak menghasilkan dua logical order; position dapat direkonstruksi dari fill; seluruh amount/notional/P&L invariant konsisten.

### Deployment and Operations

Rollout bertahap: offline replay → local dry-run → VM shadow → VM dry-run canary → soak observation → gate evaluation. Canary harus time-limited, memiliki control/baseline, metric acceptance, dan rollback otomatis/manual yang sederhana. Konfigurasi diperlakukan sebagai versioned release dan dapat di-rollback tanpa patch darurat.

_Sumber:_ [Google SRE Canarying Releases](https://sre.google/workbook/canarying-releases/), [Google SRE Configuration Design](https://sre.google/workbook/configuration-design/)

### Team Skills

Implementasi memerlukan kompetensi Python asyncio/thread boundaries, exchange microstructure, SQLite transactions/migrations, Redis delivery semantics, quantitative validation, dan production observability. Satu developer dapat mengerjakan modular monolith ini, tetapi review khusus diperlukan pada ledger/idempotency dan risk/strategy policy sebelum live trading.

### Cost and Resource Management

Tidak diperlukan Kafka, Kubernetes, atau database cloud baru. Manfaat terbesar datang dari reuse Python, SQLite, Redis, pytest, dan systemd yang sudah ada. Tambahan biaya operasional dibatasi pada storage telemetry/replay dan waktu engineering; WebSocket dapat mengurangi REST polling/rate-limit load setelah tervalidasi.

### Risk Assessment and Mitigation

- **Risiko double order setelah dispatch diperbaiki:** unique intent/order key dan reconciliation-before-retry.
- **Risiko entry meningkat tetapi kualitas buruk:** tidak tuning alpha sampai dry-run ledger bersih dan counterfactual tersedia.
- **Risiko migration merusak data:** additive schema, backup, read-only validation, reversible projection rebuild.
- **Risiko WebSocket parser salah:** shadow mode, REST cross-check, schema/offset/crossed-book guards.
- **Risiko secret bocor:** dry-run adapter tanpa secret capability; redaction dan secret scan.
- **Risiko duplicate instance:** singleton lease dan deployment authority tunggal.
- **Risiko Telegram outage:** control-plane isolation.

_Sumber:_ [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

## Technical Research Recommendations

### Implementation Roadmap

**Wave 0 — Evidence lock:** backup/snapshot, commit/runtime parity, test repair, replay corpus.
**Wave 1 — Contracts and telemetry:** typed events, structured gate results, correlation/idempotency.
**Wave 2 — Dispatch repair:** canonical trigger, queue payload preservation, pair eligibility, lifecycle isolation.
**Wave 3 — Ledger:** order/fill/position schema, transactional writes, reconciliation/projection.
**Wave 4 — Market data:** validated adapter, WebSocket shadow, REST recovery.
**Wave 5 — Gate consolidation:** counterfactual analysis, remove redundant alpha veto, calibrated final policy.
**Wave 6 — VM dry-run rollout:** shadow/canary/soak, documentation/runbook.
**Wave 7 — Optional live readiness:** separate approval, API v2 reconciliation, deadman switch, limited capital.

### Technology Stack Recommendation

Pertahankan Python + asyncio, SQLite, Redis, pytest, dan systemd. Tambahkan domain contracts, migration tooling sederhana, structured events/metrics, serta replay harness. Redis Streams dapat diadopsi bila versi/runtime siap, tetapi domain idempotency tidak boleh bergantung padanya.

### Success Metrics and KPIs

- Engine uptime/readiness dan singleton ownership.
- Market-data freshness serta invalid/crossed snapshot rate.
- Signal → intent conversion.
- Intent → terminal decision coverage = 100%.
- Reject distribution per gate class.
- Queue lag dan retry/dead-letter count.
- Duplicate logical order = 0.
- Ledger invariant violations = 0.
- Position reconciliation mismatch = 0.
- Dry-run fill realism: spread/slippage/fee tracked.
- Strategy metrics hanya setelah sample bersih: expectancy after fees, profit factor, max drawdown, calibration, dan regime breakdown.

## Research Synthesis

# Memulihkan AutoTrade Indodax: Riset Teknis Komprehensif atas Lifecycle, Execution, Risk, dan Ledger

## Executive Summary

AutoTrade tidak gagal karena pasar “tidak memberi peluang” semata. Bukti runtime menunjukkan engine lokal tidak aktif dan startup penuh terakhir shutdown akibat konflik Telegram; bukti source menunjukkan WebSocket nonaktif, REST poller tidak men-dispatch AutoTrade, serta queue consumer membuang objek sinyal dengan meneruskan `signal=None`. Dari 6.388 sinyal historis, 95,34% berakhir HOLD, sementara ledger 24 trade dry-run memiliki `amount` dan `total` nol serta portfolio kosong.

Riset terkini juga menemukan kewajiban adaptasi exchange: Indodax memindahkan order/trade history ke endpoint API v2 pada 2026, menyediakan WebSocket resmi dengan order-book offset, serta menetapkan pair metadata, minimum trade, price increment, dan mekanisme maker/taker yang harus diperlakukan dinamis. Perubahan tersebut memperkuat kebutuhan canonical market-data adapter, reconciliation-before-retry, cost model aktual, dan idempotency.

Rekomendasi strategis adalah memperbaiki decision/execution spine secara incremental, bukan menulis ulang seluruh bot. Real trading tetap terkunci; target pertama adalah dry-run yang hidup, deterministik, observable, memiliki ledger valid, dan mampu menjelaskan setiap zero-entry melalui rejection funnel.

### Key Findings

1. **Lifecycle failure:** tidak ada engine aktif; konflik duplicate Telegram polling pernah mematikan startup.
2. **Dispatch failure:** seluruh active trigger path tidak menjamin full signal mencapai runtime.
3. **Decision opacity:** lebih dari 20 early-return gate dan silent drop mencegah causal measurement.
4. **Signal scarcity:** 95,34% output final HOLD; S/R dan Quality Engine dominan.
5. **Ledger corruption/inconsistency:** notes dan kolom finansial tidak selaras; position projection kosong.
6. **Test debt:** 86 test lulus, dua test invariant gagal karena drift target konfigurasi.
7. **Exchange compatibility:** reconciliation harus diverifikasi terhadap Indodax Trade API v2.
8. **Cost realism:** limit order dapat menjadi taker; fee/tax, spread, slippage, minimum trade, dan tick size harus dinamis.

## Table of Contents

1. Research significance and methodology
2. Evidence-backed failure model
3. Current market and exchange implications
4. Target architecture
5. Integration and data contracts
6. Gate and strategy policy
7. Ledger and reconciliation
8. Testing, deployment, and security
9. Implementation roadmap
10. Risk assessment and success metrics
11. Source verification and limitations

## 1. Research Significance and Methodology

Audit menggabungkan inspeksi read-only source, test, git history, konfigurasi teredaksi, 14.007 baris log, SQLite read-only queries, dan dokumentasi web primer terkini. Temuan diklasifikasikan sebagai confirmed, deduced, atau pending verification. Kondisi pasar sesaat dipisahkan dari architectural decision agar volatilitas harian tidak menjadi alasan tuning permanen.

## 2. Evidence-Backed Failure Model

Zero-position memiliki causal chain majemuk:

```text
Engine tidak aktif / startup conflict
             ↓
Canonical trigger terputus
             ↓
Queued signal kehilangan payload
             ↓
Alpha + execution gates mengubah mayoritas kandidat menjadi HOLD
             ↓
Ledger/projection gagal merepresentasikan posisi secara konsisten
```

Memperbaiki threshold saja hanya menyentuh satu lapisan tengah dan berpotensi membuka order tanpa idempotency atau ledger yang dapat dipercaya.

## 3. Current Market and Exchange Implications

- Indodax menyediakan REST dan Market Data WebSocket resmi; WebSocket membawa offset dan order-book bid/ask terstruktur.
- Order/trade history lama dijadwalkan decommission pada 7 April 2026; endpoint v2 menjadi target reconciliation.
- Pair metadata menyediakan minimum trade dan price increment yang harus dibaca dinamis.
- Limit order yang menyentuh book dapat menjadi taker; cost model tidak boleh mengasumsikan seluruh limit fill mendapat maker economics.
- Fee/tax berlaku pada transaksi dan dapat berubah; effective all-in cost perlu versioned configuration.
- Status resmi exchange yang ditemukan tidak mendukung teori outage umum sebagai penyebab zero-position.

## 4. Target Architecture

Gunakan modular monolith dengan event-driven core: validated market snapshot → signal event → trade intent → policy decision → execution adapter → fill ledger → position projection. Notification dan dashboard menjadi consumer read-only. Setiap tahap membawa correlation ID, version, timestamp, serta provenance.

## 5. Integration and Data Contracts

Contract inti adalah `MarketDataSnapshot`, `SignalEvent`, `TradeIntent`, `GateResult`, `ExecutionDecision`, `Order`, `Fill`, dan `Position`. Queue acknowledgment dilakukan setelah decision persisten. Unique `intent_id` dan logical order key menjamin retry tidak menggandakan order.

## 6. Gate and Strategy Policy

Gate dibagi menjadi integrity, risk, execution, dan alpha. Integrity/risk selalu fail-closed; execution gate memakai biaya dan likuiditas realistis; alpha gate tidak lagi menjadi kumpulan veto redundan. Structured result dan counterfactual replay digunakan sebelum threshold dituning.

## 7. Ledger and Reconciliation

Order dan fill adalah fakta; position merupakan projection yang dapat dibangun ulang. Invariant finansial wajib mencakup quantity, price, notional, fee, realized P&L, dan one-intent/one-logical-order. Timeout exchange menghasilkan `UNKNOWN`, lalu reconciliation API v2 dilakukan sebelum retry.

## 8. Testing, Deployment, and Security

Testing bergerak dari unit/invariant ke deterministic replay, failure injection, restart recovery, shadow comparison, dan VM dry-run canary. Dry-run adapter tidak memiliki private-order capability. Deployment authority dan active-engine lease harus tunggal. Secret tidak boleh masuk queue, log, trace, fixture, atau dokumen.

## 9. Implementation Roadmap

- **Wave 0:** evidence lock, backup, parity, test repair, replay corpus.
- **Wave 1:** typed contracts, structured telemetry, idempotency.
- **Wave 2:** lifecycle isolation dan canonical dispatch.
- **Wave 3:** order/fill/position ledger dan reconciliation.
- **Wave 4:** validated market-data adapter dan WebSocket shadow.
- **Wave 5:** gate consolidation dan counterfactual tuning.
- **Wave 6:** VM dry-run canary/soak serta runbook.
- **Wave 7:** optional live readiness dengan persetujuan terpisah.

## 10. Risk Assessment and Success Metrics

Risiko terbesar adalah double order setelah dispatch dipulihkan, migration merusak data, WebSocket parser salah, serta entry meningkat sebelum quality tervalidasi. Mitigasinya adalah unique keys, additive schema, shadow mode, replay, dan real trading lock.

Success metrics utama: 100% intent memiliki decision, silent drop nol, duplicate logical order nol, ledger invariant violation nol, reconciliation mismatch nol, market-data freshness terukur, serta seluruh zero-entry memiliki reason distribution. Profitability metrics baru sah setelah forward-test bersih.

## 11. Source Verification and Limitations

Sumber primer utama:

- [Indodax official API documentation](https://github.com/btcid/indodax-official-api-docs)
- [Indodax Trade API 2.0](https://github.com/btcid/indodax-official-api-docs/blob/master/INDODAX-TradeAPI-2.md)
- [Indodax market-data WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md)
- [Indodax fees](https://help.indodax.com/hc/id/articles/4416646599705-Rincian-Biaya-Transaksi-di-INDODAX)
- [Python asyncio thread scheduling](https://docs.python.org/3.12/library/asyncio-task.html#scheduling-from-other-threads)
- [SQLite WAL](https://www.sqlite.org/wal.html)
- [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Telegram Bot API](https://core.telegram.org/bots/api#getting-updates)
- [OpenTelemetry messaging semantics](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)
- [Google SRE canary releases](https://sre.google/workbook/canarying-releases/)
- [Google production ML monitoring](https://developers.google.com/machine-learning/crash-course/production-ml-systems/monitoring)
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

Keterbatasan utama adalah runtime produksi/VM belum diverifikasi langsung pada sesi ini. Kondisi market snapshot bersifat sementara dan tidak digunakan sebagai bukti untuk threshold permanen.

## Technical Research Conclusion

Penyesuaian memang diperlukan dan cukup besar, tetapi terlokalisasi pada decision/execution spine. Implementasi harus dimulai dari Wave 0–3 dalam dry-run-only scope; tuning alpha dan WebSocket promotion mengikuti setelah jalur deterministic dan ledger valid. Aktivasi real trading, perubahan modal, dan external-order action tetap di luar scope tanpa persetujuan baru.

**Technical Research Completion Date:** 2026-08-12
**Source Verification:** Current authoritative sources plus local forensic evidence
**Confidence:** High untuk lifecycle/dispatch/ledger diagnosis; Medium untuk parity deployment produksi sampai VM diverifikasi

<!-- Content will be appended sequentially through research workflow steps -->
