---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'Patient net-profit swing autotrade untuk pasar crypto spot Indodax'
research_goals: 'Merancang Strategi 2 yang lebih sabar, hanya mengambil exit dengan expectancy positif setelah fee dan slippage, tetapi tetap memiliki invalidation risk yang terukur; membandingkannya secara walk-forward dengan strategi lama tanpa mengaktifkan live trading.'
user_name: 'Officer'
date: '2026-08-16'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-08-16
**Author:** Officer
**Research Type:** technical

---

## Research Overview

Riset ini menilai rancangan patient net-profit swing autotrade untuk pasar spot
Indodax melalui audit arsitektur, execution dan accounting, referensi resmi
exchange, pola implementasi bot trading, serta validasi time-series dan
cost-aware. Fokusnya bukan menambah frekuensi transaksi, melainkan membuktikan
expectancy bersih setelah fee, spread, slippage, dan risiko eksekusi.

Hasil utamanya adalah Strategi 2 sebagai eksperimen terisolasi: modular monolith,
state machine eksplisit, virtual ledger, hard invalidation, net-edge entry gate,
dan promotion pipeline dari replay sampai shadow dry-run. Backtest bukan bukti
tunggal dan live trading tetap membutuhkan persetujuan baru. Ringkasan keputusan,
roadmap, risiko, dan sumber terdapat pada bagian Research Synthesis.

## Technical Research Scope Confirmation

**Research Topic:** Patient net-profit swing autotrade untuk pasar crypto spot Indodax
**Research Goals:** Merancang Strategi 2 yang lebih sabar, hanya mengambil exit dengan expectancy positif setelah fee dan slippage, tetapi tetap memiliki invalidation risk yang terukur; membandingkannya secara walk-forward dengan strategi lama tanpa mengaktifkan live trading.

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

**Scope Confirmed:** 2026-08-16

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technology Stack Analysis

### Programming Languages

Python tetap menjadi pilihan utama karena bot sudah memakai Python 3.12, pandas,
NumPy, scikit-learn, asyncio, dan pytest. Mengganti bahasa tidak memperbaiki edge
trading dan justru menambah execution drift. Freqtrade juga menggunakan Python
3.11+ untuk dry-run, backtesting, optimization, dan adaptive modeling, sehingga
ekosistem pembandingnya kompatibel dengan kode saat ini.

_Popular Languages:_ Python untuk riset kuantitatif dan orchestration; SQL untuk invariant/audit.
_Emerging Languages:_ Rust relevan hanya untuk hot path simulasi skala besar, bukan runtime Strategi 2 awal.
_Language Evolution:_ Pertahankan typed Python contracts dan isolasi perhitungan numerik pure-function.
_Performance Characteristics:_ Beban satu VM dan puluhan pair belum membenarkan rewrite native.
_Confidence:_ Tinggi.
_Source:_ [Freqtrade GitHub](https://github.com/freqtrade/freqtrade), [VectorBT GitHub](https://github.com/polakowo/vectorbt)

### Development Frameworks and Libraries

Runtime production sebaiknya tetap memakai modular monolith sekarang. Untuk
research harness, VectorBT cocok untuk screening parameter secara cepat karena
berbasis pandas/NumPy dengan akselerasi Numba/Rust dan menyediakan portfolio,
drawdown, parameter sweep, serta walk-forward tooling. Namun hasil kandidat
wajib divalidasi kembali pada simulator event-driven internal yang memakai
urutan candle, spread, slippage, fee, pending fill, dan cash accounting identik
dengan runtime.

Freqtrade dipakai sebagai referensi desain, bukan dependency runtime: proyeknya
menyediakan dry-run, backtesting, Hyperopt, `lookahead-analysis`, dan
`recursive-analysis`. Dokumentasinya juga membedakan backtest, hyperopt,
forward dry-run, dan live mode—pemisahan yang harus ditiru Strategi 2.

_Major Frameworks:_ pandas/NumPy internal event engine; pytest untuk contract regression.
_Micro-frameworks:_ VectorBT opsional untuk exploration; tidak menjadi execution source of truth.
_Evolution Trends:_ Tooling anti-lookahead dan recursive-analysis lebih penting daripada optimizer agresif.
_Ecosystem Maturity:_ Freqtrade matang sebagai referensi; adopsi penuh berisiko menduplikasi bot dan ledger.
_Confidence:_ Tinggi untuk arsitektur hybrid exploration + event validation.
_Source:_ [Freqtrade repository](https://github.com/freqtrade/freqtrade), [Freqtrade strategy modes](https://github.com/freqtrade/freqtrade/blob/develop/docs/strategy-customization.md), [VectorBT documentation](https://github.com/polakowo/vectorbt/blob/master/docs/docs/index.md)

### Database and Storage Technologies

SQLite tetap ledger canonical karena transaksi order/fill/position/cash harus
atomik dan volume saat ini masih cocok untuk single-host VM. WAL memungkinkan
reader dan writer berjalan bersamaan, tetapi hanya satu writer dan wajib tetap
di host yang sama; checkpoint perlu dipantau agar read latency tidak memburuk.
Backup harus menggunakan SQLite Backup API, yang menghasilkan snapshot konsisten,
bukan menyalin file database aktif secara buta.

Redis tetap queue/inflight/decision telemetry yang ephemeral dan tidak boleh
menjadi source of truth saldo atau posisi. Dataset OHLCV riset sebaiknya disimpan
sebagai Parquet immutable per pair/timeframe dengan manifest checksum; SQLite
menyimpan metadata run, parameter, fold, dan hasil trade.

_Relational Databases:_ SQLite canonical untuk satu VM; PostgreSQL baru dipertimbangkan bila multi-writer/multi-host diperlukan.
_NoSQL Databases:_ Tidak diperlukan untuk ledger.
_In-Memory Databases:_ Redis hanya dispatch, recovery, dan telemetry bounded.
_Data Warehousing:_ Parquet lokal/versioned cukup untuk walk-forward awal.
_Confidence:_ Tinggi.
_Source:_ [SQLite WAL](https://www.sqlite.org/wal.html), [SQLite Backup API](https://www.sqlite.org/backup.html)

### Development Tools and Platforms

Git branch yang sama, pytest, deterministic fixtures, dan artifact JSON/Markdown
menjadi jalur delivery. Setiap kandidat Strategi 2 harus melewati unit test,
event-replay, fee/slippage sensitivity, lookahead test, parameter stability, dan
walk-forward out-of-sample. Hyperparameter search tidak boleh mengoptimalkan
profit mentah saja; objective harus menghukum drawdown, turnover, durasi ekstrem,
dan jumlah trade terlalu sedikit. Freqtrade memperlihatkan custom hyperopt loss
dapat menggunakan profit, trade count, duration, fee, serta drawdown-related
statistics, tetapi pemilihan bobot tetap tanggung jawab kita.

_IDE and Editors:_ Tidak menentukan performa strategi.
_Version Control:_ Git commit mengikat code hash, dataset manifest, dan experiment ID.
_Build Systems:_ Virtualenv/requirements saat ini cukup; pin versi untuk reproducibility.
_Testing Frameworks:_ pytest + replay simulator + anti-lookahead checks.
_Confidence:_ Tinggi.
_Source:_ [Freqtrade advanced Hyperopt](https://github.com/freqtrade/freqtrade/blob/develop/docs/advanced-hyperopt.md), [Freqtrade backtesting](https://github.com/gcarq/freqtrade/blob/develop/docs/backtesting.md)

### Cloud Infrastructure and Deployment

Google Compute Engine + systemd tetap memadai untuk satu instance dry-run.
Tambahkan pemisahan proses research dari service trading agar parameter sweep
tidak merebut CPU/RAM atau mengunci database runtime. Artifact research tidak
boleh ditulis langsung ke ledger produksi. Google merekomendasikan observability
VM melalui dashboard telemetry, logs, system events, dan Ops Agent; untuk bot ini
metrik tambahan yang penting adalah heartbeat, queue age, decision taxonomy,
cash/equity invariant, fill parity, dan strategy-version attribution.

_Major Cloud Providers:_ Tidak ada alasan migrasi dari GCP untuk Strategi 2.
_Container Technologies:_ Opsional; systemd sudah cukup dan lebih kecil risiko perubahan.
_Serverless Platforms:_ Tidak cocok untuk loop stateful dan SQLite local ledger.
_CDN and Edge Computing:_ Tidak relevan.
_Confidence:_ Tinggi.
_Source:_ [Google Cloud VM observability](https://docs.cloud.google.com/compute/docs/instances/observe-monitor-vms)

### Technology Adoption Trends

Arsitektur yang disarankan bukan mengganti bot dengan proyek GitHub, melainkan
mengadopsi pola yang terbukti: research cepat, validation event-driven,
forward dry-run, lalu promotion berbasis quality gate. VectorBT berguna untuk
eksplorasi ribuan konfigurasi, sedangkan diskusi maintainernya sendiri mendukung
validasi tambahan dengan backtester lain untuk meningkatkan kepercayaan.
Indodax menyediakan REST OHLC, ticker, trades, depth, serta market-data WebSocket;
data resmi ini cukup untuk membangun dataset tanpa private-order API. Public REST
dibatasi 180 request/menit, sehingga cache, batching, dan WebSocket snapshot
lebih tepat daripada polling agresif.

_Migration Patterns:_ Tambah research adapter dan strategy-version field secara additive.
_Emerging Technologies:_ Rust acceleration hanya opsional setelah profiling.
_Legacy Technology:_ Jangan menghapus SQLite/Redis sebelum ada bukti bottleneck.
_Community Trends:_ Open-source dipakai untuk benchmark desain, bukan klaim profit.
_Confidence:_ Tinggi untuk stack; rendah untuk profitabilitas sampai OOS selesai.
_Source:_ [Indodax official REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md), [Indodax official WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md), [VectorBT repository](https://github.com/polakowo/vectorbt)

## Integration Patterns Analysis

### API Design Patterns

Strategi 2 tidak membutuhkan API publik baru. Gunakan satu `MarketDataPort`
internal yang mengubah REST OHLC/ticker/depth dan WebSocket trade/orderbook
Indodax menjadi snapshot canonical. Adapter harus menyimpan `source_timestamp`,
`received_at`, pair, timeframe, sequence/offset, bid, ask, last, OHLCV, dan status
freshness. Logic strategi hanya menerima snapshot immutable dan tidak boleh
memanggil HTTP secara langsung.

_RESTful APIs:_ REST dipakai untuk bootstrap, OHLC history, pair metadata, dan gap repair.
_GraphQL APIs:_ Tidak diperlukan.
_RPC and gRPC:_ Tidak diperlukan dalam single-process modular monolith.
_Webhook Patterns:_ Telegram/control events terpisah dari market-decision events.
_Confidence:_ Tinggi.
_Source:_ [Indodax Public REST](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md), [Indodax Market Data WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md)

### Communication Protocols

HTTPS REST menjadi fallback ber-rate-limit; WebSocket menjadi sumber perubahan
market real-time. Dokumentasi resmi Indodax menyediakan heartbeat ping/pong,
subscription ID, offset, dan recovery dari offset setelah disconnect. Karena
itu consumer harus menyimpan offset terakhir per channel, mendeteksi gap, lalu
recover atau mem-bootstrap ulang snapshot sebelum mengizinkan keputusan.

Redis queue tetap at-least-once: claim, inflight, terminal decision, dan recovery.
Setiap event membawa `strategy_id`, `strategy_version`, `dataset_version`,
`correlation_id`, serta `idempotency_key`. Redis Streams menyediakan ordered IDs,
consumer-group pending list, acknowledgment, reclaim, dan bounded trimming;
migrasi dari struktur queue sekarang layak dipertimbangkan kemudian, tetapi
SQLite idempotency tetap pelindung akhir terhadap duplicate fill.

_HTTP/HTTPS Protocols:_ Bootstrap dan reconciliation; exponential backoff serta rate budget wajib.
_WebSocket Protocols:_ Streaming utama dengan offset-gap detection dan stale fail-closed.
_Message Queue Protocols:_ Redis lokal; tidak perlu Kafka/RabbitMQ.
_gRPC and Protocol Buffers:_ Overkill untuk satu VM.
_Confidence:_ Tinggi.
_Source:_ [Indodax WebSocket recovery](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md), [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)

### Data Formats and Standards

JSON versioned tetap format event/control karena mudah diaudit. Numeric market
dan accounting values harus divalidasi finite/positive dan dinormalisasi ke
precision/tick/minimum pair resmi sebelum sizing. Parquet menjadi bulk format
dataset penelitian; manifest JSON menyimpan time range, source, checksum,
timezone UTC, missing-candle policy, dan code commit.

Decision envelope minimum:
`strategy_id`, `strategy_version`, `pair`, `timeframe`, `event_time`,
`snapshot_id`, `recommendation`, `entry_reason`, `invalidation_price`,
`fee_rate`, `slippage_assumption`, `expected_net_edge`, dan feature snapshot.
Exit envelope wajib membedakan `HARD_INVALIDATION`, `PROTECTIVE_STOP`,
`BREAK_EVEN`, `TRAILING_PROFIT`, `NET_TARGET`, dan `MAX_HOLD_INVALIDATION`.

_JSON and XML:_ JSON untuk control/event; XML tidak diperlukan.
_Protobuf and MessagePack:_ Belum dibutuhkan.
_CSV and Flat Files:_ CSV hanya ekspor manusia; Parquet untuk research canonical.
_Custom Data Formats:_ Schema version wajib, bukan dict bebas tanpa kontrak.
_Confidence:_ Tinggi.
_Source:_ [Indodax pair metadata and precision](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md)

### System Interoperability Approaches

Gunakan ports-and-adapters di dalam modular monolith:

1. Indodax public adapter menghasilkan market snapshot.
2. Feature builder pure-function menghasilkan feature set tanpa future data.
3. Strategy 1 dan Strategy 2 membaca snapshot sama tetapi menghasilkan intent
   terpisah dengan version attribution.
4. Shadow evaluator merekam keputusan Strategi 2 tanpa berebut modal dengan
   Strategi 1 pada fase awal.
5. Event-driven simulator dan dry-run runtime memakai contract strategy yang sama.
6. Canonical ledger menyelesaikan cash/order/fill/position atomik per strategy.

_Point-to-Point Integration:_ Hanya melalui typed internal ports.
_API Gateway Patterns:_ Tidak diperlukan.
_Service Mesh:_ Tidak diperlukan.
_Enterprise Service Bus:_ Tidak diperlukan.
_Confidence:_ Tinggi.
_Source:_ [Freqtrade strategy anatomy](https://github.com/freqtrade/freqtrade/blob/develop/docs/strategy-customization.md)

### Microservices Integration Patterns

Jangan pecah menjadi microservices. Satu VM, satu ledger writer, dan volume
sekarang lebih aman dengan process ownership eksplisit. Research runner boleh
menjadi proses offline terpisah, tetapi tidak memiliki akses tulis ke runtime DB.
Circuit breaker diterapkan pada boundary eksternal: stale market data, REST
failure, Redis unavailable, database busy, dan incomplete snapshot semuanya
fail-closed untuk entry; monitoring posisi/exit tetap berjalan degraded.

_API Gateway Pattern:_ Ditolak untuk scope sekarang.
_Service Discovery:_ systemd unit dan localhost cukup.
_Circuit Breaker Pattern:_ Entry fail-closed; protective exit tidak boleh diveto gate profit.
_Saga Pattern:_ Ditolak; transaksi SQLite tunggal lebih kuat dan sederhana.
_Confidence:_ Tinggi.
_Source:_ [SQLite WAL concurrency](https://www.sqlite.org/wal.html)

### Event-Driven Integration

Ledger normalized adalah event journal faktual, sedangkan position/cash adalah
projection transaksional. Delivery Redis boleh berulang; handler wajib
idempotent. Ack queue hanya setelah terminal decision durable. Strategy 2 tidak
boleh mengubah intent Strategi 1 atau membaca reason cache lintas strategy.

Exit arbitration harus memiliki urutan tetap:

1. data/accounting emergency;
2. hard market-structure invalidation dan protective stop;
3. break-even protection setelah biaya tertutup;
4. trailing-profit atau net target;
5. time-based reevaluation, bukan force-sell rugi hanya karena timer habis.

Konsep “profit-only exit” tidak boleh membatalkan hard stop. Dokumentasi
Freqtrade secara eksplisit memperingatkan bahwa memblokir stoploss melalui exit
confirmation dapat menyebabkan kerugian besar; custom stoploss harus hanya
bergerak memperketat proteksi, bukan menjauhkan risiko.

_Publish-Subscribe Patterns:_ Shadow strategy boleh berlangganan snapshot yang sama.
_Event Sourcing:_ Intent/order/fill immutable; projection dapat direbuild.
_Message Broker Patterns:_ Redis dengan recovery dan retention bounded.
_CQRS Patterns:_ Read model dashboard terpisah dari atomic command transaction.
_Confidence:_ Tinggi.
_Source:_ [Freqtrade strategy callbacks](https://docs.freqtrade.io/en/latest/strategy-callbacks/), [Redis streaming patterns](https://redis.io/docs/latest/develop/use-cases/streaming/)

### Integration Security Patterns

Fase riset dan shadow dry-run hanya memakai public Indodax API. Private key tidak
boleh masuk dataset, log, event, test fixture, atau research process. Bila kelak
live dipertimbangkan, private adapter harus terpisah, least-privilege, secret dari
environment/secret store, payload signature tidak pernah dicatat, dan aktivasi
memerlukan human approval baru.

_OAuth 2.0 and JWT:_ Static token public WebSocket mengikuti dokumentasi resmi; bukan kredensial akun.
_API Key Management:_ Tidak digunakan oleh Strategi 2 dry-run.
_Mutual TLS:_ Tidak diperlukan untuk localhost modular monolith.
_Data Encryption:_ HTTPS/WSS in transit; backup dan file permission dibatasi user service.
_Observability:_ Structured events memakai nama stabil agar decision/fill dapat dikorelasikan.
_Confidence:_ Tinggi.
_Source:_ [Indodax official API repository](https://github.com/btcid/indodax-official-api-docs), [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)

## Architectural Patterns and Design

### System Architecture Patterns

Pertahankan modular monolith dengan satu SQLite writer. Strategy 2 ditambahkan
melalui anti-corruption layer agar domain baru tidak menulis langsung ke tabel
legacy. Boundary hexagonal yang diperlukan adalah `MarketDataPort`,
`StrategyPolicy`, `ExecutionSimulator`, `PositionStateMachine`, `RiskPolicy`,
`LedgerRepository`, dan `EvaluationReporter`. Research runner merupakan proses
offline terpisah tanpa write access ke runtime ledger.

Position state machine: `CANDIDATE → ARMED → PENDING → OPEN_RISK → BREAK_EVEN →
PROFIT_PROTECTED → CLOSED`, dengan terminal tambahan `INVALIDATED`, `CANCELLED`,
dan `DATA_STALE`. Setiap transisi membawa event time, trigger, price snapshot,
cost assumptions, serta strategy version.

_Trade-off:_ Monolith membatasi horizontal scale, tetapi memberi atomicity dan
operational clarity yang lebih bernilai pada satu VM.
_Source:_ [AWS hexagonal architecture practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/hexagonal-architectures/best-practices.html), [Azure anti-corruption layer](https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer)

### Design Principles and Best Practices

Business policy harus pure dan deterministic: feature snapshot yang sama,
strategy version yang sama, dan portfolio state yang sama menghasilkan decision
yang sama. I/O, clock, randomness, exchange precision, dan fee schedule diinjeksi
melalui ports. Strategy 1 dan Strategy 2 tidak boleh berbagi mutable reason cache,
cooldown, position projection, atau parameter tanpa namespace.

Protective exit merupakan invariant, bukan opsi. Profit-target policy boleh
menahan exit signal biasa sampai net break-even, tetapi tidak boleh menolak hard
invalidation, emergency exit, atau protective stop.

_Source:_ [Freqtrade strategy callbacks](https://docs.freqtrade.io/en/latest/strategy-callbacks/)

### Scalability and Performance Patterns

Scale-up single VM masih cukup. Parameter sweep dilakukan offline pada immutable
dataset dan tidak berbagi CPU budget dengan runtime service. Research vectorized
hanya menghasilkan kandidat; event replay menjadi validation authority. Cache
feature keyed oleh dataset/version/pair/timeframe/candle-close dan harus bounded.
Jangan menghitung indikator berat dalam callback exit yang berjalan setiap loop.

_Source:_ [VectorBT documentation](https://github.com/polakowo/vectorbt/blob/master/docs/docs/index.md), [Freqtrade callback performance guidance](https://docs.freqtrade.io/en/latest/strategy-callbacks/)

### Integration and Communication Patterns

Market adapter menyerap REST/WebSocket dan menerbitkan snapshot canonical.
Queue delivery at-least-once diselesaikan dengan idempotency SQLite. Ack hanya
setelah decision durable. Dashboard/read model boleh eventual-consistent tetapi
command side selalu membaca canonical ledger dalam transaksi.

_Source:_ [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/), [Azure CQRS](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)

### Security Architecture Patterns

Strategy 2 research dan shadow mode hanya menggunakan public market API. Research
process tidak mewarisi private exchange secrets. Strategy activation adalah
config allowlist, default off, dan live mode membutuhkan authority baru. Artifact
tidak boleh menyimpan credential atau raw environment.

_Source:_ [Indodax official API documentation](https://github.com/btcid/indodax-official-api-docs)

### Data Architecture Patterns

Intent/order/fill adalah journal immutable; cash/position adalah projection yang
diperbarui dalam transaksi sama dan dapat direbuild. Tambahkan attribution
`strategy_id`, `strategy_version`, `experiment_id`, serta `snapshot_id` secara
additive. Read-side metrics dibuat dari journal, bukan dari log teks.

CQRS/event sourcing dipakai ringan dalam database yang sama. Implementasi penuh
dengan store terpisah ditolak karena menambah eventual consistency dan messaging
failure tanpa kebutuhan skala saat ini.

_Source:_ [Azure CQRS and event sourcing considerations](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs), [Azure reliability patterns](https://learn.microsoft.com/en-us/azure/well-architected/reliability/design-patterns)

### Deployment and Operations Architecture

Promotion gate Strategi 2:

1. deterministic replay dan contract tests;
2. lookahead/recursive validation;
3. anchored walk-forward out-of-sample;
4. fee, spread, slippage, delay, dan missed-fill stress;
5. shadow dry-run dengan virtual portfolio terpisah;
6. limited-capital active dry-run;
7. live hanya setelah persetujuan baru.

Empat breaker dipisah: infrastructure, market-data, portfolio, dan strategy
degradation. Infrastructure/data breaker menolak entry baru tetapi tidak
mematikan monitoring protective exit posisi terbuka. Backtest tidak menjadi
promotion evidence tunggal karena asumsi fill dan intra-candle berbeda dari
runtime; dry-run wajib.

_Source:_ [Freqtrade backtesting assumptions](https://docs.freqtrade.io/en/latest/backtesting/), [Freqtrade strategy validation](https://docs.freqtrade.io/en/2026.1/strategy-101/), [Azure Circuit Breaker](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)

## Implementation Research: Strategy 2

### Adoption and Development Approach

Strategi 2 diadopsi sebagai modul eksperimen yang default-off dan tidak mengganti
Strategi 1. Implementasi memakai kontrak decision/execution/ledger yang sudah ada,
tetapi seluruh state, posisi virtual, metrik, reason, dan versi strategi diberi
namespace terpisah. Hal ini memungkinkan perbandingan counterfactual pada snapshot
pasar yang sama tanpa mencampur modal atau accounting.

Entry bukan definisi subjektif “harga murah”. Kandidat harus memenuhi tren timeframe
lebih tinggi yang sehat, pullback terukur, konfirmasi pemulihan, data segar, spread
dan likuiditas layak, serta `expected_net_edge` positif setelah fee dua sisi,
slippage, dan safety margin. Biaya menjadi gate sebelum order, bukan koreksi laporan
setelah trading.

Riset walk-forward BTC terbaru menemukan bahwa prediksi lemah yang diterjemahkan
menjadi terlalu banyak transaksi dapat kehilangan nilai setelah biaya, sementara
filter eksekusi berbasis ambang biaya mengurangi turnover dan memulihkan profit pada
sebagian konfigurasi. Temuan ini mendukung filter cost-aware, tetapi bukan bukti
bahwa konfigurasi tertentu akan profit di Indodax.

_Source:_ [Machine Learning-Based Bitcoin Trading Under Transaction Costs](https://arxiv.org/abs/2606.00060)

### Position Lifecycle and Exit Policy

State operasional adalah `CANDIDATE → ARMED → PENDING → OPEN_RISK → BREAK_EVEN →
PROFIT_PROTECTED → CLOSED`, dengan terminal `INVALIDATED`, `CANCELLED`, dan
`DATA_STALE`. Prioritas exit bersifat eksplisit: emergency/hard stop, invalidasi
tesis, proteksi break-even setelah seluruh biaya tertutup, trailing profit, target
net profit, lalu evaluasi opportunity cost. Time-based review tidak boleh memaksa
jual rugi, tetapi “menunggu bebas waktu” juga tidak boleh mengalahkan hard
invalidation.

Trailing hanya aktif setelah offset keuntungan bersih tercapai. Konfigurasi ROI dan
trailing perlu diuji bersama karena engine dapat mengeksekusi ROI lebih dahulu.

_Source:_ [Freqtrade stoploss documentation](https://docs.freqtrade.io/en/stable/stoploss/), [Freqtrade backtesting](https://docs.freqtrade.io/en/latest/backtesting/)

### Testing and Promotion Gates

Urutan validasi wajib adalah deterministic replay, contract/property tests,
lookahead analysis, recursive indicator analysis, anchored walk-forward
out-of-sample, stress fee/spread/slippage/delay/missed-fill, shadow dry-run, dan
limited active dry-run. Live trading tetap memerlukan persetujuan baru.

Backtest tunggal atau parameter terbaik tidak menjadi bukti promosi. Evaluasi utama
memakai net expectancy, drawdown, profit factor, turnover, adverse/favorable
excursion, exposure time, fill quality, dan distribusi reason. Sampel dibandingkan
per regime dan pair, bukan hanya agregat total.

_Source:_ [Freqtrade lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/), [Freqtrade recursive analysis](https://www.freqtrade.io/en/stable/recursive-analysis/)

### Deployment, Monitoring, and Rollback

Deployment awal hanya menambahkan schema dan policy secara backward-compatible.
Shadow worker memakai virtual cash/position sendiri, tidak memiliki private trading
authority, dan menghasilkan journal yang dapat direplay. Rollback cukup mematikan
feature flag Strategi 2; ledger eksperimen dipertahankan untuk audit.

Dashboard harus menampilkan funnel kandidat hingga close, reason rejection,
estimated versus realized cost, state age, drawdown, dan perbandingan Strategi 1
versus 2 pada periode pasar identik. Alert wajib untuk invariant ledger, stale data,
order tanpa fill/cancel terminal, dan breaker aktif terlalu lama.

### Risks, Cost, and Delivery Roadmap

Risiko utama adalah overfitting, survivorship/selection bias pair, fill simulation
optimistis, fee atau precision drift, posisi terkunci, dan kebocoran state antar
strategi. Mitigasinya adalah dataset/version provenance, causal features,
walk-forward, stress assumptions, hard invalidation, ledger terpisah, dan rollout
bertahap.

Roadmap implementasi:

1. kontrak Strategi 2, state machine, virtual ledger, reason taxonomy, dan unit test;
2. replay/event simulator serta cost and fill model;
3. anti-lookahead, recursive, walk-forward, dan stress validation;
4. shadow dry-run berdampingan dengan baseline;
5. limited active dry-run hanya setelah gate kuantitatif lulus;
6. rekomendasi live terpisah dengan bukti dan persetujuan eksplisit.

Python modular monolith dan SQLite tetap cukup untuk fase ini. Pengeluaran terbesar
adalah kualitas data, implementasi simulator, serta waktu observasi—bukan layanan
cloud baru. Rust, microservices, ML kompleks, atau optimisasi masif ditunda sampai
profiling dan baseline membuktikan kebutuhan.

### Implementation Decision

Implementasikan Strategi 2 sebagai eksperimen patient net-profit swing yang
cost-aware dan risk-bounded. Jangan menyalin strategi GitHub sebagai klaim profit,
jangan menurunkan gate hanya untuk menaikkan jumlah trade, dan jangan mengaktifkan
live sebelum hasil out-of-sample serta shadow menunjukkan expectancy bersih positif
dengan drawdown yang disetujui.

# Patient Net-Profit Swing Autotrade: Comprehensive Technical Research

## Executive Summary

Strategi 2 dirancang sebagai strategi spot swing yang sabar, sadar biaya, dan
tetap membatasi risiko. Prinsip “buy low, sell high” baru menjadi algoritma setelah
`low`, konfirmasi pemulihan, pembatalan tesis, dan keuntungan minimum setelah biaya
didefinisikan secara objektif. Strategi ini tidak mengganti Strategi 1: ia berjalan
sebagai eksperimen dengan ledger, state, parameter, reason, dan metrik tersendiri.

Keunggulan tidak dinilai dari jumlah trade atau backtest terbaik. Bukti promosi
harus berasal dari causal replay, walk-forward out-of-sample, stress biaya dan fill,
serta shadow dry-run. Hard invalidation selalu mengalahkan keinginan menunggu harga
kembali naik, sedangkan trailing profit baru aktif setelah fee, slippage, dan
safety margin tertutup.

**Key technical findings:**

- `expected_net_edge` adalah entry gate utama, bukan skor indikator semata.
- WebSocket perlu dipadukan dengan REST Trade API 2.0 untuk rekonsiliasi terminal.
- Backtest memiliki asumsi fill dan intrabar yang lebih optimistis dari runtime.
- Strategy 2 harus menggunakan virtual portfolio dan attribution terpisah.
- Strategi publik/GitHub adalah referensi implementasi, bukan bukti profit.

**Technical recommendations:** pertahankan Python/SQLite dan modular monolith;
implementasikan state machine dan journal terlebih dahulu; gunakan indikator yang
dapat dijelaskan; validasi cost-aware; aktifkan shadow saja sampai promotion gate
lulus dan otorisasi live diberikan secara terpisah.

## Table of Contents

1. Technical Research Introduction and Methodology
2. Technical Landscape and Architecture
3. Implementation and Trading Policy
4. Technology Stack and Integration
5. Performance, Validation, and Observability
6. Security and Governance
7. Strategic Recommendations
8. Roadmap and Risk Assessment
9. Future Outlook
10. Methodology, Sources, and Conclusion

## 1. Technical Research Introduction and Methodology

Bot yang aktif tetapi rugi dan bot yang tidak pernah entry merupakan dua kegagalan
berbeda. Riset ini memisahkan signal quality, portfolio risk, execution fidelity,
dan accounting integrity agar setiap kegagalan dapat diobservasi dan diuji.
Metodologi menggabungkan audit brownfield, dokumentasi primer Indodax dan library,
riset cost-aware, serta triangulasi antara backtest, replay, dan forward testing.

Tujuan tercapai dengan menghasilkan rancangan Strategi 2 yang sabar tetapi tidak
menahan risiko tanpa batas, menghitung hasil bersih, serta dapat dibandingkan dengan
baseline pada snapshot pasar yang sama tanpa mengaktifkan live trading.

_Source:_ [Freqtrade strategy validation](https://www.freqtrade.io/en/stable/strategy-101/), [Indodax official API documentation](https://github.com/btcid/indodax-official-api-docs)

## 2. Technical Landscape and Architecture

Arsitektur yang direkomendasikan adalah modular monolith dengan hexagonal ports.
Market data, decision policy, risk, execution, dan persistence dipisahkan melalui
kontrak tetapi tetap satu deployment dan satu transaksi database. Journal
intent/order/fill menjadi canonical truth; cash dan position adalah projection yang
dapat dibangun ulang.

Lifecycle posisi adalah `CANDIDATE → ARMED → PENDING → OPEN_RISK → BREAK_EVEN →
PROFIT_PROTECTED → CLOSED`, dengan terminal `INVALIDATED`, `CANCELLED`, dan
`DATA_STALE`. Infrastructure, market-data, portfolio, dan strategy breaker dipisah
agar gangguan entry tidak menghentikan protective exit.

_Source:_ [AWS hexagonal architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/hexagonal-architectures/best-practices.html), [Azure CQRS](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)

## 3. Implementation and Trading Policy

Entry memerlukan data segar, likuiditas dan spread layak, higher-timeframe trend
sehat, pullback terukur, recovery confirmation, risk budget tersedia, dan estimasi
net edge melebihi minimum. Estimasi mengurangi fee beli, fee jual, slippage, serta
uncertainty buffer dari expected exit value.

Prioritas exit adalah emergency/hard stop, invalidasi tesis, data-safety action,
break-even protection, trailing profit, net-profit target, lalu opportunity-cost
review. Review waktu tidak memaksa penjualan rugi, tetapi tidak dapat membatalkan
hard invalidation. Trailing hanya aktif setelah offset keuntungan bersih tercapai.

_Source:_ [Freqtrade stoploss](https://docs.freqtrade.io/en/stable/stoploss/), [Cost-aware BTC walk-forward research](https://arxiv.org/abs/2606.00060)

## 4. Technology Stack and Integration

Python, pandas/NumPy, typed contracts, pytest, dan SQLite tetap sesuai skala satu
VM. Vectorized research boleh menyaring kandidat parameter, tetapi event-driven
simulator internal menjadi validation authority. Tidak ada alasan berbasis bukti
untuk rewrite Rust atau migrasi microservices sekarang.

Market WebSocket memasok order book dan trade activity. Private WebSocket memasok
status `FILLED`, `CANCELLED`, dan `REJECTED`; REST Trade API 2.0 merekonsiliasi
event yang hilang, disconnect, dan token expiry. `clientOrderId` menjadi idempotency
key. Endpoint history legacy tidak boleh menjadi dependency baru karena dokumentasi
Indodax menyatakan migrasi ke `/api/v2/myTrades` dan `/api/v2/order/histories`.

_Source:_ [Indodax market WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Marketdata-websocket.md), [Indodax private WebSocket](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-websocket.md), [Indodax Private REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-RestAPI.md)

## 5. Performance, Validation, and Observability

Promotion wajib melewati deterministic replay, contract/property tests,
lookahead/recursive checks, anchored walk-forward dengan temporal gap, stress fee,
spread, slippage, delay dan missed fill, lalu shadow dry-run dan limited active
dry-run. Backtest mengasumsikan fill yang tidak selalu tersedia di dunia nyata;
forward test adalah bukti yang lebih dekat dengan runtime.

Metrik keputusan adalah net expectancy, drawdown, profit factor, tail loss,
turnover, exposure time, adverse/favorable excursion, fill ratio, realized versus
estimated cost, dan rejection funnel per pair/regime. Win rate atau jumlah posisi
tidak cukup.

Dashboard menampilkan funnel candidate-to-close, state age, taxonomy rejection,
pending/cancellation health, breaker, ledger invariant, dan perbandingan kedua
strategi pada periode identik.

_Source:_ [Freqtrade backtesting assumptions](https://docs.freqtrade.io/en/latest/backtesting/), [Freqtrade lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/), [Freqtrade recursive analysis](https://www.freqtrade.io/en/stable/recursive-analysis/), [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)

## 6. Security and Governance

Shadow Strategy 2 memakai public market data dan tidak mewarisi private exchange
secret. Feature flag default-off, config/version dicatat, artifact tidak menyimpan
credential, dan live activation memerlukan authority baru. Decision, order, fill,
fee, cancellation, dan parameter snapshot harus audit-friendly dan immutable.

## 7. Strategic Recommendations

Implementasikan Strategy 2 sebagai patient net-profit swing yang cost-aware dan
risk-bounded. Mulai dengan indikator rule-based yang sederhana dan explainable;
jangan menambah ML sebelum baseline, dataset provenance, dan evaluation integrity
stabil. Jangan menurunkan threshold demi activity. Jika nol entry, audit reason
funnel dan counterfactual opportunities terlebih dahulu.

Keunggulan teknis proyek bukan indikator rahasia, melainkan kesetaraan replay dengan
runtime, accounting yang benar, reason yang dapat diaudit, serta disiplin promosi.

## 8. Roadmap and Risk Assessment

1. Bangun kontrak, state machine, virtual ledger, taxonomy, dan invariant tests.
2. Bangun event replay beserta cost, latency, partial/missed-fill model.
3. Jalankan causal, walk-forward, dan stress validation.
4. Jalankan shadow berdampingan dengan baseline.
5. Promosikan ke limited active dry-run hanya bila gate kuantitatif lulus.
6. Ajukan live activation secara terpisah dengan bukti dan batas modal.

Risiko utama adalah overfitting, selection/survivorship bias, fill optimistis, fee
atau precision drift, posisi terkunci, state leakage, dan sampel tidak memadai.
Mitigasi mencakup frozen parameters, dataset/version provenance, conservative stress,
hard invalidation, namespace terpisah, serta evaluasi per regime.

## 9. Future Outlook

Prioritas satu hingga dua tahun adalah kualitas data, simulator, reconciliation, dan
observability. Adaptive/ML strategy baru layak setelah tersedia baseline stabil,
label bebas leakage, sampel forward cukup, cost-aware objective, serta model rollback.
Teknologi lebih kompleks tidak menggantikan bukti expectancy bersih.

## 10. Methodology, Sources, and Conclusion

Sumber primer meliputi dokumentasi resmi Indodax, Freqtrade, scikit-learn, SQLite,
Redis, Microsoft Azure, AWS, serta repositori resmi VectorBT. Paper akademik dipakai
untuk mendukung prinsip cost-aware dan momentum/liquidity, bukan mengekstrapolasi
profit ke pair Indodax. Keterbatasan utama adalah fee aktual per akun/pair, kualitas
historical order book, dan belum adanya hasil forward Strategy 2.

Kesimpulannya, Strategy 2 layak dibangun dan diuji, tetapi belum layak live.
“Buy low, sell high” diterjemahkan menjadi pullback terkonfirmasi, positive net-edge,
profit protection, dan hard invalidation. Kebenaran strategi ditentukan oleh hasil
out-of-sample dan shadow setelah biaya, bukan narasi, backtest terbaik, atau win rate.

**Technical Research Completion Date:** 2026-08-16  
**Source Verification:** current authoritative sources with explicit limitations  
**Technical Confidence:** high untuk arsitektur dan proses validasi; belum ditentukan untuk profitability sampai forward evidence tersedia
