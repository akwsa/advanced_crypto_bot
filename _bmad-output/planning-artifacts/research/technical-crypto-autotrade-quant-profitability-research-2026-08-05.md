---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - VM data/trading.db audit (26 closed dry-run trades, 2026-07-05 through 2026-08-04)
  - advanced_crypto_bot source and runtime logs
workflowType: research
lastStep: 6
research_type: technical
research_topic: crypto autotrade quant profitability and production architecture
research_goals: improve risk-adjusted expectancy after costs, prevent stale-position losses, validate models without leakage, and harden execution on Google Compute Engine
user_name: Officer
date: 2026-08-05
web_research_enabled: true
source_verification: true
---

# Laporan Riset: Teknis

**Tanggal:** 2026-08-05
**Penulis:** Officer
**Jenis Riset:** Teknis

---

## Ikhtisar Riset

Riset ini menggabungkan audit empiris dry-run pada VM, audit kode dan log, serta sumber primer terkini. Tujuannya bukan menjanjikan profit, melainkan membangun proses yang memiliki expectancy positif setelah fee dan slippage serta mampu menghentikan kerugian saat asumsi strategi tidak lagi berlaku.

---

## Konfirmasi Ruang Lingkup Riset Teknis

**Topik:** Profitabilitas quant dan arsitektur produksi bot autotrade crypto.
**Tujuan:** Memperbaiki risk-adjusted expectancy setelah biaya, mencegah stale-position loss, memvalidasi model tanpa leakage, dan mengeraskan eksekusi di Google Compute Engine.

**Ruang lingkup:**

- analisis arsitektur dan alur keputusan;
- metode implementasi quant, ML, dan risk management;
- bahasa, framework, penyimpanan, dan deployment;
- integrasi market data, order lifecycle, Telegram, dan observability;
- performa, concurrency, reliability, serta validasi statistik.

**Metodologi:** verifikasi sumber primer, triangulasi klaim penting, penandaan keterbatasan sampel, dan pemetaan rekomendasi ke bukti audit VM.

**Dikonfirmasi:** 2026-08-05

## Analisis Technology Stack

### Bahasa Pemrograman

Python tetap sesuai untuk bot ini karena workload didominasi I/O jaringan, orchestration, analisis data, dan ML. `asyncio` memang ditujukan untuk concurrent code berbasis `async/await` dan I/O-bound networking. Namun error VM tentang objek Telegram yang terikat ke event loop berbeda menunjukkan bahwa concurrency harus dibuat terstruktur: satu loop pemilik Telegram, queue untuk pekerjaan lintas thread, dan `TaskGroup`/supervision untuk background task. Mengganti bahasa tidak akan memperbaiki desain kepemilikan event loop yang salah.

_Bahasa utama:_ Python.
_Optimasi selektif:_ NumPy/Numba atau native library hanya setelah profiling.
_Confidence:_ tinggi.
_Sumber:_ https://docs.python.org/3.13/library/asyncio.html dan https://docs.python.org/3.13/library/asyncio-task.html

### Framework dan Library

Stack ML yang ada—scikit-learn/LightGBM serta feature engineering Python—cukup untuk baseline tabular. HistGradientBoosting menyediakan missing-value handling, regularisasi, validation set, dan early stopping; itu lebih relevan daripada menambah model “AI” baru sebelum data dan evaluasinya benar. Model perlu dibungkus pipeline versi-data/fit/predict yang deterministik dan diuji dengan split temporal serta probability calibration. Indikator teknis sebaiknya menjadi feature kandidat, bukan aturan yang otomatis dipercaya.

_Framework utama:_ scikit-learn-compatible pipeline; LightGBM hanya bila memberi uplift out-of-sample setelah biaya.
_Prioritas:_ calibration, feature lineage, reproducibility, dan model registry sederhana.
_Confidence:_ tinggi untuk kecocokan stack; rendah untuk kemungkinan profit sebelum sampel membesar.
_Sumber:_ https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html

### Database dan Penyimpanan

SQLite sesuai untuk konfigurasi dan prototipe single-writer, tetapi VM sudah mencatat `database is locked`. Dokumentasi SQLite menegaskan bahwa write tetap diserialisasi; WAL membantu reader berjalan bersama writer, bukan menjadikan banyak writer bebas konflik. Solusi jangka pendek adalah satu database-writer queue, transaksi singkat, `busy_timeout`, WAL, indeks yang tepat, dan backup melalui SQLite backup API. Untuk event trade produksi dan dashboard yang menulis bersamaan, PostgreSQL lebih aman sebagai target migrasi; Redis hanya untuk cache/queue/lease, bukan sumber kebenaran P&L.

_Relasional saat ini:_ SQLite dengan single-writer discipline.
_Target produksi:_ PostgreSQL untuk ledger/event state; Redis untuk data sementara.
_Confidence:_ tinggi karena error lock terobservasi langsung.
_Sumber:_ https://www.sqlite.org/isolation.html, https://www.sqlite.org/lockingv3.html, dan https://www.sqlite.org/walformat.html

### Development Tools dan Platform

Git, pytest, lint/type checks, serta BMad project-local sudah memadai. Kesenjangan utama adalah test harness market replay yang deterministik, golden dataset untuk keputusan entry/exit, property tests untuk ledger/P&L, dan integration test yang memaksa restart, stale ticker, partial fill, duplicate event, serta database contention. CI harus menggagalkan deployment bila backtest tidak mencantumkan fee, slippage, spread, dan temporal holdout.

_IDE:_ VS Code + Codex/BMad project-local.
_Testing:_ pytest ditambah replay/event fixtures dan stress test concurrency.
_Build/deploy:_ immutable artifact atau commit-pinned deployment, bukan copy file parsial.
_Confidence:_ tinggi berdasarkan struktur repository dan drift risiko WSL–VM.

### Cloud Infrastructure dan Deployment

Compute Engine cukup untuk skala bot saat ini, tetapi service perlu health check, log rotation, disk alert, database backup teruji, dan rollback berbasis release. Log `bot.log` sekitar 4,8 GB memperlihatkan observability belum dibatasi. Google menyatakan Ops Agent sebagai agen utama untuk telemetry VM; gunakan structured logging, metrik custom (expectancy, drawdown, stale-price age, decision latency, rejected-order reason), alert, dan retention policy.

_Platform:_ satu VM tetap layak selama ada isolation dan recovery discipline.
_Observability:_ Google Cloud Ops Agent + log rotation + dashboard/alert SLO.
_Confidence:_ tinggi.
_Sumber:_ https://docs.cloud.google.com/monitoring/agent/ops-agent

### Tren Adopsi yang Relevan

Nilai terbesar bukan migrasi ke teknologi baru, melainkan pemisahan research–paper trading–live execution, event-driven audit trail, validation temporal, dan risk engine yang tidak dapat dibypass oleh mode eksplorasi. Arsitektur sederhana yang dapat direplay dan diaudit lebih bernilai daripada ensemble model kompleks pada hanya 26 outcome.

_Rekomendasi adopsi:_ perkuat correctness dan data quality dahulu; model/regime ensemble setelah dataset outcome memadai.
_Teknologi yang ditunda:_ reinforcement learning, LLM signal generation, Kubernetes, dan microservices.
_Confidence:_ tinggi untuk urutan implementasi; profitabilitas tetap belum terbukti.

## Analisis Pola Integrasi

### Desain API

Bot sebaiknya memakai adapter terpisah untuk Public REST, Market Data WebSocket, Private REST/Trade API, dan Private WebSocket Indodax. Repository resmi Indodax menyatakan hanya stream, endpoint, parameter, dan payload yang didokumentasikan resmi yang didukung. Karena itu adapter perlu contract test terhadap schema resmi, normalisasi pair/price/volume di satu boundary, serta pencatatan raw response hash untuk audit tanpa menyimpan credential.

REST cocok untuk snapshot, rekonsiliasi, dan tindakan order; WebSocket cocok untuk tick real-time. Setiap mutasi order perlu `client_intent_id` internal yang unik dan state machine `INTENT_CREATED → SUBMITTED → ACKNOWLEDGED → PARTIALLY_FILLED/FILLED/CANCELLED/REJECTED`. Retry hanya boleh mengulang intent yang dapat direkonsiliasi, bukan membuat order baru secara buta.

_Sumber:_ https://github.com/btcid/indodax-official-api-docs
_Confidence:_ tinggi.

### Protokol Komunikasi

WebSocket harus memiliki heartbeat, `last_event_at`, sequence/gap detection bila feed menyediakan sequence, reconnect dengan exponential backoff+jitter, dan REST snapshot setelah reconnect. RFC 6455 mendefinisikan Ping/Pong sebagai keepalive dan pemeriksaan respons endpoint; koneksi TCP yang masih tampak terbuka bukan bukti harga masih segar. Entry wajib ditolak bila umur tick melewati batas pair/timeframe, sedangkan exit harus mencoba fallback REST agar proteksi tidak mati bersama stream.

Telegram harus diperlakukan sebagai presentation/notification channel, bukan execution ledger atau sumber kebenaran. Satu event loop harus memiliki Telegram client; worker lain mengirim notification intent melalui queue. Ini langsung menangani error VM `Event ... bound to a different event loop`.

_Sumber:_ https://datatracker.ietf.org/doc/html/rfc6455
_Confidence:_ tinggi.

### Format Data dan Kontrak

Gunakan envelope event berversi: `event_id`, `event_type`, `schema_version`, `occurred_at`, `received_at`, `pair`, `correlation_id`, `causation_id`, `source`, dan payload. Decimal/fixed-point harus digunakan pada boundary uang; float hanya boleh untuk feature/model, bukan ledger. Timestamp disimpan UTC dan hanya dikonversi ke Asia/Jakarta di UI.

Simpan tiga harga berbeda: observed market price, decision price, dan simulated/executed fill price. Tanpa pemisahan ini, slippage, stale data, dan kualitas sinyal tidak dapat diukur secara benar. Semua keputusan juga harus menyimpan snapshot feature/model version dan daftar gate yang pass/fail.

_Confidence:_ tinggi berdasarkan kebutuhan replay dan audit P&L.

### Interoperabilitas Sistem

Arsitektur yang tepat saat ini adalah modular monolith dengan port/adapters, bukan microservices. Market-data adapter, signal engine, risk engine, execution simulator/live adapter, ledger, dan notifier berjalan sebagai komponen yang batas kontraknya eksplisit. Redis Streams dapat dipakai untuk jalur event sementara karena menyediakan append-only log, consumer groups, acknowledgment, pending-entry inspection, dan replay. Namun dokumentasi Redis juga mengingatkan persistence/replication default tidak menjamin tidak ada kehilangan; ledger final tetap harus berada di database transaksional.

_Sumber:_ https://redis.io/docs/latest/develop/data-types/streams/ dan https://redis.io/docs/latest/develop/use-cases/streaming/
_Confidence:_ tinggi.

### Pola Integrasi Service dan Resilience

Tidak diperlukan API gateway, service mesh, atau distributed saga pada satu VM. Yang diperlukan adalah pola lokal berikut:

- circuit breaker per upstream serta circuit breaker risiko portfolio yang fail-closed;
- bulkhead agar kegagalan Telegram tidak menghentikan price monitor;
- timeout eksplisit dan bounded retry dengan jitter;
- idempotency key dan unique constraint untuk order intent, fill, exit, serta notification;
- reconciliation loop yang membandingkan posisi/order upstream dengan ledger;
- startup recovery yang membangun ulang seluruh posisi OPEN dari ledger, terlepas dari watchlist;
- outbox pattern: commit trade event dan notification intent dalam transaksi yang sama, kemudian kirim Telegram secara asynchronous.

Perbaikan 4 Agustus yang menyapu posisi OPEN di luar watchlist adalah langkah benar, tetapi harus ditambah startup invariant: tidak boleh membuka entry baru sebelum semua posisi lama sudah direkonsiliasi dan level exit berhasil dibangun ulang.

_Confidence:_ sangat tinggi karena tiga loss ekstrem berasal dari posisi lama yang tidak terlindungi secara kontinu.

### Integrasi Event-Driven

Urutan event yang direkomendasikan: `MarketObserved → FeaturesComputed → SignalProposed → RiskEvaluated → TradeIntentCreated → FillObserved/Simulated → PositionOpened → ExitConditionEvaluated → PositionClosed → OutcomeLabeled`. Setiap consumer harus idempotent; at-least-once delivery berarti duplikasi normal dan harus aman. Redis Streams mendukung acknowledgment dan reclaim pending messages, tetapi urutan per posisi harus dijaga dengan satu partition/key atau optimistic version pada aggregate posisi.

Pisahkan `research outcomes` dari `paper-trading ledger`: label ML dapat berubah setelah horizon selesai, sedangkan ledger tidak boleh ditulis ulang. Ini mencegah backfill label merusak histori finansial.

_Sumber:_ https://redis.io/docs/latest/develop/data-types/streams/
_Confidence:_ tinggi.

### Keamanan Integrasi

API key/secret hanya dibaca process runtime dari secret store atau file berpermission ketat; tidak boleh masuk log, event payload, database research, atau Telegram. Private API adapter harus menerapkan nonce/time rules sesuai dokumentasi resmi, redaction terpusat, allowlist endpoint, dan mode dry-run yang secara konstruksi tidak pernah menginisialisasi credential-bearing live executor.

Untuk Telegram, simpan `chat_id` dan `message_id` setiap notifikasi yang mungkin perlu dihapus. Bot API hanya dapat menghapus pesan biasa yang berumur kurang dari 48 jam dan `deleteMessages` menerima maksimal 100 ID per panggilan. Karena implementasi sekarang tidak menyimpan ID notifikasi autotrade, pesan historis lama tidak dapat dibersihkan penuh melalui Bot API; yang dapat dibersihkan dengan pasti adalah record dry-run sumber tampilan `/trades`.

_Sumber:_ https://core.telegram.org/bots/api#deletemessage dan https://core.telegram.org/bots/api#deletemessages
_Confidence:_ tinggi.

---

<!-- Bagian berikutnya ditambahkan secara berurutan oleh workflow riset. -->

## Architectural Patterns and Design

### System Architecture Patterns

Arsitektur yang paling masuk akal untuk bot ini adalah modular monolith berbasis port/adapters dan event ledger internal, bukan microservices. Bot masih berjalan di satu VM dan masalah utamanya bukan kekurangan skala horizontal, melainkan correctness: posisi lama lepas dari watchlist, lock database, event loop Telegram bercampur, serta decision/risk gate yang bisa terlalu longgar saat eksplorasi. Google Cloud Well-Architected menekankan desain yang sederhana, terdokumentasi, mudah diubah, dan decoupled; prinsip itu cocok dengan pemisahan komponen `market_data`, `signal_engine`, `risk_engine`, `execution`, `ledger`, dan `notifier` dalam satu proses atau sedikit proses terkoordinasi.

Keputusan arsitektural inti: ledger transaksi menjadi sumber kebenaran; Redis/queue hanya jalur kerja sementara; Telegram hanya presentasi; model research tidak boleh menulis ulang histori paper/live ledger. Mode dry-run dan live harus memakai pipeline yang sama sampai boundary executor, sehingga perbedaan dry-run vs live hanya pada fill adapter dan credential boundary.

_Sumber:_ https://docs.cloud.google.com/architecture/framework
_Confidence:_ tinggi.

### Design Principles and Best Practices

Desain domain harus berpusat pada aggregate `Position` dan state machine order, bukan pada callback harga yang kebetulan aktif. Invariant produksi yang perlu dipaksakan: setiap posisi `OPEN` wajib memiliki exit supervision aktif saat startup, setiap intent order memiliki idempotency key, setiap keputusan entry menyimpan feature snapshot/model version/gate result, dan setiap close mencatat observed price, decision price, serta fill/simulated fill price secara terpisah.

AWS Builders Library tentang idempotent API mendukung pola ini: retry aman hanya bila caller dapat menyatakan intent yang sama secara eksplisit, bukan sekadar mengirim request ulang. Untuk bot trading, bentuk praktisnya adalah `client_intent_id` unik per entry/exit dan unique constraint di ledger. Transactional outbox menyelesaikan dual-write antara update trade dan notifikasi/event eksternal: simpan state change dan notification/event intent dalam satu transaksi, lalu worker asynchronous mengirimnya.

_Sumber:_ https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ dan https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
_Confidence:_ tinggi.

### Scalability and Performance Patterns

Skalabilitas awal bukan menambah node, tetapi mengendalikan backpressure. Semua jalur I/O perlu timeout eksplisit, retry terbatas dengan exponential backoff dan jitter, serta circuit breaker per upstream. AWS menjelaskan bahwa retry dapat memperbesar beban sistem yang sedang sakit; backoff+jitter mengurangi sinkronisasi retry dan melindungi dependency. Untuk bot ini, aturan praktisnya: entry fail-closed saat market data stale, exit mencoba fallback REST, dan queue memiliki batas agar backlog tidak membuat keputusan trading dari data basi.

Performance bot harus diukur dari latency keputusan, umur tick, throughput writer database, dan waktu rekonsiliasi posisi, bukan hanya CPU. Bila SQLite dipertahankan sementara, gunakan single-writer queue dan transaksi pendek. Untuk horizon produksi, PostgreSQL lebih sesuai karena isolation dan concurrent write lebih eksplisit; dokumentasinya tetap mengingatkan bahwa serializable transaction dapat menghasilkan serialization failure, sehingga aplikasi harus siap retry transaksi yang aman.

_Sumber:_ https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter dan https://www.postgresql.org/docs/current/transaction-iso.html
_Confidence:_ tinggi.

### Integration and Communication Patterns

Integrasi sebaiknya event-driven secara internal: `MarketObserved -> FeaturesComputed -> SignalProposed -> RiskEvaluated -> TradeIntentCreated -> FillObserved/Simulated -> PositionOpened -> ExitConditionEvaluated -> PositionClosed -> OutcomeLabeled`. Setiap event memakai `event_id`, `correlation_id`, `causation_id`, `schema_version`, timestamp UTC, pair, source, dan payload yang tervalidasi. Consumer wajib idempotent karena delivery at-least-once akan membuat duplikasi sebagai kondisi normal.

Outbox pattern cocok untuk trade event dan Telegram notification karena mencegah kondisi trade sudah berubah tetapi notifikasi hilang, atau notifikasi terkirim tetapi ledger gagal commit. Untuk WebSocket market data, heartbeat dan freshness gate adalah boundary komunikasi paling penting: koneksi hidup tidak cukup; keputusan entry harus melihat `last_event_at` dan usia tick.

_Sumber:_ https://microservices.io/patterns/data/transactional-outbox.html dan https://datatracker.ietf.org/doc/html/rfc6455
_Confidence:_ tinggi.

### Security Architecture Patterns

Security architecture harus dibuat sebagai kontrol desain, bukan tambahan belakangan. OWASP ASVS menyediakan baseline untuk requirements teknis aplikasi dan service modern. Untuk bot ini, kontrol yang paling penting: secret tidak pernah masuk log/database/Telegram; private exchange adapter memakai redaction terpusat; dry-run executor tidak menginisialisasi credential live; semua admin command Telegram memiliki authorization check; destructive maintenance command seperti pembersihan histori memiliki audit log dan backup terlebih dahulu.

Selain itu, mode live harus memiliki kill switch yang independen dari model dan sinyal. Circuit breaker portfolio yang sudah aktif di VM jangan di-reset otomatis hanya karena histori dry-run dibersihkan. Security dan risk di sini bertemu: sistem yang aman adalah sistem yang gagal tertutup ketika credential, market data, database, atau risk state tidak sehat.

_Sumber:_ https://owasp.org/www-project-application-security-verification-standard/
_Confidence:_ tinggi.

### Data Architecture Patterns

Data architecture perlu memisahkan ledger finansial, event audit, feature store ringan, dan research label. Ledger bersifat append-only atau versioned; koreksi dilakukan dengan event koreksi, bukan update diam-diam. Feature/model snapshot disimpan agar setiap sinyal bisa direplay persis. Research label seperti `GOOD_BUY/BAD_BUY` boleh dihitung ulang untuk eksperimen, tetapi tidak boleh mengubah fakta `PositionClosed` dan P&L historis.

PostgreSQL adalah target yang sehat untuk ledger produksi karena transaksi, constraint, index, dan isolation lebih matang untuk concurrent writer. Untuk SQLite saat ini, pola yang harus dipakai adalah WAL, `busy_timeout`, writer tunggal, online backup API, dan delete maintenance dalam transaksi eksplisit. Ini langsung relevan untuk pembersihan histori dry-run Telegram: hapus record sumber tampilan `/trades` dari database setelah backup, bukan mencoba menghapus pesan historis yang Bot API tidak bisa jamin.

_Sumber:_ https://www.sqlite.org/isolation.html dan https://www.postgresql.org/docs/current/transaction-iso.html
_Confidence:_ tinggi.

### Deployment and Operations Architecture

Deployment di Compute Engine masih layak, tetapi harus diperlakukan sebagai workload produksi kecil: release berbasis commit/artifact, health check, log rotation, backup database yang diuji restore, startup reconciliation, dan rollback sederhana. Google Cloud Well-Architected Reliability pillar menekankan desain, deploy, dan operasi workload yang reliable; untuk bot ini artinya service tidak boleh menerima entry baru sebelum database, exchange adapter, market data freshness, dan rekonsiliasi posisi lama lulus.

Observability perlu pindah dari log besar tidak terstruktur menjadi telemetry yang bisa ditanya: OpenTelemetry mendefinisikan observability sebagai traces, metrics, dan logs yang dikumpulkan/diekspor vendor-neutral. Metrik minimum bot: expectancy setelah fee/slippage, win/loss by pair/regime, max drawdown, stale tick age, decision latency, reject reason, open position count, database lock count, Telegram send failure, dan restart recovery duration. Twelve-Factor juga relevan untuk process discipline: config dipisah dari code, proses disposable, dan log diperlakukan sebagai event stream.

_Sumber:_ https://docs.cloud.google.com/architecture/framework/reliability, https://opentelemetry.io/docs/, dan https://12factor.net/
_Confidence:_ tinggi.

## Implementation Approaches and Technology Adoption

### Technology Adoption Strategies

Adopsi teknologi untuk bot ini harus bertahap dan berbasis bukti: hardening dry-run, paper trading terukur, lalu live kecil dengan kill switch. Jangan melakukan big-bang migration ke microservices atau live trading penuh. Migrasi utama yang memberi nilai paling cepat adalah: SQLite disiplin single-writer sekarang dan PostgreSQL nanti; log file besar menjadi structured telemetry; model bebas menjadi pipeline/version registry; deployment copy-file menjadi commit-pinned release.

Urutan ini sesuai prinsip Google Cloud Well-Architected: desain workload yang secure, efficient, resilient, high-performing, cost-effective, dan sustainable. Dalam konteks bot, “adoption” bukan menambah library sebanyak mungkin, melainkan membuat setiap perubahan bisa diuji, direplay, dan di-rollback.

_Sumber:_ https://docs.cloud.google.com/architecture/framework
_Confidence:_ tinggi.

### Development Workflows and Tooling

Workflow implementasi perlu menghilangkan drift antara WSL dan VM. GitHub Actions dapat menjalankan build, lint, dan test otomatis dari repository; dokumentasi GitHub Actions menyatakan workflow dapat mengotomasi job CI/CD langsung dari repository. Untuk VM, deployment idealnya pull commit tertentu, jalankan smoke test, backup DB, restart service, dan health check. Sync file parsial dari WSL ke VM hanya dipakai untuk emergency patch yang terdokumentasi, bukan jalur normal.

DORA/Google Cloud juga mengaitkan delivery performance dengan praktik seperti continuous delivery dan trunk-based development. Untuk project kecil ini, interpretasi praktisnya: perubahan kecil, branch singkat, test wajib, dan main branch selalu deployable. Karena local worktree sedang dirty, sinkronisasi sekarang harus konservatif dan tidak menimpa perubahan user.

_Sumber:_ https://docs.github.com/actions, https://docs.github.com/en/actions/get-started/continuous-integration, https://dora.dev/capabilities/continuous-delivery/, dan https://dora.dev/capabilities/trunk-based-development/
_Confidence:_ tinggi.

### Testing and Quality Assurance

pytest tetap pilihan tepat karena framework ini ringan untuk test kecil dan cukup skalabel untuk functional/integration tests. Test yang paling penting bukan test indikator teknis tunggal, melainkan test perilaku sistem: market replay deterministik, startup recovery semua posisi `OPEN`, duplicate event/idempotency, database lock stress, Telegram one-loop ownership, stale market data fail-closed, REST fallback exit, dan golden decision fixtures.

Untuk ML/quant, validasi harus temporal. Dokumentasi scikit-learn menjelaskan bahwa cross-validation memperkirakan generalisasi, tetapi pada sampel kecil hasil bisa lebih baik dari realita hanya karena kebetulan. `TimeSeriesSplit` disediakan untuk data berurutan waktu agar model tidak training pada data masa depan dan dievaluasi pada masa lalu. Karena audit VM baru memiliki 26 closed dry-run trades, keputusan model harus diperlakukan sebagai hipotesis awal, bukan bukti profitabilitas.

_Sumber:_ https://pytest.org/, https://scikit-learn.org/stable/modules/cross_validation.html, dan https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
_Confidence:_ sangat tinggi.

### Deployment and Operations Practices

Compute Engine masih cukup untuk bot ini, tetapi harus dioperasikan seperti workload produksi kecil. Minimum praktik: log rotation, Google Ops Agent/OpenTelemetry, backup SQLite online, restore drill, alert disk/log growth, service health check, dan startup reconciliation sebelum entry baru. OpenTelemetry mendefinisikan telemetry sebagai traces, metrics, dan logs; untuk bot trading, metrik domain seperti expectancy setelah fee/slippage, stale tick age, max drawdown, DB lock count, rejected order reason, dan restart recovery duration lebih penting daripada hanya “service up”.

Google Secret Manager layak dipakai untuk credential live karena menyediakan penyimpanan rahasia yang dikelola dengan praktik seperti IAM dan rotasi. Namun dry-run executor sebaiknya secara konstruksi tidak memuat credential live sama sekali.

_Sumber:_ https://opentelemetry.io/docs/concepts/observability-primer/, https://docs.cloud.google.com/monitoring/agent/ops-agent, dan https://docs.cloud.google.com/secret-manager/docs/best-practices
_Confidence:_ tinggi.

### Team Organization and Skills

Skill implementasi yang dibutuhkan berpusat pada reliability dan quant validation: Python async ownership, SQLite/PostgreSQL transactions, event-driven ledger, exchange execution semantics, Telegram Bot API constraints, market replay testing, model calibration, observability, dan incident response. BMad yang sudah dipasang bisa membantu mengubah riset ini menjadi PRD, architecture, stories, lalu implementation checklist.

Untuk pola kerja solo/small-team, peran boleh dirangkap tetapi checklist tidak boleh hilang: reviewer mode untuk perubahan risk/execution, operator mode untuk deployment/cleanup, dan researcher mode untuk model/backtest. Perubahan yang menyentuh live execution atau circuit breaker harus punya preflight checklist dan rollback.

_Sumber:_ https://owasp.org/www-project-devsecops-guideline/ dan https://docs.cloud.google.com/architecture/framework/operational-excellence
_Confidence:_ sedang-tinggi.

### Cost Optimization and Resource Management

Jangan menambah infrastruktur mahal sebelum data pipeline benar. Google Compute Engine menyediakan rightsizing recommendation berdasarkan metrik Cloud Monitoring beberapa hari terakhir; gunakan ini untuk menyesuaikan VM. Optimasi biaya lain: log retention, archive backup lama, alert disk, dan hindari GPU/cluster untuk training kecil. Biaya terbesar yang tersembunyi adalah kerugian strategi akibat stale exit, slippage tidak dimodelkan, dan mode eksplorasi terlalu longgar.

Karena log VM sudah mencapai beberapa GB, storage/logging retention adalah prioritas langsung. Observability harus cukup untuk mendeteksi masalah, tetapi sampling dan retention perlu dibatasi agar biaya tidak menjadi beban baru.

_Sumber:_ https://docs.cloud.google.com/compute/docs/instances/apply-machine-type-recommendations-for-instances dan https://docs.cloud.google.com/architecture/framework/cost-optimization
_Confidence:_ tinggi.

### Risk Assessment and Mitigation

Risiko utama implementasi adalah data leakage, sample size kecil, stale market data, duplicate order, database lock, Telegram dianggap ledger, credential bocor di log, dan circuit breaker di-reset prematur. Mitigasi yang disarankan: entry fail-closed saat data stale; exit fallback REST; idempotency key dan unique constraint; outbox untuk event/notifikasi; temporal holdout; fee/spread/slippage wajib di semua backtest; backup sebelum dry-run cleanup; dan audit log untuk maintenance command.

Circuit breaker portfolio yang aktif di VM harus dipertahankan sampai ada keputusan eksplisit untuk mengaktifkan kembali trading. Membersihkan history dry-run bukan bukti bahwa risiko sudah hilang; itu hanya membersihkan tampilan dan data simulasi lama.

_Sumber:_ https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/, https://owasp.org/www-project-devsecops-guideline/, dan https://docs.cloud.google.com/architecture/framework/reliability
_Confidence:_ sangat tinggi.

## Technical Research Recommendations

### Implementation Roadmap

1. Stabilkan safety layer: startup reconciliation, one-loop Telegram owner, database writer queue, log rotation, and stale-entry fail-closed.
2. Bersihkan dry-run history setelah SQLite online backup dan verifikasi row dependency, tanpa reset circuit breaker live.
3. Bangun replay/backtest harness yang menghitung fee, spread, slippage, max adverse excursion, dan pair/regime segmentation.
4. Ketatkan entry: confidence calibration, pair whitelist berbasis outcome, dan BAD prediction block atau quarantine, bukan hanya reduce size.
5. Tambahkan model registry ringan: model version, data window, feature snapshot, metrics, dan deployment alias.
6. Jalankan paper trading sampai expectancy positif setelah biaya pada temporal holdout dan forward window.
7. Baru uji live kecil dengan position cap, daily loss limit, kill switch, dan reconciliation wajib.

### Technology Stack Recommendations

Python tetap stack utama. Pertahankan pytest, scikit-learn-compatible pipeline, SQLite untuk fase sekarang, dan Compute Engine. Tambahkan secara bertahap: structured logging/OpenTelemetry, Google Ops Agent, online backup script, MLflow atau registry file-based sederhana, dan PostgreSQL saat concurrency/event ledger mulai melampaui SQLite.

### Skill Development Requirements

Prioritas belajar/operasional: async Python supervision, database transaction safety, exchange order lifecycle, quant evaluation tanpa leakage, risk management, observability, dan secure operations. BMad dapat dipakai untuk memecah roadmap menjadi PRD/architecture/story agar implementasi tidak melebar liar.

### Success Metrics and KPIs

KPI teknis: zero stale-position loss, restart recovery sukses, DB lock turun, log growth terkendali, backup restore valid, dan 100% trade memiliki decision/feature/model snapshot. KPI trading: expectancy setelah fee/slippage, profit factor, max drawdown, max adverse excursion, win rate per regime, pair-level net P&L, dan jumlah trade minimal per segment sebelum pair dipercaya.

# From Dry-Run Losses to Reliable Quant Execution: Comprehensive Crypto Autotrade Profitability and Production Architecture Technical Research

## Executive Summary

Audit VM menunjukkan masalah bot bukan “kurang AI”, melainkan kombinasi sample kecil, entry eksploratif, risk gate longgar, stale-position supervision, dan operasi produksi yang belum cukup ketat. Dari 26 closed dry-run trades, hasilnya 9 winner, 17 loser, win rate 34.62%, dan total P&L simulasi sekitar -1,275,827 IDR. Kerugian ekstrem terutama terjadi karena posisi lama keluar dari watchlist sehingga exit monitoring tidak terus menjaga posisi sampai perbaikan sweep posisi `OPEN` diterapkan pada 2026-08-04.

Riset teknis dari sumber primer mendukung arah yang jelas: bot harus diperlakukan sebagai sistem trading otomatis yang membutuhkan risk controls, audit trail, model validation, dan operational reliability. NIST AI RMF menekankan test, evaluation, verification, dan validation sepanjang lifecycle AI. Sumber regulator seperti CFTC, BIS, dan ESMA menekankan risk controls, governance, oversight, dan safeguards untuk algorithmic trading karena complexity dan speed dapat memperbesar dampak error.

Implikasi strategisnya tegas: jangan mengejar indikator ajaib atau live trading lebih besar sebelum execution ledger, stale-data fail-closed, startup reconciliation, idempotency, outbox, temporal validation, dan observability domain beres. “Bot super” yang realistis adalah bot yang lebih dulu tidak bodoh saat kondisi buruk, baru kemudian mencoba menjadi pintar saat peluang valid muncul.

**Key Technical Findings:**

- Modular monolith dengan port/adapters lebih tepat daripada microservices untuk fase sekarang.
- Ledger posisi `OPEN` harus menjadi sumber recovery, bukan watchlist atau Telegram.
- Entry harus fail-closed ketika market data stale; exit harus punya fallback REST.
- Semua order/exit/notifikasi perlu idempotency dan audit trail.
- Backtest tanpa fee, spread, slippage, temporal holdout, dan sample-size warning tidak boleh dipakai untuk keputusan live.
- Circuit breaker portfolio tidak boleh di-reset hanya karena histori dry-run dibersihkan.

**Technical Recommendations:**

- Stabilkan safety layer: startup reconciliation, single Telegram event-loop owner, database writer queue, log rotation, dan stale-entry gate.
- Bersihkan histori dry-run setelah SQLite online backup dan dependency check, tanpa mengubah live/circuit breaker state.
- Bangun market replay harness yang menghitung fee, spread, slippage, max adverse excursion, dan pair/regime segmentation.
- Ketatkan entry dengan confidence calibration, whitelist pair berbasis forward result, dan block/quarantine untuk prediksi BAD.
- Jalankan paper trading sampai expectancy positif setelah biaya pada temporal forward window sebelum live kecil.

## Table of Contents

1. Technical Research Introduction and Methodology
2. Technical Landscape and Architecture Analysis
3. Implementation Approaches and Best Practices
4. Technology Stack Evolution and Current Trends
5. Integration and Interoperability Patterns
6. Performance and Scalability Analysis
7. Security and Compliance Considerations
8. Strategic Technical Recommendations
9. Implementation Roadmap and Risk Assessment
10. Future Technical Outlook and Innovation Opportunities
11. Technical Research Methodology and Source Verification
12. Technical Appendices and Reference Materials

## 1. Technical Research Introduction and Methodology

### Technical Research Significance

Crypto autotrade adalah sistem cyber-physical versi pasar: software membuat keputusan, exchange mengeksekusi, modal menanggung akibatnya. Karena itu reliability, validation, dan risk controls sama pentingnya dengan sinyal. Riset ini menjadi kritis karena audit dry-run sudah memperlihatkan bahwa satu bug supervision dapat mengubah eksperimen kecil menjadi drawdown besar.

_Technical Importance:_ algorithmic trading memerlukan kontrol risiko, pengujian, monitoring, dan governance karena keputusan otomatis bergerak lebih cepat daripada intervensi manual.
_Business Impact:_ profitabilitas tidak cukup dinilai dari win rate; harus dihitung sebagai expectancy setelah biaya, drawdown, tail loss, dan kemampuan sistem menghentikan diri saat data/eksekusi tidak sehat.
_Sumber:_ https://www.nist.gov/itl/ai-risk-management-framework, https://www.cftc.gov/sites/default/files/idc/groups/public/%40newsroom/documents/file/federalregister112415.pdf, dan https://www.bis.org/publ/mktc13.pdf

### Technical Research Methodology

Riset menggabungkan audit VM, source/runtime logs, database outcome dry-run, dan sumber primer web. Klaim teknis diverifikasi terhadap dokumentasi resmi Python, SQLite, PostgreSQL, scikit-learn, Indodax, Telegram Bot API, Google Cloud, OpenTelemetry, OWASP, AWS Builders Library, NIST, CFTC, BIS, dan ESMA.

**Technical Scope:** quant validation, risk management, execution architecture, data architecture, observability, deployment, dan Telegram cleanup.
**Data Sources:** VM `trading.db`, runtime logs, source code, serta dokumentasi primer.
**Analysis Framework:** root-cause audit, architecture decision analysis, reliability controls, and cost-aware implementation sequencing.
**Time Period:** audit dry-run 2026-07-05 sampai 2026-08-04; riset disusun 2026-08-05.
**Technical Depth:** cukup rinci untuk menjadi basis PRD, architecture, stories, dan implementation roadmap.

### Technical Research Goals and Objectives

**Original Technical Goals:** improve risk-adjusted expectancy after costs, prevent stale-position losses, validate models without leakage, and harden execution on Google Compute Engine.

**Achieved Technical Objectives:**

- Loss dry-run dipetakan ke stale-position supervision, relaxed exploration gates, dan sample kecil.
- Architecture target ditentukan: modular monolith, event ledger, startup reconciliation, outbox, idempotency, and fail-closed risk gates.
- Validation target ditentukan: temporal split, replay harness, fee/spread/slippage, MAE/MFE, pair/regime segmentation, dan probability calibration.
- Operational target ditentukan: log rotation, Ops Agent/OpenTelemetry, backup/restore, health checks, and commit-pinned deployment.

## 2. Technical Landscape and Architecture Analysis

### Current Technical Architecture Patterns

Bot berada pada fase single-VM production prototype. Arsitektur yang direkomendasikan adalah modular monolith dengan komponen eksplisit: market-data adapter, signal engine, risk engine, execution simulator/live adapter, ledger, notifier, dan operations tooling. Batas yang penting adalah kontrak data dan state machine, bukan deployment service yang terpisah.

_Dominant Patterns:_ port/adapters, event-driven internal flow, transactional ledger, outbox notification.
_Architectural Evolution:_ SQLite disciplined mode menuju PostgreSQL ledger; file logs menuju telemetry; dry-run menuju paper/live gate.
_Architectural Trade-offs:_ monolith lebih mudah direplay dan dioperasikan saat tim kecil; microservices ditunda sampai scaling benar-benar menjadi masalah.
_Sumber:_ https://docs.cloud.google.com/architecture/framework

### System Design Principles and Best Practices

Core invariant: setiap posisi `OPEN` harus direkonstruksi saat startup dan diawasi sampai close. Setiap trade intent harus punya idempotency key; setiap decision harus punya feature snapshot, model version, dan gate result; setiap close harus memisahkan observed, decision, dan fill price.

_Design Principles:_ fail-closed, idempotent, auditable, replayable, and least privilege.
_Best Practice Patterns:_ outbox, bounded retry with jitter, circuit breaker, startup reconciliation, and single-writer database discipline.
_Architectural Quality Attributes:_ correctness lebih prioritas daripada throughput; latency penting hanya setelah freshness dan recovery benar.
_Sumber:_ https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ dan https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html

## 3. Implementation Approaches and Best Practices

### Current Implementation Methodologies

Implementasi harus dimulai dari safety and replay foundation. Kode strategy boleh berubah cepat, tetapi ledger/risk/execution harus konservatif. Dry-run dan live memakai pipeline sama sampai boundary executor; bedanya hanya fill adapter dan credential access.

_Development Approaches:_ small changes, commit-pinned deployment, preflight checklist, and rollback.
_Code Organization Patterns:_ domain service untuk position/order lifecycle; adapters untuk exchange/Telegram/storage.
_Quality Assurance Practices:_ pytest unit/integration, replay fixtures, temporal ML validation, and failure injection.
_Deployment Strategies:_ backup, smoke test, restart service, health check, then observe metrics.
_Sumber:_ https://pytest.org/ dan https://docs.github.com/actions

### Implementation Framework and Tooling

Python tetap tepat untuk orchestration dan ML tabular. scikit-learn/LightGBM cukup untuk baseline setelah dataset outcome memadai; MLflow atau registry sederhana dipakai untuk lineage/versioning. Google Ops Agent/OpenTelemetry dipakai untuk telemetry; SQLite backup API dipakai sebelum maintenance; PostgreSQL disiapkan sebagai target ledger saat concurrency menuntut.

_Development Frameworks:_ asyncio, pytest, scikit-learn-compatible pipelines, LightGBM optional.
_Tool Ecosystem:_ Git/GitHub Actions, BMad, Google Ops Agent, OpenTelemetry, MLflow/file registry.
_Build and Deployment Systems:_ CI for tests; VM release pinned to commit.
_Sumber:_ https://docs.python.org/3.13/library/asyncio.html, https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html, dan https://mlflow.org/docs/latest/ml/model-registry/

## 4. Technology Stack Evolution and Current Trends

### Current Technology Stack Landscape

Stack saat ini layak dipertahankan dengan disiplin lebih ketat. SQLite bukan masalah selama single-writer, transaksi pendek, WAL, backup API, dan maintenance terkontrol. Namun error `database is locked` memberi sinyal bahwa PostgreSQL akan lebih sehat untuk event ledger produksi.

_Programming Languages:_ Python utama; native acceleration hanya setelah profiling.
_Frameworks and Libraries:_ pytest, scikit-learn/LightGBM, asyncio supervision.
_Database and Storage Technologies:_ SQLite now, PostgreSQL target, Redis only for transient queue/cache.
_API and Communication Technologies:_ Indodax REST/WebSocket, Telegram Bot API, event envelope internal.
_Sumber:_ https://www.sqlite.org/isolation.html, https://www.postgresql.org/docs/current/transaction-iso.html, dan https://github.com/btcid/indodax-official-api-docs

### Technology Adoption Patterns

Adopsi harus mengikuti risk-reducing sequence: observability and cleanup, replay validation, model governance, then live gating. Emerging methods seperti reinforcement learning, LLM signal generation, atau complex ensemble ditunda sampai dataset outcome dan simulator cukup bersih. Model kompleks di atas data salah hanya mempercepat kesalahan.

_Adoption Trends:_ practical MLOps, telemetry, and event-driven reliability lebih relevan daripada model novelty.
_Migration Patterns:_ strangler-style internal modules, not platform rewrite.
_Emerging Technologies:_ model registry, feature store ringan, calibrated ensemble; RL/LLM remain research-only.
_Sumber:_ https://www.nist.gov/itl/ai-risk-management-framework dan https://mlflow.org/docs/latest/ml/model-registry/

## 5. Integration and Interoperability Patterns

### Current Integration Approaches

REST digunakan untuk snapshot, reconciliation, order action, dan fallback. WebSocket digunakan untuk real-time ticks tetapi harus punya heartbeat, stale detection, reconnect, dan REST resync. Telegram hanya presentation channel. Setiap notifikasi yang ingin bisa dihapus di masa depan harus menyimpan `chat_id` dan `message_id`.

_API Design Patterns:_ adapter per upstream, schema contract tests, request/response redaction.
_Service Integration:_ internal event flow with idempotent consumers.
_Data Integration:_ versioned envelope with UTC timestamp, Decimal for money, and feature snapshot.
_Sumber:_ https://datatracker.ietf.org/doc/html/rfc6455, https://core.telegram.org/bots/api#deletemessage, dan https://core.telegram.org/bots/api#deletemessages

### Interoperability Standards and Protocols

Gunakan official Indodax endpoints/streams saja. Retry order action harus direkonsiliasi melalui intent id dan ledger, bukan blind resend. Redis Streams dapat menjadi transport internal sementara, tetapi database ledger tetap source of truth.

_Standards Compliance:_ official exchange docs, Bot API constraints, WebSocket RFC.
_Protocol Selection:_ REST for correctness/reconciliation, WebSocket for freshness, DB transaction for final state.
_Integration Challenges:_ stale connection, duplicate events, API timeout ambiguity, and notification dual-write.
_Sumber:_ https://redis.io/docs/latest/develop/data-types/streams/ dan https://microservices.io/patterns/data/transactional-outbox.html

## 6. Performance and Scalability Analysis

### Performance Characteristics and Optimization

Performance harus diukur berdasarkan kualitas keputusan dan freshness: tick age, decision latency, DB write latency, lock count, order acknowledgement latency, and exit evaluation interval. CPU scaling belum menjadi bottleneck utama. Backpressure lebih penting: queue bounded, retry bounded, stale decision rejected.

_Performance Benchmarks:_ baseline domain metrics dari dry-run forward trading, not synthetic throughput only.
_Optimization Strategies:_ reduce stale data, avoid DB contention, batch non-critical writes, and profile before acceleration.
_Monitoring and Measurement:_ OpenTelemetry metrics/logs/traces plus domain KPIs.
_Sumber:_ https://opentelemetry.io/docs/concepts/observability-primer/

### Scalability Patterns and Approaches

Scaling tahap awal adalah vertical and operational scaling di satu VM: log rotation, DB discipline, bounded tasks, startup recovery, and health checks. Horizontal scaling ditunda karena distributed execution dapat memperbesar risiko duplicate order bila idempotency dan ledger belum matang.

_Scalability Patterns:_ modular monolith, single-writer queue, outbox worker, and eventual PostgreSQL.
_Capacity Planning:_ Compute Engine rightsizing from observed metrics; disk alert and retention.
_Elasticity and Auto-scaling:_ not recommended for live trading executor until order lifecycle is strongly idempotent.
_Sumber:_ https://docs.cloud.google.com/compute/docs/instances/apply-machine-type-recommendations-for-instances

## 7. Security and Compliance Considerations

### Security Best Practices and Frameworks

OWASP ASVS/DevSecOps memberi baseline security verification dan secure pipeline. Untuk bot: secret redaction, IAM least privilege, no credential in dry-run executor, authorized Telegram commands, backup before destructive operations, and audit log for maintenance.

_Security Frameworks:_ OWASP ASVS, OWASP DevSecOps, Google Secret Manager best practices.
_Threat Landscape:_ credential leakage, unauthorized Telegram command, log exposure, dependency/API misuse.
_Secure Development Practices:_ secret scanning, redaction tests, least privilege, and explicit live/dry-run boundaries.
_Sumber:_ https://owasp.org/www-project-application-security-verification-standard/, https://owasp.org/www-project-devsecops-guideline/, dan https://docs.cloud.google.com/secret-manager/docs/best-practices

### Compliance and Regulatory Considerations

Walaupun bot ini bukan regulated venue, prinsip automated trading dari CFTC/BIS/ESMA tetap berguna: pre-trade controls, order size/frequency limits, kill switch, monitoring, testing, record-keeping, and governance. Ini harus diterjemahkan ke risk engine, audit ledger, and deployment checklist.

_Industry Standards:_ algorithmic trading risk controls, AI risk management, secure SDLC.
_Regulatory Compliance:_ treat as best-practice guidance, not legal advice.
_Audit and Governance:_ every strategy/model/config/deployment needs versioned record.
_Sumber:_ https://www.cftc.gov/sites/default/files/idc/groups/public/%40newsroom/documents/file/federalregister112415.pdf, https://www.bis.org/publ/mktc13.pdf, dan https://www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf

## 8. Strategic Technical Recommendations

### Technical Strategy and Decision Framework

Prioritas strategi: correctness, survivability, validation, then alpha. Sinyal profit tidak dapat dipercaya sebelum simulator, ledger, cost model, and temporal validation sehat. Technical decision harus dinilai berdasarkan dampaknya ke expectancy after costs dan tail-risk reduction.

_Architecture Recommendations:_ modular monolith, event ledger, startup reconciliation, outbox, idempotency.
_Technology Selection:_ keep Python/pytest/scikit now; add telemetry and registry; PostgreSQL later.
_Implementation Strategy:_ reduce loss modes first, then improve signal quality.
_Sumber:_ https://docs.cloud.google.com/architecture/framework dan https://www.nist.gov/itl/ai-risk-management-framework

### Competitive Technical Advantage

Keunggulan bukan berasal dari indikator populer, tetapi dari feedback loop yang lebih bersih: replayable decisions, calibrated probabilities, regime/pair selection, and risk-aware sizing. Bot yang tahu kapan tidak trading sering lebih unggul daripada bot yang selalu mencari entry.

_Technology Differentiation:_ audit-grade paper/live parity and decision replay.
_Innovation Opportunities:_ pair/regime whitelist, MAE/MFE-driven exits, volatility sizing, ensemble only after clean dataset.
_Strategic Technology Investments:_ data quality, backtesting realism, observability, model registry.
_Sumber:_ https://scikit-learn.org/stable/modules/cross_validation.html dan https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

## 9. Implementation Roadmap and Risk Assessment

### Technical Implementation Framework

Fase 1: safety and cleanup. Fase 2: replay and validation. Fase 3: signal/risk upgrade. Fase 4: paper forward validation. Fase 5: live small-cap test. Setiap fase harus punya exit criteria berbasis metrik, bukan perasaan bahwa strategi “kelihatan bagus”.

_Implementation Phases:_ stabilize, clean, replay, calibrate, forward-test, then live cap.
_Technology Migration Strategy:_ disciplined SQLite now; PostgreSQL only after ledger/event pattern proven.
_Resource Planning:_ one VM plus CI is enough for now; add managed services only when justified.
_Sumber:_ https://docs.github.com/en/actions/get-started/continuous-integration dan https://docs.cloud.google.com/architecture/framework/operational-excellence

### Technical Risk Management

Risiko terbesar yang sudah terbukti adalah stale-position loss. Risiko berikutnya: overfitting dari 26 trades, false confidence dari dry-run fill, slippage blindness, DB locks, duplicate order, and operator cleanup error. Mitigasi harus berupa code-level invariant dan tests, bukan reminder manual.

_Technical Risks:_ stale exit, event loop ownership, database contention, model leakage.
_Implementation Risks:_ partial sync WSL-VM, dirty worktree, destructive cleanup, accidental circuit breaker reset.
_Business Impact Risks:_ simulated profit yang tidak survive fee/slippage, drawdown tail, and live credential misuse.
_Sumber:_ https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ dan https://www.sqlite.org/isolation.html

## 10. Future Technical Outlook and Innovation Opportunities

### Emerging Technology Trends

Dalam 1-2 tahun, peluang terbaik adalah MLOps ringan, explainable tabular models, calibrated probability, and richer market microstructure features. Dalam 3-5 tahun, streaming feature pipelines dan managed observability bisa membantu bila volume data tumbuh. Long-term RL/LLM-agent trading tetap research-only sampai ada simulator realistis dan strict risk sandbox.

_Near-term Technical Evolution:_ better replay, calibration, observability, pair/regime gating.
_Medium-term Technology Trends:_ feature store, PostgreSQL event ledger, model registry and automated validation.
_Long-term Technical Vision:_ adaptive portfolio risk engine with human-auditable model governance.
_Sumber:_ https://mlflow.org/docs/latest/ml/model-registry/ dan https://www.nist.gov/itl/ai-risk-management-framework

### Innovation and Research Opportunities

Research yang paling berguna: max adverse/favorable excursion by pair, volume/liquidity filters, spread-aware entries, volatility-normalized position sizing, regime detection, and probability calibration. LLM lebih cocok sebagai analyst/reporting assistant, bukan signal executor.

_Research Opportunities:_ MAE/MFE exits, meta-labeling, abstention model, risk-budget sizing, and market replay simulator.
_Emerging Technology Adoption:_ use only after measurable uplift out-of-sample.
_Innovation Framework:_ every innovation starts in offline replay, moves to dry-run, then paper forward, then capped live.
_Sumber:_ https://scikit-learn.org/stable/modules/cross_validation.html

## 11. Technical Research Methodology and Source Verification

### Comprehensive Technical Source Documentation

_Primary Technical Sources:_ Python asyncio docs, scikit-learn docs, SQLite/PostgreSQL docs, Indodax official API docs, Telegram Bot API, Google Cloud Architecture Framework/Ops Agent/Secret Manager, OpenTelemetry, OWASP ASVS/DevSecOps, AWS Builders Library, NIST AI RMF, CFTC/BIS/ESMA automated trading sources.
_Secondary Technical Sources:_ Microservices.io transactional outbox and Redis Streams documentation for implementation pattern support.
_Technical Web Search Queries:_ architecture patterns, transactional outbox, idempotent APIs, OpenTelemetry, Google Cloud ops/cost, pytest, TimeSeriesSplit, MLflow model registry, AI RMF, algorithmic trading risk controls.

### Technical Research Quality Assurance

_Technical Source Verification:_ high-impact claims were tied to primary or official documentation wherever available.
_Technical Confidence Levels:_ high for architecture/reliability findings; medium for profitability improvement until larger forward sample exists.
_Technical Limitations:_ dry-run sample has only 26 closed trades; fills are simulated; pair-level inference is weak for n=1 pairs; Telegram historical message deletion is constrained by Bot API and missing message IDs.
_Methodology Transparency:_ conclusions combine observed VM evidence with current technical references; no claim guarantees profit.

## 12. Technical Appendices and Reference Materials

### Detailed Technical Data Tables

_Architectural Pattern Tables:_ modular monolith selected over microservices due to simpler replay, lower operational risk, and current single-VM scale.
_Technology Stack Analysis:_ Python/pytest/scikit/SQLite/Compute Engine remain valid short-term; PostgreSQL/OpenTelemetry/MLflow-style registry are next candidates.
_Performance Benchmark Data:_ baseline audit: 26 closed dry-run trades, 9 winners, 17 losers, win rate 34.62%, P&L approximately -1,275,827 IDR.

### Technical Resources and References

_Technical Standards:_ RFC 6455 WebSocket, OWASP ASVS, NIST AI RMF.
_Open Source Projects:_ pytest, scikit-learn, LightGBM, MLflow, Redis.
_Research Papers and Publications:_ BIS FX execution algorithms; CFTC automated trading risk-control materials; ESMA algorithmic trading supervision briefing.
_Technical Communities:_ Google Cloud Architecture/DORA, OpenTelemetry, Python/scikit-learn ecosystem.

## Technical Research Conclusion

### Summary of Key Technical Findings

Bot harus dibuat reliable dahulu sebelum dibuat lebih agresif. Root cause kerugian dry-run terbesar berasal dari supervision yang tidak terus menjaga posisi, bukan semata sinyal yang lemah. Setelah reliability diperbaiki, profitabilitas masih harus dibuktikan dengan validation yang benar karena sample outcome saat ini terlalu kecil.

### Strategic Technical Impact Assessment

Riset ini mengubah arah pengembangan dari “cari metode profit” menjadi “bangun sistem yang bisa membuktikan atau menolak metode profit dengan aman”. Dampaknya besar: lebih sedikit false positive, lebih sedikit tail loss, dan keputusan live yang lebih defensible.

### Next Steps Technical Recommendations

Langkah langsung setelah riset: backup VM database, bersihkan histori dry-run yang menjadi sumber tampilan Telegram, jangan reset circuit breaker, lalu implementasikan safety backlog: log rotation, startup reconciliation invariant, DB writer discipline, Telegram message ID tracking, and market replay validation.

**Technical Research Completion Date:** 2026-08-05
**Research Period:** current comprehensive technical analysis
**Source Verification:** All critical technical facts cited with current sources
**Technical Confidence Level:** High for reliability recommendations; medium for profit strategy until larger forward-tested sample exists.

_This comprehensive technical research document serves as an authoritative technical reference on crypto autotrade quant profitability and production architecture and provides strategic technical insights for informed decision-making and implementation._
